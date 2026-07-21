import os

class CommandBuilder:
    """
    Classe utilitária para montar comandos robocopy, PsExec e msiexec
    """
    def __init__(self):
        self.psexec_params = {}
        self.msi_params = {}
        self.robocopy_params = None
        self.file_path = None
        self.folder_path = None
        self.powershell_params = {}  # NOVO
        self.cmd_params = {}  # NOVO

    def set_file(self, file_path):
        self.file_path = file_path

    def set_psexec_params(self, params: dict):
        self.psexec_params = params

    def set_msi_params(self, params: dict):
        self.msi_params = params

    def set_robocopy_params(self, params):
        self.robocopy_params = params

    def set_powershell_params(self, params: dict):
        self.powershell_params = params

    def set_cmd_params(self, params: dict):
        self.cmd_params = params

    def set_file_selection(self, selection):
        """
        Armazena seleção de arquivo ou pasta.
        selection: dict com 'mode', 'file', 'folder'.
        """
        self.selection = selection
        self.file_path = selection.get('file') if selection else None
        self.folder_path = selection.get('folder') if selection else None
        self.selection_mode = selection.get('mode', 'file') if selection else 'file'

    def _extract_flag_value(self, combo_text: str) -> str:
        """Extrai o valor da flag do texto do combobox que contém descrição"""
        if not combo_text or combo_text == "Nenhum":
            return ""
        
        # Extrai apenas a parte da flag (antes do parênteses)
        if "(" in combo_text:
            return combo_text.split("(")[0].strip()
        return combo_text.strip()

    def build_robocopy(self):
        """
        Gera o comando robocopy apropriado para o tipo de seleção:
        - Arquivo: copia apenas o arquivo
        - Pasta: copia a pasta inteira
        """
        if not self.robocopy_params or not self.psexec_params:
            return ""
        if not hasattr(self, 'selection') or not self.selection:
            # Se não há seleção, não há robocopy
            return ""
        if self.selection_mode == 'folder' and getattr(self, 'folder_path', None):
            return self._build_robocopy_folder()
        else:
            return self._build_robocopy_file()

    def _build_robocopy_file(self):
        """Copia apenas o arquivo selecionado"""
        if not self.robocopy_params or not self.psexec_params:
            return "# Erro: parâmetros de robocopy ou psexec ausentes"
        if not self.file_path:
            return "# Erro: arquivo não selecionado"
        dest = self.robocopy_params.get('dest')
        if not dest or not dest.strip():
            return "# Erro: destino de cópia não especificado"
        dest = dest.strip()
        dest = dest.replace('"', '').replace("'", '').strip()
        if isinstance(dest, str) and dest.lower().startswith('c:'):
            dest = dest[2:].lstrip('\\/').replace('/', '\\')
        dest = '\\'.join(part for part in dest.split('\\') if part)
        switches = self.robocopy_params.get('switches', '/NFL /NDL /NJH /NJS /nc /ns /np')
        file_path = os.path.normpath(self.file_path.strip()) if self.file_path else ''
        file_path = os.path.abspath(file_path) if file_path else ''
        src_dir = os.path.dirname(file_path) if file_path else ''
        file_name = os.path.basename(file_path) if file_path else ''
        if not src_dir or not os.path.isdir(src_dir):
            return f"# Erro: Diretório de origem não encontrado: {src_dir}"
        host = self.psexec_params.get('host', '').strip().strip('\\') if self.psexec_params.get('host') else ''
        if not host:
            return "# Erro: host remoto não especificado"
        cmd = f'robocopy "{src_dir}" "\\\\{host}\\C$\\{dest}" "{file_name}" {switches}'
        return cmd

    def _build_robocopy_folder(self):
        """Copia a pasta inteira selecionada"""
        if not self.robocopy_params or not self.psexec_params:
            return "# Erro: parâmetros de robocopy ou psexec ausentes"
        if not self.folder_path:
            return "# Erro: pasta não selecionada"
        dest = self.robocopy_params.get('dest')
        if not dest or not dest.strip():
            return "# Erro: destino de cópia não especificado"
        dest = dest.strip()
        dest = dest.replace('"', '').replace("'", '').strip()
        if isinstance(dest, str) and dest.lower().startswith('c:'):
            dest = dest[2:].lstrip('\\/').replace('/', '\\')
        dest = '\\'.join(part for part in dest.split('\\') if part)
        switches = self.robocopy_params.get('switches', '/NFL /NDL /NJH /NJS /nc /ns /np')
        src_dir = self.folder_path
        folder_name = os.path.basename(os.path.normpath(self.folder_path)) if self.folder_path else ''
        host = self.psexec_params.get('host', '').strip().strip('\\') if self.psexec_params.get('host') else ''
        if not host:
            return "# Erro: host remoto não especificado"
        if not src_dir or not os.path.isdir(src_dir):
            return f"# Erro: Diretório de origem não encontrado: {src_dir}"
        cmd = f'robocopy "{src_dir}" "\\\\{host}\\C$\\{dest}\\{folder_name}" /E {switches}'
        return cmd

    def build_psexec(self):
        """
        Gera o comando PsExec apropriado para o tipo de seleção:
        - .exe: executa o arquivo
        - .msi: executa via msiexec
        - .ps1: executa via powershell
        - .bat: executa via cmd
        - outro arquivo: executa pelo nome
        - pasta: executa o arquivo escolhido dentro da pasta copiada
        - comando manual: executa o comando digitado pelo usuário
        """
        if not self.psexec_params:
            return "# PsExec.exe \\\\<host> [opções] <comando>"
        # Caso especial: comando manual digitado pelo usuário
        remote_cmd = self.psexec_params.get('remote_cmd', '').strip() if self.psexec_params else ''
        if (not self.file_path and not self.folder_path) and remote_cmd:
            cmd = self._base_psexec_cmd()
            cmd.append(remote_cmd)
            if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
                cmd.append(self.psexec_params['extra_args'])
            return " ".join(cmd)
        if not self.file_path:
            return "# PsExec.exe \\\\<host> [opções] <comando>"
        if self.selection_mode == 'folder' and getattr(self, 'folder_path', None):
            return self._build_psexec_folder()
        ext = os.path.splitext(self.file_path)[1].lower() if self.file_path else ''
        if ext == '.exe':
            return self._build_psexec_exe()
        elif ext == '.msi':
            return self._build_psexec_msi()
        elif ext == '.ps1':
            return self._build_psexec_ps_script()
        elif ext == '.bat':
            return self._build_psexec_bat_script()
        else:
            return self._build_psexec_other()

    def _build_psexec_exe(self):
        """Executa um arquivo .exe (nome ou caminho conforme -c)"""
        if not self.psexec_params:
            return "# Erro: parâmetros de psexec ausentes"
        if not self.file_path:
            return "# Erro: arquivo não selecionado"
        cmd = self._base_psexec_cmd()
        if self.psexec_params.get('-c') or self.psexec_params.get('-f'):
            file_path = os.path.normpath(self.file_path) if self.file_path else ''
            cmd.append(f'"{file_path}"')
        else:
            file_name = os.path.basename(self.file_path) if self.file_path else ''
            cmd.append(file_name)
        if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
            cmd.append(self.psexec_params['extra_args'])
        return " ".join(cmd)

    def _build_psexec_msi(self):
        """Executa um arquivo .msi via msiexec"""
        if not self.psexec_params:
            return "# Erro: parâmetros de psexec ausentes"
        if not self.file_path:
            return "# Erro: arquivo .msi não selecionado"
        cmd = self._base_psexec_cmd()
        msiexec_cmd = self.build_msiexec()
        cmd.append(msiexec_cmd)
        return " ".join(cmd)

    def _build_psexec_ps_script(self):
        """Executa um arquivo .ps1 via powershell (nome ou caminho conforme -c), usando parâmetros avançados se fornecidos"""
        if not self.psexec_params:
            return "# Erro: parâmetros de psexec ausentes"
        cmd = self._base_psexec_cmd()
        # Se robocopy está habilitado, usar caminho remoto
        robocopy_dest = None
        if self.robocopy_params:
            dest = self.robocopy_params.get('dest')
            if dest and dest.strip():
                dest = dest.strip().replace('"', '').replace("'", '').strip()
                if isinstance(dest, str) and dest.lower().startswith('c:'):
                    dest = dest[2:].lstrip('\\/').replace('/', '\\')
                dest = '\\'.join(part for part in dest.split('\\') if part)
                
                # CORREÇÃO: Lidar corretamente com pasta vs arquivo
                if hasattr(self, 'selection_mode') and self.selection_mode == 'folder' and hasattr(self, 'folder_path'):
                    # Se é pasta, calcular o caminho relativo do arquivo dentro da pasta
                    folder_name = os.path.basename(os.path.normpath(self.folder_path)) if self.folder_path else ''
                    relpath = os.path.relpath(self.file_path, self.folder_path) if self.file_path and self.folder_path else ''
                    robocopy_dest = f'C:\\{dest}\\{folder_name}\\{relpath}'.replace('/', '\\')
                else:
                    # Se é arquivo individual
                    file_name = os.path.basename(self.file_path) if self.file_path else ''
                    robocopy_dest = f'C:\\{dest}\\{file_name}'
                    
        if robocopy_dest:
            exec_path = robocopy_dest
        elif self.psexec_params.get('-c') or self.psexec_params.get('-f'):
            exec_path = os.path.normpath(self.file_path) if self.file_path else ''
        else:
            exec_path = os.path.basename(self.file_path) if self.file_path else ''
        # Montar comando powershell com parâmetros avançados
        ps_cmd = ['powershell']
        p = self.powershell_params or {}
        if p.get('NoProfile'):
            ps_cmd.append('-NoProfile')
        if p.get('NoExit'):
            ps_cmd.append('-NoExit')
        if p.get('ExecutionPolicy'):
            ps_cmd.append(f'-ExecutionPolicy {p["ExecutionPolicy"]}')
        if p.get('WindowStyle'):
            ps_cmd.append(f'-WindowStyle {p["WindowStyle"]}')
        # Prioridade: EncodedCommand > Command > File
        if p.get('EncodedCommand'):
            ps_cmd.append(f'-EncodedCommand {p["EncodedCommand"]}')
        elif p.get('Command'):
            ps_cmd.append(f'-Command {p["Command"]}')
        else:
            if self.file_path:
                ps_cmd.append(f'-File "{exec_path}"')
        ps_cmd_str = ' '.join(ps_cmd)
        cmd.append(ps_cmd_str)
        if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
            cmd.append(self.psexec_params['extra_args'])
        return " ".join(cmd)

    def _build_psexec_bat_script(self):
        """Executa um arquivo .bat via cmd (nome ou caminho conforme -c), usando parâmetros avançados se fornecidos"""
        if not self.psexec_params:
            return "# Erro: parâmetros de psexec ausentes"
        cmd = self._base_psexec_cmd()
        # Se robocopy está habilitado, usar caminho remoto
        robocopy_dest = None
        if self.robocopy_params:
            dest = self.robocopy_params.get('dest')
            if dest and dest.strip():
                dest = dest.strip().replace('"', '').replace("'", '').strip()
                if isinstance(dest, str) and dest.lower().startswith('c:'):
                    dest = dest[2:].lstrip('\\/').replace('/', '\\')
                dest = '\\'.join(part for part in dest.split('\\') if part)
                
                # CORREÇÃO: Lidar corretamente com pasta vs arquivo
                if hasattr(self, 'selection_mode') and self.selection_mode == 'folder' and hasattr(self, 'folder_path'):
                    # Se é pasta, calcular o caminho relativo do arquivo dentro da pasta
                    folder_name = os.path.basename(os.path.normpath(self.folder_path)) if self.folder_path else ''
                    relpath = os.path.relpath(self.file_path, self.folder_path) if self.file_path and self.folder_path else ''
                    robocopy_dest = f'C:\\{dest}\\{folder_name}\\{relpath}'.replace('/', '\\')
                else:
                    # Se é arquivo individual
                    file_name = os.path.basename(self.file_path) if self.file_path else ''
                    robocopy_dest = f'C:\\{dest}\\{file_name}'
                    
        if robocopy_dest:
            exec_path = robocopy_dest
        elif self.psexec_params.get('-c') or self.psexec_params.get('-f'):
            exec_path = os.path.normpath(self.file_path) if self.file_path else ''
        else:
            exec_path = os.path.basename(self.file_path) if self.file_path else ''
        # Montar comando cmd com parâmetros avançados
        c = self.cmd_params or {}
        cmd_flags = []
        if c.get('/C'):
            cmd_flags.append('/C')
        if c.get('/K'):
            cmd_flags.append('/K')
        if c.get('/Q'):
            cmd_flags.append('/Q')
        if c.get('/D'):
            cmd_flags.append('/D')
        if c.get('/S'):
            cmd_flags.append('/S')
        # Prioridade: Command > exec_path
        if c.get('Command'):
            cmd_str = c['Command']
        else:
            cmd_str = exec_path
        if cmd_str:
            cmd.append(f'cmd {" ".join(cmd_flags)} "{cmd_str}"')
        else:
            cmd.append(f'cmd {" ".join(cmd_flags)}')
        if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
            cmd.append(self.psexec_params['extra_args'])
        return " ".join(cmd)

    def _build_psexec_other(self):
        """Executa outro tipo de arquivo (nome ou caminho conforme -c)"""
        if not self.psexec_params:
            return "# Erro: parâmetros de psexec ausentes"
        if not self.file_path:
            return "# Erro: arquivo não selecionado"
        cmd = self._base_psexec_cmd()
        if self.psexec_params.get('-c') or self.psexec_params.get('-f'):
            file_path = os.path.normpath(self.file_path) if self.file_path else ''
            cmd.append(f'"{file_path}"')
        else:
            file_name = os.path.basename(self.file_path) if self.file_path else ''
            cmd.append(file_name)
        if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
            cmd.append(self.psexec_params['extra_args'])
        return " ".join(cmd)

    def _build_psexec_folder(self):
        """Executa o arquivo escolhido dentro da pasta copiada, mantendo o caminho relativo"""
        if not self.robocopy_params or not self.psexec_params:
            return "# Erro: parâmetros de robocopy ou psexec ausentes"
        if not self.file_path or not self.folder_path:
            return "# Erro: arquivo ou pasta não selecionados"
        cmd = self._base_psexec_cmd()
        dest = self.robocopy_params.get('dest', 'Temp') if self.robocopy_params else 'Temp'
        dest = dest.strip() if isinstance(dest, str) else 'Temp'
        if isinstance(dest, str) and dest.lower().startswith('c:'):
            dest = dest[2:].lstrip('\\/').replace('/', '\\')
        dest = '\\'.join(part for part in dest.split('\\') if part)
        folder_name = os.path.basename(os.path.normpath(self.folder_path)) if self.folder_path else ''
        relpath = os.path.relpath(self.file_path, self.folder_path) if self.file_path and self.folder_path else ''
        exec_path = f'C:\\{dest}\\{folder_name}\\{relpath}'.replace('/', '\\')
        ext = os.path.splitext(self.file_path)[1].lower() if self.file_path else ''
        if ext == '.ps1':
            # Montar comando powershell com parâmetros avançados dos tabs
            ps_cmd = ['powershell']
            p = self.powershell_params or {}
            if p.get('NoProfile'):
                ps_cmd.append('-NoProfile')
            if p.get('NoExit'):
                ps_cmd.append('-NoExit')
            if p.get('ExecutionPolicy'):
                ps_cmd.append(f'-ExecutionPolicy {p["ExecutionPolicy"]}')
            if p.get('WindowStyle'):
                ps_cmd.append(f'-WindowStyle {p["WindowStyle"]}')
            # Prioridade: EncodedCommand > Command > File
            if p.get('EncodedCommand'):
                ps_cmd.append(f'-EncodedCommand {p["EncodedCommand"]}')
            elif p.get('Command'):
                ps_cmd.append(f'-Command {p["Command"]}')
            else:
                ps_cmd.append(f'-File "{exec_path}"')
            ps_cmd_str = ' '.join(ps_cmd)
            cmd.append(ps_cmd_str)
        elif ext == '.bat':
            cmd.append(f'cmd /c "{exec_path}"')
        elif ext == '.msi':
            msiexec_cmd = f'msiexec /i "{exec_path}"'
            cmd.append(msiexec_cmd)
        else:
            cmd.append(f'"{exec_path}"')
        if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
            cmd.append(self.psexec_params['extra_args'])
        return " ".join(cmd)

    def _base_psexec_cmd(self):
        """Monta a base do comando PsExec com parâmetros comuns"""
        import os
        from utils.pstools import resolve_pstools_tool

        host = self.psexec_params.get('host', '').strip()
        pstools = self.psexec_params.get('psexec_path', '').strip()
        psexec_path = resolve_pstools_tool(pstools, ("PsExec64.exe", "PsExec.exe"))
        if psexec_path:
            psexec_path = os.path.normpath(psexec_path.replace('"', '').replace("'", ''))
            if ' ' in psexec_path:
                cmd = [f'"{psexec_path}"']
            else:
                cmd = [psexec_path]
        else:
            cmd = ["PsExec.exe"]
        cmd.append(f"\\\\{host}")
        if self.psexec_params.get('user') and self.psexec_params['user'].strip():
            cmd.append(f"-u {self.psexec_params['user']}")
        if self.psexec_params.get('password') and self.psexec_params['password'].strip():
            cmd.append(f"-p {self.psexec_params['password']}")
        # Processar flags de elevação
        for flag in ['-h', '-s', '-l']:
            if self.psexec_params.get(flag):
                cmd.append(flag)
        if self.psexec_params.get('session_interactive'):
            session_id = self.psexec_params.get('session_id', 0)
            if session_id == 0:
                cmd.append("-i")
            else:
                cmd.append(f"-i {session_id}")
        priority_value = self._extract_flag_value(self.psexec_params.get('priority', ''))
        if priority_value and priority_value != "Nenhum":
            cmd.append(priority_value)
        affinity_value = self.psexec_params.get('affinity', '').strip()
        if affinity_value:
            cmd.append(f"-a {affinity_value}")
        group_value = self._extract_flag_value(self.psexec_params.get('group', ''))
        if group_value and group_value != "Nenhum":
            if "(" in group_value:
                group_value = group_value.split("(")[0].strip()
            cmd.append(f"-g {group_value}")
        if self.psexec_params.get('timeout') and self.psexec_params['timeout'] > 0:
            cmd.append(f"-n {self.psexec_params['timeout']}")
        # Não adicionar -c ou -f se robocopy estiver habilitado
        skip_copy_flags = self.robocopy_params is not None
        for flag in ['-d', '-e', '-c', '-f', '-v', '-accepteula', '-nobanner']:
            if flag in ['-c', '-f'] and skip_copy_flags:
                continue
            if self.psexec_params.get(flag):
                cmd.append(flag)
        return cmd

    def build_msiexec(self):
        # Monta comando msiexec se habilitado
        if not self.msi_params.get('enable'):
            return ""
        if not self.file_path:
            return "# msiexec [opções] <arquivo.msi>"
        dest = self.robocopy_params.get('dest') if self.robocopy_params else None
        if not dest or not str(dest).strip():
            return "# Erro: destino de cópia não especificado"
        dest = str(dest).strip()
        if isinstance(dest, str) and dest.lower().startswith('c:'):
            dest = dest[2:].lstrip('\\/').replace('/', '\\')
        dest = '\\'.join(part for part in dest.split('\\') if part)
        cmd = ["msiexec"]
        # Ação - extrair apenas a flag
        action_value = self._extract_flag_value(self.msi_params.get('action', ''))
        if action_value and action_value != "Nenhum":
            cmd.append(action_value)
        file_name = os.path.basename(self.file_path) if self.file_path else ''
        cmd.append(f'"C:\\{dest}\\{file_name}"')
        # Agora, adicionar os demais parâmetros na ordem correta
        # Interface
        interface_value = self._extract_flag_value(self.msi_params.get('interface', ''))
        if interface_value and interface_value != "Nenhum":
            cmd.append(interface_value)
        # Reinício
        restart_value = self._extract_flag_value(self.msi_params.get('restart', ''))
        if restart_value and restart_value != "Nenhum":
            cmd.append(restart_value)
        # Log
        if self.msi_params.get('log') and self.msi_params.get('log_file') and self.msi_params['log_file'].strip():
            cmd.append(f'/l*vx "{self.msi_params["log_file"]}"')
        # Repair
        if self.msi_params.get('repair') and self.msi_params['repair'].strip():
            cmd.append(f'-f{self.msi_params["repair"]}')
        # Update
        if self.msi_params.get('update') and self.msi_params['update'].strip():
            cmd.append(self.msi_params['update'])
        # Argumentos extras para o arquivo MSI executado
        if self.psexec_params.get('extra_args') and self.psexec_params['extra_args'].strip():
            cmd.append(self.psexec_params['extra_args'])
        return " ".join(cmd)

    def build_full_command(self):
        # Gera o comando completo para preview e execução
        robocopy_cmd = self.build_robocopy()
        # Para arquivos .ps1, sempre usar _build_psexec_ps_script para preservar parâmetros da aba PowerShell
        if self.file_path and self.file_path.lower().endswith('.ps1'):
            psexec_cmd = self._build_psexec_ps_script()
        # Para arquivos .bat, sempre usar _build_psexec_bat_script para preservar parâmetros da aba CMD
        elif self.file_path and self.file_path.lower().endswith('.bat'):
            psexec_cmd = self._build_psexec_bat_script()
        else:
            psexec_cmd = self.build_psexec()
        if robocopy_cmd:
            return f"{robocopy_cmd}\n{psexec_cmd}"
        else:
            return psexec_cmd
