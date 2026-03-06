# Documentação técnica — PSExecGUI v3

Lógicas completas de **Backend** (montagem e execução de comandos) e **Frontend** (interface, abas, sinais e estado).

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
  - **Pasta**: `_build_psexec_folder()` — usa caminho remoto após Robocopy (C:\dest\folder_name\relpath), trata .ps1, .bat, .msi ou genérico.  
  - Por extensão:  
    - `.exe` → `_build_psexec_exe()` (nome ou caminho com -c/-f).  
    - `.msi` → `_build_psexec_msi()` (chama `build_msiexec()` e encadeia no PsExec).  
    - `.ps1` → `_build_psexec_ps_script()` (powershell com parâmetros da aba PowerShell; caminho local ou remoto se Robocopy).  
    - `.bat` → `_build_psexec_bat_script()` (cmd com parâmetros da aba CMD; idem para caminho).  
    - Outros → `_build_psexec_other()`.

- **`_base_psexec_cmd()`**  
  Monta lista: `[psexec_path ou "PsExec.exe", "\\\\host", "-u user", "-p password", flags de elevação, -i [session_id], prioridade, -a affinity, -g group, -n timeout, -d, -e, -c, -f, -v, -accepteula, -nobanner]`.  
  Se `robocopy_params` está definido, **não** adiciona -c nem -f (cópia é feita pelo Robocopy).

- **`build_msiexec()`**  
  Só roda se `msi_params['enable']` e há `file_path`. Exige destino (Robocopy). Monta `msiexec [ação] "C:\dest\file.msi" [interface] [restart] [log] [repair] [update]` e extrai valores de combo via `_extract_flag_value()`.

- **`build_full_command()`**  
  - Chama `build_robocopy()`.  
  - Para `.ps1` usa `_build_psexec_ps_script()`, para `.bat` usa `_build_psexec_bat_script()`, senão `build_psexec()`.  
  - Se há comando Robocopy, retorna `robocopy_cmd + "\n" + psexec_cmd`; senão só `psexec_cmd`.

### Regras de negócio importantes

- Destino Robocopy: relativo ao C: do remoto; normalizado (sem C:, barras unificadas).  
- Caminho remoto para script: `C:\dest\file_name` (arquivo) ou `C:\dest\folder_name\relpath` (pasta).  
- Prioridade na aba PowerShell/CMD: EncodedCommand > Command > File (ou caminho do script).  
- Flags -c e -f são desabilitadas na UI para .msi, .ps1, .bat; e não são adicionadas pelo builder quando Robocopy está ativo.

---

## 1.2 Executor (`core/executor.py`)

Executa um comando em um **ThreadPoolExecutor** (1 worker) e emite sinais Qt para saída padrão, erro e término.

### Sinais

- `outputReceived(str)`: linha de stdout.
- `errorReceived(str)`: linha de stderr.
- `finished(int)`: código de saída do processo.

### Fluxo

1. **`run(command)`**  
   Chama `stop()` para cancelar execução anterior, guarda `command`, submete `_run_command(command)` ao executor e agenda `_check_future()` com `QTimer.singleShot(100, ...)`.

2. **`_run_command(command)`** (em thread)  
   - Detecta se o comando é Robocopy (primeiro token = robocopy) para prefixar saída com `[ROBOCOPY]`.  
   - `subprocess.Popen(..., shell=True, stdout=PIPE, stderr=PIPE, text=True, encoding='utf-8', errors='replace')`.  
   - Lê stdout/stderr linha a linha e emite `outputReceived` / `errorReceived`.  
   - Ao terminar (`poll() is not None`), lê o restante e retorna `returncode`.  
   - Exceções emitem `errorReceived` e retornam 1.

3. **`_check_future()`**  
   Se `future.done()`, obtém resultado (exit code), emite `finished(exit_code)` e limpa `future`. Senão, re-agenda com `QTimer.singleShot(100, _check_future)`.

4. **`stop()`**  
   Termina o processo (se existir), limpa referência e cancela o `future`.

---

## 1.3 Utilitários

- **`utils/api.py`**  
  Usa `kernel32` (ctypes) para: `get_processor_groups()`, `get_processor_count(group_id)`, `get_all_processor_info()`. Usado na aba PsExec para grupo CPU e afinidade.

- **`utils/validator.py`**  
  `AffinityValidator`: valida valor de afinidade CPU (ex.: "1,2,3") conforme número máximo de CPUs do grupo selecionado.

---

# Parte 2 — Frontend

## 2.1 MainWindow (`main.py`)

Janela principal: barra de seleção de arquivo/pasta, **QTabWidget** (PsExec + abas condicionais), preview do comando, botões Executar/Parar/Reiniciar e área de log.

### Inicialização

