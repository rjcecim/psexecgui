from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PsInfoResult:
    host: str
    header: List[str]
    system: Dict[str, str]
    applications: List[str]
    disks_raw: List[str]
    raw_text: str


@dataclass
class PsInfoDiskRow:
    volume: str
    type: str
    format: str
    label: str
    size: str
    free: str
    free_pct: str


def _strip_host(host: str) -> str:
    h = (host or "").strip()
    # Aceita entrada como "\\\\HOST" ou "HOST"
    return h.strip("\\").strip()


def build_psinfo_target(host: str) -> str:
    h = _strip_host(host)
    return f"\\\\{h}" if h else ""


def parse_psinfo_output(text: str, host: str = "") -> PsInfoResult:
    """
    Faz parse do stdout do PsInfo (Sysinternals).
    Suporta:
    - bloco "System information for \\\\HOST:" seguido de pares "Chave: Valor"
    - seção "Applications:" (lista até o fim)
    - tabela de volumes (quando chamado com -d)
    """
    raw = text or ""
    lines = raw.splitlines()

    header: List[str] = []
    system: Dict[str, str] = {}
    applications: List[str] = []
    disks_raw: List[str] = []

    in_system = False
    in_apps = False
    in_disks = False

    for ln in lines:
        s = ln.rstrip("\n\r")
        if not s.strip():
            # Mantém linhas em branco apenas dentro da tabela de discos (ajuda no layout)
            if in_disks:
                disks_raw.append(s)
            continue

        if s.startswith("PsInfo v") or "Sysinternals" in s or "www.sysinternals.com" in s:
            header.append(s)
            continue

        if s.startswith("System information for"):
            in_system = True
            in_apps = False
            in_disks = False
            header.append(s)
            continue

        if s.strip() == "Applications:":
            in_apps = True
            in_system = False
            in_disks = False
            continue

        # Heurística para iniciar tabela de discos: cabeçalho do PsInfo -d
        if s.strip().startswith("Volume") and "Free" in s and "Format" in s:
            in_disks = True
            in_system = False
            in_apps = False
            disks_raw.append(s)
            continue

        if in_apps:
            applications.append(s.strip())
            continue

        if in_disks:
            disks_raw.append(s)
            continue

        if in_system:
            # Formato: "Kernel version:            Windows 10 Pro, ..."
            if ":" in s:
                key, val = s.split(":", 1)
                system[key.strip()] = val.strip()
            else:
                header.append(s)
            continue

        header.append(s)

    return PsInfoResult(
        host=_strip_host(host),
        header=header,
        system=system,
        applications=applications,
        disks_raw=disks_raw,
        raw_text=raw,
    )


def format_key_values(system: Dict[str, str], order: Optional[List[str]] = None) -> List[tuple[str, str]]:
    if not system:
        return []
    if not order:
        return sorted(system.items(), key=lambda kv: kv[0].lower())
    out: List[tuple[str, str]] = []
    remaining = dict(system)
    for k in order:
        if k in remaining:
            out.append((k, remaining.pop(k)))
    for k in sorted(remaining.keys(), key=lambda x: x.lower()):
        out.append((k, remaining[k]))
    return out


def parse_disks_table(disks_raw: List[str]) -> List[PsInfoDiskRow]:
    """
    Converte a tabela do PsInfo -d em linhas estruturadas.
    Observação: o output é alinhado por espaços, então usamos split por múltiplos espaços.
    """
    if not disks_raw:
        return []

    rows: List[PsInfoDiskRow] = []
    for line in disks_raw:
        s = (line or "").rstrip()
        if not s.strip():
            continue
        if s.strip().startswith("Volume"):
            continue

        # Esperado (ex):
        # C: Fixed NTFS ETSETIN-CAU01 476.10 GB 277.68 GB 58.3%
        parts = [p for p in s.split() if p]
        if len(parts) < 7:
            continue

        volume = parts[0]
        vol_type = parts[1]
        fmt = parts[2]
        free_pct = parts[-1]
        free = " ".join(parts[-3:-1])  # "277.68 GB"
        size = " ".join(parts[-5:-3])  # "476.10 GB"
        label = " ".join(parts[3:-5])  # pode conter espaços

        rows.append(
            PsInfoDiskRow(
                volume=volume,
                type=vol_type,
                format=fmt,
                label=label,
                size=size,
                free=free,
                free_pct=free_pct,
            )
        )
    return rows
