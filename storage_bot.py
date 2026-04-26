#!/usr/bin/env python3
"""
Discord Infinite Storage Bot v10.0 – Extreme Edition
- Compressão zlib (nível 3) antes de base64
- Download paralelo (threads)
- Velocidade de upload em tempo real
"""
import os, sys, json, time, base64, random, tempfile, requests, math, tarfile, hashlib, zlib
from datetime import datetime, timezone
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

try:
    import tkinter as tk
    from tkinter import filedialog
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# ---------- CONFIGURAÇÕES ----------
load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = 
INITIAL_CHANNEL_ID = 
MAX_MSGS_PER_CHANNEL = 100
CHANNEL_PREFIX = "storage"
METADATA_FILE = "metadata.json"
MAX_ATTACHMENT_SIZE = 7 * 1024 * 1024        # 7 MB (volta a ser maior porque a compressão reduz o efetivo)
MAX_ATTACHMENTS_PER_MSG = 10
DOWNLOAD_FOLDER = "downloads"

BASE_URL = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "DiscordStorageBot/10.0",
}
UPLOAD_HEADERS = {**HEADERS, "Connection": "close"}

# ---------- UTILITÁRIOS ----------
def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(units)-1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {units[i]}"

def api_call(method, url, **kwargs):
    custom_headers = kwargs.pop("custom_headers", None)
    headers_to_use = custom_headers if custom_headers is not None else HEADERS
    while True:
        try:
            resp = requests.request(method, url, headers=headers_to_use, timeout=60, **kwargs)
        except requests.exceptions.RequestException as e:
            print(f"  [!] Erro de conexão: {e}. Tentando novamente em 5s...")
            time.sleep(5)
            continue
        if resp.status_code == 429:
            retry = resp.json().get("retry_after", 1)
            print(f"  [!] Rate limit, aguardando {retry:.1f}s...")
            time.sleep(retry)
            continue
        return resp

def channel_exists(channel_id):
    return api_call("GET", f"{BASE_URL}/channels/{channel_id}").ok

def verify_bot_access():
    resp = api_call("POST", f"{BASE_URL}/channels/{INITIAL_CHANNEL_ID}/messages",
                    json={"content": "🤖 Bot online – verificação."})
    if resp.ok:
        api_call("DELETE", f"{BASE_URL}/channels/{INITIAL_CHANNEL_ID}/messages/{resp.json()['id']}")
        print("[✓] Acesso confirmado ao canal inicial.")
        return True
    print(f"[✗] ERRO {resp.status_code}: {resp.text}")
    return False

def count_messages(channel_id):
    count = 0
    last_id = None
    while True:
        params = {"limit": 100}
        if last_id:
            params["before"] = last_id
        resp = api_call("GET", f"{BASE_URL}/channels/{channel_id}/messages", params=params)
        if not resp.ok:
            break
        msgs = resp.json()
        if not msgs:
            break
        count += len(msgs)
        last_id = msgs[-1]["id"]
        if len(msgs) < 100:
            break
        time.sleep(0.2)
    return count

def create_channel(name):
    payload = {"name": name, "type": 0}
    resp = api_call("POST", f"{BASE_URL}/guilds/{GUILD_ID}/channels", json=payload)
    if resp.ok:
        data = resp.json()
        print(f"  [+] Canal criado: {data['name']} (ID: {data['id']})")
        return str(data["id"])
    print(f"  [!] Erro ao criar canal: {resp.status_code}")
    return None

def get_active_channel(metadata):
    channels = metadata.get("channels", {})
    active_id = metadata.get("active_channel")

    if not active_id:
        active_id = str(INITIAL_CHANNEL_ID)
        channels[active_id] = {"name": "initial", "message_count": 0}
        metadata["active_channel"] = active_id
        metadata["channels"] = channels
        save_metadata(metadata)
        return active_id

    if not channel_exists(int(active_id)):
        print(f"  [!] Canal ativo {active_id} não existe. Voltando ao inicial.")
        active_id = str(INITIAL_CHANNEL_ID)
        channels[active_id] = {"name": "initial", "message_count": 0}
        metadata["active_channel"] = active_id
        metadata["channels"] = channels
        save_metadata(metadata)
        return active_id

    count = count_messages(int(active_id))
    channels[active_id]["message_count"] = count
    metadata["channels"] = channels
    save_metadata(metadata)

    if count >= MAX_MSGS_PER_CHANNEL:
        next_num = metadata.get("next_channel_number", 1)
        new_name = f"{CHANNEL_PREFIX}_{next_num}"
        new_id = create_channel(new_name)
        if new_id:
            channels[new_id] = {"name": new_name, "message_count": 0}
            metadata["active_channel"] = new_id
            metadata["channels"] = channels
            metadata["next_channel_number"] = next_num + 1
            save_metadata(metadata)
            return new_id
    return active_id

