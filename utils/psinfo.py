from __future__ import annotations

import re
import shlex
import winreg
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


@dataclass
class InstalledApp:
    display_name: str
    version: str
    publisher: str
    display_line: str
    product_code: str
    uninstall_string: str
    quiet_uninstall_string: str
    is_msi: bool
    arch: str  # "64" | "32"


_GUID_RE = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}")
_UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


def _strip_host(host: str) -> str:
    h = (host or "").strip()
    # Aceita entrada como "\\\\HOST" ou "HOST"
    return h.strip("\\").strip()


def build_psinfo_target(host: str) -> str:
    h = _strip_host(host)
    return f"\\\\{h}" if h else ""


def _reg_str(sub, value_name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(sub, value_name)
        text = str(value or "").strip()
        # Remove nulos/controles que quebram cmd/Qt
        return "".join(ch for ch in text if ch >= " " or ch in "\t")
    except OSError:
        return ""


def _detect_msi(sub_key: str, uninstall_string: str) -> tuple[bool, str]:
    key = (sub_key or "").strip()
    if _GUID_RE.fullmatch(key):
        return True, key
    us = uninstall_string or ""
    if "msiexec" in us.lower():
        m = _GUID_RE.search(us)
        if m:
            return True, m.group(0)
    return False, ""


def _apps_from_uninstall(root, access: int, arch: str) -> Dict[str, InstalledApp]:
    """Retorna {DisplayName: InstalledApp} para a view indicada."""
    apps: Dict[str, InstalledApp] = {}
    try:
        uninstall = winreg.OpenKey(root, _UNINSTALL_KEY, 0, access)
    except OSError:
        return apps
    try:
        i = 0
        while True:
            try:
                sub_name = winreg.EnumKey(uninstall, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(uninstall, sub_name) as sub:
                    name = _reg_str(sub, "DisplayName")
                    if not name:
                        continue
                    version = _reg_str(sub, "DisplayVersion")
                    publisher = _reg_str(sub, "Publisher")
                    uninstall_string = _reg_str(sub, "UninstallString")
                    quiet = _reg_str(sub, "QuietUninstallString")
                    is_msi, product_code = _detect_msi(sub_name, uninstall_string)
                    display_line = f"{name} {version}".strip() if version else name
                    app = InstalledApp(
                        display_name=name,
                        version=version,
                        publisher=publisher,
                        display_line=display_line,
                        product_code=product_code,
                        uninstall_string=uninstall_string,
                        quiet_uninstall_string=quiet,
                        is_msi=is_msi,
                        arch=arch,
                    )
                    prev = apps.get(name)
                    if prev is None or (version and not prev.version):
                        apps[name] = app
            except OSError:
                continue
    finally:
        uninstall.Close()
    return apps


def _with_arch_suffix(app: InstalledApp, arch_label: str) -> InstalledApp:
    """Acrescenta (64-bit)/(32-bit) no nome quando o DisplayName não indica arquitetura."""
    label = f"({arch_label})"
    if label.casefold() in app.display_name.casefold():
        return app
    new_name = f"{app.display_name} {label}"
    display_line = f"{new_name} {app.version}".strip() if app.version else new_name
    return InstalledApp(
        display_name=new_name,
        version=app.version,
        publisher=app.publisher,
        display_line=display_line,
        product_code=app.product_code,
        uninstall_string=app.uninstall_string,
        quiet_uninstall_string=app.quiet_uninstall_string,
        is_msi=app.is_msi,
        arch=app.arch,
    )


def list_remote_installed_apps_ex(host: str) -> tuple[bool, List[InstalledApp]]:
    """
    Lista aplicativos instalados no host via Remote Registry (HKLM Uninstall),
    unindo as views 64-bit e 32-bit (Wow6432Node).

    Retorna (ok, apps):
    - ok=False se o host estiver inacessível / ConnectRegistry falhar;
    - ok=True com lista (possivelmente vazia) quando a conexão remoto funcionou.
    """
    h = _strip_host(host)
    if not h:
        return False, []

    try:
        root = winreg.ConnectRegistry(rf"\\{h}", winreg.HKEY_LOCAL_MACHINE)
    except OSError:
        return False, []

    try:
        apps_64 = _apps_from_uninstall(root, winreg.KEY_READ | winreg.KEY_WOW64_64KEY, "64")
        apps_32 = _apps_from_uninstall(root, winreg.KEY_READ | winreg.KEY_WOW64_32KEY, "32")
    finally:
        root.Close()

    names_64 = set(apps_64)
    names_32 = set(apps_32)
    only_64 = names_64 - names_32
    only_32 = names_32 - names_64
    both = names_64 & names_32

    out: List[InstalledApp] = []
    for n in only_64:
        out.append(apps_64[n])
    for n in only_32:
        out.append(apps_32[n])
    for n in both:
        out.append(_with_arch_suffix(apps_64[n], "64-bit"))
        out.append(_with_arch_suffix(apps_32[n], "32-bit"))

    # Dedup por (display_line, arch, product_code/uninstall) — manter ordem estável
    seen: set[tuple[str, str, str]] = set()
    unique: List[InstalledApp] = []
    for app in sorted(out, key=lambda a: a.display_line.casefold()):
        key = (app.display_line.casefold(), app.arch, app.product_code or app.uninstall_string)
        if key in seen:
            continue
        seen.add(key)
        unique.append(app)
    return True, unique


def list_remote_installed_apps(host: str) -> List[InstalledApp]:
    """
    Lista aplicativos instalados no host via Remote Registry (HKLM Uninstall),
    unindo as views 64-bit e 32-bit (Wow6432Node).

    display_line no formato PsInfo: "DisplayName DisplayVersion".
    Em falha de conexão retorna lista vazia (compatível com uso anterior).
    """
    _ok, apps = list_remote_installed_apps_ex(host)
    return apps


def extract_uninstall_executable(uninstall_string: str) -> str:
    """
    Extrai o caminho do executável de um UninstallString.
    Trata caminhos sem aspas com espaços (ex.: C:\\Program Files\\WinRAR\\uninstall.exe).
    """
    s = (uninstall_string or "").strip()
    if not s:
        return ""
    if s.lower().startswith("msiexec"):
        return ""
    if s.startswith('"'):
        end = s.find('"', 1)
        if end > 1:
            return s[1:end]
    lower = s.lower()
    for ext in (".exe", ".cmd", ".bat"):
        idx = lower.find(ext)
        if idx != -1:
            return s[: idx + len(ext)].strip()
    try:
        parts = shlex.split(s, posix=False)
    except ValueError:
        parts = s.split()
    if not parts:
        return ""
    return parts[0].strip().strip('"')


def quote_uninstall_command(cmd: str) -> str:
    """Garante aspas no executável quando o caminho tem espaços (necessário p/ PsExec)."""
    s = (cmd or "").strip()
    if not s:
        return s
    if s.lower().startswith("msiexec"):
        return s
    if s.startswith('"'):
        return s
    exe = extract_uninstall_executable(s)
    if not exe or " " not in exe:
        return s
    if s.startswith(exe):
        rest = s[len(exe) :].lstrip()
        return f'"{exe}"' + (f" {rest}" if rest else "")
    return f'"{exe}"'


def build_uninstall_remote_cmd(app: InstalledApp, extra_params: str = "") -> str:
    """
    Monta o comando remoto de desinstalação (já com aspas corretas).
    MSI: msiexec /x '{GUID}' /qn /norestart [extras]
    EXE com extras: "exe" + extras
    EXE sem extras: QuietUninstallString ou UninstallString (aspas se necessário)
    """
    extra = (extra_params or "").strip()

    if app.is_msi and app.product_code:
        # Aspas duplas no GUID: mais seguro no cmd.exe do que aspas simples
        cmd = f'msiexec /x "{app.product_code}" /qn /norestart'
        if extra:
            cmd = f"{cmd} {extra}"
        return cmd

    base = (app.quiet_uninstall_string or "").strip() or (app.uninstall_string or "").strip()
    if not base:
        raise ValueError("Este aplicativo não possui string de desinstalação no registro.")

    if extra:
        exe = extract_uninstall_executable(base)
        if not exe:
            raise ValueError("Não foi possível obter o executável de desinstalação deste aplicativo.")
        quoted = f'"{exe}"' if (" " in exe and not exe.startswith('"')) else exe
        return f"{quoted} {extra}"

    return quote_uninstall_command(base)


def describe_uninstall(app: InstalledApp, extra_params: str = "") -> str:
    """Texto curto para tooltip: tipo + comando (truncado para o limite do Qt)."""
    kind = "MSI" if app.is_msi and app.product_code else "EXE"
    try:
        cmd = build_uninstall_remote_cmd(app, extra_params)
    except ValueError as exc:
        return f"{kind}: {exc}"
    # Evita "Application text must be shorter than 32768 characters" e tooltips gigantes
    if len(cmd) > 400:
        cmd = cmd[:397] + "..."
    return f"{kind}: {cmd}"


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
