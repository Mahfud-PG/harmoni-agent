"""
Harmoni Agent - Background Task Scheduler Engine
Memantau dan mengeksekusi tugas terjadwal (Jadwal_Tugas_Eksekusi.json) secara mandiri di background service.
Mendukung eksekusi tepat waktu, tugas berulang (interval multi-hari/menit), auto-retry, dan notifikasi Telegram.
"""

import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

CURRENT_DIR = Path(__file__).parent.resolve()
# PENTING: folder program harus masuk sys.path DULU. Pada Python tertanam
# (yang memakai berkas ._pth), folder skrip tidak otomatis ikut sys.path.
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from sari_core.paths import DATA_ROOT  # folder data pengguna (bisa beda dari folder program)
AI_ASISTEN_DIR = DATA_ROOT
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from dotenv import load_dotenv
load_dotenv(DATA_ROOT / ".env")

logger = logging.getLogger("HarmoniScheduler")

from sari_core.paths import OBSIDIAN_DIR
FILE_JADWAL = OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json"

_jadwal_lock = asyncio.Lock()

def get_user_call_name() -> str:
    """Mengambil nama panggilan pengguna secara dinamis dari personalisasi.json."""
    try:
        from sari_core.paths import PROJECT_ROOT
        p_file = PROJECT_ROOT / "personalisasi.json"
        if p_file.exists():
            with open(p_file, "r", encoding="utf-8") as f:
                return json.load(f).get("user_call_name") or "Pengguna"
    except Exception:
        pass
    return "Pengguna"


def kirim_telegram_aman(pesan: str) -> bool:
    """Mengirim pesan notifikasi ke Telegram pemilik secara aman dengan auto-fallback plain text."""
    import requests
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # 1. Coba dengan Markdown
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": pesan, "parse_mode": "Markdown"}, timeout=10)
        if r.status_code == 200:
            return True
    except Exception:
        pass
        
    # 2. Fallback plain text jika karakter khusus Markdown ditolak Telegram
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": pesan}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Gagal kirim notifikasi Telegram: {e}")
        return False