# ---------- METADADOS ----------
def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {"items": {}, "channels": {}, "active_channel": None, "next_channel_number": 1, "next_group_index": 0}

def save_metadata(meta):
    with open(METADATA_FILE, "w") as f:
        json.dump(meta, f, indent=2, default=str)

def _int_to_excel_col(num):
    col = ""
    while True:
        num, remainder = divmod(num, 26)
        col = chr(65 + remainder) + col
        if num == 0:
            break
        num -= 1
    return col

def generate_item_id(metadata, suffix, base_letter=None):
    if base_letter is None:
        group_idx = metadata.get("next_group_index", 0)
        base_letter = _int_to_excel_col(group_idx)
        metadata["next_group_index"] = group_idx + 1
        save_metadata(metadata)
    return f"{base_letter}{suffix}"

def select_file_dialog():
    if not GUI_AVAILABLE:
        return input("Caminho do arquivo: ").strip().strip('"')
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Selecione um arquivo")
    root.destroy()
    return file_path

def select_folder_dialog():
    if not GUI_AVAILABLE:
        return input("Caminho da pasta: ").strip().strip('"')
    root = tk.Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Selecione uma pasta")
    root.destroy()
    return folder_path

# ---------- VALIDAÇÃO PÓS‑ENVIO (tolerância maior) ----------
def validate_message(channel_id, message_id, expected_file_count, expected_total_size):
    resp = api_call("GET", f"{BASE_URL}/channels/{channel_id}/messages/{message_id}")
    if not resp.ok:
        return False
    attachments = resp.json().get("attachments", [])
    if len(attachments) != expected_file_count:
        return False
    total = sum(a["size"] for a in attachments)
    return abs(total - expected_total_size) <= 100   # tolerância de 100 bytes

# ---------- UPLOAD COM COMPRESSÃO ----------
def _do_upload_item(item_id, raw_bytes, metadata, label=""):
    original_size = len(raw_bytes)
    original_hash = hashlib.sha256(raw_bytes).hexdigest()

    # Compressão zlib (nível 3, rápido)
    compressed = zlib.compress(raw_bytes, level=3)
    print(f"  [*] Compressão: {format_size(original_size)} -> {format_size(len(compressed))} "
          f"({(1 - len(compressed)/original_size)*100:.1f}% menor)")

    b64_str = base64.b64encode(compressed).decode("ascii")
    part_size = MAX_ATTACHMENT_SIZE
    parts = [b64_str[i:i+part_size] for i in range(0, len(b64_str), part_size)]
    total_parts = len(parts)

    lotes = [parts[i:i+MAX_ATTACHMENTS_PER_MSG] for i in range(0, total_parts, MAX_ATTACHMENTS_PER_MSG)]
    total_lotes = len(lotes)

    message_refs = []
    current_channel = get_active_channel(metadata)
    start_time = time.time()
    bytes_enviados = 0

    for lote_idx, lote in enumerate(lotes, start=1):
        files_dict = {}
        part_bytes = []
        for idx_in_lote, part_data in enumerate(lote):
            global_part_index = (lote_idx-1) * MAX_ATTACHMENTS_PER_MSG + idx_in_lote
            filename_part = f"{item_id}.part{global_part_index+1:04d}.b64"
            field_name = f"file{idx_in_lote}"
            encoded = part_data.encode("ascii")
            files_dict[field_name] = (filename_part, BytesIO(encoded), "application/octet-stream")
            part_bytes.append((filename_part, len(encoded)))

        expected_attachment_size = sum(size for _, size in part_bytes)
        num_files = len(part_bytes)
        bytes_enviados += expected_attachment_size

        if lote_idx == 1:
            payload_content = f"{item_id}|{total_parts}|{original_hash}"
        else:
            payload_content = f"{item_id}|{total_parts}"

        success = False
        for attempt in range(5):
            resp = api_call("POST",
                f"{BASE_URL}/channels/{current_channel}/messages",
                data={"payload_json": json.dumps({"content": payload_content})},
                files=files_dict,
                custom_headers=UPLOAD_HEADERS
            )
            if resp.ok:
                msg_data = resp.json()
                msg_id = msg_data["id"]
                if validate_message(current_channel, msg_id, num_files, expected_attachment_size):
                    part_indexes = list(range((lote_idx-1)*MAX_ATTACHMENTS_PER_MSG,
                                              min(lote_idx*MAX_ATTACHMENTS_PER_MSG, total_parts)))
                    message_refs.append({
                        "channel_id": current_channel,
                        "message_id": msg_id,
                        "part_indexes": part_indexes
                    })
                    success = True
                    break
                else:
                    print(f"    [!] Mensagem {msg_id} não validada. Removendo...")
                    api_call("DELETE", f"{BASE_URL}/channels/{current_channel}/messages/{msg_id}")
                    time.sleep(1)
            else:
                print(f"    [!] Erro {resp.status_code} (tentativa {attempt+1})")
                time.sleep(1)

        if not success:
            print(f"  [!!!] Falha ao enviar lote {lote_idx} após 5 tentativas.")
            return None

        elapsed = time.time() - start_time
        velocidade = bytes_enviados / elapsed if elapsed > 0 else 0
        pct = (lote_idx / total_lotes) * 100
        eta_str = ""
        if lote_idx > 1:
            eta = (elapsed / (lote_idx-1)) * (total_lotes - lote_idx)
            eta_str = f" | ETA: {int(eta//60)}m{int(eta%60)}s"
        print(f"  [{lote_idx}/{total_lotes}] {pct:.0f}% {label} | "
              f"{format_size(bytes_enviados)} enviados @ {format_size(velocidade)}/s{eta_str}")

        count = metadata["channels"].get(current_channel, {}).get("message_count", 0)
        if count >= MAX_MSGS_PER_CHANNEL - 1:
            current_channel = get_active_channel(metadata)
        else:
            metadata["channels"][current_channel]["message_count"] = count + 1
            save_metadata(metadata)

        time.sleep(0.5)

    return {
        "size_bytes": original_size,
        "parts": total_parts,
        "messages": message_refs,
        "hash": original_hash,
        "compressed": True
    }

