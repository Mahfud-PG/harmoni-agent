import os
import requests

def kirim_pesan_telegram(pesan: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return "Gagal: Token atau Chat ID Telegram tidak ditemukan."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": pesan, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload)
        return "Berhasil dikirim ke Telegram." if res.status_code == 200 else f"Gagal: {res.text}"
    except Exception as e:
        return f"Error: {e}"

def kirim_file_telegram(path_file: str, caption: str = ""):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return "Gagal: Token atau Chat ID Telegram tidak ditemukan."
    if not os.path.exists(path_file):
        return f"Gagal: File {path_file} tidak ditemukan."
    try:
        ukuran_mb = os.path.getsize(path_file) / (1024 * 1024)
        if ukuran_mb > 49:
            return f"Gagal mengirim: Ukuran file {ukuran_mb:.1f} MB terlalu besar (Maks Telegram 50MB)."
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(path_file, 'rb') as doc:
            files = {'document': doc}
            data = {'chat_id': chat_id, 'caption': caption}
            res = requests.post(url, files=files, data=data)
        return f"Berhasil mengirim file {os.path.basename(path_file)} ke Telegram." if res.status_code == 200 else f"Gagal: {res.text}"
    except Exception as e:
        return f"Error: {e}"