async def eksekusi_lapor_telegram_async(prompt_konten: str, laporan_deskripsi: str, params_dict: dict) -> tuple[bool, str]:
    """Menangani tugas terjadwal pelaporan: teks langsung, rangkuman email, berita hangat, atau analisis AI."""
    try:
        import ssl, urllib.request
        import xml.etree.ElementTree as ET
        
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        teks_siap = params_dict.get("teks") or params_dict.get("isi_pesan") or params_dict.get("konten") or ""
        gabung_cek = (str(prompt_konten) + " " + str(laporan_deskripsi) + " " + str(params_dict.get("teks", ""))).lower()
        kata_perintah = ["cek ", "baca ", "lapor ", "buatkan ", "tuliskan ", "rangkum ", "kirim ", "ingatkan ", "cari ", "analisa "]
        adalah_perintah = any(k in gabung_cek for k in kata_perintah) or any(k in gabung_cek for k in ["email", "berita", "puisi", "pantun", "laporan"])

        # KASUS 1: Cek Email Masuk & Rangkum (Prioritas Utama jika ada instruksi email)
        if "email" in gabung_cek and any(k in gabung_cek for k in ["cek", "baca", "lapor", "masuk"]):
            try:
                from bot_otomatis import baca_email
                raw_email = baca_email(jumlah=8, hanya_baru=False)
            except Exception as e_mail:
                raw_email = f"Error membaca email: {e_mail}"

            if "AUTHENTICATIONFAILED" in str(raw_email) or "Invalid credentials" in str(raw_email):
                isi_laporan = (
                    "📧 **Laporan Email Terjadwal:**\n\n"
                    "⚠️ Gagal membaca kotak masuk Gmail karena sandi aplikasi Gmail belum valid atau belum diatur.\n"
                    "💡 *Silakan perbarui Alamat & Sandi Aplikasi Google (16 karakter) di tab '📬 Perpesanan & Chat' -> '📧 Email Studio'.*"
                )
            else:
                u_call = get_user_call_name()
                prompt_ai = (
                    f"Data Email Masuk Riil:\n{raw_email}\n\n"
                    f"Instruksi: Buatkan laporan cek email yang rapi, padat, dan jelas untuk {u_call}. "
                    "PENTING: Email dari Facebook DILARANG dilaporkan (abaikan/buang). "
                    "Jika semua email dari Facebook atau tidak ada email penting baru, laporkan bahwa situasi aman dan tidak ada email penting di luar Facebook."
                )
                from sari_core.bridge import process_telegram_message_async
                isi_laporan = await process_telegram_message_async(chat_id, "Harmoni Scheduler", prompt_ai)
                if not isi_laporan.strip():
                    isi_laporan = f"📧 **Laporan Cek Email Pagi:**\n\n{str(raw_email)[:500]}"
            kirim_telegram_aman(isi_laporan)
            return True, f"Laporan email terkirim: {isi_laporan[:60]}"
            
        # KASUS 2: Berita / Kabar Aktual (Topik MENGIKUTI permintaan pengguna, bukan hardcode)
        elif any(k in gabung_cek for k in ["berita", "news", "kabar"]):
            import re as _re

            # 1. Tentukan kata kunci pencarian dari topik yang benar-benar diminta
            kandidat_topik = (
                params_dict.get("topik")
                or params_dict.get("kata_kunci")
                or params_dict.get("query")
                or prompt_konten
                or laporan_deskripsi
                or ""
            )
            query = str(kandidat_topik).strip()
            query = _re.sub(r'^(tolong\s+)?(cari|carikan|baca|lapor|laporkan|buatkan|rangkum|kirim|sampaikan|cek)\s+', '', query, flags=_re.IGNORECASE)
            query = _re.split(r'[,.!?;]|\s+(?:lalu|kemudian)\s+', query)[0].strip()
            query = _re.sub(r'\s+(dari|di)\s+internet.*$', '', query, flags=_re.IGNORECASE).strip()
            if not query:
                query = "berita terbaru hari ini"
            if not any(k in query.lower() for k in ["berita", "kabar", "news"]):
                query = f"berita {query}"

            # 2. Tentukan kata kunci topik esensial untuk MENYARING berita yang relevan
            _stop = {
                "berita", "kabar", "news", "terbaru", "terkini", "hari", "ini", "dari", "di", "ke", "dan", "atau",
                "lalu", "rangkum", "paling", "penting", "beberapa", "seputar", "tentang", "internet", "dengan",
                "untuk", "yang", "saya", "minta", "tolong", "cari", "kirim", "informasikan", "informasi", "update",
                "the", "and", "for", "with", "about", "top", "latest"
            }
            _sinonim = {
                "ai": ["ai", "a.i", "artificial intelligence", "kecerdasan buatan", "kecerdasan artifisial", "machine learning", "llm", "chatgpt", "gemini", "openai"],
                "teknologi": ["teknologi", "technology", "tech", "digital", "gadget", "aplikasi"],
                "musik": ["musik", "music", "lagu", "band", "konser"],
                "politik": ["politik", "politics", "pemilu", "partai", "dpr", "presiden"],
                "ekonomi": ["ekonomi", "economy", "bisnis", "keuangan", "saham", "harga"],
                "olahraga": ["olahraga", "sport", "sepak bola", "sepakbola", "liga"],
            }
            token_topik = [w for w in _re.findall(r'[a-zA-Z0-9]+', query.lower()) if w not in _stop and len(w) > 1]

            pola_relevan = []
            for tk in token_topik:
                varian = _sinonim.get(tk, [tk])
                for v in varian:
                    pola_relevan.append(r'(?<![a-zA-Z0-9])' + _re.escape(v) + r'(?![a-zA-Z0-9])')

            def _relevan(teks: str) -> bool:
                if not pola_relevan:
                    return True
                t_low = str(teks).lower()
                return any(_re.search(p, t_low) for p in pola_relevan)

            logger.info(f"[Scheduler Berita] Topik='{query}' | filter kata kunci={token_topik}")

            # 3. Kumpulkan kandidat berita: RSS portal (judul nyata) + hasil pencarian internet
            item_berita = []   # list of dict(title, link, isi)
            berita_list = []

            # 3a. RSS portal (dipilih sesuai topik)
            kategori_tekno = any(tk in ["ai", "teknologi", "tech", "digital"] for tk in token_topik)
            daftar_rss = [
                "https://www.antaranews.com/rss/tekno.xml",
                "https://inet.detik.com/rss",
                "https://www.cnnindonesia.com/teknologi/rss",
                "https://www.tempo.co/rss/tekno",
                "https://techno.okezone.com/rss",
            ] if kategori_tekno else [
                "https://www.cnnindonesia.com/nasional/rss",
                "https://www.antaranews.com/rss/terkini.xml",
                "https://www.cnnindonesia.com/ekonomi/rss",
            ]
            for rss_url in daftar_rss:
                try:
                    ctx = ssl._create_unverified_context()
                    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                        root = ET.fromstring(response.read())
                    for it in root.findall('.//item')[:15]:
                        t = it.find('title').text if it.find('title') is not None else ""
                        d = it.find('description').text if it.find('description') is not None else ""
                        l = it.find('link').text if it.find('link') is not None else ""
                        if t and _relevan(t + " " + d):
                            item_berita.append({"title": t.strip(), "link": (l or "").strip(), "isi": d.strip()[:600]})
                except Exception as e_rss:
                    logger.warning(f"Warning fetch RSS {rss_url}: {e_rss}")

            # 3b. Hasil pencarian internet (disaring sesuai topik)
            try:
                from plugins.web_browser_plugin import cari_di_internet
                hasil_cari = await asyncio.to_thread(cari_di_internet, query)
                if hasil_cari and "Tidak ditemukan" not in hasil_cari:
                    for blok in hasil_cari.split("\n\n"):
                        blok = blok.strip()
                        if not blok.startswith("•"):
                            continue
                        if _relevan(blok):
                            item_berita.append({"title": "", "link": "", "isi": blok})
            except Exception as e_cari:
                logger.warning(f"[Scheduler Berita] Gagal pencarian internet: {e_cari}")

            # 4. Susun data final (maksimal 6 berita relevan)
            if item_berita:
                for idx, it_b in enumerate(item_berita[:6], 1):
                    if it_b["title"]:
                        blok = f"📌 {idx}. {it_b['title']}"
                        if it_b["link"]:
                            blok += f"\n   Tautan: {it_b['link']}"
                        if it_b["isi"]:
                            blok += f"\n   Ringkasan: {_re.sub(r'<[^>]+>', '', it_b['isi'])}"
                        berita_list.append(blok)
                    else:
                        berita_list.append(it_b["isi"])
                data_berita_str = "\n\n".join(berita_list)

                # 4b. Perkaya: buka 1-2 tautan berita teratas untuk isi yang lebih nyata
                try:
                    from plugins.web_browser_plugin import baca_link_internet
                    tautan_artikel = [it_b["link"] for it_b in item_berita[:6] if it_b.get("link")]
                    artikel_teks = []
                    for u_bersih in tautan_artikel[:2]:
                        try:
                            isi = await asyncio.to_thread(baca_link_internet, u_bersih)
                            if isi and "Gagal membaca" not in isi and len(isi) > 400:
                                artikel_teks.append(isi[:2500])
                        except Exception:
                            continue
                    if artikel_teks:
                        data_berita_str += "\n\n===== ISI ARTIKEL (PEMBAHASAN MENDALAM) =====\n\n" + "\n\n".join(artikel_teks)
                except Exception as e_rik:
                    logger.warning(f"[Scheduler Berita] Gagal memperkaya artikel: {e_rik}")
            else:
                data_berita_str = "TIDAK ADA berita yang relevan dengan topik ditemukan di sumber mana pun."

            prompt_ai = (
                f"TOPIK BERITA YANG DIMINTA PENGGUNA (WAJIB DIPATUHI): \"{query}\"\n\n"
                f"Data berita hasil pencarian & agregasi RSS (SUDAH DISARING sesuai topik):\n{data_berita_str}\n\n"
                "Instruksi: Sampaikan berita yang SESUAI TOPIK DI ATAS SAJA. Bila diminta rangkuman 3-5 berita, rangkum sebanyak yang tersedia di data. "
                "DILARANG KERAS menyampaikan berita di luar topik yang diminta (misalnya berita kriminal/politik umum bila topiknya AI). "
                "Bila data kosong atau tidak berkaitan, katakan jujur bahwa hari ini belum ada berita yang bisa diambil dan jangan ganti ke topik lain. "
                "Gaya bahasa: Hangat, ramah, santai, to the point. Sebutkan judul dan inti beritanya, serta sumbernya bila ada. "
                "DILARANG KERAS hanya mengirim pesan konfirmasi kosong (seperti 'siap sudah terkirim'). LANGSUNG TULIS BERITANYA!"
            )
            from sari_core.bridge import process_telegram_message_async
            isi_laporan = await process_telegram_message_async(chat_id, "Harmoni Scheduler", prompt_ai)
            if not isi_laporan.strip():
                isi_laporan = f"📰 **Berita ({query}):**\n\n{berita_list[0] if berita_list else laporan_deskripsi}"
            kirim_telegram_aman(isi_laporan)
            return True, f"Berita terkirim: {isi_laporan[:60]}"

        # KASUS 3: Teks Statis Murni (Hanya jika BUKAN kalimat perintah/instruksi ke AI)
        elif not adalah_perintah and teks_siap and len(str(teks_siap).strip()) > 3:
            kirim_telegram_aman(str(teks_siap).strip())
            return True, f"Teks langsung terkirim: {str(teks_siap)[:60]}"

        # KASUS 4: Tugas Perintah AI / Analisis Umum
        else:
            u_call = get_user_call_name()
            prompt_bawah = prompt_konten or laporan_deskripsi or params_dict.get("teks", "") or f"Sampaikan laporan tugas terjadwal ke {u_call}."
            from sari_core.bridge import process_telegram_message_async
            isi_laporan = await process_telegram_message_async(chat_id, "Harmoni Scheduler", prompt_bawah)
            if not isi_laporan.strip():
                isi_laporan = f"⏰ **Laporan Terjadwal Harmoni:**\n\n{laporan_deskripsi or prompt_konten}"
            kirim_telegram_aman(isi_laporan)
            return True, f"Laporan umum terkirim: {isi_laporan[:60]}"
            
    except Exception as e:
        logger.error(f"Error eksekusi lapor telegram: {e}")
        return False, str(e)


