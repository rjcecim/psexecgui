# Documentação técnica — PSExecGUI 1.5.0

**Versão:** `1.5.0` (`APP_VERSION` em `ui/branding.py`)  
**Nome exibido:** Instalador Remoto via PsExec (`APP_DISPLAY_NAME`)

---

# Arquitetura

```
UI (MainWindow, tabs, widgets)
        ↓
Application / Use Cases (services/ops.py)
        ↓
Domain (core/models.py — CommandSpec, ExecutionResult, options)
        ↓
Infrastructure (Executor, win_cmd, PsInfo, Remote Registry, Robocopy, RustDesk)
```

A UI solicita uma operação; o serviço executa; a UI recebe resultado / sinais.

---

# Segurança de credenciais

Módulo central: `utils/redaction.py`.

| Superfície | Comportamento |
|------------|---------------|
| Preview | `CommandSpec.display_command` já sanitizado |
| Log UI / exceções | `redact_command_text` |
| `exec_history.log` | apenas texto sanitizado |
| Arquivos temporários | **não** gravam senha (desinstalação usa argv em memória) |
| JSON / config | senha nunca serializada |

### Limitação inerente ao PsExec

Com `-u`/`-p`, a senha permanece na command line do processo Windows. O app mitiga exposição em disco/UI/logs, mas não pode eliminar a inspeção via Task Manager / ETW / auditing do SO.

Preferência: omitir `-u`/`-p` e usar a sessão atual.

---

# Domain models (`core/models.py`)

- `CommandSpec` — `args` reais + `display_command` sanitizado
- `ExecutionResult` — return_code, stdout/stderr, timing, cancelled, timed_out, success, `remote_may_continue`
- `PsExecOptions`, `MSIOptions`, `RobocopyOptions`, `PowerShellOptions`, `CmdOptions`
- `OperationStatus` — started / completed / failed / cancelled / timed_out / unknown

---

# CommandBuilder (`core/builder.py`)

- `build_*()` → strings **sempre** sanitizadas (preview)
- `build_*_spec()` / `build_execution_plan()` → `CommandSpec` para execução
- MSI em **folder mode** propaga opções da aba MSI (ação, interface, restart, etc.) — correção de regressão
- `set_file()` aceita path string **ou** dict de seleção (compat UI)

---

# Executor (`core/executor.py`)

- Lê stdout/stderr em threads separadas (evita deadlock)
- Aceita `CommandSpec`, argv ou string legada
- `stop()` encerra o processo **local**; documenta que o remoto via PsExec pode continuar
- Emite `finished(int)` e `resultReady(ExecutionResult)`

---

# Serviços (`services/ops.py`)

| Serviço | Responsabilidade |
|---------|------------------|
| `CommandExecutionService` | Robocopy interno + PsExec em console externo |
| `RemoteUninstallService` | Desinstalação sem senha em arquivos temp |
| `RustDeskService` | get-id remoto + connect local |

---

# ApplicationCatalog (`utils/app_catalog.py`)

- Validação explícita (`validate_catalog_data`) — entradas ruins geram warnings, não derrubam o app
- Matching: nome normalizado, padrão mais longo, publisher, arquitetura (boost)
- Campos `architecture`, `requiresElevation`, `requiresReboot`: **metadata documental** — não alteram o comando de desinstalação nesta versão; apenas `uninstallArgs` influencia EXE

---

# Inventário / Remote Registry (`utils/psinfo.py`)

- Views 32 e 64 bits (`KEY_WOW64_*`)
- Deduplicação por `product_code` ou `(nome, versão, publisher, arch)`
- `HostInventoryStatus` diferencia: unreachable, auth, remote_registry, invalid_host
- `winreg` com import lazy (testes lógicos sem Windows APIs no import)

---

# hosts.json

- `hosts.example.json` — exemplos fictícios (versionado)
- `hosts.json` — local (`.gitignore`)
- Migração: copie o example; o app não sobrescreve dados do usuário

---

# Logging (`utils/app_logging.py`)

- Diretório: `%LOCALAPPDATA%\PSExecGUI\logs` ou `logs/` em modo portable
- Nunca registra comando não sanitizado

---

# Terminal externo (`core/win_cmd.py`)

`cmd.exe /k` é usado **sem** `shell=True`, via lista de argumentos, para preservar a experiência de acompanhamento visual. Motivo documentado no módulo.

---

# Testes

```
tests/unit/          # sem rede, sem PsExec real
tests/integration/   # marcados @windows
```

```bash
pytest tests/unit -q
```

---

# PyInstaller

`PSExecGUI.spec` inclui `assets`, `config`, `hosts.example.json`. Exclui testes, hosts reais, logs e credenciais.

---

# Versionamento / LICENSE

- Versão centralizada em `ui/branding.py` (`1.5.0`) e refletida no README/`pyproject.toml`
- Inconsistências históricas de tags Git **não** foram reescritas
- O repositório **não** possui LICENSE explícita — escolha é do proprietário

---

Fim da documentação técnica do **PSExecGUI 1.5.0**.
