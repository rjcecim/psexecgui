# Documentação técnica — PSExecGUI 1.5.0

Lógicas de **backend** (montagem e execução de comandos) e **frontend** (interface, branding, abas, sinais e estado).

**Versão:** `1.5.0` (`APP_VERSION` em `ui/branding.py`)  
**Nome exibido:** Instalador Remoto via PsExec (`APP_DISPLAY_NAME`)

---

# Parte 0 — Identidade e empacotamento

## 0.1 Branding (`ui/branding.py`)

Centraliza metadados e resolução de assets (desenvolvimento e PyInstaller):

| Constante / API | Função |
|-----------------|--------|
| `APP_NAME` | `"PSExecGUI"` — nome interno / `QCoreApplication` |
| `APP_DISPLAY_NAME` | Título da janela e cabeçalho |
| `APP_VERSION` | `"1.5.0"` |
| `ORG_NAME` | Organização Qt |
| `app_icon()` | Preferência `assets/icon.ico`; fallback `assets/app_icon.png` |
| `app_mark_pixmap(size)` | Carrega `assets/app_mark.png` escalado (cabeçalho) |
| `assets_dir()` / `asset_path()` | `_MEIPASS/assets` quando frozen; senão pasta do repositório |

Paleta de referência: `BRAND_NAVY`, `BRAND_AZURE`, `BRAND_CYAN`.

## 0.2 Assets (`assets/`)

| Arquivo | Uso |
|---------|-----|
| `icon.ico` | Ícone do `.exe` (PyInstaller `icon=`) e da janela |
| `app_icon.png` | Fallback de ícone; master para regenerar ICO |
| `app_mark.png` | Marca visual no cabeçalho da UI |

Script auxiliar: `scripts/generate_brand_assets.py` — reexporta o ICO a partir de `app_icon.png`.

## 0.3 Spec PyInstaller (`PSExecGUI.spec`)

- `console=False` (só janela).
- `name='PSExecGUI'` → `dist/PSExecGUI.exe`.
- `icon='assets/icon.ico'`.
- `datas=[('assets', 'assets')]` — embute os três assets no executável.

---

# Parte 1 — Backend

## 1.1 CommandBuilder (`core/builder.py`)

Classe responsável por montar as strings de comando **Robocopy**, **PsExec** e **msiexec** a partir dos parâmetros definidos na UI.

### Estado interno

- `psexec_params`: dicionário com host, caminho do PsExec, usuário, senha, flags (-h, -s, -l, -d, -e, -c, -f, -v, -accepteula, -nobanner), sessão, prioridade, afinidade, grupo, timeout, extra_args, remote_cmd.
- `msi_params`: ação, interface, restart, log, log_file, repair, update, enable.
- `robocopy_params`: dest (pasta destino no remoto), switches (ex.: /NFL /NDL /NJH /NJS /nc /ns /np).
- `file_path`, `folder_path`, `selection`, `selection_mode` ('file' | 'folder'): definidos por `set_file_selection()`.
- `powershell_params`, `cmd_params`: parâmetros das abas PowerShell e CMD.

### Métodos principais

| Método | Descrição |
|--------|-----------|
| `set_file_selection(selection)` | Define arquivo/pasta e modo (file/folder). |
| `set_psexec_params(params)` | Define parâmetros do PsExec. |
| `set_msi_params(params)` | Define parâmetros do msiexec. |
| `set_robocopy_params(params)` | Define destino e switches do Robocopy (ou None para desabilitar). |
| `set_powershell_params(params)` | NoProfile, NoExit, ExecutionPolicy, WindowStyle, Command, EncodedCommand. |
| `set_cmd_params(params)` | /C, /K, /Q, /D, /S e Command. |

### Geração de comandos

- **`build_robocopy()`**  
  - Se não há `robocopy_params` ou `psexec_params`, retorna `""`.  
  - Se `selection_mode == 'folder'` e há `folder_path`, chama `_build_robocopy_folder()` (copia pasta com `/E`).  
  - Senão chama `_build_robocopy_file()` (copia um único arquivo).  
  - Normaliza destino (remove C:, barras), monta origem/destino e aplica switches.