async def _proses_pesan_wa_cerdas(kontak_raw: str, psn_raw: str) -> tuple[str, str]:
    """Menyelesaikan nomor kontak dan memproses instruksi kreatif (puisi, pantun, pesan) via AI jika diperlukan."""
    kontak = str(kontak_raw or "istri").strip()
    psn = str(psn_raw or "").strip()

    # 1. Resolusi nama kontak ke nomor jika bukan digit
    if not any(c.isdigit() for c in kontak):
        try:
            from plugins.whatsapp_plugin import resolve_contact_auto
            info_k = resolve_contact_auto(kontak)
            if info_k.get("status") == "found":
                kontak = info_k.get("number")
        except Exception:
            pass

    # 2. Deteksi apakah isi pesan adalah instruksi/perintah pembuatan teks ke AI
    psn_lower = psn.lower()
    kata_perintah = ["kirim ", "buatkan ", "tuliskan ", "bikin ", "susunkan ", "karangkan ", "ingatkan "]
    kata_kreatif = ["puisi", "pantun", "kata romantis", "pesan romantis", "salam hangat", "kata-kata"]
    perlu_ai = any(psn_lower.startswith(k) for k in kata_perintah) or any(k in psn_lower for k in kata_kreatif)

    if perlu_ai:
        try:
            import re
            from sari_core.bridge import process_telegram_message_async
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            u_call = get_user_call_name()
            prompt_ai = (
                f"Instruksi Pengguna: {psn}\n\n"
                f"Tugas Anda: Anda adalah asisten pribadi {u_call} yang sedang menyiapkan pesan WhatsApp untuk dikirimkan kepada penerima.\n"
                "ATURAN WAJIB:\n"
                "1. LANGSUNG TULIS ISI PESAN / PUISI JADI yang siap dibaca oleh penerima.\n"
                "2. DILARANG KERAS menyertakan basa-basi asisten seperti 'Tentu, ini puisinya', 'Baik Kak', 'Berikut pesannya', atau kata pengantar apapun.\n"
                "3. Jangan gunakan tanda kutip di awal dan akhir pesan.\n"
                f"4. Susun dengan bahasa yang hangat, tulus, dan indah sesuai arahan {u_call}."
            )
            ai_res = await process_telegram_message_async(chat_id, "Harmoni Scheduler", prompt_ai)
            if ai_res and len(ai_res.strip()) > 5:
                clean_res = re.sub(r'🧠\s*_\[Otak:.*?\]_', '', ai_res).strip()
                if clean_res:
                    psn = clean_res
        except Exception as e_ai:
            logger.warning(f"[Scheduler WA] Gagal memproses teks via AI: {e_ai}")

    return kontak, psn


