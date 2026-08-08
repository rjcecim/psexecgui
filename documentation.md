# Documentação técnica — PSExecGUI 1.5.0

**Versão programática:** `core.version.__version__` (`1.5.0`)  
**UI:** `APP_VERSION` em `ui/branding.py` importa essa fonte.  
**Empacotamento:** `pyproject.toml` usa versão dinâmica (`tool.setuptools.dynamic`).  
**Nome exibido:** Instalador Remoto via PsExec (`APP_DISPLAY_NAME`)

---

# Arquitetura

```
UI (MainWindow, tabs, widgets)
        ↓
Application / Use Cases (services/ops.py)
        ↓
Domain (core/models.py — CommandSpec, ExecutionResult, OperationStatus)
        ↓
Infrastructure (Executor, win_cmd, win_cmdline, PsInfo, Remote Registry, Robocopy, RustDesk)
```

A UI solicita uma operação; o serviço executa; a UI recebe resultado / sinais.

---

# Segurança de credenciais

Módulo central: `utils/redaction.py`.

| Superfície | Comportamento |
|------------|---------------|
| Preview | `CommandSpec.display_command` sanitizado; flag `-p` isolada |
| CommandBuilder | **não** armazena senha bruta — só `has_password` + placeholder |
| Execução | senha injetada via `materialize_password_in_argv` / `CredentialContext` |
| Log UI / exceções | `redact_command_text` |
| `exec_history.log` | única escrita por operação (`log_operation`) |
| Arquivos temporários | **não** gravam senha |
| JSON / config | senha nunca serializada |

### O que o app garante

- Senha não persistida em `CommandBuilder`, JSON, logs ou temporários.
- Preview e histórico não exibem o valor bruto.
- Redaction não confunde `-Path`/`-Profile`/`-Priority` com `-p`.

### O que o app NÃO pode garantir

- Zeroização criptográfica de strings Python imutáveis.
- Impedir inspeção da command line do processo Windows (Task Manager / ETW) quando PsExec recebe `-p`.
- Monitorar o exit code remoto quando a execução usa terminal externo independente.

Preferência: omitir `-u`/`-p` e usar a sessão atual.

---

# Domain models (`core/models.py`)

Tipos ativos:

- `CommandSpec` — argv + `display_command` sanitizado
- `ExecutionResult` — return_code, stdout/stderr, timing, cancelled, timed_out, success, `remote_may_continue`
- `OperationStatus` — started / completed / failed / cancelled / timed_out / unknown
- `FileSelection`

Modelos tipados de opções (`PsExecOptions`, `MSIOptions`, …) foram removidos na 2ª rodada: o builder continua baseado nos dicts da UI; abstrações mortas foram eliminadas.

---

# CommandBuilder (`core/builder.py`)

- `build_*()` → strings **sempre** sanitizadas (preview)
- `build_*_spec()` / `build_execution_plan()` → `CommandSpec` com placeholder de senha
- Comando manual: `split_windows_command_line` (`CommandLineToArgvW`) — não um único token
- MSI em **folder mode** propaga opções da aba MSI
- `set_file()` aceita path string **ou** dict de seleção

---

# Executor (`core/executor.py`)

- Lê stdout/stderr em threads sobre handles locais do `Popen` (não `self.process` mutável)
- Geração (`_run_generation`) descarta resultados obsoletos
- Serializado (1 worker)
- `stop()` encerra o processo **local**; remoto via PsExec pode continuar

---

# Terminal externo (`core/win_cmd.py`)

PsExec / desinstalação usam `open_external_console_argv` → `CREATE_NEW_CONSOLE` direto no argv (sem `cmd /k`, sem `shell=True`).

Motivo: o quoting do `cmd.exe` não garante round-trip seguro para credenciais com metacaracteres (`%`, `!`, `&`, etc.).

