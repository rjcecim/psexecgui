from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

# Pasta padrão das PSTools (PsExec, PsInfo, etc.)
DEFAULT_PSTOOLS_DIR = r"C:\PSTools"
# Compat: nome histórico aponta para o padrão
PSTOOLS_DIR = DEFAULT_PSTOOLS_DIR

_SETTINGS_ORG = "PSExecGUI"
_SETTINGS_APP = "PSExecGUI"
_SETTINGS_KEY = "pstools/dir"

_runtime_dir: Optional[str] = None


def normalize_pstools_dir(path: str) -> str:
    """
    Normaliza o campo PSTools.
    Aceita pasta (C:\\PSTools\\) ou caminho antigo para um .exe (usa o diretório).
    """
    p = (path or "").strip().replace('"', "").replace("'", "")
    if not p:
        return ""
    p = os.path.normpath(p)
    if p.lower().endswith(".exe"):
        p = os.path.dirname(p)
    return p


def _load_from_settings() -> str:
    try:
        from PyQt6.QtCore import QSettings

        raw = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY, "")
        normalized = normalize_pstools_dir(str(raw or ""))
        return normalized or DEFAULT_PSTOOLS_DIR
    except Exception:
        return DEFAULT_PSTOOLS_DIR


def _save_to_settings(path: str) -> None:
    try:
        from PyQt6.QtCore import QSettings

        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY, path)
    except Exception:
        pass


def get_pstools_dir() -> str:
    """Pasta PSTools em uso (persistida; padrão C:\\PSTools)."""
    global _runtime_dir
    if _runtime_dir is None:
        _runtime_dir = _load_from_settings()
    return _runtime_dir


def set_pstools_dir(path: str, *, persist: bool = True) -> str:
    """Define a pasta PSTools em runtime (e opcionalmente persiste)."""
    global _runtime_dir
    normalized = normalize_pstools_dir(path) or DEFAULT_PSTOOLS_DIR
    _runtime_dir = normalized
    if persist:
        _save_to_settings(normalized)
    return normalized


def resolve_pstools_tool(pstools_dir: str, names: Sequence[str]) -> str:
    """
    Resolve o caminho de uma ferramenta dentro da pasta PSTools.
    Tenta cada nome em ordem; se nenhum existir, retorna pasta+primeiro nome
    (ou só o nome, se a pasta estiver vazia — usa PATH).
    """
    base = normalize_pstools_dir(pstools_dir)
    names = [n for n in names if n]
    if not names:
        return ""
    if not base:
        return names[0]
    for name in names:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(base, names[0])


def probe_pstools(pstools_dir: Optional[str] = None) -> Dict[str, object]:
    """
    Inspeciona a pasta PSTools e retorna status dos binários principais.
    (RustDesk NÃO fica em PSTools — ver ``probe_rustdesk_local``.)
    """
    base = normalize_pstools_dir(pstools_dir or get_pstools_dir()) or DEFAULT_PSTOOLS_DIR
    tools: List[Tuple[str, Sequence[str]]] = [
        ("PsExec", ("PsExec64.exe", "PsExec.exe")),
        ("PsInfo", ("PsInfo64.exe", "PsInfo.exe")),
    ]
    items = []
    found_count = 0
    for label, names in tools:
        resolved = ""
        present = False
        for name in names:
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                resolved = candidate
                present = True
                found_count += 1
                break
        if not resolved and names:
            resolved = os.path.join(base, names[0])
        items.append(
            {
                "label": label,
                "names": list(names),
                "path": resolved,
                "found": present,
            }
        )
    dir_ok = os.path.isdir(base)
    return {
        "dir": base,
        "dir_ok": dir_ok,
        "tools": items,
        "ok_count": found_count,
        "total": len(items),
        "healthy": dir_ok and found_count >= 2,  # PsExec + PsInfo
    }


def rustdesk_local_candidates() -> List[str]:
    """Caminhos locais usuais do RustDesk (instalação em Program Files)."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    return [
        os.path.join(pf, "RustDesk", "rustdesk.exe"),
        os.path.join(pfx86, "RustDesk", "rustdesk.exe"),
    ]


def probe_rustdesk_local() -> Dict[str, object]:
    """Status do RustDesk instalado localmente (não usa a pasta PSTools)."""
    candidates = rustdesk_local_candidates()
    for path in candidates:
        if os.path.isfile(path):
            return {
                "found": True,
                "path": path,
                "candidates": candidates,
            }
    return {
        "found": False,
        "path": candidates[0] if candidates else r"C:\Program Files\RustDesk\rustdesk.exe",
        "candidates": candidates,
    }
