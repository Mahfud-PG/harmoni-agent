import os
import sys
import time
import json
import logging
import asyncio
import urllib.request
import urllib.parse
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

logger = logging.getLogger("HarmoniWABridge")

def ensure_wa_node_bridge():
    """Memastikan service Node.js Baileys wa_bridge menyala di background."""
    try:
        req = urllib.request.Request("http://localhost:3000/status")
        with urllib.request.urlopen(req, timeout=1.5) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    wa_dir = CURRENT_DIR / "wa_bridge"
    if (wa_dir / "wa_bridge.js").exists():
        logger.info("Menyalakan service Node.js WhatsApp Bridge...")
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        from sari_core.paths import cari_node, env_bridge
        subprocess.Popen([cari_node(), "wa_bridge.js"], cwd=str(wa_dir), creationflags=flags,
                         env=env_bridge())
        for _ in range(12):
            time.sleep(1)
            try:
                with urllib.request.urlopen("http://localhost:3000/status", timeout=1.5) as r:
                    if r.status == 200:
                        logger.info("WhatsApp Bridge Node.js online.")
                        return True
            except Exception:
                pass
    return False

def transkripsi_voice_note(audio_path: str) -> str:
    """Mengubah rekaman suara Voice Note menjadi teks menggunakan Gemini / Groq Whisper."""
    if not audio_path or not os.path.exists(audio_path):
        return ""
    
    # 1. Coba Gemini Flash
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            uploaded_audio = genai.upload_file(path=audio_path)
            model_vn = genai.GenerativeModel("gemini-2.5-flash")
            resp = model_vn.generate_content([
                uploaded_audio,
                "Transkripsikan audio rekaman suara ini kata demi kata secara presisi dalam bahasa aslinya. Hanya keluarkan teks transkripsinya saja."
            ])
            try:
                uploaded_audio.delete()
            except Exception:
                pass
            if resp and resp.text and resp.text.strip():
                return resp.text.strip()
        except Exception as e_gem:
            logger.warning(f"Transkripsi Gemini error: {e_gem}")

    # 2. Coba Groq Whisper
    groq_key = os.getenv("GROQ_API_KEY_1") or os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client_g = Groq(api_key=groq_key)
            with open(audio_path, "rb") as f:
                res_g = client_g.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f.read()),
                    model="whisper-large-v3-turbo"
                )
            if res_g and hasattr(res_g, "text") and res_g.text.strip():
                return res_g.text.strip()
        except Exception as e_grq:
            logger.warning(f"Transkripsi Groq error: {e_grq}")

    return ""