Limitação de UX: a janela fecha quando o processo termina (não há `/k`). Em troca, o argv chega intacto ao CreateProcess.

`cmd.exe /k` permanece disponível para casos sem segredo (ex.: ping, help).

---

# Semântica de lançamento PsExec

`LaunchResult.status = STARTED` + mensagem:
`Execução iniciada em terminal externo; resultado remoto não monitorado.`

Não confundir “terminal aberto” com “operação remota concluída”.

---

# Serviços (`services/ops.py`)

| Serviço | Responsabilidade |
|---------|------------------|
| `CommandExecutionService` | Robocopy interno + PsExec em console externo |
| `RemoteUninstallService` | Desinstalação sem senha em arquivos temp |
| `RustDeskService` | get-id remoto + connect local |
| `CredentialContext` | credencial de curta duração + `clear()` |

---

# ApplicationCatalog (`utils/app_catalog.py`)

- Validação explícita (`validate_catalog_data`)
- Matching por nome, publisher, arquitetura
- `uninstallArgs` influencia EXE; demais campos são metadata documental

---

# Inventário / Remote Registry (`utils/psinfo.py`)

- Views 32 e 64 bits
- `HostInventoryStatus` diferencia unreachable / auth / remote_registry / invalid_host
- PsInfo UI: timeout configurável `PSINFO_TIMEOUT_SECONDS` (padrão 90s)

---

# Busca multi-host

Interrupção solicita cancelamento de futures pendentes. Consultas Win32 já iniciadas
**podem** finalizar em segundo plano. A UI:

- informa isso explicitamente;
- deixa de aceitar resultados tardios (`_accepting_search_results = False`).

---

# hosts.json

- `hosts.example.json` — exemplos fictícios (**versionado**)
- `hosts.json` — configuração local (`.gitignore`, **não rastreado** pelo Git)
- Migração: copie o example; o app não sobrescreve dados do usuário

---

# Logging (`utils/app_logging.py`)

- Histórico de operações: `exec_history.log` — escrita única via `_append_history_line` / `log_operation`
- Diagnóstico: `app.log` (FileHandler do logger) — arquivo separado
- Diretório: `%LOCALAPPDATA%\PSExecGUI\logs` ou `logs/` em modo portable

---

# Dependências

| Extra | Conteúdo |
|-------|----------|
| runtime | PyQt6 |
| `dev` | ruff |
| `build` | Pillow (assets), PyInstaller |

```bash
pip install -e ".[dev]"
pip install -e ".[build]"   # gerar assets / exe
```

---

# Qualidade (CI)

```bash
python -m compileall -q core services utils ui main.py
ruff check core services utils main.py
```

CI falha se Ruff falhar. Não há suíte de testes automatizados no repositório.

---

# PyInstaller

`PSExecGUI.spec` inclui `assets`, `config`, `hosts.example.json`. Exclui hosts reais, logs e credenciais.

---

# Versionamento / LICENSE

- Fonte programática: `core/version.py`
- README pode citar a versão como documentação
- O repositório **não** declara licença SPDX — escolha pendente do proprietário
- Tags Git históricas **não** foram reescritas

---

# Checklist de smoke test manual (Windows)

1. Abrir aplicação  
2. Preview sem senha  
3. Comando remoto `ipconfig /all`  
4. Comando `cmd`  
5. PowerShell  
6. EXE / MSI / MSI folder / PS1 / BAT  
7. Robocopy  
8. PsInfo  
9. Busca multi-host + interrupção  
10. Desinstalação  
11. RustDesk get-id / connect  
12. Usuário/senha (incl. caracteres especiais)  
13. Caminho com espaços / UNC  
14. PsExec/PsInfo inexistente  
15. Host inacessível / Remote Registry indisponível / timeout  
16. Build PyInstaller  

Não executar operações destrutivas em hosts reais durante testes automatizados.

---

Fim da documentação técnica do **PSExecGUI 1.5.0**.
