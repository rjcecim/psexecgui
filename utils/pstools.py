from __future__ import annotations

import os
from typing import Sequence

# Pasta fixa das PSTools (PsExec, PsInfo, etc.)
PSTOOLS_DIR = r"C:\PSTools"


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