- Cria **FileSelectorWidget**, **PsExecTab**, **MsiTab**, **RobocopyTab**, **PowerShellTab**, **CmdTab**, **CommandPreviewWidget**, **LogOutputWidget**.  
- Adiciona só a aba PsExec; MSI, PowerShell, CMD e Robocopy são adicionadas/removidas dinamicamente.  
- Instancia **CommandBuilder** e **Executor**.  
- Conecta todos os sinais dos widgets a `update_command`, `on_file_selected`, `on_run`, `on_stop`, `on_restart`, `on_remote_cmd_edit_changed`, e sinais do executor ao log e `on_process_finished`.  
- Chama `update_command()` uma vez no fim do `__init__`.  
- Opcional: **Mica** (Windows 11) via `enable_mica_for_widget(window)`.  
- stdout/stderr e `sys.excepthook` são redirecionados para o log interno.

### Seleção de arquivo/pasta

- **`on_file_selected(selection)`**  
  - `selection`: `{'mode': 'file'|'folder', 'file': path, 'folder': path ou None}`.  
  - Chama `command_builder.set_file_selection(selection)`.  
  - Para extensão `msi`, `ps1`, `bat`: desmarca e desabilita flags -c e -f na aba PsExec.  
  - Chama `update_tab_visibility(is_msi, is_exe)` e `update_command()`.

### Visibilidade das abas

- **`should_enable_robocopy()`**  
  - Retorna `False` se não há arquivo selecionado ou se a extensão é `.exe`.  
  - Se o comando remoto estiver preenchido e for diferente de "Comando gerado automaticamente", e não for só `cmd`/`cmd.exe` ou `powershell`/`powershell.exe`, retorna `False` (comando manual desativa Robocopy).  
  - Caso contrário retorna `True`.

- **`update_tab_visibility(is_msi, is_exe)`**  
  - Remove todas as abas exceto a primeira (PsExec).  
  - **MSI**: adiciona aba MSI se `is_msi`.  
  - **PowerShell**: adiciona se extensão é `ps1` ou se comando remoto é `powershell`/`powershell.exe`; em caso de arquivo .ps1, desabilita campos de comando da aba PowerShell (`set_command_fields_enabled(False)`).  
  - **CMD**: adiciona se extensão é `bat` ou se comando remoto é `cmd`/`cmd.exe`; em caso de arquivo .bat, desabilita campo de comando (`set_command_field_enabled(False)`).  
  - **Robocopy**: adiciona se `should_enable_robocopy()`.

### Montagem do comando para preview e execução

- **`build_command_for_execution()`**  
  Define qual método do CommandBuilder usar:

  - Com **arquivo selecionado**:  
    - Se `should_enable_robocopy()`: `build_full_command()` (Robocopy + PsExec).  
    - Se `.bat` e aba atual é CMD: `_build_psexec_bat_script()`.  
    - Se `.ps1`: `_build_psexec_ps_script()`.  
    - Caso contrário: `build_psexec()`.  
  - Sem arquivo (comando manual):  
    - Se comando remoto é `powershell`/`powershell.exe`: `_build_psexec_ps_script()`.  
    - Se é `cmd`/`cmd.exe`: `_build_psexec_bat_script()`.  
    - Se aba atual é CMD: `_build_psexec_bat_script()`.  
    - Se aba atual é PowerShell: `_build_psexec_ps_script()`.  
    - Senão: `build_psexec()`.

### Atualização do preview

- **`update_command()`**  
  - Monta `msi_params` da aba MSI e chama `set_msi_params`.  
  - Obtém seleção do FileSelector (file, folder, mode) e `robocopy_enabled`.  
  - Sempre chama `set_powershell_params(powershell_tab.get_params())` e `set_cmd_params(cmd_tab.get_params())`.  
  - **Com arquivo/pasta**:  
    - `set_file_selection(file_selection)`.  
    - Coloca comando remoto em somente leitura com texto "Comando gerado automaticamente".  
    - Monta `psexec_params` a partir da aba PsExec, `robocopy_params` da aba Robocopy (se habilitado), chama `set_psexec_params` e `set_robocopy_params`.  
  - **Sem arquivo**: libera comando remoto para edição e monta só `psexec_params`.  
  - Chama `build_command_for_execution()` e `command_preview.set_command(command)`.

### Execução

- **`on_run()`**  
  - Obtém comando com `build_command_for_execution()`.  
  - Limpa o log, desabilita Executar e habilita Parar.  
  - Escreve comando no log e em `exec_history.log`.  
  - Se o comando contém `\n`: divide em duas linhas (robocopy_cmd e psexec_cmd); executa robocopy via `executor.run(robocopy_cmd)` e, no sinal `finished`, se exit code 0, executa PsExec com `subprocess.Popen('start cmd /k ' + psexec_cmd, shell=True)`.  
  - Se não contém `\n`: executa só PsExec com `subprocess.Popen('start cmd /k ' + psexec_cmd, shell=True)`.  
  - Reabilita Executar e desabilita Parar.

- **`on_stop()`**  
  Chama `executor.stop()` e ajusta botões.

- **`on_process_finished(exit_code)`**  
  Reabilita Executar, desabilita Parar e registra código no log.

- **`on_remote_cmd_edit_changed(text)`**  
  Atualiza visibilidade das abas e chama `update_command()`; habilita/desabilita botões de arquivo/pasta do selector conforme o texto do comando remoto.

### Geometria e encerramento

