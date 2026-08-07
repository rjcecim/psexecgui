from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from utils.psinfo import InstalledApp

_CATALOG_FILENAME = "ApplicationCatalog.json"
_CATALOG_SUBDIR = "config"
_cached_path: Optional[str] = None
_cached_mtime: Optional[float] = None
_cached_entries: List[Dict[str, Any]] = []


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # utils/ → raiz do projeto
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def catalog_candidates() -> List[str]:
    """Locais possíveis do ApplicationCatalog.json (prioridade: config/)."""
    root = _app_dir()
    paths = [
        os.path.join(root, _CATALOG_SUBDIR, _CATALOG_FILENAME),
        os.path.join(root, _CATALOG_FILENAME),  # fallback legado na raiz
    ]
    # Empacotado com PyInstaller (datas)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(os.path.join(meipass, _CATALOG_SUBDIR, _CATALOG_FILENAME))
        paths.append(os.path.join(meipass, _CATALOG_FILENAME))
    # Dedup preservando ordem
    out: List[str] = []
    seen: set[str] = set()
    for p in paths:
        key = os.path.normcase(os.path.normpath(p))
        if key in seen:
            continue
        seen.add(key)
        out.append(os.path.normpath(p))
    return out


def resolve_catalog_path() -> Optional[str]:
    for path in catalog_candidates():
        if os.path.isfile(path):
            return path
    return None


def load_catalog(force: bool = False) -> List[Dict[str, Any]]:
    """Carrega a lista de aplicações do ApplicationCatalog.json (com cache por mtime)."""
    global _cached_path, _cached_mtime, _cached_entries

    path = resolve_catalog_path()
    if not path:
        _cached_path = None
        _cached_mtime = None
        _cached_entries = []
        return []

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []

    if (
        not force
        and _cached_path == path
        and _cached_mtime == mtime
        and _cached_entries is not None
    ):
        return _cached_entries

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        _cached_path = path
        _cached_mtime = mtime
        _cached_entries = []
        return []

    apps = data.get("applications") if isinstance(data, dict) else None
    entries: List[Dict[str, Any]] = []
    if isinstance(apps, list):
        for item in apps:
            if isinstance(item, dict):
                entries.append(item)

    _cached_path = path
    _cached_mtime = mtime
    _cached_entries = entries
    return entries


def entry_publishers(entry: Dict[str, Any]) -> List[str]:
    """
    Aceita ``publishers`` (lista) e/ou ``publisher`` (string) no JSON.
    Ex.: "publishers": ["geek software GmbH", "PDF24.org"]
    """
    out: List[str] = []
    seen: set[str] = set()

    def _add(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                _add(item)
            return
        text = str(value or "").strip()
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    _add(entry.get("publishers"))
    _add(entry.get("publisher"))
    return out


def _publisher_matches(entry: Dict[str, Any], publisher: str) -> bool:
    pub = (publisher or "").casefold()
    if not pub:
        return False
    for entry_pub in entry_publishers(entry):
        ep = entry_pub.casefold()
        if ep in pub or pub in ep:
            return True
    return False


def find_catalog_entry(
    display_name: str,
    publisher: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Localiza a entrada do catálogo cujo padrão em ``match`` aparece no DisplayName
    (sem diferenciar maiúsculas/minúsculas).

    Prioridade: padrão mais longo; em empate, prefere publisher compatível.
    O publisher/publishers do JSON é só um desempate — não bloqueia o match pelo nome.
    """
    name = (display_name or "").casefold()
    if not name:
        return None

    best: Optional[Dict[str, Any]] = None
    best_key = (-1, -1)  # (len padrão, publisher bate?)

    for entry in load_catalog():
        patterns = entry.get("match") or []
        if not isinstance(patterns, list):
            continue
        pub_ok = 1 if _publisher_matches(entry, publisher) else 0
        for pat in patterns:
            p = str(pat or "").strip()
            if not p:
                continue
            if p.casefold() not in name:
                continue
            key = (len(p), pub_ok)
            if key > best_key:
                best = entry
                best_key = key
    return best


def catalog_uninstall_args(app: InstalledApp) -> str:
    """
    Retorna uninstallArgs do catálogo para o app, ou string vazia.
    Aplica-se apenas a instaladores EXE (MSI usa msiexec /qn e ignora o catálogo).
    """
    if app.is_msi and app.product_code:
        return ""
    entry = find_catalog_entry(app.display_name or "", app.publisher or "")
    if not entry:
        # Tenta também display_line (às vezes vem "Nome Versão")
        entry = find_catalog_entry(app.display_line or "", app.publisher or "")
    if not entry:
        return ""
    return str(entry.get("uninstallArgs") or "").strip()


def resolve_uninstall_extras(app: InstalledApp, manual_extras: str = "") -> str:
    """
    Parâmetros efetivos para desinstalação:
    - se o usuário preencheu Parametros Extras, usa isso (override);
    - senão, para EXE, usa uninstallArgs do ApplicationCatalog.json quando houver match;
    - MSI não usa o catálogo (permanece com /qn /norestart + extras manuais, se houver).
    """
    manual = (manual_extras or "").strip()
    if manual:
        return manual
    return catalog_uninstall_args(app)
