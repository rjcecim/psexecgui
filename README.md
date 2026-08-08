<p align="center">
  <img src="https://img.shields.io/badge/version-1.5.0-0B5CAB?style=flat-square" alt="Version" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
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
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Uso rápido](#uso-rápido)
- [Segurança de credenciais](#segurança-de-credenciais)
- [hosts.json](#hostsjson)
- [Testes](#testes)
- [Build](#build)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Documentação](#documentação)

---

## Visão geral

| Recurso | Descrição |
|--------|-----------|
| **Arquivos** | `.exe`, `.msi`, `.ps1`, `.bat` e outros — seleção por arquivo ou pasta |
| **Cópia remota** | Robocopy integrado para enviar arquivos/pastas ao host antes de executar |
| **Comando manual** | Digite o comando remoto (ex.: `cmd`, `powershell`) quando não houver arquivo |
| **Preview** | Comando sanitizado (senha mascarada) atualizado em tempo real |
| **Execução** | Terminal externo (`cmd /k` via lista de args, sem `shell=True`) |
| **Inventário** | PsInfo remoto + Remote Registry (32/64 bits) |
| **Busca multi-host** | Pesquisa de aplicativos em lista de hosts (`hosts.json`) |
| **RustDesk** | Coleta ID no host e abre conexão local |

Versão do aplicativo: **`1.5.0`** (`APP_VERSION` em `ui/branding.py`).

---

## Requisitos

| Item | Observação |
|------|------------|
| **Sistema** | Windows 10 ou 11 |
| **Python** | 3.10+ |
| **PyQt6** | Interface gráfica |
| **PsExec** | PSTools — padrão `C:\PSTools\` |
| **PsInfo64** | Inventário remoto |
| **RustDesk** | Opcional — conexão remota |
| **Rede** | SMB / Remote Registry conforme o fluxo |

---

## Instalação

```bash
cd psexecgui
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Ou apenas runtime:

```bash
pip install PyQt6
```

---

## Uso rápido

```bash
python main.py
```

1. Selecione um arquivo (ou pasta) no cabeçalho.
2. Preencha **host remoto** e, se necessário, usuário/senha na aba **PsExec**.
3. Ajuste opções nas abas (MSI, PowerShell, CMD, Robocopy).
4. Confira o **preview** (senha aparece como `********`) e clique em **Executar**.

### Inventário (PsInfo)

Botão **PsInfo** ao lado do Ping — coleta sistema, aplicativos e discos.

### RustDesk

Botão **RustDesk** — obtém o ID no host (`--get-id` via PsExec `-h -s`) e abre `rustdesk.exe --connect <ID>` localmente.

---

## Segurança de credenciais

Política central em `utils/redaction.py`:

- A senha **nunca** aparece no preview, logs, `exec_history.log`, mensagens de erro ou arquivos temporários.
- O comando real (com `-p`) só existe em memória no momento da execução.
- Preferência: use a sessão Windows atual (sem `-u`/`-p`) quando possível.

### Limitação inerente ao PsExec

Quando `-u`/`-p` são necessários, o PsExec recebe a senha na linha de comando do processo. Isso é uma limitação do transporte Sysinternals — o aplicativo **não consegue eliminá-la**, apenas evita gravá-la em disco/UI/logs.

---

## hosts.json

Arquivo **local** (não versionar hosts reais):

1. Copie `hosts.example.json` → `hosts.json`
2. Edite com os nomes dos computadores do seu ambiente

`hosts.json` está no `.gitignore`. O arquivo de exemplo acompanha o repositório e o build.

---

## Logging

Histórico sanitizado em:

- **Padrão:** `%LOCALAPPDATA%\PSExecGUI\logs\exec_history.log`
- **Portable:** pasta `logs\` ao lado do exe (crie `portable.flag` ou defina `PSEXECGUI_PORTABLE=1`)

---

## Testes

```bash
pip install -e ".[dev]"
pytest tests/unit -q
python -m compileall -q core services utils ui main.py
```

Testes **não** executam PsExec contra máquinas reais. CI: GitHub Actions (`windows-latest`).

---

## Build

```bash
pip install pyinstaller
pyinstaller PSExecGUI.spec --noconfirm
```

Gera `dist/PSExecGUI.exe` com `assets/`, `config/` e `hosts.example.json`. **Não** empacota `hosts.json`, credenciais, logs ou testes.

---

## Estrutura do projeto

```
psexecgui/
├── main.py                 # UI / MainWindow
├── core/
│   ├── builder.py          # CommandBuilder → CommandSpec
│   ├── executor.py         # Executor + ExecutionResult
│   ├── models.py           # Domain models
│   └── win_cmd.py          # subprocess sem shell=True
├── services/
│   └── ops.py              # Execução, uninstall, RustDesk
├── utils/
│   ├── redaction.py        # Política central de senha
│   ├── app_logging.py      # Logging seguro
│   ├── app_catalog.py      # ApplicationCatalog + validação
│   ├── psinfo.py           # Parser / Remote Registry
│   └── hosts.py            # hosts.json
├── ui/                     # Abas e widgets
├── config/ApplicationCatalog.json
├── hosts.example.json
├── tests/unit/
├── pyproject.toml
└── PSExecGUI.spec
```

---

## Documentação

Detalhes técnicos: **[documentation.md](documentation.md)**.