- **`build_psexec()`**  
  - Sem `psexec_params`: retorna texto de placeholder.  
  - **Comando manual**: se não há `file_path` nem `folder_path` mas há `remote_cmd`, monta `_base_psexec_cmd()` + `remote_cmd` (+ extra_args).  
  - Sem arquivo: retorna placeholder.  
  - **Pasta**: `_build_psexec_folder()` — usa caminho remoto após Robocopy (`C:\dest\folder_name\relpath`), trata .ps1, .bat, .msi ou genérico.  
  - Por extensão:  
    - `.exe` → `_build_psexec_exe()`  
    - `.msi` → `_build_psexec_msi()`  
    - `.ps1` → `_build_psexec_ps_script()`  
    - `.bat` → `_build_psexec_bat_script()`  
    - Outros → `_build_psexec_other()`

- **`_base_psexec_cmd()`**  
  Monta lista: `[psexec_path ou "PsExec.exe", "\\\\host", "-u user", "-p password", flags de elevação, -i [session_id], prioridade, -a affinity, -g group, -n timeout, -d, -e, -c, -f, -v, -accepteula, -nobanner]`.  
  Se `robocopy_params` está definido, **não** adiciona -c nem -f (cópia via Robocopy).

- **`build_msiexec()`**  
  Só roda se `msi_params['enable']` e há `file_path`. Exige destino (Robocopy). Monta `msiexec ...` e extrai valores de combo via `_extract_flag_value()`.

- **`build_full_command()`**  
  - Chama `build_robocopy()`.  
  - Para `.ps1` usa `_build_psexec_ps_script()`, para `.bat` usa `_build_psexec_bat_script()`, senão `build_psexec()`.  
  - Se há Robocopy, retorna `robocopy_cmd + "\n" + psexec_cmd`; senão só `psexec_cmd`.

### Regras de negócio importantes

- Destino Robocopy: relativo ao C: do remoto; normalizado.  
- Caminho remoto para script: `C:\dest\file_name` ou `C:\dest\folder_name\relpath`.  
- Prioridade PowerShell/CMD: EncodedCommand > Command > File.  
- Flags -c e -f desabilitadas na UI para .msi/.ps1/.bat; omitidas no builder quando Robocopy está ativo.

---

## 1.2 Executor (`core/executor.py`)

Executa um comando em um **ThreadPoolExecutor** (1 worker) e emite sinais Qt.

### Sinais

- `outputReceived(str)`: linha de stdout.
- `errorReceived(str)`: linha de stderr.
- `finished(int)`: código de saída.

### Fluxo

1. **`run(command)`** — cancela execução anterior, submete `_run_command` e agenda `_check_future()` via `QTimer`.
2. **`_run_command(command)`** (thread) — `Popen` com decodificação (`utf-8-sig` → `mbcs` → `cp1252`); prefixa `[ROBOCOPY]` quando aplicável.
3. **`_check_future()`** — emite `finished` quando a future termina; senão reagenda.
4. **`stop()`** — termina o processo e cancela a future.

---

## 1.3 Utilitários

- **`utils/api.py`** — grupos/contagem de processadores (`kernel32`), usados na aba PsExec (afinidade/grupo).
- **`utils/psinfo.py`** — parser do PsInfo64 (`parse_psinfo_output`, `parse_disks_table`).
- **`utils/validator.py`** — `AffinityValidator` para afinidade CPU.

---

# Parte 2 — Frontend

## 2.1 MainWindow (`main.py`)

Janela principal: **cabeçalho de marca + seletor na mesma linha**, `QTabWidget` (PsExec + abas condicionais), preview, botões Executar/Parar/Reiniciar e log.

Metadados Qt (`setApplicationName`, `setApplicationVersion`, ícone) vêm de `ui.branding`.

### Cabeçalho (`_build_brand_header`)

Uma única linha horizontal:

1. `app_mark.png` (28×28) via `app_mark_pixmap(28)`
2. Coluna de texto: título (`APP_DISPLAY_NAME`) + subtítulo
3. `FileSelectorWidget` (stretch) — status do arquivo + botões arquivo/pasta/ajuda

### Inicialização

- Cria FileSelector, abas (PsExec sempre; MSI/PowerShell/CMD/Robocopy dinâmicas), preview, log.
- **PsInfo** criada sob demanda (botão ℹ️).
- Instancia `CommandBuilder` e `Executor`.
- Conecta sinais; `update_command()` no fim do `__init__`.
- Opcional: Mica (`enable_mica_for_widget`).
- stdout/stderr e `excepthook` redirecionados ao log.

