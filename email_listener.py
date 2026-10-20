import os
import sys
import time
import json
import logging
import asyncio
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from dotenv import load_dotenv

CURRENT_DIR = Path(__file__).parent.resolve()
# PENTING: folder program harus masuk sys.path DULU. Pada Python tertanam
# (yang memakai berkas ._pth), folder skrip tidak otomatis ikut sys.path.
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from sari_core.paths import DATA_ROOT  # folder data pengguna (bisa beda dari folder program)
AI_ASISTEN_DIR = DATA_ROOT

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

load_dotenv(DATA_ROOT / ".env")

logger = logging.getLogger("HarmoniEmailBridge")

CONFIG_EMAIL_FILE = DATA_ROOT / "konfigurasi_email.json"
CONFIG_YT_FILE = DATA_ROOT / "konfigurasi_youtube.json"

def baca_konfigurasi_email() -> dict:
    if CONFIG_EMAIL_FILE.exists():
        try:
            with open(CONFIG_EMAIL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"admin_email_enabled": False, "notify_telegram": True}

def simpan_konfigurasi_email(data: dict):
    try:
        with open(CONFIG_EMAIL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Gagal simpan konfigurasi email: {e}")

def baca_konfigurasi_youtube() -> dict:
    if CONFIG_YT_FILE.exists():
        try:
            with open(CONFIG_YT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"satpam_youtube_enabled": False, "notify_telegram": True}

def simpan_konfigurasi_youtube(data: dict):
    try:
        with open(CONFIG_YT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Gagal simpan konfigurasi youtube: {e}")

def decode_mime_words(s):
    if not s:
        return ""
    res = ""
    for word, encoding in decode_header(s):
        if isinstance(word, bytes):
            try:
                res += word.decode(encoding or "utf-8", errors="ignore")
            except Exception:
                res += word.decode("latin-1", errors="ignore")
        else:
            res += str(word)
    return res

async def kirim_notif_telegram_async(pesan: str, reply_markup: dict = None):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        import requests
        payload = {"chat_id": chat_id, "text": pesan[:4000], "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=8)
    except Exception as e:
        logger.warning(f"Gagal kirim notif Telegram dari Email/YT: {e}")

_LAST_SEEN_EMAIL_ID = None

async def periksa_email_masuk_sekali_async():
    """Memeriksa email baru via IMAP dan menangani notifikasi atau balasan otomatis."""
    global _LAST_SEEN_EMAIL_ID
    cfg = baca_konfigurasi_email()
    admin_enabled = cfg.get("admin_email_enabled", False)
    notify_tg = cfg.get("notify_telegram", True)

    if not admin_enabled and not notify_tg:
        return

    email_user = os.getenv("EMAIL_ADDRESS")
    email_pass = os.getenv("EMAIL_APP_PASSWORD")
    if not email_user or not email_pass:
        return

    try:
        def _fetch_unread():
            m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=12)
            m.login(email_user, email_pass)
            m.select("INBOX")
            status, messages_id = m.search(None, "(UNSEEN)")
            if status != "OK" or not messages_id or not messages_id[0]:
                m.logout()
                return None, None, None, None
            ids = messages_id[0].split()
            if not ids:
                m.logout()
                return None, None, None, None
            latest_id = ids[-1].decode("utf-8") if isinstance(ids[-1], bytes) else str(ids[-1])
            status_f, msg_data = m.fetch(latest_id, "(RFC822)")
            m.logout()
            if status_f != "OK" or not msg_data or not msg_data[0]:
                return latest_id, None, None, None
            msg_obj = email.message_from_bytes(msg_data[0][1])
            return latest_id, msg_obj, None, None

        latest_id, msg_obj, _, _ = await asyncio.to_thread(_fetch_unread)
        if not latest_id or not msg_obj:
            return

        if _LAST_SEEN_EMAIL_ID is None:
            # Inisialisasi awal saat bot baru start: catat ID terakhir agar tidak spam email lama
            _LAST_SEEN_EMAIL_ID = latest_id
            return

        if latest_id == _LAST_SEEN_EMAIL_ID:
            return

        _LAST_SEEN_EMAIL_ID = latest_id

        sender_raw = decode_mime_words(msg_obj.get("From", ""))
        subject = decode_mime_words(msg_obj.get("Subject", "Tanpa Subjek"))

        # Ekstrak alamat email bersih
        import re
        match_addr = re.search(r"<([^>]+)>", sender_raw)
        sender_email = match_addr.group(1) if match_addr else sender_raw.strip()

        # Abaikan notifikasi sistem atau medsos otomatis jika diinginkan
        sender_lower = sender_raw.lower()
        if any(ign in sender_lower for ign in ["no-reply", "noreply", "facebook", "mailer-daemon"]):
            return

        # Ekstrak cuplikan body
        body_snippet = ""
        if msg_obj.is_multipart():
            for part in msg_obj.walk():
                if part.get_content_type() == "text/plain" and not body_snippet:
                    try:
                        body_snippet = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    except Exception:
                        pass
        else:
            try:
                body_snippet = msg_obj.get_payload(decode=True).decode(msg_obj.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                body_snippet = str(msg_obj.get_payload())

        clean_snippet = body_snippet.strip()[:250].replace("\n", " ")

        logger.info(f"[Email Masuk] Dari: {sender_raw} | Subjek: {subject}")

        # 1. Balas Otomatis AI (Admin Email)
        balasan_ai = ""
        if admin_enabled:
            try:
                from sari_core.bridge import process_email_message_async
                from bot_otomatis import kirim_email
                balasan_ai = await process_email_message_async(sender_email, subject, body_snippet)
                if balasan_ai:
                    await asyncio.to_thread(kirim_email, sender_email, f"Re: {subject}", balasan_ai)
                    logger.info(f"[Admin Email] Berhasil membalas email ke {sender_email}.")
            except Exception as e_reply:
                logger.error(f"[Admin Email] Gagal balas otomatis: {e_reply}")

        # 2. Notifikasi ke Telegram
        if notify_tg:
            pesan_notif = (
                f"📧 **EMAIL BARU MASUK!**\n\n"
                f"👤 **Dari:** {sender_raw}\n"
                f"📑 **Subjek:** {subject}\n"
                f"💬 **Isi:** {clean_snippet}...\n"
            )
            if admin_enabled and balasan_ai:
                pesan_notif += f"\n🤖 **Balasan Otomatis AI Terkirim:**\n_{balasan_ai[:200]}..._\n"

            kb = None
            try:
                from sari_core.quick_reply_broker import register_reply_target
                rid = register_reply_target(channel="email", to=sender_email, name=sender_raw, subject=subject)
                kb = {
                    "inline_keyboard": [
                        [{"text": f"✉️ Balas Email ({sender_email[:25]})", "callback_data": f"qr_act:{rid}"}]
                    ]
                }
            except Exception as e_kb:
                logger.warning(f"Gagal buat tombol balas email: {e_kb}")

            await kirim_notif_telegram_async(pesan_notif, reply_markup=kb)

    except Exception as e_poll:
        logger.warning(f"Error polling email: {e_poll}")

async def email_listener_loop():
    """Loop berkala pengecekan email masuk setiap 120 detik."""
    logger.info("Harmoni Email Listener mulai berjalan (interval 120 detik)...")
    await asyncio.sleep(10)
    while True:
        try:
            await periksa_email_masuk_sekali_async()
        except Exception as e:
            logger.error(f"Error pada loop email listener: {e}")
        await asyncio.sleep(120)

_LAST_SEEN_YT_COMMENTS = set()

async def periksa_youtube_komentar_sekali_async():
    """Memeriksa komentar baru di channel YouTube dan memberi notifikasi ke Telegram."""
    global _LAST_SEEN_YT_COMMENTS
    cfg = baca_konfigurasi_youtube()
    satpam_enabled = cfg.get("satpam_youtube_enabled", False)
    notify_tg = cfg.get("notify_telegram", True)

    if not satpam_enabled and not notify_tg:
        return

    token_file = DATA_ROOT / "token_utama.json"
    if not token_file.exists():
        return

    try:
        from youtube_api import get_authenticated_service, get_comments
        def _get_yt():
            try:
                srv = get_authenticated_service("utama")
                return get_comments(srv, max_results=5)
            except Exception as e:
                return f"Error: {e}"

        komen_txt = await asyncio.to_thread(_get_yt)
        if not komen_txt or "Belum ada" in komen_txt or "Error" in komen_txt:
            return

        import hashlib
        h = hashlib.md5(komen_txt.encode("utf-8")).hexdigest()
        if not _LAST_SEEN_YT_COMMENTS:
            _LAST_SEEN_YT_COMMENTS.add(h)
            return

        if h not in _LAST_SEEN_YT_COMMENTS:
            _LAST_SEEN_YT_COMMENTS.add(h)
            if notify_tg:
                pesan_yt = f"🔴 **KOMENTAR BARU DI YOUTUBE!**\n\n{komen_txt}"
                await kirim_notif_telegram_async(pesan_yt)

    except Exception as e_yt:
        logger.warning(f"Error periksa komentar YouTube: {e_yt}")

async def youtube_listener_loop():
    """Loop berkala pengecekan komentar YouTube setiap 4 jam (14400 detik)."""
    logger.info("Harmoni YouTube Comment Watcher mulai berjalan (interval 4 jam)...")
    await asyncio.sleep(30)
    while True:
        try:
            await periksa_youtube_komentar_sekali_async()
        except Exception as e:
            logger.error(f"Error pada loop youtube listener: {e}")
        await asyncio.sleep(14400)