def upload_single_file(filepath, metadata=None):
    if metadata is None:
        metadata = load_metadata()
    if not os.path.isfile(filepath):
        print("  [!] Arquivo não encontrado.")
        return False

    filename = os.path.basename(filepath)
    item_id = generate_item_id(metadata, "1")
    print(f"[*] Enviando '{filename}' como {item_id}")

    with open(filepath, "rb") as f:
        raw = f.read()
    created = os.path.getctime(filepath)
    export_time = datetime.now(timezone.utc).isoformat()

    upload_info = _do_upload_item(item_id, raw, metadata, label=f"({filename})")
    if upload_info is None:
        print("  [!] Falha no envio. Item não registrado.")
        return False

    metadata["items"][item_id] = {
        "id": item_id,
        "type": "file",
        "name": filename,
        "size_bytes": len(raw),
        "created_at": datetime.fromtimestamp(created, tz=timezone.utc).isoformat(),
        "exported_at": export_time,
        "parts": upload_info["parts"],
        "messages": upload_info["messages"],
        "hash": upload_info["hash"],
        "compressed": True,
        "parent_id": None,
        "is_tar": False
    }
    save_metadata(metadata)
    print(f"  [✓] {item_id} armazenado com sucesso.")
    return True

def upload_folder(folder_path, metadata=None):
    if metadata is None:
        metadata = load_metadata()
    if not os.path.isdir(folder_path):
        print("  [!] Pasta inválida.")
        return False

    folder_name = os.path.basename(folder_path.rstrip(os.sep))
    base_letter = _int_to_excel_col(metadata.get("next_group_index", 0))
    metadata["next_group_index"] = metadata.get("next_group_index", 0) + 1
    save_metadata(metadata)
    item_id = generate_item_id(metadata, "0", base_letter)

    print(f"[*] Compactando pasta '{folder_name}' em .tar...")
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        tar.add(folder_path, arcname=folder_name)
    raw = tar_buffer.getvalue()
    print(f"  [*] Tamanho do .tar: {format_size(len(raw))}")

    created = os.path.getctime(folder_path)
    export_time = datetime.now(timezone.utc).isoformat()

    upload_info = _do_upload_item(item_id, raw, metadata, label=f"({folder_name}.tar)")
    if upload_info is None:
        print("  [!] Falha no envio do .tar. Item não registrado.")
        return False

    metadata["items"][item_id] = {
        "id": item_id,
        "type": "file",
        "name": folder_name + ".tar",
        "size_bytes": len(raw),
        "created_at": datetime.fromtimestamp(created, tz=timezone.utc).isoformat(),
        "exported_at": export_time,
        "parts": upload_info["parts"],
        "messages": upload_info["messages"],
        "hash": upload_info["hash"],
        "compressed": True,
        "parent_id": None,
        "is_tar": True,
        "original_folder_name": folder_name
    }
    save_metadata(metadata)
    print(f"  [✓] Pasta '{folder_name}' enviada como {item_id}")
    return True

