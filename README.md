<p align="center">
  <img src="https://img.shields.io/badge/version-1.5.0-0B5CAB?style=flat-square" alt="Version" />
  <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/PyQt6-GUI-41CD52?style=flat-square&logo=qt&logoColor=white" alt="PyQt6" />
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows" />
</p>

# PSExecGUI 1.5.0

> Interface gráfica para execução remota de comandos e instalação de arquivos em máquinas Windows via **PsExec** (PSTools).

<p align="center">
  <img src="assets/app_icon.png" alt="PSExecGUI" width="96" />
</p>

Interface moderna com identidade visual própria, preview em tempo real e abas dinâmicas conforme o tipo de arquivo. Execute instaladores, scripts e comandos em hosts remotos sem digitar linhas de comando.

---

## Índice

- [Visão geral](#visão-geral)
- [Identidade visual](#identidade-visual)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Uso rápido](#uso-rápido)
- [Funcionalidades](#funcionalidades)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Documentação](#documentação)

---

## Visão geral

| Recurso | Descrição |
|--------|-----------|
| **Arquivos** | `.exe`, `.msi`, `.ps1`, `.bat` e outros — seleção por arquivo ou pasta |
| **Cópia remota** | Robocopy integrado para enviar arquivos/pastas ao host antes de executar |
| **Comando manual** | Digite o comando remoto (ex.: `cmd`, `powershell`) quando não houver arquivo |
| **Preview** | Comando completo atualizado em tempo real antes de executar |
| **Execução** | Comando aberto em terminal externo (`cmd /k`) para acompanhamento visual |
| **Inventário** | PsInfo remoto (sistema, aplicativos, discos) sob demanda |
| **RustDesk** | Coleta ID no host e abre conexão local |

Versão do aplicativo: **`1.5.0`** (`APP_VERSION` em `ui/branding.py`).

---

## Identidade visual

Constante e assets centralizados em `ui/branding.py` e `assets/`:

| Asset | Uso |
|-------|-----|
| `assets/icon.ico` | Ícone do executável (PyInstaller) e da janela |
| `assets/app_icon.png` | Fallback do ícone da janela / documentação |
| `assets/app_mark.png` | Marca no cabeçalho da UI (mesma linha do seletor de arquivo) |

Paleta de referência: azure sólido `#0B5CAB` (fundo do ícone sem degradê), cyan `#38BDF8`.
Nome exibido: **Instalador Remoto via PsExec**.

Para regenerar o `.ico` a partir de `app_icon.png`:

```bash
python scripts/generate_brand_assets.py
```

---

## Requisitos

| Item | Observação |
|------|------------|
| **Sistema** | Windows 10 ou 11 (APIs para Mica e grupos de processador) |
| **Python** | 3.x |
| **PyQt6** | Interface gráfica |
| **PsExec** | PSTools — caminho configurável (padrão: `C:\PSTools\PsExec.exe`) |
| **PsInfo64** | PSTools — inventário remoto (padrão: `C:\PSTools\PsInfo64.exe`) |
| **RustDesk** | Para “Conectar via RustDesk”: instalado no host remoto e no PC local |
| **Rede** | Acesso ao host remoto (SMB), credenciais se necessário |

---

## Instalação

```bash
cd psexecgui

python -m venv .venv
.venv\Scripts\activate

pip install PyQt6
```

### Executável standalone (sem janela de console)

```bash
pip install pyinstaller
pyinstaller PSExecGUI.spec --noconfirm
```

O executável será gerado em **`dist/PSExecGUI.exe`** (ícone e pasta `assets/` embutidos).

---

## Uso rápido

```bash
python main.py
```

1. No cabeçalho, selecione um arquivo (ou pasta).
2. Preencha **host remoto** e, se precisar, usuário/senha na aba **PsExec**.
3. Ajuste opções nas abas que aparecerem (MSI, PowerShell, CMD, Robocopy).
4. Confira o **preview** do comando e clique em **Executar**.

O comando é aberto em um terminal externo para você acompanhar a saída.

### Inventário remoto (PsInfo)

1. Preencha **Host remoto** na aba **PsExec**.
2. Clique no botão **PsInfo** ao lado do **Ping**.
3. A aba **PsInfo** abre e coleta **Sistema + Aplicativos + Discos** com:
   - `PsInfo64.exe \\HOST -s -d -accepteula -nobanner`

Na aba PsInfo, os cards podem ser ocultados/expandidos, há spinner durante a coleta, e o app esconde preview, log e botões Play/Stop/Restart.

### Conectar via RustDesk

1. Preencha **Host remoto** na aba **PsExec**.
2. Clique no botão **RustDesk** (ao lado do Ping/PsInfo).
3. O app coleta o ID no host via PsExec (`-h -s`) e abre localmente:
   - `rustdesk.exe --connect <ID>`

Status e erros aparecem no **Log de Execução**.

---

## Funcionalidades

### Seleção

- **Arquivo** — `.exe`, `.msi`, `.ps1`, `.bat` ou outro.
- **Pasta** — diretório para cópia integral com Robocopy.
- **Ajuda** — executa o arquivo com `/?` para ver argumentos (quando aplicável).

### Aba PsExec (sempre visível)

| Card | Conteúdo |
|------|----------|
| **Conexão** | Caminho do PsExec, host remoto (Ping / PsInfo / RustDesk), comando remoto |
| **Autenticação** | Usuário e senha (`DOMAIN\user`) |
| **Privilégios e sessão** | Elevação (-h, -s, -l), sessão interativa (-i), ID de sessão |
| **Desempenho** | Prioridade, grupo CPU, afinidade |
| **Flags e argumentos** | Timeout, -d, -e, -c, -f, -v, -accepteula, -nobanner, args extras |

Campos de texto (Host, Comando remoto, Usuário, Senha, Args extras) têm ícone de limpar quando há conteúdo.

### Aba PsInfo (sob demanda)

| Card | Conteúdo |
|------|----------|
| **Sistema** | Windows / CPU / RAM / etc. em grade chave/valor |
| **Aplicativos** | Lista com busca + contador |
| **Discos** | Volume / Tipo / Formato / Rótulo / Tamanho / Livre / % |

### Abas dinâmicas

| Aba | Quando aparece | Principais opções |
|-----|----------------|-------------------|
| **MSI** | Arquivo `.msi` | Ação, interface, reinício, log, repair, update |
| **PowerShell** | Arquivo `.ps1` ou comando `powershell` | -NoProfile, -NoExit, -ExecutionPolicy, -WindowStyle, -Command, -EncodedCommand |
| **CMD** | Arquivo `.bat` ou comando `cmd` | /C, /K, /Q, /D, /S, campo de comando |
| **Robocopy** | Arquivo ou pasta (exceto `.exe`) e comando não manual | Destino relativo ao C:, switches |

### Execução e log

- **Preview** — comando completo (Robocopy + PsExec quando houver) em tempo real.
- **Executar** — `start cmd /k <comando>` (terminal externo).
- **Parar** — interrompe processo do executor interno.
- **Reiniciar** — reinicia o aplicativo.
- **Log** — saída na interface e registro em `exec_history.log`.

---

## Estrutura do projeto

```
psexecgui/
├── main.py                 # Entrada, MainWindow e cabeçalho de marca
├── assets/
│   ├── app_icon.png        # Ícone completo (tile) — fallback da janela
│   ├── app_mark.png        # Marca — cabeçalho da UI
│   └── icon.ico            # Ícone do executável / janela Windows
├── core/
│   ├── builder.py          # Montagem PsExec, Robocopy, msiexec
│   └── executor.py         # Execução assíncrona
├── ui/
│   ├── branding.py         # APP_NAME / APP_VERSION / ícone / marca
│   ├── style.py            # Estilos globais
│   ├── mica.py             # Efeito Mica (Windows 11)
│   ├── tabs/               # psexec, psinfo, msi, robocopy, powershell, cmd
│   └── widgets/            # selector, preview, log, card, flow, spinner
├── utils/
│   ├── api.py              # API Windows (processadores)
│   ├── psinfo.py           # Parse do output do PsInfo
│   └── validator.py        # Validadores (afinidade, etc.)
├── scripts/
│   └── generate_brand_assets.py  # Reexporta ICO a partir de app_icon.png
├── PSExecGUI.spec          # PyInstaller (exe sem console + ícone + assets)
├── README.md
└── documentation.md        # Lógicas backend e frontend
```

---

## Documentação

Para detalhes de **backend** (CommandBuilder, Executor, fluxo de comandos) e **frontend** (MainWindow, branding, abas, sinais, preview), consulte **[documentation.md](documentation.md)**.
