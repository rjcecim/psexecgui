<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/PyQt6-GUI-41CD52?style=flat-square&logo=qt&logoColor=white" alt="PyQt6" />
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows" />
</p>

# 🖥️ PSExecGUI v4

> Interface gráfica para execução remota de comandos e instalação de arquivos em máquinas Windows via **PsExec** (PSTools).

Interface moderna, preview em tempo real e abas dinâmicas conforme o tipo de arquivo. Execute instaladores, scripts e comandos em hosts remotos sem digitar linhas de comando.

---

## 📑 Índice

- [Visão geral](#visão-geral)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Uso rápido](#uso-rápido)
- [Funcionalidades](#funcionalidades)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Documentação](#documentação)

---

## 📋 Visão geral

| Recurso | Descrição |
|--------|-----------|
| 📄 **Arquivos** | `.exe`, `.msi`, `.ps1`, `.bat` e outros — seleção por arquivo ou pasta |
| 📤 **Cópia remota** | Robocopy integrado para enviar arquivos/pastas ao host antes de executar |
| ⌨️ **Comando manual** | Digite o comando remoto (ex.: `cmd`, `powershell`) quando não houver arquivo |
| 👁️ **Preview** | Comando completo atualizado em tempo real antes de executar |
| ▶️ **Execução** | Comando enviado para terminal externo (`cmd /k`) para acompanhamento visual |

---

## ✅ Requisitos

| Item | Observação |
|------|------------|
| 🪟 **Sistema** | Windows 10 ou 11 (APIs para Mica e grupos de processador) |
| 🐍 **Python** | 3.x |
| 🎨 **PyQt6** | Interface gráfica |
| 🔧 **PsExec** | PSTools — caminho configurável (padrão: `C:\PSTools\PsExec.exe`) |
| ℹ️ **PsInfo64** | PSTools — usado para inventário remoto (padrão: `C:\PSTools\PsInfo64.exe`) |
| 🌐 **Rede** | Acesso ao host remoto (SMB), credenciais se necessário |

---

## 📦 Instalação

```bash
# Clone ou baixe o projeto e entre na pasta
cd PSExecGUIv4

# Crie um ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate

# Instale a dependência
pip install PyQt6
```

### 📌 Executável standalone (sem janela de console)

```bash
pip install pyinstaller
pyinstaller PSExecGUIv4.spec
```

O executável será gerado em **`dist/PSExecGUIv4.exe`**.

---

## 🚀 Uso rápido

```bash
python main.py
```

1. 📂 **Selecione** um arquivo (ou pasta) no topo da janela.
2. ✏️ **Preencha** host remoto e, se precisar, usuário/senha na aba **PsExec**.
3. ⚙️ Ajuste opções nas abas que aparecerem (MSI, PowerShell, CMD, Robocopy).
4. 👁️ Confira o **preview** do comando e clique em **Executar** ▶️.

O comando é aberto em um terminal externo para você acompanhar a saída.

### ℹ️ Inventário remoto (PsInfo)

1. ✏️ Preencha **Host remoto** na aba **PsExec**.
2. Clique no botão **ℹ️ PsInfo** ao lado do **Ping**.
3. A aba **PsInfo** abre e coleta automaticamente **Sistema + Aplicativos + Discos** usando:
   - `PsInfo64.exe \\HOST -s -d -accepteula -nobanner`

Na aba **PsInfo**, os cards podem ser **ocultados/expandidos** e o app **esconde** o preview do comando, o log e os botões Play/Stop/Restart (porque não se aplicam ao inventário).

---

## ✨ Funcionalidades

### 📂 Seleção

- 📄 **Arquivo** — escolha `.exe`, `.msi`, `.ps1`, `.bat` ou qualquer outro.
- 📁 **Pasta** — seleção de diretório para cópia integral com Robocopy.
- ❓ **Ajuda** — executa o arquivo com `/?` para ver argumentos (quando aplicável).

### 🖥️ Aba PsExec (sempre visível)

| Card | Conteúdo |
|------|----------|
| 🔗 **Conexão** | Caminho do PsExec, host remoto (com Ping), comando remoto (auto ou manual) |
| 🔐 **Autenticação** | Usuário e senha (`DOMAIN\user`) |
| ⬆️ **Privilégios e sessão** | Elevação (-h, -s, -l), sessão interativa (-i), ID de sessão |
| ⚡ **Desempenho** | Prioridade, grupo CPU, afinidade |
| 🏷️ **Flags e argumentos** | Timeout, -d, -e, -c, -f, -v, -accepteula, -nobanner, args extras |

Campos de texto (Host, Comando remoto, Usuário, Senha, Args extras) têm **ícone de limpar** 🗑️ no final quando há conteúdo.

### ℹ️ Aba PsInfo (sob demanda)

| Card | Conteúdo |
|------|----------|
| 🖥️ **Sistema** | Informações do Windows/CPU/RAM/etc em grade (chave/valor) |
| 📦 **Aplicativos** | Lista com busca + contador de itens visíveis |
| 💾 **Discos** | Tabela com Volume/Tipo/Formato/Rótulo/Tamanho/Livre/% |

> A aba PsInfo só aparece quando você clica no botão de informação (ℹ️) ao lado do Ping.

### 📑 Abas dinâmicas

| Aba | Quando aparece | Principais opções |
|-----|----------------|-------------------|
| 📦 **MSI** | Arquivo `.msi` | Ação (/i, /x, …), interface (/quiet, /passive, …), reinício, log, repair, update |
| 🔷 **PowerShell** | Arquivo `.ps1` ou comando `powershell` | -NoProfile, -NoExit, -ExecutionPolicy, -WindowStyle, -Command, -EncodedCommand |
| 💻 **CMD** | Arquivo `.bat` ou comando `cmd` | /C, /K, /Q, /D, /S, campo de comando |
| 📤 **Robocopy** | Arquivo ou pasta (exceto `.exe`) e comando não manual | Pasta destino (relativa ao C:), switches (/NFL, /NDL, …) |

### ▶️ Execução e log

- 👁️ **Preview** — comando completo (Robocopy + PsExec quando houver) em tempo real.
- ▶️ **Executar** — envia para `start cmd /k <comando>` (terminal externo).
- ⏹️ **Parar** — interrompe processo quando em uso pelo executor interno.
- 🔄 **Reiniciar** — reinicia o aplicativo.
- 📜 **Log** — saída na interface e registro em `exec_history.log`.

---

## 📁 Estrutura do projeto

```
PSExecGUIv4/
├── main.py                 # Entrada e janela principal
├── core/
│   ├── builder.py          # Montagem PsExec, Robocopy, msiexec
│   └── executor.py         # Execução assíncrona
├── ui/
│   ├── style.py            # Estilos globais
│   ├── mica.py             # Efeito Mica (Windows 11)
│   ├── tabs/               # psexec, psinfo, msi, robocopy, powershell, cmd
│   └── widgets/            # selector, preview, log, card, flow
├── utils/
│   ├── api.py              # API Windows (processadores)
│   ├── psinfo.py            # Parse do output do PsInfo (inventário)
│   └── validator.py        # Validadores (afinidade, etc.)
├── PSExecGUIv4.spec        # PyInstaller (exe sem console)
├── README.md
└── documentation.md        # Lógicas Backend e Frontend
```

---

## 📚 Documentação

Para detalhes das lógicas de **backend** (CommandBuilder, Executor, fluxo de comandos) e **frontend** (MainWindow, abas, sinais, preview), consulte **[documentation.md](documentation.md)**.