# ---------- DOWNLOAD PARALELO ----------
def _download_raw_parallel(item):
    parts_dict = {}
    urls = {}
    # Coleta todas as mensagens primeiro para obter URLs
    for msg_ref in item["messages"]:
        resp = api_call("GET", f"{BASE_URL}/channels/{msg_ref['channel_id']}/messages/{msg_ref['message_id']}")
        if not resp.ok:
            continue
        attachments = resp.json().get("attachments", [])
        for att in attachments:
            if ".part" in att["filename"] and att["filename"].endswith(".b64"):
                try:
                    num_str = att["filename"].split(".part")[1].split(".b64")[0]
                    part_idx = int(num_str) - 1
                    urls[part_idx] = att["url"]
                except:
                    pass

    if len(urls) != item["parts"]:
        return None

    # Download paralelo
    def fetch_part(idx_url):
        idx, url = idx_url
        try:
            r = requests.get(url, timeout=30)
            if r.ok:
                return idx, r.text
        except:
            pass
        return idx, None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_part, (idx, url)) for idx, url in urls.items()]
        for future in as_completed(futures):
            idx, text = future.result()
            if text is not None:
                parts_dict[idx] = text

    if len(parts_dict) != item["parts"]:
        return None
    b64_full = "".join(parts_dict[i] for i in range(item["parts"]))
    try:
        compressed = base64.b64decode(b64_full)
    except Exception:
        return None
    # Descompressão
    try:
        raw = zlib.decompress(compressed)
    except Exception:
        return None
    # Verificação de hash
    if "hash" in item:
        if hashlib.sha256(raw).hexdigest() != item["hash"]:
            print("  [!] Hash não confere! Dados corrompidos.")
            return None
    return raw

def download_item(item_id, metadata):
    if item_id not in metadata["items"]:
        print(f"  [!] Item {item_id} não encontrado.")
        return

    item = metadata["items"][item_id]
    print(f"[*] Baixando '{item.get('original_folder_name', item['name'])}'...")
    raw = _download_raw_parallel(item)
    if raw is None:
        print(f"  [!] Falha ao obter dados. Removendo item corrompido: {item_id}")
        del metadata["items"][item_id]
        save_metadata(metadata)
        return

    if item.get("is_tar"):
        try:
            with tarfile.open(fileobj=BytesIO(raw)) as tar:
                os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(path=DOWNLOAD_FOLDER, filter="data")
                else:
                    tar.extractall(path=DOWNLOAD_FOLDER)
            print(f"  [✓] Pasta extraída em '{DOWNLOAD_FOLDER}'.")
        except tarfile.ReadError as e:
            print(f"  [!] Erro ao ler .tar: {e}")
    else:
        save_path = os.path.join(DOWNLOAD_FOLDER, item["name"])
        with open(save_path, "wb") as f:
            f.write(raw)
        print(f"  [✓] Salvo como {save_path} ({format_size(len(raw))})")

# ---------- LISTAGEM ----------
def list_items():
    metadata = load_metadata()
    items = metadata.get("items", {})
    if not items:
        print("Nenhum item armazenado.")
        return
    print("\n📁 Itens Armazenados:")
    for iid, it in sorted(items.items()):
        if it.get("is_tar"):
            size_str = format_size(it["size_bytes"])
            print(f"  {iid} - Pasta: {it['original_folder_name']} (.tar, {size_str})")
        else:
            size_str = format_size(it["size_bytes"])
            print(f"  {iid} - Arquivo: {it['name']} ({size_str})")