### Seleção de arquivo/pasta

- **`on_file_selected(selection)`** — atualiza builder, desabilita -c/-f para msi/ps1/bat, chama `update_tab_visibility` e `update_command`.

### Visibilidade das abas

- **`should_enable_robocopy()`** — falso para `.exe` ou comando remoto manual (exceto cmd/powershell puros).
- **`update_tab_visibility`** — reinsere MSI / PowerShell / CMD / Robocopy; PsInfo permanece última aba quando existir.

### PsInfo

- **`open_psinfo_tab()`** — exige host; cria ou foca aba e dispara coleta.
- Ao sair da aba PsInfo, ela é removida (`deleteLater()`).
- **`_update_psinfo_mode_ui()`** — em modo PsInfo, oculta preview, log e Play/Stop/Restart.

### Montagem do comando

- **`build_command_for_execution()`** — escolhe `build_full_command`, builders de script ou `build_psexec` conforme arquivo/comando/aba.
- **`update_command()`** — sincroniza params das abas no builder e atualiza o preview.

### Execução

- **`on_run()`** — log + `exec_history.log`; se houver `\n`, roda Robocopy via Executor e PsExec em `cmd /k`; senão só PsExec externo.
- **`on_stop()`** / **`on_process_finished()`** — controlam botões e log.
- **`on_remote_cmd_edit_changed`** — recalcula abas e estado do seletor.

### Geometria e encerramento

- **`_apply_initial_geometry()`** — sizeHint + limites da tela, centraliza.
- **`closeEvent`** — `executor.stop()` e shutdown do pool se existir.

---

## 2.2 Componentes de UI

### FileSelectorWidget (`ui/widgets/selector.py`)

- Sinal: `fileSelected` (mode, file, folder).
- Botões: arquivo, pasta, ajuda (`/?`).
- Ícone do arquivo só aparece após seleção; rótulo expande (`stretch`).

### Aba PsExec (`ui/tabs/psexec.py`)

- Cards: Conexão, Autenticação, Privilégios e Sessão, Desempenho, Flags e Argumentos.
- Clear icon em Host, Comando remoto, Usuário, Senha, Args extras.
- Host: Ping + PsInfo (`openPsInfoRequested`) + RustDesk (`openRustDeskRequested`).

### Aba PsInfo (`ui/tabs/psinfo.py`)

- Coleta: `PsInfo64.exe \\HOST -s -d -accepteula -nobanner`.
- Cards Sistema / Aplicativos / Discos; colapsáveis; `DotsSpinner` durante loading.

### RustDesk

- ID remoto via PsExec (`-h -s`) em `Program Files` / `(x86)`.
- Local: `rustdesk.exe --connect <ID>`.
- Logs `[RUSTDESK] ...`.

### Demais abas

- **MSI** — ação, interface, restart, log, repair, update.
- **Robocopy** — destino + switches.
- **PowerShell** / **CMD** — flags e comando; campos desabilitados quando o comando vem do arquivo.

### Widgets de suporte

- **CommandPreviewWidget** — monoespaçado, somente leitura.
- **LogOutputWidget** — `append_log` / `clear_log`.
- **CardWidget** — ícone MDL2, título, grid; colapsável.
- **DotsSpinner** — loading sem assets externos.
- **style.py** — `apply_ui_defaults` (Segoe UI, densidades).
- **mica.py** — backdrop Windows 11.

---

## 2.3 TabBar customizada (`main.py`)

- **`_Mdl2TabBar`**: ícone Unicode (Segoe MDL2 Assets) + texto; `tabData(index)`; `setExpanding(False)`.

---

## 2.4 Fluxo de dados resumido

1. Usuário seleciona arquivo/pasta ou edita campos → sinais dos widgets.
2. MainWindow reage com `on_file_selected` ou `update_command`.
3. `update_command` preenche o CommandBuilder e chama `build_command_for_execution()`.
4. Resultado vai ao preview e fica disponível para `on_run`.
5. `on_run` executa via Executor (Robocopy) e/ou subprocess (`cmd /k` para PsExec).
6. Sinais do Executor atualizam log e botões.

---

Fim da documentação técnica do **PSExecGUI 1.5.0**.
