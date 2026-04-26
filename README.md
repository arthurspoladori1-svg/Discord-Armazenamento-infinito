# 🧊 Discord Infinite Storage Bot

Transforme canais de texto do Discord em um **HD infinito**!  
Envie arquivos e pastas gigantes (até terabytes) codificados como anexos, com compressão, verificação de integridade e download turbo.

---

## ✨ Funcionalidades

- 📂 **Envio de arquivo único** – selecione qualquer arquivo pelo Explorer.
- 📁 **Envio de pasta inteira** – a pasta é compactada em `.tar`, comprimida e enviada como um único pacote.
- 🗜️ **Compressão zlib** – reduz o tamanho em até 70% antes do envio.
- ⚡ **Upload multi‑anexo** – até 10 partes de 7 MB por mensagem.
- 🔒 **Validação pós‑envio** – cada lote é verificado imediatamente; se falhar, é reenviado.
- 🌐 **Download paralelo** – baixa todas as partes ao mesmo tempo (até 10 threads).
- 🔐 **Hash SHA256** – garante que o arquivo restaurado é idêntico ao original.
- 🧹 **Limpeza automática de itens corrompidos**.
- 💣 **Reset nuclear** – apaga canais de armazenamento e mensagens com código de confirmação.
- 📊 **Progresso detalhado** – porcentagem, tempo, ETA e velocidade de upload.
- 🖥️ **Interface gráfica opcional** (diálogos do Explorer) – ou modo texto puro.
- 🗃️ **Pastas preservadas** – ao baixar, a estrutura de diretórios original é recriada.

---

## 🚀 Modo SUPREME

O segredo da velocidade está em **comprimir → empacotar → dividir → validar → paralelizar**:

1. **Compressão zlib (nível 3)** – antes do base64, reduz drasticamente o volume de dados.
2. **Tarfile** – pastas viram um único arquivo `.tar`.
3. **Base64 + chunks de 7 MB** – cada parte vira um anexo `.b64`.
4. **Lotes de até 10 anexos por mensagem** – menos chamadas à API.
5. **Validação imediata** – a cada lote enviado, o bot confere se os anexos chegaram corretos.
6. **Download paralelo** – `ThreadPoolExecutor` dispara várias requisições simultâneas.
7. **Descompressão + verificação de hash** – garante integridade total.

Resultado: **arquivos de 1 GB são enviados em minutos e baixados em segundos**.

---

## 📦 Pré‑requisitos

- Python **3.10+**
- Token de um bot Discord (com as permissões: `Send Messages`, `Attach Files`, `Read Message History`, `Manage Messages`)
- Servidor Discord onde o bot foi adicionado
- Canal inicial (já existente)

---

## ⚙️ Instalação

1. **Clone** este repositório ou baixe o script `storage_bot.py`.
2. Instale as dependências:
   ```bash
   pip install requests python-dotenv
3.Crie um arquivo .env na mesma pasta com o token do bot:
   TOKEN=coloque_seu_token_aqui
4.(Opcional) Altere as configurações no topo do script:
  GUILD_ID, INITIAL_CHANNEL_ID, MAX_MSGS_PER_CHANNEL etc.
5.Execute
  python storage_bot.py