async def jalankan_satu_tugas_async(item: dict) -> tuple[bool, str]:
    """Mengeksekusi satu item tugas terjadwal berdasarkan nama fungsi dan parameternya."""
    fungsi_nama = item.get("fungsi", "")
    params = item.get("params", {})
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except Exception:
            params = {"kata_kunci": params}
    if not isinstance(params, dict):
        params = {"param": params}
        
    p_copy = dict(params)
    kw = p_copy.get("kata_kunci") or p_copy.get("query") or p_copy.get("param") or ""
    
    # 1. Normalisasi Alias Fungsi
    alias_map = {
        "kirim_whatsapp": "kirim_pesan_whatsapp",
        "kirim_wa": "kirim_pesan_whatsapp",
        "kirim_pesan_wa": "kirim_pesan_whatsapp",
        "kirim_pesan_ke_wa": "kirim_pesan_whatsapp",
        "whatsapp": "kirim_pesan_whatsapp",
        "kirim_vn": "kirim_vn_whatsapp",
        "kirim_vn_wa": "kirim_vn_whatsapp",
        "buat_status_wa": "kirim_status_whatsapp",
        "update_status_wa": "kirim_status_whatsapp",
        "status_wa": "kirim_status_whatsapp",
        "kirim_status_wa": "kirim_status_whatsapp",
        "lapor_email": "lapor_telegram",
        "cek_email": "lapor_telegram",
        "cek_email_dan_lapor": "lapor_telegram",
        "baca_email": "lapor_telegram",
        "baca_email_dan_lapor": "lapor_telegram",
        "lapor_email_telegram": "lapor_telegram",
        "kirim_berita": "lapor_telegram",
        "lapor_berita": "lapor_telegram",
        "chat_telegram": "lapor_telegram",
        "kirim_chat_telegram": "lapor_telegram",
        "restart_pc": "atur_daya_pc",
        "restart": "atur_daya_pc",
        "restart_komputer": "atur_daya_pc",
        "reboot": "atur_daya_pc",
        "reboot_pc": "atur_daya_pc",
        "matikan_pc": "atur_daya_pc",
        "matikan_komputer": "atur_daya_pc",
        "matikan": "atur_daya_pc",
        "shutdown": "atur_daya_pc",
        "shutdown_pc": "atur_daya_pc"
    }
    real_func = alias_map.get(fungsi_nama, fungsi_nama)
    logger.info(f"[Scheduler] Mengeksekusi tugas #{item.get('id')}: {fungsi_nama} -> {real_func}")

    try:
        # A. Tugas Lapor Telegram (Email, Berita, Konten AI, Chat)
        if real_func == "lapor_telegram":
            prompt_t = p_copy.get("pesan_atau_prompt") or p_copy.get("prompt") or p_copy.get("pesan") or item.get("pesan_atau_prompt") or item.get("laporan", "")
            return await eksekusi_lapor_telegram_async(prompt_t, item.get("laporan", ""), p_copy)

        # B. Tugas WhatsApp Pesan Teks
        elif real_func == "kirim_pesan_whatsapp":
            from plugins.whatsapp_plugin import kirim_pesan_whatsapp
            kontak_raw = p_copy.get("nama_kontak") or p_copy.get("tujuan") or p_copy.get("number") or p_copy.get("kontak") or p_copy.get("penerima") or p_copy.get("nama") or "istri"
            psn_raw = p_copy.get("pesan") or p_copy.get("pesan_teks") or p_copy.get("isi") or p_copy.get("teks") or p_copy.get("puisi") or kw or item.get("pesan_atau_prompt", "") or item.get("laporan", "")
            target_pid = p_copy.get("profile_id") or p_copy.get("profile") or p_copy.get("profil") or item.get("profile_id", "")
            kontak, psn = await _proses_pesan_wa_cerdas(kontak_raw, psn_raw)
            res = await asyncio.to_thread(kirim_pesan_whatsapp, kontak, psn, profile_id=target_pid)
            return True, str(res)

        # C. Tugas WhatsApp Voice Note (VN)
        elif real_func == "kirim_vn_whatsapp":
            from plugins.whatsapp_plugin import kirim_vn_whatsapp
            kontak_raw = p_copy.get("nama_kontak") or p_copy.get("tujuan") or p_copy.get("number") or p_copy.get("kontak") or p_copy.get("penerima") or p_copy.get("nama") or "istri"
            psn_raw = p_copy.get("pesan_teks") or p_copy.get("pesan") or p_copy.get("isi") or p_copy.get("teks") or p_copy.get("puisi") or kw or item.get("pesan_atau_prompt", "") or item.get("laporan", "")
            target_pid = p_copy.get("profile_id") or p_copy.get("profile") or p_copy.get("profil") or item.get("profile_id", "")
            kontak, psn = await _proses_pesan_wa_cerdas(kontak_raw, psn_raw)
            res = await asyncio.to_thread(kirim_vn_whatsapp, kontak, psn, profile_id=target_pid)
            return True, str(res)

        # C2. Tugas WhatsApp Status
        elif real_func == "kirim_status_whatsapp":
            from plugins.whatsapp_plugin import kirim_status_whatsapp
            teks = p_copy.get("teks") or p_copy.get("pesan") or p_copy.get("isi") or kw or item.get("pesan_atau_prompt", "") or item.get("laporan", "")
            p_file = p_copy.get("path_file") or p_copy.get("file_path", "")
            target_pid = p_copy.get("profile_id") or p_copy.get("profile") or p_copy.get("profil") or item.get("profile_id", "")
            res = await asyncio.to_thread(kirim_status_whatsapp, teks, p_file, profile_id=target_pid, force_send=True)
            return True, str(res)

        # D. Tugas Putar YouTube
        elif real_func == "putar_youtube":
            from bot_otomatis import putar_youtube
            kata = str(kw or p_copy.get("kata_kunci") or p_copy.get("judul") or item.get("laporan", "")).strip()
            res = await asyncio.to_thread(putar_youtube, kata)
            return True, str(res)

        # E. Tugas Kirim Email Langsung
        elif real_func == "kirim_email":
            from bot_otomatis import kirim_email
            tuj = p_copy.get("tujuan") or p_copy.get("email") or p_copy.get("penerima", "")
            subj = p_copy.get("subjek", "Pesan Terjadwal dari Harmoni Agent")
            psn_raw = p_copy.get("pesan") or p_copy.get("isi", "") or item.get("pesan_atau_prompt", "") or item.get("laporan", "")
            
            psn = str(psn_raw).strip()
            psn_lower = psn.lower()
            if any(psn_lower.startswith(k) for k in ["kirim ", "buatkan ", "tuliskan ", "susunkan "]) or any(k in psn_lower for k in ["draft", "surat", "penawaran", "jadwal", "nota", "invoice", "email"]):
                try:
                    import re
                    from sari_core.bridge import process_telegram_message_async
                    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
                    u_call = get_user_call_name()
                    prompt_ai = (
                        f"Instruksi Pengguna: {psn}\n\n"
                        f"Tujuan Penerima: {tuj}\nSubjek: {subj}\n\n"
                        f"Tugas Anda: Anda adalah asisten pribadi {u_call} yang sedang menyusun email resmi untuk klien/penerima.\n"
                        "ATURAN WAJIB:\n"
                        "1. LANGSUNG TULIS ISI EMAIL JADI (Salam pembuka, isi pesan, dan salam penutup).\n"
                        "2. DILARANG KERAS menyertakan basa-basi asisten seperti 'Tentu, ini emailnya' atau kata pengantar apapun.\n"
                        "3. Gunakan bahasa yang sopan, profesional, dan rapi."
                    )
                    ai_res = await process_telegram_message_async(chat_id, "Harmoni Scheduler", prompt_ai)
                    if ai_res and len(ai_res.strip()) > 10:
                        clean_res = re.sub(r'🧠\s*_\[Otak:.*?\]_', '', ai_res).strip()
                        if clean_res:
                            psn = clean_res
                except Exception as e_ai:
                    logger.warning(f"[Scheduler Email] Gagal proses prompt via AI: {e_ai}")

            lamp = p_copy.get("file_lampiran", None)
            res = await asyncio.to_thread(kirim_email, tuj, subj, psn, lamp)
            return True, str(res)

        # F. Tugas Kontrol Daya PC (Restart / Shutdown)
        elif real_func == "atur_daya_pc":
            from bot_otomatis import atur_daya_pc
            aksi_p = p_copy.get("aksi")
            if not aksi_p:
                nama_cek = (fungsi_nama + " " + real_func).lower()
                aksi_p = "shutdown" if any(k in nama_cek for k in ["matikan", "shutdown"]) else "restart"
            waktu_m = p_copy.get("waktu_menit", 0)
            kata_aksi = "me-restart" if aksi_p == "restart" else "mematikan"
            u_call = get_user_call_name()
            kirim_telegram_aman(f"⏰ **[EKSEKUSI OTOMATIS TERJADWAL]**\n\nHarmoni sedang {kata_aksi} PC {u_call} sekarang sesuai jadwal! 🔌✨\n*(PC akan {kata_aksi} dalam 5 detik)*")
            res = await asyncio.to_thread(atur_daya_pc, aksi=aksi_p, waktu_menit=waktu_m, jeda_detik=5)
            return True, str(res)

        # G. Fallback ke Registry Alat Universal Harmoni (151+ tools)
        else:
            from sari_core.brain import tool_registry
            t_obj = tool_registry.get_tool(real_func)
            if not t_obj:
                # Coba cari di available_functions bot_otomatis
                import bot_otomatis as b_mod
                target_f = b_mod.available_functions.get(real_func)
            else:
                target_f = t_obj.get("handler")
                
            if target_f:
                try:
                    res = await asyncio.to_thread(target_f, **p_copy)
                except TypeError:
                    res = await asyncio.to_thread(target_f, kw)
                return True, str(res)
            else:
                return False, f"Alat/fungsi '{fungsi_nama}' tidak terdaftar di sistem."

    except Exception as ex:
        logger.error(f"[Scheduler] Error eksekusi {real_func}: {ex}", exc_info=True)
        return False, str(ex)