# ---------- BULK DELETE ----------
def delete_all_messages_fast(channel_id):
    total = 0
    while True:
        resp = api_call("GET", f"{BASE_URL}/channels/{channel_id}/messages?limit=100")
        if not resp.ok:
            break
        msgs = resp.json()
        if not msgs:
            break
        now = datetime.now(timezone.utc)
        bulk_ids = []
        for msg in msgs:
            try:
                msg_time = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
                if (now - msg_time).days < 14:
                    bulk_ids.append(msg["id"])
                else:
                    api_call("DELETE", f"{BASE_URL}/channels/{channel_id}/messages/{msg['id']}")
                    total += 1
                    time.sleep(0.2)
            except:
                pass
        if bulk_ids:
            if len(bulk_ids) == 1:
                api_call("DELETE", f"{BASE_URL}/channels/{channel_id}/messages/{bulk_ids[0]}")
                total += 1
            else:
                resp_bulk = api_call("POST", f"{BASE_URL}/channels/{channel_id}/messages/bulk-delete",
                                     json={"messages": bulk_ids})
                if resp_bulk.ok:
                    total += len(bulk_ids)
                else:
                    for mid in bulk_ids:
                        api_call("DELETE", f"{BASE_URL}/channels/{channel_id}/messages/{mid}")
                        total += 1
                        time.sleep(0.2)
            time.sleep(0.5)
        else:
            break
    return total

def nuclear_reset():
    metadata = load_metadata()
    code = random.randint(100_000_000, 999_999_999)
    print(f"\n  ⚠️  CÓDIGO DE CONFIRMAÇÃO: {code}")
    user_input = input("  Digite o código para APAGAR TUDO: ").strip()
    if user_input != str(code):
        print("  [!] Código incorreto.")
        return

    resp = api_call("GET", f"{BASE_URL}/guilds/{GUILD_ID}/channels")
    if not resp.ok:
        print(f"  [!] Erro ao listar canais: {resp.status_code}")
        return

    keep_id = str(INITIAL_CHANNEL_ID)
    deleted = 0
    for ch in resp.json():
        if ch["type"] != 0 or str(ch["id"]) == keep_id:
            continue
        if not ch.get("name", "").startswith(CHANNEL_PREFIX):
            continue
        print(f"  [*] Apagando canal #{ch['name']} ({ch['id']})...")
        if api_call("DELETE", f"{BASE_URL}/channels/{ch['id']}").ok:
            deleted += 1
        time.sleep(0.3)

    print(f"\n  [-] Canais de armazenamento removidos: {deleted}")
    limpar = input("  [?] Limpar também o canal inicial? (s/N): ").strip().lower()
    if limpar == 's':
        print("  [*] Removendo mensagens do canal inicial...")
        removed = delete_all_messages_fast(str(INITIAL_CHANNEL_ID))
        print(f"  [+] {removed} mensagens removidas.")

    metadata["items"] = {}
    metadata["channels"] = {keep_id: {"name": "initial", "message_count": 0}}
    metadata["active_channel"] = keep_id
    metadata["next_channel_number"] = 1
    metadata["next_group_index"] = 0
    save_metadata(metadata)
    print("  [✓] Metadata resetado.")

# ---------- MENU ----------
def main():
    if not TOKEN:
        print("Erro: TOKEN não encontrado no .env")
        sys.exit(1)

    print("[*] Verificando conexão com o Discord...")
    if not verify_bot_access():
        sys.exit(1)

    print("\n╔══════════════════════════════════════╗")
    print("║   Discord Infinite Storage v10.0    ║")
    print("║   EXTREME: compressão + paralelo   ║")
    print("╚══════════════════════════════════════╝")

    while True:
        print("\n  1 - Enviar arquivo único")
        print("  2 - Enviar pasta inteira (compactada)")
        print("  3 - Listar todos os itens")
        print("  4 - Baixar item (pelo ID)")
        print("  5 - Reset nuclear")
        print("  0 - Sair")
        choice = input("\nEscolha: ").strip()
        if not choice:
            continue
        if choice == "1":
            path = select_file_dialog()
            if path and os.path.isfile(path):
                upload_single_file(path)
        elif choice == "2":
            folder = select_folder_dialog()
            if folder and os.path.isdir(folder):
                upload_folder(folder)
        elif choice == "3":
            list_items()
        elif choice == "4":
            list_items()
            code = input("\nID do item: ").strip()
            if code:
                download_item(code, load_metadata())
        elif choice == "5":
            nuclear_reset()
        elif choice == "0":
            print("Saindo...")
            break
        else:
            print("  [!] Opção inválida.")

if __name__ == "__main__":
    main()