def kirim_notif_telegram(pesan: str, reply_markup: dict = None):
    """Mengirim ringkasan laporan aktivitas WhatsApp langsung ke Telegram pengguna."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = {
            "chat_id": chat_id,
            "text": pesan,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            body["reply_markup"] = reply_markup
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error(f"Gagal kirim notif Telegram: {e}")

def baca_semua_profil_wa() -> dict:
    """Membaca seluruh profil nomor WhatsApp (multi-nomor) dari konfigurasi.

    Urutan: konfigurasi_multi_wa.json -> konfigurasi_wa.json (berkas lama) -> kosong.
    """
    multi_file = DATA_ROOT / "konfigurasi_multi_wa.json"
    cfg_file = DATA_ROOT / "konfigurasi_wa.json"

    if multi_file.exists():
        try:
            with open(multi_file, "r", encoding="utf-8") as mf:
                m_all = json.load(mf)
            profiles = m_all.get("profiles", {}) or {}
            if profiles:
                return profiles
        except Exception as e:
            logger.warning(f"Gagal membaca konfigurasi_multi_wa.json: {e}")

    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return {"nomor_1": json.load(f)}
        except Exception as e:
            logger.warning(f"Gagal membaca konfigurasi_wa.json: {e}")

    return {}


def _ambil_pesan_profil(profile_id: str) -> list:
    """Menarik antrean pesan masuk khusus satu profil nomor WhatsApp."""
    try:
        url = f"http://localhost:3000/messages?profile={urllib.parse.quote(profile_id)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data if isinstance(data, list) else []
    except Exception:
        return []


_sent_attachments_cache = {}
_auto_reply_cooldown = {}


def _is_outside_business_hours(jam_buka: str, jam_tutup: str) -> bool:
    """Memeriksa apakah waktu saat ini berada di luar jam operasional bisnis."""
    try:
        now = time.localtime()
        cur_min = now.tm_hour * 60 + now.tm_min
        b_jam, b_menit = [int(x) for x in (jam_buka or "09:00").split(":")[:2]]
        t_jam, t_menit = [int(x) for x in (jam_tutup or "18:00").split(":")[:2]]
        open_min = b_jam * 60 + b_menit
        close_min = t_jam * 60 + t_menit
        if open_min <= close_min:
            return cur_min < open_min or cur_min >= close_min
        else:
            return not (cur_min >= open_min or cur_min < close_min)
    except Exception:
        return False


def _resolve_attachment_path(fpath: str) -> str:
    """Mencari jalur berkas lampiran yang valid (termasuk bila ada jalur warisan)."""
    if not fpath:
        return ""
    if os.path.exists(fpath):
        return fpath
    fname = Path(fpath).name
    kandidat = [
        DATA_ROOT / "File" / "Lampiran_WA" / fname,
        DATA_ROOT / "File" / "Temp" / fname,
        DATA_ROOT / "File" / fname,
    ]
    for k in kandidat:
        if k.exists():
            return str(k)
    return ""

def _kirim_balasan_wa(profile_id: str, nomor: str, pesan: str) -> bool:
    """Mengirim balasan WA memakai sesi nomor (profil) yang benar."""
    try:
        req_send = urllib.request.Request(
            "http://localhost:3000/send",
            data=json.dumps({"number": nomor, "message": pesan, "profile": profile_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req_send, timeout=30)
        return True
    except Exception as e:
        logger.error(f"[WA Error][{profile_id}] Gagal mengirim balasan ke {nomor}: {e}")
        return False


def _kirim_media_wa(profile_id: str, nomor: str, file_path: str, caption: str = "") -> bool:
    """Mengirim file media/lampiran ke klien memakai sesi nomor WhatsApp yang benar."""
    try:
        req_send = urllib.request.Request(
            "http://localhost:3000/send-media",
            data=json.dumps({
                "number": nomor,
                "filePath": file_path,
                "caption": caption or "",
                "profile": profile_id
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req_send, timeout=40)
        return True
    except Exception as e:
        logger.error(f"[WA Media Error][{profile_id}] Gagal mengirim lampiran {file_path} ke {nomor}: {e}")
        return False


async def wa_listener_loop():
    """Loop multi-nomor: tiap profil WA punya identitas, sakelar, dan sesi sendiri."""
    ensure_wa_node_bridge()
    hitungan_putaran = 0

    while True:
        try:
            # Jaga-jaga: bila service Node mati (mis. dibunuh manual), nyalakan ulang berkala
            hitungan_putaran += 1
            if hitungan_putaran % 8 == 0:
                try:
                    with urllib.request.urlopen("http://localhost:3000/status", timeout=1.5) as r_cek:
                        if r_cek.status != 200:
                            ensure_wa_node_bridge()
                except Exception:
                    logger.warning("Service WhatsApp Bridge terputus. Menyalakan ulang...")
                    ensure_wa_node_bridge()

            profil_semua = baca_semua_profil_wa()

            for pid, pdata in profil_semua.items():
                admin_enabled = pdata.get("admin_wa_enabled", True)
                notify_tg = pdata.get("notify_telegram", True)
                auto_stt = pdata.get("auto_transcribe_vn", True)
                nama_usaha = pdata.get("business_name") or pdata.get("label") or pid
                nomor_usaha = pdata.get("target_phone", "")
                vips = pdata.get("vip_numbers", "") or ""
                vip_list = [v.strip() for v in vips.replace(";", ",").split(",") if v.strip()]

                pesan_masuk = _ambil_pesan_profil(pid)

                for msg in pesan_masuk:
                    pengirim = str(msg.get('from', '')).strip()
                    nama = msg.get('name', 'Klien')
                    isi_pesan = msg.get('body', '')
                    is_group = msg.get('isGroup', False)
                    is_vn = msg.get('isVoiceNote', False)
                    v_path = msg.get('voicePath')

                    # Abaikan pesan grup WA
                    if is_group:
                        continue

                    # ANTI-LOOP: Jangan balas pesan dari nomor profil sendiri di sistem
                    is_nomor_sendiri = False
                    for _p in profil_semua.values():
                        tp = str(_p.get("target_phone", "")).strip()
                        tp_clean = "".join([c for c in tp if c.isdigit()])
                        if tp_clean and tp_clean in pengirim:
                            is_nomor_sendiri = True
                            break
                        if tp_clean.startswith("62") and ("0" + tp_clean[2:]) in pengirim:
                            is_nomor_sendiri = True
                            break
                    if is_nomor_sendiri:
                        logger.info(f"[Anti-Loop] Mengabaikan pesan dari profil sendiri ({pengirim}) pada profil {pid}.")
                        continue

                    # 1. Transkripsi otomatis Voice Note klien
                    transkrip_info = ""
                    if is_vn and v_path and auto_stt:
                        logger.info(f"[WA VN][{pid}] Mentranskripsi Voice Note dari {nama}...")
                        teks_vn = transkripsi_voice_note(v_path)
                        if teks_vn:
                            transkrip_info = teks_vn
                            isi_pesan = f"[Klien Mengirim Pesan Suara / Voice Note]: \"{teks_vn}\""
                        else:
                            isi_pesan = "[Klien Mengirim Voice Note, audio belum berhasil ditranskrip]"

                    logger.info(f"[WA Masuk][{pid} | {nama_usaha}] Dari: {nama} ({pengirim}) - Pesan: {isi_pesan}")

                    # Helper untuk tombol balas cepat Telegram
                    def _buat_tombol_balas_wa():
                        try:
                            from sari_core.quick_reply_broker import register_reply_target
                            target_to = msg.get("senderNumber") or pengirim
                            rid = register_reply_target(channel="whatsapp", to=target_to, name=nama, profile_id=pid)
                            return {"inline_keyboard": [[{"text": f"💬 Balas WA ({nama[:20]})", "callback_data": f"qr_act:{rid}"}]]}
                        except Exception:
                            return None

                    # -------------------------------------------------------------
                    # A. JAWABAN KILAT (KATA KUNCI INSTAN TANPA LLM)
                    # -------------------------------------------------------------
                    quick_replies = pdata.get("quick_replies", []) or []
                    pesan_lower = isi_pesan.lower()
                    matched_qr = None
                    if quick_replies:
                        for qr in quick_replies:
                            raw_kws = qr.get("keywords", "") or ""
                            kws = [k.strip().lower() for k in raw_kws.replace(";", ",").split(",") if k.strip()]
                            if kws and any(k in pesan_lower for k in kws):
                                matched_qr = qr
                                break

                    if matched_qr:
                        qr_reply = matched_qr.get("reply", "").strip()
                        if qr_reply:
                            _kirim_balasan_wa(pid, pengirim, qr_reply)
                            logger.info(f"[WA Quick Reply][{pid}] Terkirim ke {pengirim}: {qr_reply[:80]}...")
                            if notify_tg:
                                tipe_pesan = "🎤 *Voice Note*" if is_vn else "💬 *Teks*"
                                rekap_msg = (
                                    f"⚡ *[JAWABAN KILAT WHATSAPP]*\n"
                                    f"📱 *Nomor:* {nama_usaha} ({nomor_usaha or '-'})\n"
                                    f"👤 *Klien:* {nama} (`{pengirim}`)\n"
                                    f"📩 *Tipe:* {tipe_pesan}\n"
                                    f"💬 *Pesan:* \"{transkrip_info or isi_pesan}\"\n\n"
                                    f"⚡ *Balasan Kilat (Tanpa AI):* \"{qr_reply}\""
                                )
                                kirim_notif_telegram(rekap_msg, reply_markup=_buat_tombol_balas_wa())
                            continue

                    # -------------------------------------------------------------
                    # B. MODE SIBUK & DI LUAR JAM KERJA (AUTO-REPLY COOLDOWN)
                    # -------------------------------------------------------------
                    auto_reply_mode = pdata.get("auto_reply_mode", "off")
                    auto_reply_text = pdata.get("auto_reply_text", "")
                    open_hr = pdata.get("business_hours_open", "09:00")
                    close_hr = pdata.get("business_hours_close", "18:00")

                    is_busy = False
                    busy_label = ""
                    if auto_reply_mode == "always":
                        is_busy = True
                        busy_label = "Mode Sibuk / Istirahat"
                    elif auto_reply_mode == "outside_hours" and _is_outside_business_hours(open_hr, close_hr):
                        is_busy = True
                        busy_label = f"Di Luar Jam Kerja ({open_hr} - {close_hr})"

                    if is_busy:
                        now_ts = time.time()
                        cooldown_sec = int(pdata.get("auto_reply_cooldown_menit", 15)) * 60
                        cache_key = f"{pid}:{pengirim}"
                        last_sent = _auto_reply_cooldown.get(cache_key, 0)
                        if now_ts - last_sent > cooldown_sec:
                            _auto_reply_cooldown[cache_key] = now_ts
                            teks_balas = auto_reply_text.strip() or f"Halo! Saat ini kami sedang {busy_label.lower()}. Pesan Kakak akan segera kami balas."
                            _kirim_balasan_wa(pid, pengirim, teks_balas)
                            logger.info(f"[WA Auto-Reply][{pid}] ({busy_label}) Terkirim ke {pengirim}: {teks_balas[:80]}...")
                            if notify_tg:
                                tipe_pesan = "🎤 *Voice Note*" if is_vn else "💬 *Teks*"
                                rekap_msg = (
                                    f"🌙 *[AUTO-REPLY WHATSAPP ({busy_label})]*\n"
                                    f"📱 *Nomor:* {nama_usaha} ({nomor_usaha or '-'})\n"
                                    f"👤 *Klien:* {nama} (`{pengirim}`)\n"
                                    f"📩 *Tipe:* {tipe_pesan}\n"
                                    f"💬 *Pesan:* \"{transkrip_info or isi_pesan}\"\n\n"
                                    f"🤖 *Balasan Otomatis:* \"{teks_balas}\""
                                )
                                kirim_notif_telegram(rekap_msg, reply_markup=_buat_tombol_balas_wa())
                        else:
                            logger.info(f"[WA Auto-Reply][{pid}] Cooldown aktif untuk {pengirim}, tidak mengirim pesan auto-reply berulang.")
                        continue

                    # -------------------------------------------------------------
                    # C. SAKELAR ADMIN AI AKTIF / NONAKTIF
                    # -------------------------------------------------------------
                    if not admin_enabled:
                        logger.info(f"[WA {pid}] Admin AI nonaktif. Pesan dicatat tanpa balasan.")
                        if notify_tg:
                            tipe_pesan = "🎤 *Voice Note*" if is_vn else "💬 *Teks*"
                            rekap_msg = (
                                f"🔔 *[PESAN WHATSAPP MASUK (AI Nonaktif)]*\n"
                                f"📱 *Nomor:* {nama_usaha} ({nomor_usaha or '-'})\n"
                                f"👤 *Klien:* {nama} (`{pengirim}`)\n"
                                f"📩 *Tipe:* {tipe_pesan}\n"
                                f"💬 *Pesan:* \"{transkrip_info or isi_pesan}\""
                            )
                            kirim_notif_telegram(rekap_msg, reply_markup=_buat_tombol_balas_wa())
                        continue

                    try:
                        from sari_core.bridge import process_wa_message_async
                        balasan = await process_wa_message_async(pengirim, nama, isi_pesan, profile_id=pid)
                        _kirim_balasan_wa(pid, pengirim, balasan)
                        logger.info(f"[WA Terkirim][{pid}] Balasan ke {pengirim}: {balasan[:80]}...")

                        # 2. Cek berkas lampiran siap kirim berdasarkan pemicu kata kunci
                        attachments = pdata.get("attachments", []) or []
                        if attachments:
                            now_ts = time.time()
                            for att in attachments:
                                raw_fpath = att.get("file_path", "")
                                fpath = _resolve_attachment_path(raw_fpath)
                                if not fpath or not os.path.exists(fpath):
                                    continue
                                pemicu_raw = att.get("trigger_keywords", "") or ""
                                triggers = [t.strip().lower() for t in pemicu_raw.replace(";", ",").split(",") if t.strip()]
                                if triggers and any(tr in pesan_lower for tr in triggers):
                                    cache_key = f"{pid}:{pengirim}:{att.get('id', raw_fpath)}"
                                    last_sent = _sent_attachments_cache.get(cache_key, 0)
                                    if now_ts - last_sent > 180:  # Cooldown 3 menit per berkas
                                        _sent_attachments_cache[cache_key] = now_ts
                                        logger.info(f"[WA Lampiran][{pid}] Mengirim file '{att.get('label')}' ({fpath}) ke {pengirim}...")
                                        await asyncio.sleep(1.0)
                                        _kirim_media_wa(pid, pengirim, fpath, att.get("caption", ""))

                        # 3. Lapor rekap chat WA ke Telegram (per nomor usaha)
                        if notify_tg:
                            tipe_pesan = "🎤 *Voice Note*" if is_vn else "💬 *Teks*"
                            rekap_msg = (
                                f"🔔 *[AKTIVITAS WHATSAPP MASUK]*\n"
                                f"📱 *Nomor:* {nama_usaha} ({nomor_usaha or '-'})\n"
                                f"👤 *Klien:* {nama} (`{pengirim}`)\n"
                                f"📩 *Tipe:* {tipe_pesan}\n"
                            )
                            if transkrip_info:
                                rekap_msg += f"📝 *Transkrip Suara:* \"{transkrip_info}\"\n"
                            else:
                                rekap_msg += f"💬 *Pesan:* \"{isi_pesan}\"\n"

                            rekap_msg += f"\n🤖 *Balasan Otomatis:* \"{balasan}\""
                            kirim_notif_telegram(rekap_msg, reply_markup=_buat_tombol_balas_wa())

                    except Exception as e_send:
                        logger.error(f"[WA Error][{pid}] Gagal memproses pesan dari {pengirim}: {e_send}")

        except Exception as e_loop:
            logger.error(f"Error loop WA: {e_loop}")

        await asyncio.sleep(2.5)