def hitung_jadwal_berikutnya(anchor_ts: int, interval_m: int, now_ts: int) -> tuple[int, str]:
    """
    Menghitung waktu eksekusi berikutnya untuk tugas berulang dengan mempertahankan
    jangkar waktu asli (anchor time).
    
    Jika laptop mati/tidur dan baru menyala setelah jadwal terlewati (misal jadwal jam 05:00,
    laptop baru menyala jam 08:00), tugas tetap dieksekusi saat menyala, lalu jadwal berikutnya
    TIDAK digeser ke jam 08:00, melainkan tetap dihitung dari jangkar jam 05:00 asli sehingga
    jadwal berikutnya tetap jatuh pada jam 05:00 di hari berikutnya (atau kelipatan interval di masa depan).
    """
    step_sec = interval_m * 60
    if step_sec <= 0:
        return now_ts, datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M:%S")

    base_ts = anchor_ts if (anchor_ts and anchor_ts > 0) else now_ts

    # Hitung waktu berikutnya dari jangkar asli
    next_ts = base_ts + step_sec

    # Jika laptop mati berjam-jam atau berhari-hari sehingga next_ts masih di masa lalu atau saat ini (<= now_ts),
    # majukan terus per interval sampai berada di masa depan (> now_ts)
    if next_ts <= now_ts:
        selisih = now_ts - base_ts
        lompatan = (selisih // step_sec) + 1
        next_ts = base_ts + (lompatan * step_sec)

    next_dt_obj = datetime.fromtimestamp(next_ts)
    # Jika interval kelipatan menit/jam/hari (>= 1 menit), rapikan detik ke 00 jika ada jitter detik
    if step_sec >= 60 and next_dt_obj.second != 0:
        next_dt_obj = next_dt_obj.replace(second=0)
        next_ts = int(next_dt_obj.timestamp())
        if next_ts <= now_ts:
            next_ts += step_sec
            next_dt_obj = datetime.fromtimestamp(next_ts).replace(second=0)

    next_dt = next_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    return next_ts, next_dt


async def periksa_dan_eksekusi_jadwal_async():
    """Membaca file jadwal dan memproses semua tugas yang jatuh tempo."""
    if not FILE_JADWAL.exists():
        return

    async with _jadwal_lock:
        try:
            with open(FILE_JADWAL, "r", encoding="utf-8") as f:
                daftar = json.load(f)
        except Exception as e:
            logger.error(f"Gagal membaca file jadwal: {e}")
            return

        if not isinstance(daftar, list) or not daftar:
            return

        now_ts = int(time.time())
        updated = False

        for item in daftar:
            st = item.get("status", "pending")
            ts_target = item.get("timestamp_target", 0)

            # Kondisi eksekusi: status pending/retrying dan waktu sekarang >= target
            if st in ["pending", "retrying", "guaranteed_retry"] and now_ts >= ts_target:
                task_id = item.get("id", "task_unknown")
                laporan = item.get("laporan", "Tugas Terjadwal")
                fungsi_nama = item.get("fungsi", "")
                dt_now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                logger.info(f"⏰ [Scheduler Wakeup] Task #{task_id} ({fungsi_nama}) jatuh tempo pada {dt_now_full}")

                sukses, detail_res = await jalankan_satu_tugas_async(item)

                interval_m = int(item.get("interval_menit", 0)) if str(item.get("interval_menit", 0)).isdigit() else 0
                total_ulang = int(item.get("total_pengulangan", 1)) if str(item.get("total_pengulangan", 1)).isdigit() else 1

                if sukses:
                    logger.info(f"✅ [Scheduler Sukses] Task #{task_id}: {detail_res[:100]}")
                    item["eksekusi_berjalan"] = item.get("eksekusi_berjalan", 0) + 1
                    item["dieksekusi_pada"] = dt_now_full
                    item["last_error"] = ""
                    updated = True

                    # Cek apakah tugas berulang
                    if interval_m > 0 and (total_ulang <= 0 or item["eksekusi_berjalan"] < total_ulang):
                        anchor_ts = item.get("target_awal_ts") or ts_target
                        next_ts, next_dt = hitung_jadwal_berikutnya(anchor_ts, interval_m, now_ts)
                        item["timestamp_target"] = next_ts
                        item["target_awal_ts"] = next_ts
                        item["waktu_str"] = next_dt
                        item["status"] = "pending"
                        item["retry_count"] = 0
                        ulang_str = f"ke-{item['eksekusi_berjalan']} dari {total_ulang if total_ulang > 0 else 'selamanya'}"

                        sisa_detik = max(0, next_ts - now_ts)
                        sisa_jam = sisa_detik // 3600
                        sisa_mnt = (sisa_detik % 3600) // 60
                        if sisa_jam > 0:
                            sisa_str = f"{sisa_jam} jam {sisa_mnt} menit lagi" if sisa_mnt > 0 else f"{sisa_jam} jam lagi"
                        else:
                            sisa_str = f"{sisa_mnt} menit lagi"

                        kirim_telegram_aman(
                            f"🔄 **[JADWAL BERULANG AKTIF]**\n\n"
                            f"Tugas: *{laporan}*\n"
                            f"Status: Berhasil dijalankan ({ulang_str}).\n"
                            f"Jadwal berikutnya: **{next_dt}** ({sisa_str}) ⏰"
                        )
                    else:
                        item["status"] = "done"
                        # Hanya kirim notif konfirmasi jika fungsi bukan lapor_telegram (karena lapor_telegram sudah kirim isi laporannya sendiri)
                        if fungsi_nama not in ["lapor_telegram", "kirim_chat_telegram", "kirim_berita", "lapor_berita", "lapor_email", "cek_email", "atur_daya_pc", "restart_pc", "matikan_pc"]:
                            kirim_telegram_aman(
                                f"⏰ **[EKSEKUSI OTOMATIS BERHASIL]**\n\n"
                                f"Harmoni baru saja mengeksekusi tugas terjadwal:\n*{laporan}*! 🎶✨"
                            )
                else:
                    logger.warning(f"❌ [Scheduler Gagal] Task #{task_id}: {detail_res}")
                    item["retry_count"] = item.get("retry_count", 0) + 1
                    item["last_error"] = detail_res
                    item["terakhir_dicoba"] = dt_now_full
                    updated = True
                    max_r = item.get("max_retries", 3)

                    is_fatal = ("tidak terdaftar" in detail_res.lower()) or (item["retry_count"] >= max_r)
                    if is_fatal:
                        item["status"] = "failed"
                        kirim_telegram_aman(
                            f"❌ **[EKSEKUSI JADWAL DIBATALKAN]**\n\n"
                            f"Tugas: *{laporan}*\n"
                            f"Kendala: `{detail_res}`\n\n"
                            f"Tugas ini dihentikan agar tidak terjadi pengulangan error."
                        )
                    else:
                        item["status"] = "retrying"
                        if "target_awal_ts" not in item:
                            item["target_awal_ts"] = ts_target
                        # Coba lagi 1 menit berikutnya
                        item["timestamp_target"] = now_ts + 60
                        logger.info(f"[Scheduler Retry] Task #{task_id} dijadwalkan ulang dalam 60 detik (Percobaan {item['retry_count']}/{max_r})")

        if updated:
            try:
                with open(FILE_JADWAL, "w", encoding="utf-8") as f:
                    json.dump(daftar, f, indent=2, ensure_ascii=False)
            except Exception as e_w:
                logger.error(f"Gagal menyimpan pembaruan jadwal: {e_w}")


async def start_task_scheduler_loop():
    """Perulangan utama background scheduler: memeriksa jadwal setiap 5 detik."""
    logger.info("Harmoni Task Scheduler Engine mulai berjalan (interval 5 detik)...")
    while True:
        try:
            await periksa_dan_eksekusi_jadwal_async()
        except asyncio.CancelledError:
            logger.info("Task Scheduler dihentikan.")
            break
        except Exception as e:
            logger.error(f"Error di loop scheduler: {e}", exc_info=True)
        await asyncio.sleep(5)


if __name__ == "__main__":
    print("Menjalankan uji manual satu siklus periksa jadwal...")
    asyncio.run(periksa_dan_eksekusi_jadwal_async())
    print("Selesai.")