- **`_apply_initial_geometry()`**  
  Ajusta tamanho da janela com base em `sizeHint()` e geometria da tela (min/max), e centraliza.

- **`closeEvent`**  
  Chama `executor.stop()` e, se existir, `executor.executor.shutdown(wait=False)`.

---

## 2.2 Componentes de UI

### FileSelectorWidget (`ui/widgets/selector.py`)

- Sinais: `fileSelected` (dict com mode, file, folder).  
- Botões: arquivo, pasta, ajuda (executa arquivo com `/?`).  
- Atualiza ícone e rótulo conforme seleção; emite `fileSelected` ao escolher arquivo ou pasta.

### Aba PsExec (`ui/tabs/psexec.py`)

- **Cards**: Conexão, Autenticação, Privilégios e Sessão, Desempenho, Flags e Argumentos.  
- Helper **`_line_edit_with_clear_icon()`**: retorna um container (QWidget com borda) contendo QLineEdit + QToolButton (ícone X). O botão aparece quando há texto e, ao clicar, limpa o campo. Usado em: PsExec path (não), Host, Comando remoto, Usuário, Senha, Args extras.  
- Host: container com clear + botão Ping (abre cmd com `ping -n 4 -w 1000 <host>`).  
- Autenticação: usuário e senha (QLineEdit com clear).  
- Desempenho: prioridade, grupo CPU (via `utils.api`), afinidade (com `AffinityValidator`).  
- Flags: checkboxes para -d, -e, -c, -f, -v, -accepteula, -nobanner; timeout; args extras (com clear).

### Aba MSI (`ui/tabs/msi.py`)

- Combos: ação (/i, /x, etc.), interface (/quiet, /passive, etc.), política de reinício.  
- Log: checkbox e campo de caminho do arquivo de log.  
- Repair e Update: campos de texto.  
- Usa `grid_in_card` e `add_row` do `ui/widgets/card.py`.

### Aba Robocopy (`ui/tabs/robocopy.py`)

- Campo de destino (relativo ao C:).  
- Checkboxes para switches: /NFL, /NDL, /NJH, /NJS, /nc, /ns, /np.  
- `get_params()` retorna `{'dest': ..., 'switches': "..."}`.

### Aba PowerShell (`ui/tabs/powershell.py`)

- Opções: -NoProfile, -NoExit, -ExecutionPolicy, -WindowStyle.  
- Comando: -Command e -EncodedCommand.  
- `set_command_fields_enabled(enabled)`: habilita/desabilita campos de comando (desabilitado quando o comando é gerado a partir de arquivo .ps1).  
- `get_params()` retorna dicionário com todas as opções e comandos.

### Aba CMD (`ui/tabs/cmd.py`)

- Opções: /C, /K, /Q, /D, /S.  
- Campo de comando.  
- `set_command_field_enabled(enabled)` e `get_params()` análogos à aba PowerShell.

### CommandPreviewWidget (`ui/widgets/preview.py`)

- QPlainTextEdit somente leitura, fonte monoespaçada.  
- `set_command(text)` atualiza o texto exibido.

### LogOutputWidget (`ui/widgets/log.py`)

- Área de log (ex.: QPlainTextEdit) com `append_log(text)` e `clear_log()`.

### CardWidget (`ui/widgets/card.py`)

- Card com ícone (Unicode Segoe MDL2), título e conteúdo em grid.  
- Funções: `make_field_label`, `add_row`, `add_row_full_width`, `grid_in_card`.

### Estilo global (`ui/style.py`)

- **apply_ui_defaults(app)**: define fonte (Segoe UI), min-height para QLineEdit/QComboBox/QSpinBox/QCheckBox, bordas e padding para QLineEdit, estilos para QTabBar, etc.

### Mica (`ui/mica.py`)

- **enable_mica_for_widget(widget)**: em Windows 11 (build >= 22000), aplica efeito Mica/backdrop na janela via WinAPI (ctypes). Falha em silêncio em Windows 10 ou em erro.

---

## 2.3 TabBar customizada (`main.py`)

- **`_Mdl2TabBar`**: desenha ícone (char em Segoe MDL2 Assets) + texto em cada aba; ícone armazenado em `tabData(index)`. Abas com tamanho baseado no conteúdo (`setExpanding(False)`).

---

## 2.4 Fluxo de dados resumido

1. Usuário seleciona arquivo/pasta ou edita campos → **FileSelector** ou widgets das abas emitem mudanças.  
2. **MainWindow** reage com `on_file_selected` ou `update_command` (conectado a vários sinais).  
3. **update_command** lê todos os parâmetros das abas, chama **CommandBuilder** (set_*) e depois **build_command_for_execution()**.  
4. Resultado é passado para **CommandPreviewWidget** e fica disponível para **on_run**.  
5. **on_run** usa o mesmo **build_command_for_execution()**, grava no log e executa via **Executor** (robocopy) e/ou **subprocess** (PsExec em cmd externo).  
6. **Executor** emite **outputReceived** / **errorReceived** / **finished** → log e botões são atualizados.

Isso encerra a documentação das lógicas de Backend e Frontend do PSExecGUI v3.
