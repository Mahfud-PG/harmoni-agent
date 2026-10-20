import logging
import os
import json
import re
import traceback
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from sari_core.paths import PROJECT_ROOT, PROGRAM_ROOT, DATA_ROOT, OBSIDIAN_DIR

logger = logging.getLogger(__name__)

# ==== PENAMPIL PROSES (Gaya Hermes) : Menampilkan langkah kerja asisten di chat ====
import contextvars

# Kunci sesi aktif tempat langkah proses dicatat (dipakai UI Desktop untuk polling）
CURRENT_STEP_SINK = contextvars.ContextVar("harmoni_step_sink", default=None)
# Penyimpanan sementara langkah proses per sesi: {session_key: [(id, teks), ...]}
LIVE_STEPS: Dict[str, List[Dict[str, Any]]] = {}


# ==== PENAMPIL PROSES (Gaya Hermes) : Menampilkan langkah kerja asisten di chat Telegram ====
def _format_tool_step(func_name: str, func_args: dict) -> str:
    """Menerjemahkan panggilan alat menjadi satu baris ringkas yang mudah dibaca."""
    a = func_args or {}

    def ambil(*kunci, default=""):
        for k in kunci:
            v = a.get(k)
            if v:
                return str(v)
        return default

    def pendek(teks, batas=80):
        teks = " ".join(str(teks).split())
        return teks if len(teks) <= batas else teks[: batas - 1] + "…"

    fn = func_name

    # --- Pencarian ---
    if fn in ("cari_di_web", "cari_web", "search_web", "cari_informasi", "web_search", "cari_berita", "cari_di_internet"):
        return f"🔎 Mencari di web: {pendek(ambil('kata_kunci', 'query', 'q', 'search', 'topik'))}"
    if fn in ("cari_di_youtube", "cek_youtube_channel_publik", "search_youtube", "cari_video_youtube", "youtube_search", "cek_video_youtube"):
        return f"🎬 Memeriksa YouTube: {pendek(ambil('nama_channel', 'kata_kunci', 'query', 'q'))}"
    if fn in ("cari_di_obsidian", "baca_memori", "cari_memori", "search_memory"):
        return f"🔎 Mencari memori: {pendek(ambil('kata_kunci', 'query', 'topik', 'q'))}"

    # --- Berkas ---
    if fn in ("cari_file_lokal", "cari_file"):
        return f"🔎 Mencari di komputer: {pendek(ambil('query', 'kata_kunci', 'nama'))} ({ambil('drive', default='C:')})"
    if fn in ("baca_file", "baca_berkas", "read_file", "lihat_file", "baca_dokumen"):
        return f"📖 Membaca {ambil('path', 'file', 'nama_file', 'berkas')}"
    if fn in ("tulis_file", "simpan_file", "write_file", "edit_file", "ubah_file", "buat_file"):
        return f"🔧 Menulis {ambil('path', 'file', 'nama_file', 'berkas')}"
    if fn in ("daftar_file", "list_file", "lihat_folder", "daftar_folder", "list_dir"):
        return f"📂 Melihat folder {ambil('path', 'folder', 'direktori', 'dir')}"

    # --- Sistem & terminal ---
    if fn in ("jalankan_perintah_sistem", "jalankan_terminal", "terminal", "jalankan_perintah", "run_command", "eksekusi_perintah"):
        cmd = pendek(ambil("perintah", "command", "cmd"), 70)
        return f"💻 Terminal: {cmd}"
    if fn in ("buka_aplikasi", "jalankan_aplikasi", "buka_program"):
        return f"🚀 Membuka aplikasi: {ambil('nama_aplikasi', 'aplikasi', 'nama')}"
    if fn == "atur_daya_pc":
        return f"⏻ Mengatur daya PC: {ambil('aksi')}"
    if fn in ("cek_sistem", "kesehatan_sistem", "cek_health", "status_sistem", "info_sistem", "cek_spesifikasi"):
        return "🖥️ Memeriksa kondisi sistem"
    if fn in ("cek_token", "cek_kuota", "status_model", "cek_model", "cek_sisa_kuota_token", "kuota_ai", "sisa_kuota"):
        return f"🧠 Memeriksa kuota & status model AI: {ambil('provider', default='semua')}"
    if fn in ("kontrol_reaper", "reaper"):
        return f"🎛️ Mengendalikan REAPER: {ambil('aksi', 'perintah')} {ambil('jumlah_track', 'track', 'nama_track', default='')}".strip()

    # --- Komunikasi ---
    if fn in ("kirim_pesan_whatsapp", "kirim_wa", "send_whatsapp"):
        return f"💬 Mengirim WhatsApp ke {ambil('nama_kontak', 'kontak', 'nomor', 'target')}"
    if fn in ("kirim_vn_whatsapp", "kirim_voice_note_whatsapp", "kirim_vn"):
        return f"🎙️ Mengirim Voice Note ke {ambil('nama_kontak', 'kontak', 'nomor', 'target')}"
    if fn in ("kirim_file_whatsapp", "kirim_dokumen_whatsapp", "kirim_media_whatsapp"):
        return f"📎 Mengirim berkas ke {ambil('nama_kontak', 'kontak', 'nomor', 'target')}"
    if fn in ("kirim_status_whatsapp", "buat_status_wa", "update_status_wa"):
        return f"📱 Membuat Status WhatsApp: {pendek(ambil('teks', 'path_file', 'isi'))}"
    if fn in ("cek_penonton_status_whatsapp", "cek_status_wa", "penonton_status"):
        return "👁️ Memeriksa penonton status WhatsApp"
    if fn in ("baca_pesan_terakhir_wa", "baca_wa", "cek_wa_unread", "unread_wa"):
        return f"📩 Memeriksa chat WhatsApp masuk: {ambil('profile_id', default='semua nomor')}"
    if fn in ("atur_mode_sibuk_wa", "mode_sibuk_wa"):
        return f"🌙 Mengatur mode sibuk WhatsApp: {ambil('mode', 'pesan')}"
    if fn in ("tambah_jawaban_kilat_wa", "tambah_quick_reply"):
        return f"⚡ Menambah jawaban kilat: {ambil('kata_kunci')}"
    if fn in ("daftar_jawaban_kilat_wa", "lihat_jawaban_kilat"):
        return "⚡ Melihat daftar jawaban kilat WhatsApp"
    if fn in ("hapus_jawaban_kilat_wa", "hapus_quick_reply"):
        return f"🗑️ Menghapus jawaban kilat: {ambil('kata_kunci')}"
    if fn in ("cari_kontak", "lihat_kontak", "daftar_kontak", "resolve_contact"):
        return f"📇 Mencari kontak: {pendek(ambil('nama_kontak', 'nama', 'query', 'kata_kunci'))}"
    if fn in ("kirim_telegram", "kirim_pesan_telegram"):
        return "✈️ Mengirim pesan Telegram"
    if fn in ("cek_email", "baca_email", "list_email"):
        return "📧 Memeriksa email masuk"
    if fn in ("kirim_email", "balas_email"):
        return f"📧 Mengirim email ke {ambil('tujuan', 'to', 'penerima')}"

    # --- Penjadwalan ---
    if fn in ("buat_jadwal", "jadwalkan_tugas", "tambah_jadwal", "buat_tugas"):
        return f"⏰ Membuat jadwal: {pendek(ambil('nama_tugas', 'judul', 'tugas', 'aksi'))} pukul {ambil('jam', 'waktu')}"
    if fn in ("lihat_jadwal", "daftar_jadwal", "cek_jadwal", "list_jadwal"):
        return "⏰ Melihat daftar jadwal"
    if fn in ("hapus_jadwal", "batalkan_jadwal"):
        return f"🗑️ Menghapus jadwal: {pendek(ambil('nama_tugas', 'judul', 'tugas', 'id'))}"

    # --- Google Drive / YouTube / Google ---
    if fn in ("unggah_ke_drive", "upload_drive", "simpan_drive"):
        return f"☁️ Mengunggah ke Google Drive: {ambil('nama_file', 'file', 'path')}"
    if fn in ("cari_di_drive", "list_drive"):
        return f"☁️ Mencari di Google Drive: {pendek(ambil('kata_kunci', 'query', 'nama_file'))}"
    if fn in ("unggah_ke_youtube", "upload_youtube"):
        return f"📺 Mengunggah ke YouTube: {pendek(ambil('judul', 'path', 'nama_file'))}"
    if fn in ("cek_komentar_youtube", "komentar_youtube"):
        return "📺 Memeriksa komentar YouTube"
    if fn in ("ingatkan", "simpan_ke_ingatan", "simpan_memori", "catat_memori"):
        return f"💾 Menyimpan catatan: {pendek(ambil('topik', 'judul', 'catatan', 'isi'))}"

    # --- Fallback umum ---
    ringkas = ", ".join(
        f"{k}={pendek(v, 40)}"
        for k, v in a.items()
        if k not in ("chat_id", "profile_id", "reason") and v
    )
    if ringkas:
        return f"🔧 {fn}: {pendek(ringkas, 110)}"
    return f"🔧 {fn}"


def _pesan_gagal_otak(last_error: str) -> str:
    """Ubah kegagalan otak AI jadi pesan yang berguna bagi pengguna biasa."""
    pesan = str(last_error or "")
    rendah = pesan.lower()

    # Belum ada kunci API sama sekali (biasanya pemasangan baru)
    kesan_kunci_kosong = (
        "missing credentials" in rendah
        or "invalid api key" in rendah
        or "401" in rendah
        or "incorrect api key" in rendah
        or "api key not valid" in rendah
    )
    if kesan_kunci_kosong:
        return (
            "Otak AI belum tersambung.\n\n"
            "Kunci API belum diisi atau sudah tidak berlaku. Silakan buka menu "
            "Pengaturan -> Otak AI, lalu isi salah satu kunci (misalnya DeepSeek "
            "atau Gemini), kemudian simpan.\n\n"
            "Setelah itu kirim pesan lagi."
        )

    if "429" in rendah or "quota" in rendah or "rate limit" in rendah or "limit" in rendah:
        return (
            "Otak AI sedang kehabisan kuota atau kena batas pemakaian.\n\n"
            "Silakan tunggu beberapa saat, atau ganti ke model cadangan lewat menu "
            "Pengaturan -> Otak AI."
        )

    if any(k in rendah for k in ("connection", "timeout", "getaddrinfo", "unreachable", "ssl")):
        return (
            "Otak AI tidak bisa dihubungi karena jaringan bermasalah.\n\n"
            "Silakan periksa sambungan internet lalu kirim pesan lagi."
        )

    return f"Semua otak AI gagal menjawab. Rincian terakhir:\n{pesan}"


# Kalimat sapaan yang TIDAK BOLEH muncul sebagai jawaban atas sebuah perintah.
# Kalau otak menghasilkan salah satunya padahal ada alat yang sudah dijalankan,
# jawabannya diganti dengan laporan hasil alat.
_SAPAAN_GENERIK = (
    "ada yang bisa siti bantu",
    "ada yang bisa harmoni bantu",
    "ada yang bisa lisa bantu",
    "ada yang bisa saya bantu",
    "ada yang bisa dibantu",
    "how can i help",
    "ada yang bisa aku bantu",
)


def _jawaban_terlalu_tipis(teks: str) -> bool:
    """Apakah jawaban ini tidak membawa keterangan apa pun?

    Kejadian nyata (30 Sep 2026): pengguna mengirim "cek drive c", seluruh alat
    mengembalikan teks kosong, dan otak menjawab "Berhasil" saja. Bagi pengguna
    pembaca layar, jawaban itu tidak memuat satu pun angka atau daftar yang bisa
    dibacakan - sementara ia menyangka perintahnya berhasil padahal tidak ada
    yang dikerjakan.

    Sengaja memakai daftar kata yang SEMPIT (harus sama persis) supaya jawaban
    pendek yang sah seperti "Sudah saya matikan." tidak ikut tertimpa.
    """
    bersih = (teks or "").strip().lower().strip(".!*_ \n")
    return bersih in {
        "berhasil", "sukses", "ok", "oke", "done", "selesai", "sudah",
        "sudah selesai", "berhasil dijalankan", "tuntas", "baik",
    }


def _laporan_hasil_alat(user_call: str, hasil: list) -> str:
    """Susun laporan dari alat yang sudah dijalankan.

    Dipakai sebagai jalur cadangan ketika otak tidak menghasilkan kalimat akhir
    yang layak. Aturannya tegas: kalau ada alat yang sudah berjalan, JANGAN
    pernah membalas sapaan. Pengguna mengirim PERINTAH, dan sapaan membuatnya
    mengira perintahnya tidak diproses.

    Kejadian nyata (30 Sep 2026, 06:22): pengguna mengirim
    "cek drive c/user/nama user/dokumen/reaper media", otak menjalankan 13 alat
    (putaran 5/5 habis), lalu menjawab "Halo Kakak! Ada yang bisa Harmoni bantu
    atau lanjutkan?" - seolah tidak terjadi apa-apa.
    """
    bersih = []
    for h in hasil:
        teks = str(h).strip()
        if not teks:
            continue
        # Kata "Berhasil" tanpa keterangan tidak berarti apa-apa bagi pengguna
        # yang mendengarkan lewat pembaca layar. Ganti dengan kalimat yang jujur.
        if teks.strip(".! ") in ("Berhasil", "Sukses", "OK", "ok", "Done"):
            teks = ("Berhasil dijalankan, tetapi perintahnya tidak menghasilkan "
                    "keluaran yang bisa dilaporkan.")
        bersih.append(teks)

    if not bersih:
        return (f"Maaf {user_call}, perintahnya sudah dijalankan tetapi tidak ada "
                f"keluaran yang bisa saya laporkan.")

    # Ambil beberapa hasil terakhir saja supaya balasan tetap terbaca.
    gabung = "\n\n".join(bersih[-3:])
    return f"Hasil yang saya dapat:\n{gabung}"


def _get_user_call() -> str:
    """Ambil sebutan untuk pengguna dari berkas personalisasi (fallback: 'Kak')."""
    try:
        pers_file = PROJECT_ROOT / "personalisasi.json"
        if pers_file.exists():
            with open(pers_file, "r", encoding="utf-8") as pf:
                return (json.load(pf).get("user_call_name") or "").strip() or "Kak"
    except Exception:
        pass
    return "Kak"


import threading
import time


def _tg_token():
    """Ambil token bot Telegram dari .env (dengan cache sederhana)."""
    global _TG_TOKEN_CACHE
    if _TG_TOKEN_CACHE:
        return _TG_TOKEN_CACHE
    try:
        from dotenv import dotenv_values
        env_vals = dotenv_values(str(PROJECT_ROOT / ".env"))
        tok = env_vals.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        if tok:
            _TG_TOKEN_CACHE = tok
        return tok
    except Exception:
        return os.getenv("TELEGRAM_BOT_TOKEN")


_TG_TOKEN_CACHE = None


def _tg_send(token, chat_id, teks) -> Optional[int]:
    """Kirim pesan Telegram tanpa bunyi notifikasi. Kembalikan message_id."""
    import urllib.request, urllib.parse, json as _json
    data = urllib.parse.urlencode({
        "chat_id": str(chat_id), "text": teks, "disable_notification": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=8) as r:
        return _json.loads(r.read())["result"]["message_id"]


def _tg_edit(token, chat_id, message_id, teks):
    """Perbarui pesan Telegram yang sama (tanpa memicu notifikasi baru)."""
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "chat_id": str(chat_id), "message_id": str(message_id), "text": teks,
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/editMessageText", data=data)
    urllib.request.urlopen(req, timeout=8).read()


def _tg_delete(token, chat_id, message_id):
    """Hapus pesan Telegram (dipakai untuk membersihkan balon proses)."""
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "chat_id": str(chat_id), "message_id": str(message_id),
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/deleteMessage", data=data)
    urllib.request.urlopen(req, timeout=8).read()


# ==== SATU BALON PROSES PER PERINTAH (gaya Hermes) ====
# Semua langkah satu perintah dikumpulkan dulu, lalu ditampilkan di SATU pesan
# Telegram yang isinya diperbarui (edit) di tempat. Tidak lagi mengirim satu
# pesan per langkah, supaya ruang obrolan tidak penuh.
_TG_STEPS: Dict[str, list] = {}          # chat_id -> daftar entri langkah
_TG_MSG: Dict[str, dict] = {}            # chat_id -> {"token", "msg_id", "t0", "dibersihkan"}
_TG_KUNCI = threading.RLock()


def _tg_baris_langkah(entri: dict) -> str:
    """Ubah satu entri langkah menjadi satu baris ringkas untuk Telegram."""
    status = entri.get("status")
    teks = entri.get("text", "")
    if status == "info":
        return teks
    if status == "jalan":
        return f"⏳ {teks}"

    ikon = "⚠️" if status == "gagal" else "✅"
    hasil = (entri.get("hasil") or "").strip()
    for buang in ("✅ ", "⚠️ "):
        if hasil.startswith(buang):
            hasil = hasil[len(buang):].strip()
    durasi = entri.get("durasi")
    ekor = f" → {hasil}" if hasil else ""
    waktu = f" ({durasi} detik)" if durasi is not None else ""
    return f"{ikon} {teks}{ekor}{waktu}"


def _tg_susun_isi(chat_id: str, catatan: str = "") -> str:
    """Susun isi pesan proses dari seluruh langkah yang sudah tercatat."""
    baris = [_tg_baris_langkah(e) for e in _TG_STEPS.get(chat_id, [])]
    if catatan:
        baris.append(catatan)
    isi = "\n".join(b for b in baris if b)

    # Telegram membatasi ~4096 karakter: kalau kepanjangan, buang langkah paling awal
    while len(isi) > 3500 and len(baris) > 3:
        baris.pop(1)  # sisakan baris otak (paling atas)
        isi = "\n".join(b for b in baris if b)
    return isi[:4000]


def _tg_tampilkan(chat_id: str, catatan: str = "", paksa: bool = False):
    """Kirim (sekali) atau perbarui balon proses. Dijalankan di latar belakang."""
    if not chat_id:
        return

    def _kerja():
        try:
            with _TG_KUNCI:
                if _TG_MSG.get(chat_id, {}).get("dibersihkan"):
                    return
                token = _tg_token()
                if not token:
                    return
                isi = _tg_susun_isi(chat_id, catatan)
                if not isi:
                    return

                keadaan = _TG_MSG.setdefault(chat_id, {"token": token, "msg_id": None, "t0": time.monotonic()})
                mid = keadaan.get("msg_id")

                # Rem sederhana: jangan mengedit terlalu sering (batas Telegram)
                if mid and not paksa:
                    selisih = time.monotonic() - keadaan.get("t0", 0)
                    if selisih < 1.1:
                        time.sleep(1.1 - selisih)

                if not mid:
                    keadaan["msg_id"] = _tg_send(token, chat_id, isi)
                    keadaan["t0"] = time.monotonic()
                else:
                    _tg_edit(token, chat_id, mid, isi)
                    keadaan["t0"] = time.monotonic()
        except Exception as e:
            logger.debug(f"Gagal menampilkan balon proses: {e}")

    threading.Thread(target=_kerja, daemon=True).start()


def _tg_progress_mulai(chat_id):
    """Siapkan balon proses baru untuk satu perintah (dipanggil saat perintah masuk)."""
    if not chat_id:
        return
    with _TG_KUNCI:
        _TG_STEPS[chat_id] = []
        _TG_MSG[chat_id] = {"token": None, "msg_id": None, "t0": time.monotonic(), "dibersihkan": False}


def _tg_progress_bersihkan(chat_id, hapus: bool = True):
    """Hapus balon proses setelah jawaban akhir terkirim (gaya Hermes)."""
    if not chat_id:
        return
    with _TG_KUNCI:
        keadaan = _TG_MSG.get(chat_id) or {}
        keadaan["dibersihkan"] = True
        token, mid = keadaan.get("token") or _tg_token(), keadaan.get("msg_id")
        _TG_MSG[chat_id] = keadaan
        _TG_STEPS.pop(chat_id, None)

    if not hapus or not mid or not token:
        return

    def _kerja():
        try:
            _tg_delete(token, chat_id, mid)
        except Exception as e:
            logger.debug(f"Gagal menghapus balon proses: {e}")

    threading.Thread(target=_kerja, daemon=True).start()


def _step_begin(chat_id, teks: str):
    """Mulai satu langkah kerja: catat ke penampil Desktop & kepala balon proses Telegram."""
    handle = {
        "teks": teks,
        "t0": time.monotonic(),
        "chat_id": chat_id,
        "sink": None,
        "entri": None,
        "tg": None,
    }

    entri = {"id": 0, "text": teks, "status": "jalan", "durasi": None, "hasil": None}

    # Penampil proses UI Desktop
    try:
        sink = CURRENT_STEP_SINK.get()
        if sink:
            daftar = LIVE_STEPS.setdefault(sink, [])
            entri["id"] = len(daftar) + 1
            daftar.append(entri)
            handle["sink"] = sink
            handle["entri"] = entri
    except Exception:
        pass

    # Telegram: tambahkan sebagai baris di balon proses yang SAMA
    if chat_id:
        try:
            with _TG_KUNCI:
                daftar = _TG_STEPS.setdefault(chat_id, [])
                entri["id"] = len(daftar) + 1
                daftar.append(entri)
            handle["entri_tg"] = entri
            _tg_tampilkan(chat_id)
        except Exception as e:
            logger.debug(f"Gagal mencatat langkah Telegram: {e}")

    return handle


def _step_end(handle, hasil, ok: bool = True):
    """Selesaikan langkah: lengkapi dengan hasil + durasi (Desktop & Telegram)."""
    if not handle:
        return
    durasi = time.monotonic() - handle.get("t0", time.monotonic())

    hasil_bersih = " ".join(str(hasil or "").split())
    for buang in ("Error: ", "Tool Error: ", "Permission Denied: "):
        if hasil_bersih.startswith(buang):
            hasil_bersih = hasil_bersih[len(buang):]
    if len(hasil_bersih) > 90:
        hasil_bersih = hasil_bersih[:89] + "…"
    ikon = "✅" if ok else "⚠️"

    for kunci in ("entri", "entri_tg"):
        entri = handle.get(kunci)
        if entri is not None:
            entri["status"] = "selesai" if ok else "gagal"
            entri["durasi"] = round(durasi, 1)
            entri["hasil"] = f"{ikon} {hasil_bersih}".strip()

    if handle.get("entri_tg") is not None:
        _tg_tampilkan(handle.get("chat_id"))


def _push_line(chat_id, teks: str):
    """Baris informasi tunggal (misal otak yang sedang bekerja) tanpa hasil/durasi."""
    handle = _step_begin(chat_id, teks)
    for kunci in ("entri", "entri_tg"):
        if handle.get(kunci) is not None:
            handle[kunci]["status"] = "info"
            handle[kunci]["hasil"] = None
    if handle.get("entri_tg") is not None:
        _tg_tampilkan(chat_id)
    return handle


def _notify_tool_step(chat_id, func_name: str, func_args: dict):
    """Catat & tampilkan satu baris langkah kerja asisten (Telegram + UI Desktop)."""
    try:
        teks = _format_tool_step(func_name, func_args)
    except Exception:
        return None
    return _step_begin(chat_id, teks)


class PermissionDeniedError(Exception):
    pass

class ToolRegistry:
    """
    Sari AI Operating System - Central Tool Registry
    Sandboxed capabilities with explicit permission scopes.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register_tool(self, name: str, risk_level: str, handler: callable, description: str, schema: Dict[str, Any] = None):
        self._tools[name] = {
            "risk_level": risk_level, # LOW, MEDIUM, CRITICAL
            "handler": handler,
            "description": description,
            "schema": schema
        }
        logger.info(f"Registered tool {name} [Risk: {risk_level}]")
        
    def get_tool(self, name: str):
        return self._tools.get(name)

    def unregister_tool(self, name: str) -> bool:
        """Mencabut satu alat dari registry.

        WAJIB ada supaya sakelar ON/OFF plugin di Pengaturan benar-benar
        bekerja. Tanpa ini, mematikan plugin hanya mengubah daftar berkas di
        disk, sementara alat yang SUDAH terdaftar di memori tetap hidup dan
        tetap bisa dipanggil AI (mis. sadap_suara_ruangan tetap jalan walau
        plugin CCTV dimatikan).
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def unregister_banyak(self, nama_list) -> int:
        """Mencabut banyak alat sekaligus. Mengembalikan jumlah yang tercabut."""
        jumlah = 0
        for nm in list(nama_list or []):
            if self.unregister_tool(nm):
                jumlah += 1
        return jumlah

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        schemas = []
        for name, tool in self._tools.items():
            if tool.get("schema"):
                schemas.append({"type": "function", "function": tool["schema"]})
        return schemas

tool_registry = ToolRegistry()




# ============================================================================
# IZIN TINDAKAN KOMPUTER (Security Gate)
# ----------------------------------------------------------------------------
# Sebelumnya pengaturan "Mode Aman / Mode Otonom" di layar Pengaturan hanya
# tersimpan tanpa pernah dibaca, dan SELURUH alat didaftarkan bertingkat "LOW"
# sehingga tidak pernah ada yang dicek. Akibatnya Mode Aman tidak berpengaruh
# apa pun: perintah hapus file langsung dijalankan tanpa bertanya.
# ============================================================================

# Kata kunci pada NAMA alat yang menandakan tindakan merusak / mengubah data.
_KATA_BERISIKO = (
    "hapus", "buang", "kosongkan", "timpa", "overwrite", "format",
    "pindah", "ganti_nama", "rename", "ubah_nama",
    "instal", "uninstall", "pasang", "cabut",
    "telepon", "panggil",
)

# Tindakan tingkat sistem: selalu minta izin, bahkan di Mode Otonom.
_KATA_KRITIS = (
    "atur_daya", "matikan_pc", "restart_pc", "reboot", "shutdown", "mati_pc",
    "format_disk", "bersihkan_disk", "wipe",
)

# Penyimpanan izin sekali-pakai: person_id -> {"alat", "waktu", "deskripsi"}
_IZIN_MENUNGGU: Dict[str, Dict[str, Any]] = {}
_MASA_BERLAKU_IZIN = 900  # detik (15 menit) agar izin lama tidak nyangkut

# Kata balasan yang dianggap sebagai izin sah dari pengguna.
_FRASA_SETUJU = {
    "ya", "iya", "yak", "yap", "gas", "lanjut", "lanjutkan", "konfirmasi",
    "boleh", "setuju", "silakan", "oke", "ok", "ya silakan", "ya lanjut",
    "ya hapus", "benar", "betul", "ya benar", "setuju hapus", "tolong lanjutkan",
    "ya tolong", "silakan hapus",
}

# ---------------------------------------------------------------------------
# Bahaya tidak selalu ada di NAMA alat, tapi di ARGUMENnya.
# Contoh nyata yang lolos: alat bernama "kelola_file_lokal" (kedengaran tidak
# berbahaya) tapi dipanggil dengan action="delete" -> menghapus berkas.
# ---------------------------------------------------------------------------
_KUNCI_ARGUMEN_AKSI = ("action", "aksi", "operasi", "mode", "metode")
_NILAI_AKSI_BERISIKO = (
    "delete", "hapus", "remove", "buang", "kosongkan", "bersihkan",
    "overwrite", "timpa", "format", "wipe",
    "move", "pindah", "rename", "ganti_nama", "ubah_nama",
    "uninstall", "cabut", "install", "pasang",
)

_KUNCI_ARGUMEN_PERINTAH = ("perintah", "command", "cmd", "script", "kode")
_FRASA_SHELL_BERISIKO = (
    "del ", "del/", "erase ", "rmdir", "rm -", "rm /", "remove-item",
    "rd /", "rd/s", "format ", "unlink", "clear-content", "shutdown /s",
    "shutdown /r", "stop-process",
)


def risiko_dari_argumen(args) -> str:
    """Tentukan risiko dari ISI argumen, bukan hanya dari nama alat.

    Ini menutup celah alat yang namanya tidak mencurigakan tetapi argumennya
    memerintahkan penghapusan/penggantian (mis. action="delete").
    """
    if not isinstance(args, dict):
        return "LOW"

    for kunci, nilai in args.items():
        k = str(kunci).lower()
        v = str(nilai or "").lower()

        if k in _KUNCI_ARGUMEN_AKSI and any(b in v for b in _NILAI_AKSI_BERISIKO):
            return "MEDIUM"

        if k in _KUNCI_ARGUMEN_PERINTAH and any(b in v for b in _FRASA_SHELL_BERISIKO):
            return "MEDIUM"

    return "LOW"


_PERINGKAT_RISIKO = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}


def tingkat_risiko_efektif(nama_alat: str, deskripsi: str, args) -> str:
    """Ambil tingkat risiko tertinggi antara penilaian nama alat dan isi argumen."""
    dari_nama = klasifikasi_risiko(nama_alat, deskripsi)
    dari_args = risiko_dari_argumen(args)
    return max((dari_nama, dari_args), key=lambda t: _PERINGKAT_RISIKO.get(t, 0))


def klasifikasi_risiko(nama_alat: str, deskripsi: str = "") -> str:
    """Tentukan tingkat risiko alat: LOW / MEDIUM / CRITICAL.

    Dipakai saat pendaftaran alat supaya tidak lagi semua dianggap LOW.
    """
    n = (nama_alat or "").lower()
    d = (deskripsi or "").lower()
    if any(k in n for k in _KATA_KRITIS) or any(k in d[:200] for k in ("shutdown", "restart komputer", "matikan komputer")):
        return "CRITICAL"
    if any(k in n for k in _KATA_BERISIKO):
        return "MEDIUM"
    return "LOW"


def baca_mode_izin() -> str:
    """Baca pengaturan Mode Aman / Mode Otonom dari personalisasi.json."""
    try:
        f = PROJECT_ROOT / "personalisasi.json"
        if f.exists():
            with open(f, "r", encoding="utf-8") as pf:
                mode = str(json.load(pf).get("quality_gate_mode") or "safe").strip().lower()
                return "yolo" if mode == "yolo" else "safe"
    except Exception:
        pass
    return "safe"


def _teks_pengguna_terakhir(messages) -> str:
    """Ambil teks pesan terakhir dari pengguna (untuk menilai apakah ia menyetujui)."""
    for m in reversed(messages or []):
        try:
            if isinstance(m, dict) and m.get("role") == "user":
                return str(m.get("content") or "")
        except Exception:
            continue
    return ""


def _bersihkan_izin_kadaluarsa():
    sekarang = time.monotonic()
    for pid in list(_IZIN_MENUNGGU.keys()):
        if sekarang - _IZIN_MENUNGGU[pid].get("waktu", 0) > _MASA_BERLAKU_IZIN:
            _IZIN_MENUNGGU.pop(pid, None)


def _normalkan_teks_pengguna(teks) -> str:
    """Bersihkan teks pengguna dari awalan nama yang ditambahkan jembatan pesan.

    Pesan disimpan dengan bentuk "[Nama]: ya", sehingga tanpa pembersihan ini
    kata persetujuan 'ya' tidak akan pernah dikenali dan gerbang izin akan
    menolak terus walaupun pengguna sudah menyetujui.
    """
    t = str(teks or "").strip()
    m = re.match(r"^\[[^\]]{1,40}\]\s*:?\s*", t)
    if m:
        t = t[m.end():]
    return " ".join(t.lower().split())


def _pengguna_setuju(teks: str) -> bool:
    t = _normalkan_teks_pengguna(teks)
    if not t:
        return False
    if t in _FRASA_SETUJU:
        return True
    return len(t) <= 40 and any(t.startswith(f + " ") or t == f for f in ("ya", "iya", "gas", "lanjut", "setuju", "silakan", "oke", "ok"))


def _pesan_minta_izin(nama_alat: str, tingkat: str, u_call: str) -> str:
    label = "pengaturan daya komputer" if tingkat == "CRITICAL" else "tindakan yang mengubah/menghapus data"
    return (
        f"PERLU IZIN: Tindakan '{nama_alat}' termasuk {label}, sedangkan Mode Aman sedang aktif.\n"
        f"Alat ini BELUM dijalankan. Sampaikan kepada {u_call} secara jelas dan singkat apa yang akan "
        f"dilakukan, lalu minta dia membalas 'ya' bila setuju. Setelah dia membalas 'ya', panggil ulang "
        f"alat ini SEKALI lagi."
    )


class QualityGate:
    """
    Sari AI Operating System - Quality Gate / Decision Engine
    Evaluates LLM reasoning output before execution.
    """
    
    @staticmethod
    def evaluate_action(person_id: str, tool_name: str, args: Dict[str, Any], teks_pengguna: str = "") -> bool:
        """
        Evaluates if the requested action is safe to execute automatically.
        Returns True if safe, raises PermissionDeniedError if HITL (Human In The Loop) is required.

        Tingkat risiko dibaca dari hasil klasifikasi saat alat didaftarkan, dan
        keputusan mengikuti pengaturan Mode Aman / Mode Otonom di personalisasi.json.
        """
        tool = tool_registry.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} is not registered.")

        # Tingkat risiko dinilai ulang setiap panggilan: gabungan penilaian NAMA alat
        # dan ISI argumennya (mis. action="delete" pada alat yang namanya biasa saja).
        tingkat = tingkat_risiko_efektif(tool_name, tool.get("description", ""), args)

        if tingkat == "LOW":
            return True  # Aman dijalankan otomatis

        mode = baca_mode_izin()

        # Mode Otonom: tindakan tingkat sedang boleh langsung.
        # Tingkat CRITICAL (daya komputer) TETAP minta izin demi keamanan.
        if mode == "yolo" and tingkat == "MEDIUM":
            logger.info(f"Mode Otonom: '{tool_name}' [{tingkat}] dijalankan langsung.")
            return True

        # Mode Aman (atau tingkat CRITICAL): butuh izin pengguna.
        _bersihkan_izin_kadaluarsa()
        tunggu = _IZIN_MENUNGGU.get(person_id)
        if tunggu and tunggu.get("alat") == tool_name and _pengguna_setuju(teks_pengguna):
            _IZIN_MENUNGGU.pop(person_id, None)
            logger.info(f"Izin diterima untuk '{tool_name}'. Dijalankan satu kali.")
            return True

        _IZIN_MENUNGGU[person_id] = {"alat": tool_name, "waktu": time.monotonic()}
        logger.warning(f"'{tool_name}' [{tingkat}] DITAHAN: menunggu izin dari {person_id}.")
        raise PermissionDeniedError(_pesan_minta_izin(tool_name, tingkat, _get_user_call()))

class PersonaLayer:
    """Injects the personality constraints without mixing with logic."""
    
    # System knowledge about the user's machine.
    # Dihitung otomatis dari komputer yang sedang dipakai, BUKAN dipaku,
    # supaya aplikasi ini bisa jalan di komputer siapa pun.
    @staticmethod
    def _konteks_sistem() -> str:
        import os
        from pathlib import Path as _Path

        home = _Path.home()
        nama_pengguna = os.environ.get("USERNAME") or home.name
        return (
            "\n\n[KONTEKS SISTEM PC PENGGUNA]:\n"
            f"- Username Windows: '{nama_pengguna}'\n"
            f"- Path Desktop: {home / 'Desktop'}\n"
            f"- Path Documents: {home / 'Documents'}\n"
            f"- Path Downloads: {home / 'Downloads'}\n"
            f"- Folder aplikasi: {PROGRAM_ROOT}\n"
            f"- Folder data pengguna: {DATA_ROOT}\n"
            "- OS: Windows\n"
        )
    
    @staticmethod
    def get_system_prompt(platform="TELEGRAM", profile_id=None) -> str:
        # Muat konfigurasi personalisasi dinamis (Gaya, Nada, Nama Panggilan, Instruksi Khusus)
        import json
        pers_file = PROJECT_ROOT / "personalisasi.json"
        pers = {
            "bot_name": "Harmoni",
            "user_call_name": "Kak",
            "tone": "santai",
            "enthusiasm": "normal",
            "emoji_level": "sedikit",
            "format_style": "default",
            "custom_instructions": ""
        }
        if pers_file.exists():
            try:
                with open(pers_file, "r", encoding="utf-8") as pf:
                    pers.update(json.load(pf))
            except Exception:
                pass

        bot_name = pers.get("bot_name", "Harmoni")
        user_call = pers.get("user_call_name") or "Kak"
        tone = pers.get("tone", "santai")
        emoji_level = pers.get("emoji_level", "sedikit")
        custom_inst = pers.get("custom_instructions", "")

        tone_rules = ""
        if tone == "profesional":
            tone_rules = "- Gaya bicara: Profesional, lugas, formal, sopan dan to the point tanpa basa-basi berlebih.\n"
        elif tone == "ringkas":
            tone_rules = "- Gaya bicara: Sangat ringkas, padat, 1-2 kalimat jika memungkinkan, efisien waktu.\n"
        elif tone == "kreatif":
            tone_rules = "- Gaya bicara: Kreatif, puitis, kaya perbendaharaan kata, cocok untuk ide musik/lirik.\n"
        else:
            tone_rules = "- Gaya bicara: Santai, ramah, hangat, gaul dan bersahabat seperti anak buah yang loyal.\n"

        if emoji_level == "tanpa_emoji":
            tone_rules += "- ATURAN EMOJI: DILARANG MENGGUNAKAN EMOJI SAMA SEKALI demi kenyamanan screen reader.\n"
        elif emoji_level == "sedikit":
            tone_rules += "- ATURAN EMOJI: Gunakan emoji sangat minimal/tipis-tipis saja (maksimal 1 di akhir kalimat).\n"
        elif emoji_level == "banyak":
            tone_rules += "- ATURAN EMOJI: Gunakan emoji ceria untuk menghidupkan suasana.\n"

        if platform == "WHATSAPP":
            # Muat identitas usaha dari profil WA yang BENAR (multi-nomor)
            from sari_core.wa_profile import muat_profil_wa
            profil_wa = muat_profil_wa(profile_id)
            wa_bot_name = profil_wa["bot_name"]
            studio_name = profil_wa["business_name"]
            studio_address = profil_wa["business_address"]
            wa_tone = profil_wa["tone"]
            custom_info = profil_wa["custom_info"]
            portfolio = profil_wa["portfolio"]
            jenis_usaha = profil_wa["jenis_usaha"]
            owner_name = profil_wa.get("owner_name") or profil_wa.get("vip_numbers") or ""

            tone_desc = "Jawab dengan gaya bahasa gaul, hangat, natural (pakai haha, wkwk, santai). Panggil lawan bicara dengan Kak atau Mas/Mbak/Namanya."
            if wa_tone == "formal":
                tone_desc = "Jawab dengan gaya bahasa profesional, sopan, formal, dan santun sebagai representasi resmi layanan."
            elif wa_tone == "ringkas":
                tone_desc = "Jawab dengan gaya sangat ringkas, to the point, padat informasi (1-2 kalimat pendek)."
            elif wa_tone == "fokus_bisnis":
                tone_desc = (
                    "MODE FOKUS LAYANAN BISNIS: Kamu HANYA merespons hal-hal yang berkaitan dengan bisnis dan layanan "
                    f"'{studio_name}' (seperti harga, jenis layanan, jam operasional, alamat, sampel/portofolio, dan reservasi/booking). "
                    "Jika pelanggan menanyakan atau mengajak bicara di luar topik bisnis (misal curhat, gosip, politik, candaan iseng, "
                    "atau hal di luar usaha), TOLAK DENGAN RAMAH, SOPAN, DAN TEGAS. Katakan bahwa nomor WhatsApp ini "
                    f"dikhususkan untuk informasi dan layanan '{studio_name}', lalu tawarkan apakah ada hal seputar layanan yang bisa dibantu."
                )

            info_layanan_block = (
                f"[LAYANAN & HARGA RESMI DARI PEMILIK - JADIKAN SATU-SATUNYA ACUAN]:\n{custom_info}\n"
                if custom_info else
                "[LAYANAN & HARGA RESMI DARI PEMILIK]: (belum diisi pemilik, jangan mengarang harga/layanan)\n"
            )
            portfolio_block = f"[PORTOFOLIO / LINK RESMI UNTUK DIBAGIKAN KE KLIEN]: {portfolio}\n" if portfolio else ""

            portfolio_rule = (
                f"15. PEMBAGIAN PORTOFOLIO / CONTOH KARYA: Jika pelanggan meminta contoh, portofolio, hasil karya, audio/video sampel, "
                f"atau link resmi kami, kamu WAJIB menyertakan tautan portofolio berikut dalam balasanmu: {portfolio}\n"
                if portfolio else ""
            )

            owner_rule = (
                f"16. IDENTITAS PEMILIK USAHA: Pemilik/pimpinan dari usaha '{studio_name}' adalah '{owner_name}'. "
                f"Hanya sebutkan nama pemilik jika pelanggan SECARA EKSPLISIT BERTANYA siapa pemilik/owner/bos/pengelola usaha ini. "
                "Jika pelanggan tidak bertanya, JANGAN pernah menyebutkan nama pemilik secara sembarangan.\n"
                if owner_name else ""
            )

            base_prompt = (
                f"NAMA KAMU ADALAH {wa_bot_name}. KAMU ADALAH ADMIN PELAYANAN WHATSAPP DARI USAHA '{studio_name}'.\n"
                f"ATURAN MUTLAK NAMA: Nama kamu MURNI '{wa_bot_name}'. DILARANG memakai nama lain.\n"
                f"ATURAN IDENTITAS & KERAHASIAAN (SANGAT PENTING):\n"
                f"1. Kamu mewakili usaha '{studio_name}' saja, bukan asisten pribadi siapa pun.\n"
                "2. KERAHASIAAN IDENTITAS: DILARANG menyebut nama keluarga, nomor pribadi keluarga, atau urusan rumah tangga. Jika pelanggan bertanya siapa pemilik usaha ini, jawab sesuai data nama pemilik resmi di bawah (jika ada).\n"
                "3. DILARANG menawarkan atau menyebut jasa yang tidak ada di daftar layanan resmi di bawah.\n"
                f"ATURAN DATA TERBARU & LAYANAN (WAJIB DIPATUHI):\n"
                "4. KEBENARAN DATA TERBARU: Data layanan, jam operasional, dan tarif resmi di bawah ini adalah KEBENARAN UTAMA YANG PALING MUTAKHIR. Jika pada obrolan sebelumnya kamu pernah menjawab belum tahu, belum ada info, atau akan konfirmasi ke admin, ABAIKAN jawaban lama itu dan jawab sekarang menggunakan data mutakhir di bawah.\n"
                "5. JAM OPERASIONAL & TARIF: Jika pelanggan bertanya jam buka/tutup atau tarif, LANGSUNG jawab dengan jelas dan ramah sesuai data resmi di bawah. Dilarang menunda atau bilang akan tanya admin untuk hal yang sudah tertulis di data.\n"
                "6. PENJELASAN ISTILAH LAYANAN: Jika pelanggan bertanya arti istilah atau perbedaan jenis layanan (misalnya apa bedanya massage/pijat, shiatsu, dan refleksi, atau apa itu mixing dan mastering), kamu BOLEH dan DIANJURKAN menjelaskannya secara ramah, ringkas (1-3 kalimat), dan informatif menggunakan pengetahuan umum yang relevan. Yang dilarang adalah mengarang tarif baru atau menawarkan layanan di luar daftar resmi.\n"
                "7. ARAHAN 'HUBUNGI ADMIN': Jika ada kalimat seperti 'silakan hubungi admin' atau 'konsultasi ke admin', itu adalah opsi yang kamu tawarkan KEPADA PELANGGAN jika mereka membutuhkan konsultasi khusus atau booking terapis. JANGAN jadikan kalimat itu alasan kamu menolak menjawab pertanyaan yang bisa kamu jelaskan.\n"
                "8. Jika ada pertanyaan khusus yang BENAR-BENAR belum tercantum di data dan di luar pengetahuan umum (misal request diskon khusus, negosiasi harga, ketersediaan terapis tertentu di jam tertentu), katakan dengan sopan bahwa kamu akan konfirmasi ke admin/pemilik — TANPA menyebut nama siapa pun.\n"
                f"ATURAN NGOBROL:\n"
                f"9. Kamu adalah CS yang ramah. {tone_desc}\n"
                "10. Jika pelanggan hanya menyapa atau mengobrol bebas, balas ramah dan singkat. JANGAN langsung menyodorkan daftar harga yang tidak ditanya.\n"
                "11. Jika pelanggan bertanya soal layanan, harga, atau cara pesan, jawab berdasarkan data resmi di bawah.\n"
                f"12. ATURAN ALAMAT: DILARANG menyebut alamat bila pelanggan tidak bertanya. Jika ditanya, alamatnya: {studio_address or 'belum tersedia, katakan akan dikonfirmasi ke admin'}\n"
                "13. Jika ada topik terlarang (SARA, penipuan, pinjam uang, spam), tolak dengan halus dan alihkan pembicaraan.\n"
                f"14. Balasan WA harus PENDEK (1-3 kalimat) seperti chat WA asli. JANGAN memakai tanda bintang/markdown berlebihan.\n"
                f"{portfolio_rule}"
                f"{owner_rule}"
                f"{info_layanan_block}"
                f"{portfolio_block}"
            )

            # --- RAG Injection: HANYA untuk usaha studio musik/rekaman ---
            if jenis_usaha == "recording":
                try:
                    import os
                    harga_path = str(OBSIDIAN_DIR / "02_Basis_Pengetahuan" / "keuangan_Daftar_Harga_Recording.md")
                    if not os.path.exists(harga_path):
                        harga_path = str(OBSIDIAN_DIR / "02_Pengetahuan_Studio" / "keuangan_Daftar_Harga_Recording.md")
                    if os.path.exists(harga_path):
                        with open(harga_path, "r", encoding="utf-8") as f:
                            isi_harga = f.read()
                        base_prompt += "\n\n[MEMORI OBSIDIAN TERKAIT - HARGA STUDIO]:\n" + isi_harga
                except Exception as e:
                    print('RAG ERROR:', e)
        else:
            inst_block = f"[INSTRUKSI KHUSUS DARI PENGGUNA]:\n{custom_inst}\n" if custom_inst else ""
            base_prompt = (
                f"Kamu adalah {bot_name}, asisten AI otonom tingkat dewa, sekaligus anak buah/asisten pribadi dari {user_call}.\n"
                f"Nama kamu murni '{bot_name}'. Panggil lawan bicaramu dengan sebutan '{user_call}'.\n"
                f"{tone_rules}"
                f"{inst_block}"
                "Kamu bekerja sama dengan asisten WhatsApp yang menangani pesan pelanggan. "
                "Nama asisten WhatsApp itu diatur terpisah per profil nomor, jangan menebak namanya. "
                "PENTING: kamu dan asisten WhatsApp itu menangani urusan yang BERBEDA. "
                "Jangan pernah menyebut nama pemilik kepada pelanggan, dan jangan mencampur "
                "informasi satu usaha dengan usaha lainnya.\n"
                f"Tugas utamamu adalah membantu semua pekerjaannya di komputer dengan sigap, sopan, ramah, dan cekatan.\n\n"
            
            "KEMAMPUAN UTAMA:\n"
            "1. Kamu PUNYA KENDALI PENUH pada komputer (mouse, keyboard, file, aplikasi) melalui alat-alat (tools) yang disediakan.\n"
            "2. PENTING: Untuk memeriksa video terbaru dari channel YouTube orang lain atau channel publik (contoh: 'cek vidio terbaru sanstekno', 'cek channel gadgetin'), WAJIB langsung gunakan tool 'cek_youtube_channel_publik(nama_channel=...)'. DILARANG membuka browser Chrome di komputer kecuali pengguna secara eksplisit meminta 'buka browser' atau 'buka chrome'.\n"
            "3. Kamu BISA MEMBUAT VIDEO YOUTUBE SECARA OTOMATIS menggunakan alat 'buat_video_youtube'.\n"
            "4. Kamu bisa mengontrol DAW REAPER (play, stop, record, dll) menggunakan alat 'kontrol_reaper'.\n"
            "5. JIKA DISURUH MEMBUAT VIDEO LIRIK, WAJIB gunakan alat 'buat_video_lirik'.\n"
            "6. Untuk mengirim WhatsApp (pesan teks: 'kirim_pesan_whatsapp', pesan suara/VN: 'kirim_vn_whatsapp', file/dokumen: 'kirim_file_whatsapp'): Parameter 'nama_kontak' bisa berupa nomor telepon ATAU nama orang/panggilan (misal: 'istri', 'Tubagus Abiem', 'Bang Ceper'). Sistem otomatis mencocokkan nama ke nomor telepon. Jika pengguna menyebutkan profil pengirim ('nomor 1', 'nomor 2', 'studio', 'pijat'), WAJIB sertakan di parameter 'profile_id'. Jika TIDAK menyebutkan profil pengirim, KOSONGKAN 'profile_id' agar sistem memunculkan tombol konfirmasi nomor pengirim.\n"
            "6b. Untuk membuat/mengunggah Status (Story) WhatsApp: gunakan alat 'kirim_status_whatsapp(teks=..., path_file=..., profile_id=...)'. Untuk mengecek penonton status WhatsApp: gunakan 'cek_penonton_status_whatsapp(profile_id=...)'.\n"
            "6c. Untuk mengatur Mode Sibuk / Jam Kerja WhatsApp: gunakan alat 'atur_mode_sibuk_wa(profile_id=..., mode='always'/'outside_hours'/'off', pesan=..., jam_buka=..., jam_tutup=...)'. Untuk mengelola jawaban kilat FAQ instan (tanpa kuota AI): gunakan 'tambah_jawaban_kilat_wa', 'daftar_jawaban_kilat_wa', 'hapus_jawaban_kilat_wa'.\n"
            "6d. Untuk membaca pesan/chat WhatsApp yang baru masuk: gunakan alat 'baca_pesan_terakhir_wa(profile_id=..., jumlah=5)'. Parameter 'profile_id' bisa diisi 'nomor_1' atau 'nomor_2' jika pengguna menyebutkan profil tertentu, atau dikosongkan untuk melihat semua nomor. PENTING: Saat melaporkan hasil baca_pesan_terakhir_wa, kamu WAJIB MENYERTAKAN SELURUH TEKS DAN TAG [AKSI_BALAS_WA: ...] persis apa adanya dari output alat tanpa dipotong atau diubah, agar tombol balas interaktif bisa muncul di layar pengguna!\n"
            "6e. Untuk memeriksa kuota token / saldo model AI (9Router Antigravity, OpenRouter, DeepSeek, Groq, dll): gunakan alat 'cek_sisa_kuota_token(provider=...)'. Parameter 'provider' bisa diisi '9router' (khusus Antigravity), 'openrouter', 'deepseek', 'groq', atau dikosongkan untuk melihat ringkasan seluruh provider.\n"
            "7. Jika diminta mencari chord/kunci gitar, gunakan alat 'cari_chord_lagu'.\n"
            "7b. Untuk mengunduh software/installer dari halaman artikel website (seperti blindhelp.net, blog, forum download): gunakan alat 'unduh_dari_halaman_web(url=..., pilihan_kata_kunci='x64')'. Alat ini otomatis mencari tombol unduh asli, membypass redirect, dan mendownload filenya ke disk.\n"
            "7c. JIKA PENGGUNA MEMINTA MEMASANG / MENGINSTAL SOFTWARE, APLIKASI, ATAU ADD-ON: gunakan alat 'pasang_atau_install_software(target=...)'. Alat serbaguna ini bisa menginstall aplikasi via Winget (seperti VLC, 7zip), mengeksekusi installer mentah (.exe, .msi), mengekstrak arsip (.7z, .zip), atau memasang add-on NVDA (.nvda-addon). PENTING: DILARANG menginstall/memasang otomatis tanpa perintah/permintaan eksplisit dari pengguna!\n"
            "8. Jika disuruh mengirim email, SELALU gunakan fungsi 'kirim_email'.\n"
            "8b. ATURAN ALAMAT KLIEN: Saat berinteraksi (di Telegram/Email), DILARANG KERAS memberikan informasi lokasi/alamat studio secara proaktif kecuali klien bertanya secara spesifik.\n"
            f"9. ATURAN PENJADWALAN MASA DEPAN TERKUNCI: Jika {user_call} menyebutkan waktu/jam di masa depan (seperti 'nanti jam 08:16 play...', 'nanti jam 07:46 kirim WA...'), kamu WAJIB MEMANGGIL ALAT 'jadwalkan_tugas_otomatis'! DILARANG KERAS memanggil 'pasang_pengingat' untuk tugas aksi! Alat 'pasang_pengingat' HANYA untuk alarm pengingat suara speaker (misal 'ingatkan aku sholat').\n"
            f"9b. ATURAN JADWAL LAPOR BERITA & PESAN TELEGRAM: Jika {user_call} meminta jadwal berita, laporan, update, atau berkata 'lapor ke saya', 'infokan ke saya', 'kasih saya berita', atau 'kirim ke saya' dari Telegram TANPA menyebut kata 'speaker'/'suara'/'bacakan keras', kamu WAJIB menggunakan fungsi_aksi 'lapor_telegram' agar pesan terkirim sebagai CHAT TEKS KE TELEGRAM {user_call}! DILARANG KERAS menggunakan 'berbicara_lewat_pc' jika tidak disuruh membacanya di speaker!\n"
            f"9c. ATURAN JADWAL BERULANG / MULTI-HARI: Jika {user_call} meminta jadwal yang berulang selama beberapa hari atau menit (contoh: 'selama 5 hari setiap jam 9 pagi', 'setiap 1 menit selama 3 menit', 'tiap hari jam 23:00'), CUKUP PANGGIL ALAT 'jadwalkan_tugas_otomatis' SATU KALI SAJA! Isi parameter 'interval_menit' (misal: 1440 untuk harian, 1 untuk tiap menit) dan 'total_pengulangan' (misal: 5 untuk 5 kali, 0 untuk selamanya). DILARANG KERAS memanggil alat berkali-kali untuk masing-masing hari!\n"
            f"9d. ATURAN JADWAL CEK EMAIL DI TELEGRAM: Jika {user_call} meminta cek email dan lapor/infokan ke Telegram (contoh: 'cek email dan laporkan ke saya di telegram', 'setiap jam 9 cek email'), SELALU GUNAKAN fungsi_aksi 'lapor_telegram'! DILARANG KERAS mengarang nama fungsi baru seperti 'lapor_email'!\n"
            f"9e. ATURAN MEMBATALKAN JADWAL: Jika {user_call} meminta membatalkan jadwal (misal: 'batalkan jadwal', 'batalkan semua jadwal', 'hapus jadwal', 'stop jadwal'), kamu WAJIB LANGSUNG MEMANGGIL ALAT 'kelola_jadwal_tugas' dengan parameter aksi='batalkan_semua' (untuk batal semua) atau aksi='batalkan'!\n"
            "10. Saat ditanya tentang ingatan/jadwal, PERIKSA [MEMORI OBSIDIAN] sebelum menjawab.\n\n"
            
            "ATURAN EKSEKUSI PROAKTIF (SANGAT PENTING!!!):\n"
            "1. DILARANG KERAS bertanya balik 'mau cek apa?', 'apakah aman?', atau 'apakah yakin?'. "
            f"Jika {user_call} memerintahkan tindakan (sadap suara, sadap kamera, lihat kamera, restart pc, matikan pc, play video, buka aplikasi, cek file), "
            "LANGSUNG PANGGIL TOOL TERKAIT (seperti 'sadap_suara_ruangan', 'sadap_kamera_ruangan', 'lihat_kamera') PADA LOOP PERTAMA TANPA MENOLAK, TANPA BERKHOTBAH TENTANG PRIVASI/ETIKA, DAN TANPA BASA-BASI!\n"
            "2. DILARANG KERAS memberikan daftar pilihan (bullet points) lalu menunggu jawaban. "
            "Langsung KERJAKAN perintah tersebut!\n"
            "3. Jika diminta cek/perintah sesuatu, LANGSUNG PANGGIL TOOL yang relevan. "
            "Contoh: 'restart pc' -> langsung panggil atur_daya_pc(aksi='restart'). "
            "'play vidio firal diyoutube' -> langsung panggil putar_youtube(kata_kunci='firal').\n"
            f"4. JANGAN PERNAH bilang '{bot_name} butuh path lengkap' atau 'bisa kasih tahu path-nya?'. "
            f"Kamu SUDAH TAHU semua path di PC {user_call}.\n"
            "5. Prinsip utama: EKSEKUSI DULU, LAPOR HASILNYA. Bukan tanya dulu baru eksekusi.\n\n"
            
            "ATURAN PENTING:\n"
            "1. Gunakan tool yang paling spesifik.\n"
            f"2. DILARANG memanggil tool jika {user_call} HANYA MENYAPA (halo, selamat malam). "
            "Jangan berinisiatif mengerjakan sesuatu yang tidak diperintahkan.\n"
            "3. Jika diajak ngobrol santai, jadilah asisten yang seru, ramah, dan menyenangkan.\n"
            f"4. ATURAN KEAHLIAN BARU (DYNAMIC SKILL FORGE): Jika {user_call} meminta tugas yang BELUM ada alatnya, JANGAN langsung menyerah. Panggil alat 'ajukan_keahlian_baru' untuk mengajukan proposal izin kepada {user_call}.\n"
            f"5. HANYA panggil 'eksekusi_rakit_keahlian' jika {user_call} secara sadar membalas persetujuan ('ya', 'gas', 'lanjutkan', 'buat') terhadap proposal yang baru saja diajukan. DILARANG memanggilnya di luar konteks persetujuan.\n"
            "6. ATURAN PEMBELAJARAN MANDIRI (SELF-IMPROVEMENT & SOP LEARNING):\n"
            f"- Jika {user_call} mengajarkan aturan baru, memberikan koreksi, atau menetapkan SOP/standar kerja (contoh: 'mulai sekarang kalau kirim pesan...', 'aturan kerja...', 'koreksi saya: ...', 'catat aturan ini...'), kamu WAJIB memanggil alat 'catat_memori_obsidian' dengan kategori yang relevan ('klien', 'keuangan', 'peralatan', 'proyek', atau 'umum')!\n"
            "- Tuliskan catatan sebagai instruksi operasional yang ringkas dan jelas agar mudah dipatuhi.\n"
            "- Setelah mencatat, sertakan badge bukti pembelajaran di akhir jawaban:\n"
            "  💾 _[Self-improvement review: Aturan/SOP '<topik>' berhasil dipelajari dan dicatat ke Vault]_\n"
            f"- Di sesi berikutnya, selalu periksa memori Obsidian agar kamu tidak mengulangi kesalahan dan selalu patuh pada arahan {user_call}.\n"
            f"7. ANTI-OVERTRIGGER: DILARANG KERAS memanggil alat pembersihan/reset memori hanya karena ada kata 'reset' atau 'clear' dalam obrolan bahasa Inggris atau kalimat santai {user_call}.\n\n"
        )
        
        from datetime import datetime
        base_prompt += PersonaLayer._konteks_sistem()
        base_prompt += f"- Waktu Real-Time Sistem PC saat ini: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # Injeksi aturan kustom dari ingatan permanen (Dynamic Custom Instructions)
        try:
            import json
            import os
            mem_path = str(PROJECT_ROOT / "ingatan_sari.json")
            if os.path.exists(mem_path):
                with open(mem_path, "r", encoding="utf-8") as f:
                    mem_data = json.load(f)
                    aturan_list = mem_data.get("catatan", {}).get("aturan", [])
                    if aturan_list:
                        base_prompt += f"\n\nATURAN KUSTOM DARI {user_call} (WAJIB DIPATUHI SELAMANYA):\n"
                        for at in aturan_list:
                            base_prompt += f"- {at}\n"
        except Exception:
            pass
        
        # Katalog Keahlian Prosedural (Markdown Skills On-Demand)
        try:
            from sari_core.skills_manager import get_skills_catalog_prompt
            skills_cat = get_skills_catalog_prompt()
            if skills_cat:
                base_prompt += f"\n\nKATALOG KEAHLIAN PROSEDURAL (SKILLS ON-DEMAND):\n{skills_cat}\n"
        except Exception:
            pass

        return base_prompt

class ReasoningLayer:
    """
    The Brain - Generates responses or tool calls based on ConversationState.
    """
    @staticmethod
    async def process_state(state, chat_id_override=None) -> Dict[str, Any]:
        """
        Multi-Provider Reasoning Engine.
        Urutan: Groq GPT-OSS 120B -> DeepSeek V3 (Chat) -> MiMo V2.5 -> Gemini 3.8 Flash.
        """
        from sari_core.memory_broker import memory_broker
        from openai import OpenAI
        
        logger.info(f"Reasoning Layer processing state for {state.person_id} at revision {state.revision_number}")

        # Satu balon proses per perintah (gaya Hermes): bersihkan sisa perintah sebelumnya.
        if chat_id_override:
            try:
                _tg_progress_mulai(chat_id_override)
            except Exception:
                pass

        # Auto-Compaction: Padatkan riwayat percakapan lampau otomatis jika obrolan panjang
        try:
            from sari_core.compaction import run_auto_compaction_if_needed
            pointers = await run_auto_compaction_if_needed(state, memory_broker)
            if pointers:
                state.context_pointers.update(pointers)
        except Exception as e_comp:
            logger.warning(f"[ReasoningLayer] Auto-Compaction lewati kendala: {e_comp}")

        # Build Messages Array (OpenAI format - works for MiMo & DeepSeek directly)
        messages = [{"role": "system", "content": PersonaLayer.get_system_prompt(platform=state.platform, profile_id=getattr(state, "wa_profile_id", None))}]

        # Sisipkan ringkasan percakapan lampau jika sudah dipadatkan
        compacted_summary = (state.context_pointers or {}).get("compacted_summary")
        if compacted_summary:
            messages.append({
                "role": "system",
                "content": f"[RINGKASAN KONTEKS PERCAKAPAN SEBELUMNYA / COMPACTED BOOKMARK]:\n{compacted_summary}\n[LANJUTAN PERCAKAPAN AKTIF]"
            })

        # Auto-Load Skill Markdown yang relevan dengan pertanyaan pengguna
        try:
            from sari_core.skills_manager import match_skills_for_context, get_skill_content
            last_text = ""
            for m in reversed(state.recent_messages or []):
                if m.get("role") == "user":
                    last_text = str(m.get("content", ""))
                    break
            if last_text:
                matched_skills = match_skills_for_context(last_text)
                for sk in matched_skills[:2]:
                    sk_content = get_skill_content(sk["name"])
                    if sk_content:
                        messages.append({
                            "role": "system",
                            "content": f"[PROSEDUR KERJA / SKILL AKTIF: {sk['name']}]\n{sk_content}"
                        })
                        logger.info(f"[ReasoningLayer] Skill '{sk['name']}' aktif otomatis untuk konteks ini.")
        except Exception as e_sk_load:
            logger.warning(f"Gagal auto-load skill: {e_sk_load}")

        # Injeksi persetujuan pengguna jika sedang menunggu izin
        try:
            tunggu = _IZIN_MENUNGGU.get(state.person_id)
            if tunggu and last_text and _pengguna_setuju(last_text):
                alat_tunggu = tunggu.get("alat")
                messages.append({
                    "role": "system",
                    "content": f"[KONFIRMASI IZIN RESMI]: {_get_user_call()} telah menyetujui ('{last_text}') tindakan '{alat_tunggu}'. Kamu WAJIB LANGSUNG memanggil tool '{alat_tunggu}' sekarang tanpa basa-basi!"
                })
        except Exception:
            pass
        
        # Sanitize recent_messages: repair any orphaned assistant tool_calls from previous interruptions
        sanitized_recent = []
        for i, m in enumerate(state.recent_messages):
            sanitized_recent.append(m)
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
                tool_call_ids = [tc["id"] for tc in m["tool_calls"] if isinstance(tc, dict) and "id" in tc]
                found_ids = set()
                j = i + 1
                while j < len(state.recent_messages) and isinstance(state.recent_messages[j], dict) and state.recent_messages[j].get("role") == "tool":
                    found_ids.add(state.recent_messages[j].get("tool_call_id"))
                    j += 1
                for missing_id in set(tool_call_ids) - found_ids:
                    sanitized_recent.append({
                        "role": "tool",
                        "tool_call_id": missing_id,
                        "name": "eksekusi_alat",
                        "content": "Aksi telah diselesaikan sebelumnya."
                    })

        # Ringkas context window aktif untuk LLM (jaga pesan terbaru agar hemat token & cepat)
        active_window_limit = 10 if compacted_summary else 18
        if len(sanitized_recent) > active_window_limit:
            sanitized_recent = sanitized_recent[-active_window_limit:]
            while sanitized_recent and sanitized_recent[0].get("role") == "tool":
                sanitized_recent.pop(0)
            while sanitized_recent and sanitized_recent[0].get("role") == "assistant" and sanitized_recent[0].get("tool_calls"):
                if len(sanitized_recent) == 1 or sanitized_recent[1].get("role") != "tool":
                    sanitized_recent.pop(0)
                else:
                    break

        # Hemat Token: Padatkan output alat lampau (> 800 karakter) yang sudah lewat dari giliran sebelumnya
        # Semua pesan user dan jawaban asisten tetap 100% utuh tanpa dipotong sedikit pun!
        for idx, item in enumerate(sanitized_recent[:-3]):
            if isinstance(item, dict) and item.get("role") == "tool":
                c = str(item.get("content", ""))
                if len(c) > 800:
                    item["content"] = c[:500] + "\n...[output alat lampau dipadatkan untuk hemat token]"

        messages.extend(sanitized_recent)
        
        # Extract last user messages for Smart Tool Filtering
        last_user_msg = ""
        user_msgs = [m.get("content", "") for m in state.recent_messages if m.get("role") == "user"]
        if user_msgs:
            latest_msg = user_msgs[-1].strip().lower()
            short_acks = ["ok", "oke", "siap", "makasih", "terima kasih", "thanks", "sip", "mantap", "keren", "ya", "iya", "halo", "hai", "p"]
            if latest_msg in short_acks or (len(latest_msg.split()) <= 3 and any(latest_msg.startswith(a) for a in short_acks)):
                last_user_msg = user_msgs[-1]
            else:
                last_user_msg = " ".join(user_msgs[-2:])

        all_schemas = tool_registry.get_all_schemas()

        if state.platform == "WHATSAPP":
            tools = []
            logger.info(f"[ReasoningLayer] Tools DISABLED for WHATSAPP platform (Security).")
        else:
            # Semua alat aktif dan siap digunakan.
            tools = all_schemas
            logger.info(f"[ReasoningLayer] {len(tools)} alat aktif dikirim ke AI.")
        
        # === SISTEM MULTI-MODEL FLEKSIBEL DENGAN RANTAI CADANGAN OTOMATIS ===
        from sari_core.model_config import get_active_model_info, load_model_config, resolve_model_for_task
        
        # Ekstrak teks pesan terakhir user untuk mendeteksi divisi spesialis
        last_user_text = ""
        has_media = False
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_text = str(m.get("content", ""))
                break
                
        task_info = resolve_model_for_task(
            text=last_user_text,
            has_media=has_media,
            platform=getattr(state, "platform", "TELEGRAM")
        )
        chosen_model_id = task_info.get("model", "gemini-3.8-flash")
        show_footer = task_info.get("show_footer", True)
        is_specialist = task_info.get("is_specialist", False)
        specialist_role = task_info.get("specialist_role", "")

        from sari_core.model_config import get_provider_keys
        gemini_keys = get_provider_keys("gemini")
        deepseek_keys = get_provider_keys("deepseek")
        openai_keys = get_provider_keys("openai")
        mimo_keys = get_provider_keys("mimo")
        openrouter_keys = get_provider_keys("openrouter")

        gemini_key = gemini_keys[0] if gemini_keys else None
        deepseek_key = deepseek_keys[0] if deepseek_keys else None
        openai_key = openai_keys[0] if openai_keys else None
        mimo_key = mimo_keys[0] if mimo_keys else None
        openrouter_key = openrouter_keys[0] if openrouter_keys else None

        # Bangun kamus seluruh model yang siap digunakan
        model_candidates = {}

        # 1. PRIORITAS CADANGAN UTAMA: DeepSeek (Hemat kuota, respons super cepat, dan stabil)
        if deepseek_key:
            model_candidates["deepseek-flash"] = {
                "nama": "DeepSeek V4.1 Flash",
                "client": OpenAI(base_url="https://api.deepseek.com", api_key=deepseek_key),
                "model": "deepseek-flash",
                "type": "openai"
            }
            model_candidates["deepseek-chat"] = {
                "nama": "DeepSeek V3 Chat",
                "client": OpenAI(base_url="https://api.deepseek.com", api_key=deepseek_key),
                "model": "deepseek-chat",
                "type": "openai"
            }
            model_candidates["deepseek-reasoner"] = {
                "nama": "DeepSeek R1 Reasoner",
                "client": OpenAI(base_url="https://api.deepseek.com", api_key=deepseek_key),
                "model": "deepseek-reasoner",
                "type": "openai"
            }

        # 2. PRIORITAS CADANGAN KEDUA: Gemini (Hanya dipanggil jika DeepSeek juga mengalami kendala)
        if gemini_key:
            model_candidates["gemini-2.5-flash"] = {
                "nama": "Google Gemini 2.5 Flash",
                "client": None,
                "model": "gemini-2.5-flash",
                "type": "gemini",
                "api_key": gemini_key
            }
            model_candidates["gemini-3.8-flash"] = {
                "nama": "Google Gemini 3.8 Flash",
                "client": None,
                "model": "gemini-3.8-flash",
                "type": "gemini",
                "api_key": gemini_key
            }
            model_candidates["gemini-2.5-pro"] = {
                "nama": "Google Gemini 2.5 Pro",
                "client": None,
                "model": "gemini-2.5-pro",
                "type": "gemini",
                "api_key": gemini_key
            }

        if openai_key:
            model_candidates["gpt-4o-mini"] = {
                "nama": "OpenAI GPT-4o Mini",
                "client": OpenAI(api_key=openai_key),
                "model": "gpt-4o-mini",
                "type": "openai"
            }
            model_candidates["gpt-4o"] = {
                "nama": "OpenAI GPT-4o (Flagship)",
                "client": OpenAI(api_key=openai_key),
                "model": "gpt-4o",
                "type": "openai"
            }

        if mimo_key:
            model_candidates["mimo-v2.5"] = {
                "nama": "MiMo V2.5",
                "client": OpenAI(base_url="https://api.xiaomimimo.com/v1", api_key=mimo_key),
                "model": "mimo-v2.5",
                "type": "openai"
            }

        # Periksa apakah chosen_model_id adalah model kustom (OpenRouter / 9Router / lainnya) di konfigurasi
        cfg_models = load_model_config().get("available_models", {})
        active_custom_entry = None
        for m_entry in cfg_models.values():
            if m_entry.get("id") == chosen_model_id:
                active_custom_entry = m_entry
                break

        # Jika model adalah model kustom (9Router / OpenRouter / provider lain), HARUS selalu menimpa model bawaan
        # agar tidak tertabrak nama ID yang sama (misalnya 'gemini-2.5-pro' milik Google Gemini resmi)
        if active_custom_entry and (chosen_model_id not in model_candidates or active_custom_entry.get("custom") or active_custom_entry.get("provider") in ["9router", "ninerouter", "antigravity", "openrouter", "cerebras", "sambanova", "together", "mistral", "qwen", "alibaba", "xai", "grok", "perplexity", "cohere", "ollama"]):
            c_provider = active_custom_entry.get("provider", "openrouter")
            c_name = active_custom_entry.get("name", chosen_model_id)
            c_base_url = active_custom_entry.get("base_url")
            
            c_key = None
            if c_provider in ["9router", "ninerouter", "antigravity"]:
                c_key = os.getenv("9ROUTER_API_KEY") or os.getenv("NINEROUTER_API_KEY") or "9router-local"
                c_base_url = c_base_url or "http://localhost:20128/v1"
            elif c_provider == "openrouter":
                c_key = openrouter_key
                c_base_url = c_base_url or "https://openrouter.ai/api/v1"
            elif c_provider == "deepseek":
                c_key = deepseek_key
                c_base_url = c_base_url or "https://api.deepseek.com"
            elif c_provider == "openai":
                c_key = openai_key
                c_base_url = c_base_url or "https://api.openai.com/v1"
            elif c_provider == "groq":
                c_key = os.getenv("GROQ_API_KEY_1") or os.getenv("GROQ_API_KEY")
                c_base_url = c_base_url or "https://api.groq.com/openai/v1"
            elif c_provider == "cerebras":
                c_key = os.getenv("CEREBRAS_API_KEY")
                c_base_url = c_base_url or "https://api.cerebras.ai/v1"
            elif c_provider == "sambanova":
                c_key = os.getenv("SAMBANOVA_API_KEY")
                c_base_url = c_base_url or "https://api.sambanova.ai/v1"
            elif c_provider == "together":
                c_key = os.getenv("TOGETHER_API_KEY")
                c_base_url = c_base_url or "https://api.together.xyz/v1"
            elif c_provider == "mistral":
                c_key = os.getenv("MISTRAL_API_KEY")
                c_base_url = c_base_url or "https://api.mistral.ai/v1"
            elif c_provider in ["alibaba", "qwen"]:
                c_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY")
                c_base_url = c_base_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            elif c_provider in ["xai", "grok"]:
                c_key = os.getenv("XAI_API_KEY")
                c_base_url = c_base_url or "https://api.x.ai/v1"
            elif c_provider == "perplexity":
                c_key = os.getenv("PERPLEXITY_API_KEY")
                c_base_url = c_base_url or "https://api.perplexity.ai"
            elif c_provider == "cohere":
                c_key = os.getenv("COHERE_API_KEY")
                c_base_url = c_base_url or "https://api.cohere.com/v2"
            elif c_provider in ["mimo", "xiaomi"]:
                c_key = mimo_key or os.getenv("XIAOMI_MIMO_API_KEY") or os.getenv("MIMO_API_KEY")
                c_base_url = c_base_url or "https://api.xiaomimimo.com/v1"
            elif c_provider == "ollama":
                c_key = "ollama"
                c_base_url = c_base_url or "http://localhost:11434/v1"
            else:
                c_key = active_custom_entry.get("api_key") or openrouter_key or openai_key
                c_base_url = c_base_url or "https://openrouter.ai/api/v1"

            if c_key:
                model_candidates[chosen_model_id] = {
                    "nama": c_name,
                    "client": OpenAI(base_url=c_base_url, api_key=c_key),
                    "model": chosen_model_id,
                    "type": "openai"
                }

        # Susun urutan eksekusi: Model pilihan pengguna selalu di posisi Nomor 1!
        providers = []

        # Deteksi provider asal dari chosen_model_id untuk ekspansi multi-akun
        prov_origin = "openrouter"
        c_base_for_multi = None
        c_display_name = chosen_model_id
        if active_custom_entry:
            prov_origin = active_custom_entry.get("provider", "openrouter")
            c_base_for_multi = active_custom_entry.get("base_url")
            c_display_name = active_custom_entry.get("name", chosen_model_id)
        elif chosen_model_id.startswith("deepseek"):
            prov_origin = "deepseek"
            c_base_for_multi = "https://api.deepseek.com"
            c_display_name = model_candidates.get(chosen_model_id, {}).get("nama", "DeepSeek")
        elif chosen_model_id.startswith("gemini"):
            prov_origin = "gemini"
            c_display_name = model_candidates.get(chosen_model_id, {}).get("nama", "Google Gemini")
        elif chosen_model_id.startswith("gpt-") or chosen_model_id.startswith("o1") or chosen_model_id.startswith("o3"):
            prov_origin = "openai"
            c_base_for_multi = "https://api.openai.com/v1"
            c_display_name = model_candidates.get(chosen_model_id, {}).get("nama", "OpenAI")
        elif chosen_model_id.startswith("mimo"):
            prov_origin = "mimo"
            c_base_for_multi = "https://api.xiaomimimo.com/v1"
            c_display_name = "Xiaomi MiMo"

        keys_for_chosen = get_provider_keys(prov_origin)

        # Jika provider mendukung multi-kunci dan pengguna mengisi > 1 akun:
        if prov_origin in ["9router", "ninerouter", "antigravity"]:
            if chosen_model_id in model_candidates:
                providers.append(model_candidates[chosen_model_id])
        elif len(keys_for_chosen) > 1:
            for k_idx, k_val in enumerate(keys_for_chosen, 1):
                lbl_akun = f"{c_display_name} (Akun {k_idx}/{len(keys_for_chosen)})"
                if prov_origin == "gemini":
                    providers.append({
                        "nama": lbl_akun,
                        "client": None,
                        "model": chosen_model_id,
                        "type": "gemini",
                        "api_key": k_val
                    })
                else:
                    providers.append({
                        "nama": lbl_akun,
                        "client": OpenAI(base_url=c_base_for_multi or "https://openrouter.ai/api/v1", api_key=k_val),
                        "model": chosen_model_id,
                        "type": "openai"
                    })
        elif chosen_model_id in model_candidates:
            providers.append(model_candidates[chosen_model_id])

        # Cadangan Prioritas 1 (Fallback Utama): DeepSeek V4.1 Flash (atau sesuai setting fallback_model)
        cfg_data = load_model_config()
        fallback_model_id = cfg_data.get("fallback_model", "deepseek-flash")
        
        cand_fallback = None
        if fallback_model_id in model_candidates:
            cand_fallback = model_candidates[fallback_model_id]
        else:
            for m_entry in cfg_models.values():
                if m_entry.get("id") == fallback_model_id:
                    fb_prov = m_entry.get("provider", "openrouter")
                    fb_key = None
                    fb_base = m_entry.get("base_url")
                    if fb_prov in ["9router", "ninerouter", "antigravity"]:
                        fb_key = os.getenv("9ROUTER_API_KEY") or "9router-local"
                        fb_base = fb_base or "http://localhost:20128/v1"
                    elif fb_prov == "openrouter":
                        fb_key = openrouter_key
                        fb_base = fb_base or "https://openrouter.ai/api/v1"
                    elif fb_prov == "deepseek":
                        fb_key = deepseek_key
                        fb_base = fb_base or "https://api.deepseek.com"
                    elif fb_prov == "openai":
                        fb_key = openai_key
                        fb_base = fb_base or "https://api.openai.com/v1"
                    elif fb_prov == "cerebras":
                        fb_key = os.getenv("CEREBRAS_API_KEY")
                        fb_base = fb_base or "https://api.cerebras.ai/v1"
                    elif fb_prov == "sambanova":
                        fb_key = os.getenv("SAMBANOVA_API_KEY")
                        fb_base = fb_base or "https://api.sambanova.ai/v1"
                    else:
                        fb_key = openrouter_key or deepseek_key
                        fb_base = fb_base or "https://openrouter.ai/api/v1"

                    cand_fallback = {
                        "nama": m_entry.get("name", fallback_model_id),
                        "client": OpenAI(
                            base_url=fb_base,
                            api_key=fb_key or "belum-diisi"
                        ),
                        "model": fallback_model_id,
                        "type": "openai"
                    }
                    break

        if cand_fallback and cand_fallback not in providers:
            providers.append(cand_fallback)

        # Rantai cadangan otomatis berikutnya (tambahkan sisa model lain yang berbeda tipe/keluarga untuk keamanan)
        for mid, cand in model_candidates.items():
            if cand not in providers:
                providers.append(cand)

        # Rotasi multi-akun Groq sebagai jaring pengaman darurat paling bawah
        groq_keys = get_provider_keys("groq")
        for idx, g_key in enumerate(groq_keys, 1):
            lbl_groq = f"Groq Akun {idx}/{len(groq_keys)} (GPT-OSS 120B)" if len(groq_keys) > 1 else f"Groq Akun {idx} (GPT-OSS 120B)"
            providers.append({
                "nama": lbl_groq,
                "client": OpenAI(base_url="https://api.groq.com/openai/v1", api_key=g_key),
                "model": "gpt-oss-120b",
                "type": "openai"
            })

        if not providers:
            return {"type": "text", "content": "Error: Tidak ada API key yang tersedia (Gemini/DeepSeek/OpenAI/MiMo)."}

        # === EKSEKUSI DENGAN RANTAI CADANGAN (FALLBACK CASCADE) ===
        last_error = ""
        primary_provider_name = providers[0]["nama"] if providers else "Unknown"
        primary_error = ""

        for idx, provider in enumerate(providers):
            try:
                is_primary = (idx == 0)
                logger.info(f"Mencoba provider [{idx+1}/{len(providers)}]: {provider['nama']} {'(Utama)' if is_primary else '(Cadangan)'}")

                # Penampil proses: tampilkan otak yang sedang bekerja (dan perpindahan cadangan)
                try:
                    if is_primary:
                        _push_line(chat_id_override, f"🧠 Otak: {provider['nama']}")
                    else:
                        _push_line(chat_id_override, f"⚠️ Otak utama gagal, beralih ke: {provider['nama']}")
                except Exception:
                    pass

                if provider["type"] == "openai":
                    result = await ReasoningLayer._process_openai(
                        provider, messages, tools, state, memory_broker, chat_id_override
                    )
                else:
                    result = await ReasoningLayer._process_gemini(
                        provider, messages, tools, state, memory_broker, chat_id_override
                    )
                
                if result:
                    is_fallback = (idx > 0)
                    logger.info(f"Sukses dengan provider: {provider['nama']} (Fallback: {is_fallback})")
                    return {
                        "type": "text",
                        "content": result,
                        "provider_used": provider["nama"],
                        "model_used": provider["model"],
                        "is_fallback": is_fallback,
                        "primary_error": primary_error,
                        "primary_name": primary_provider_name,
                        "show_footer": show_footer,
                        "is_specialist": is_specialist,
                        "specialist_role": specialist_role
                    }
                    
            except Exception as e:
                err_msg = str(e)
                if idx == 0:
                    primary_error = err_msg
                last_error = f"{provider['nama']}: {err_msg}"
                logger.warning(f"Provider {provider['nama']} gagal: {err_msg}. Mencoba cadangan berikutnya...")
                continue

        return {"type": "text", "content": _pesan_gagal_otak(last_error)}
    
    @staticmethod
    async def _process_openai(provider, messages, tools, state, memory_broker, chat_id_override) -> str:
        """Process via OpenAI-compatible API (MiMo, DeepSeek)."""
        import uuid

        user_call = _get_user_call()
        
        client = provider["client"]
        model = provider["model"]
        
        # Copy messages to avoid mutation
        msgs = [m.copy() for m in messages]
        teks_pengguna = _teks_pengguna_terakhir(msgs)
        
        max_loops = 5
        last_tool_result = ""
        # Akumulasi hasil alat dari SELURUH putaran. Dipakai sebagai bahan laporan
        # cadangan: kalau ada alat yang sudah berjalan, pengguna harus menerima
        # laporannya - bukan sapaan generik.
        semua_hasil_alat = []
        
        for loop in range(max_loops):
            logger.info(f"[{provider['nama']}] LLM Call Loop {loop+1}/{max_loops}")
            
            # Trim context if too long and sanitize orphaned tool messages
            if len(msgs) > 50:
                sys_msg = msgs[0]
                tail = msgs[-49:]
                
                # Remove any leading 'tool' role messages from tail
                while tail and tail[0].get("role") == "tool":
                    tail.pop(0)
                    
                # Remove any leading 'assistant' tool_calls if cut off from its tool result
                while tail and tail[0].get("role") == "assistant" and tail[0].get("tool_calls"):
                    if len(tail) == 1 or tail[1].get("role") != "tool":
                        tail.pop(0)
                    else:
                        break
                
                msgs = [sys_msg] + tail
                        
            # Muat konfigurasi temperature dinamis
            target_temp = 0.7
            pers_file_check = PROJECT_ROOT / "personalisasi.json"
            if pers_file_check.exists():
                try:
                    with open(pers_file_check, "r", encoding="utf-8") as pfc:
                        target_temp = float(json.load(pfc).get("temperature", 0.7))
                except Exception:
                    pass

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    tools=tools if tools else None,
                    temperature=target_temp,
                    max_tokens=2500,
                    timeout=25.0
                )
            except Exception as e_tool:
                if "tool" in str(e_tool).lower() and tools:
                    logger.warning(f"Provider {provider.get('nama', model)} tidak mendukung tool calling, mencoba kembali tanpa tools...")
                    response = client.chat.completions.create(
                        model=model,
                        messages=msgs,
                        temperature=target_temp,
                        max_tokens=2500,
                        timeout=25.0
                    )
                else:
                    raise e_tool
            
            res_msg = response.choices[0].message
            
            # 1. Collect standard tool_calls, DSML markup, OR Bracket format [Tool: ...]
            tool_calls_to_process = []
            clean_content_prefix = ""
            
            if res_msg.tool_calls:
                for tc in res_msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception as e:
                        args = {}
                    tool_calls_to_process.append({"id": tc.id, "name": tc.function.name, "args": args})
            elif res_msg.content:
                if "DSML" in res_msg.content:
                    invokes = re.findall(r'<｜｜DSML｜｜\s*invoke name="([^"]+)"\s*>(.*?)</｜｜DSML｜｜\s*invoke>', res_msg.content, re.DOTALL)
                    for idx, (name, body) in enumerate(invokes):
                        params = {}
                        param_matches = re.findall(r'<｜｜DSML｜｜\s*parameter name="([^"]+)"[^>]*>(.*?)</｜｜DSML｜｜\s*parameter>', body, re.DOTALL)
                        for p_name, p_val in param_matches:
                            params[p_name] = p_val.strip()
                        tool_calls_to_process.append({"id": f"dsml_{idx}", "name": name, "args": params})
                
                if "[Tool:" in res_msg.content:
                    bracket_matches = re.findall(r'\[Tool:\s*([a-zA-Z0-9_]+)\s*(.*?)\]', res_msg.content, re.DOTALL)
                    for idx, (name, args_str) in enumerate(bracket_matches):
                        params = {}
                        kv_pairs = re.findall(r"([a-zA-Z0-9_]+)=['\"]?(.*?)['\"]?(?=\s+[a-zA-Z0-9_]+=|$)", args_str)
                        if not kv_pairs:
                            kv_pairs = re.findall(r"(?:dengan\s+)?([a-zA-Z0-9_]+)=['\"]?(.*?)['\"]?$", args_str)
                        for k, v in kv_pairs:
                            params[k.strip()] = v.strip().strip("'\"")
                        tool_calls_to_process.append({"id": f"bracket_{idx}", "name": name, "args": params})
                    
                    clean_content_prefix = re.sub(r'\[Tool:.*?\]', '', res_msg.content, flags=re.DOTALL).strip()
            
            if tool_calls_to_process:
                msgs.append(res_msg)
                # Menunjuk ke akumulasi di luar loop supaya hasil alat dari
                # putaran sebelumnya tidak hilang saat putaran habis.
                tool_results_list = semua_hasil_alat
                
                for tool_call in tool_calls_to_process:
                    func_name = tool_call["name"]
                    func_args = tool_call["args"]
                    call_id = tool_call["id"]
                    
                    # Synonym mappings for DSML/bracket names
                    alias_map = {
                        "jadwalkan_tugas_automatis": "jadwalkan_tugas_otomatis",
                        "jadwalkan_tugas": "jadwalkan_tugas_otomatis",
                        "jadwal_tugas": "jadwalkan_tugas_otomatis",
                        "lapor_email": "jadwalkan_tugas_otomatis",
                        "jadwalkan_email": "jadwalkan_tugas_otomatis",
                        "jadwalkan_berita": "jadwalkan_tugas_otomatis",
                        "cek_email": "baca_email"
                    }
                    func_name = alias_map.get(func_name, func_name)
                    
                    if func_name in ["pasang_pengingat", "pasang_pengingat_suara"]:
                        func_name = "jadwalkan_tugas_otomatis"
                        jam = func_args.get("jam_atau_tanggal") or func_args.get("menit") or func_args.get("waktu") or "5"
                        if isinstance(jam, int) or (isinstance(jam, str) and str(jam).isdigit()):
                            from datetime import datetime, timedelta
                            jam = (datetime.now() + timedelta(minutes=int(jam))).strftime("%H:%M")
                        
                        fungsi_aksi = func_args.get("fungsi_aksi") or "putar_youtube"
                        param = func_args.get("parameter_json") or func_args.get("pesan") or func_args.get("teks") or "{}"
                        func_args = {
                            "jam_atau_tanggal": str(jam),
                            "fungsi_aksi": str(fungsi_aksi),
                            "parameter_json": str(param)
                        }
                    elif func_name == "jalankan_perintah":
                        func_name = "jalankan_perintah_sistem"
                    elif func_name in ["restart_komputer", "restart_pc", "restart", "reboot", "reboot_pc"]:
                        func_name = "atur_daya_pc"
                        func_args = {"aksi": "restart"}
                    elif func_name in ["matikan_komputer", "matikan_pc", "matikan", "shutdown", "shutdown_pc"]:
                        func_name = "atur_daya_pc"
                        func_args = {"aksi": "shutdown"}
                    
                    logger.info(f"[{provider['nama']}] Executing Tool: {func_name} with args: {func_args}")
                    
                    # Save Tool Call Event
                    await memory_broker.append_event(state.person_id, "TOOL_CALLED", {
                        "id": call_id, "name": func_name, "args": func_args
                    })
                    
                    # Execute Tool
                    tool_def = tool_registry.get_tool(func_name)
                    if not tool_def:
                        alias_redirects = {
                            "cari_di_youtube": "cek_youtube_channel_publik",
                            "search_youtube": "cek_youtube_channel_publik",
                            "cari_video_youtube": "cek_youtube_channel_publik",
                            "youtube_search": "cek_youtube_channel_publik",
                            "cek_video_youtube": "cek_youtube_channel_publik",
                        }
                        if func_name in alias_redirects:
                            target_func = alias_redirects[func_name]
                            tool_def = tool_registry.get_tool(target_func)
                            if tool_def and "nama_channel" not in func_args:
                                arg_val = func_args.get("kata_kunci") or func_args.get("query") or func_args.get("q") or func_args.get("search") or ""
                                func_args["nama_channel"] = arg_val

                    _langkah = None
                    if not tool_def:
                        result_str = f"Error: Alat '{func_name}' tidak ditemukan."
                    else:
                        try:
                            QualityGate.evaluate_action(state.person_id, func_name, func_args, teks_pengguna)
                            handler = tool_def["handler"]
                            
                            _langkah = _notify_tool_step(chat_id_override, func_name, func_args)

                            import inspect
                            sig = inspect.signature(handler)
                            
                            # Filter pintar parameter agar aman dari parameter gaib/tambahan LLM (seperti 'reason')
                            valid_params = {}
                            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                            
                            if has_var_keyword:
                                valid_params = func_args.copy()
                            else:
                                for p_name, p_val in func_args.items():
                                    if p_name in sig.parameters:
                                        valid_params[p_name] = p_val
                            
                            if "chat_id" in sig.parameters and chat_id_override:
                                valid_params["chat_id"] = chat_id_override
                            
                            result = handler(**valid_params)
                            result_str = str(result)
                        except PermissionDeniedError as pde:
                            result_str = f"Permission Denied: {str(pde)}"
                        except Exception as e:
                            result_str = f"Tool Error: {str(e)}"
                    
                    _hasil_ok = not result_str.startswith(("Error: ", "Tool Error: ", "Permission Denied: "))
                    _step_end(_langkah, result_str, ok=_hasil_ok)

                    last_tool_result = result_str
                    tool_results_list.append(result_str)
                    logger.info(f"[{provider['nama']}] Tool {func_name} result: {result_str[:100]}...")
                    
                    # Save Tool Result Event
                    await memory_broker.append_event(state.person_id, "TOOL_RESULT", {
                        "tool_call_id": call_id, "name": func_name, "content": result_str
                    })
                    
                    if hasattr(res_msg, 'tool_calls') and res_msg.tool_calls:
                        msgs.append({
                            "role": "tool", "tool_call_id": call_id,
                            "name": func_name, "content": result_str
                        })
                    else:
                        # For bracket/DSML calls, we cannot use 'tool' role without matching 'tool_calls'
                        msgs.append({
                            "role": "user",
                            "content": f"Sistem (Internal): Alat '{func_name}' telah dijalankan. Hasil:\n{result_str}\n\nSampaikan laporan hasil eksekusi alat ini kepada {user_call} secara ramah, jelas, dan mendetail."
                        })

                # Biarkan LLM merangkai kalimat natural di loop berikutnya
                continue
            else:
                final_text = res_msg.content or ""
                # Strip raw DSML & bracket tags if present in final text
                final_text = re.sub(r'<｜｜DSML｜｜.*?>', '', final_text, flags=re.DOTALL)
                final_text = re.sub(r'\[Tool:.*?\]', '', final_text, flags=re.DOTALL).strip()
                
                # Proteksi: kalau alat SUDAH dijalankan, jangan biarkan teks sapaan
                # generik ATAU jawaban kosong seperti "Berhasil" menimpa laporan
                # hasilnya. Pengguna mengirim PERINTAH dan berhak menerima hasilnya.
                _sapaan_kosong = any(gen in (final_text or "").lower() for gen in _SAPAAN_GENERIK)
                _terlalu_tipis = _jawaban_terlalu_tipis(final_text)

                # Jika alat yang dijalankan adalah baca_pesan_terakhir_wa, pastikan tag [AKSI_BALAS_WA: ...] tetap ikut
                if any("[AKSI_BALAS_WA:" in str(h) for h in semua_hasil_alat):
                    if "[AKSI_BALAS_WA:" not in (final_text or ""):
                        # Sisipkan tag aksi balas WA dari hasil alat agar tombol interaktif UI tetap render
                        for h in semua_hasil_alat:
                            h_str = str(h)
                            tags = re.findall(r'\[AKSI_BALAS_WA:[^\]]+\]', h_str)
                            if tags:
                                final_text = (final_text or "").strip() + "\n\n" + "\n".join(tags)
                                break

                if semua_hasil_alat and (not final_text or _sapaan_kosong or _terlalu_tipis):
                    return _laporan_hasil_alat(user_call, semua_hasil_alat)

                if not final_text:
                    reasoning = getattr(res_msg, 'reasoning_content', '') or getattr(res_msg, 'reasoning', '')
                    if reasoning:
                        try:
                            synth_msgs = list(msgs)
                            synth_msgs.append({"role": "assistant", "content": reasoning})
                            synth_msgs.append({"role": "user", "content": f"Berdasarkan pemikiranmu tadi, jawab langsung ke {user_call} dalam 1-2 kalimat secara ramah, sopan, dan to the point."})
                            synth_res = provider["client"].chat.completions.create(
                                model=provider["model"],
                                messages=synth_msgs,
                                max_tokens=200,
                                timeout=15.0
                            )
                            final_text = synth_res.choices[0].message.content or ""
                        except Exception:
                            pass

                if not final_text:
                    if semua_hasil_alat:
                        return _laporan_hasil_alat(user_call, semua_hasil_alat)
                    final_text = f"Halo {user_call}! Ada yang bisa Harmoni bantu atau lanjutkan?"
                return final_text
        
        # Seluruh putaran habis. Kalau ada alat yang sudah berjalan, laporkan
        # hasilnya - JANGAN membalas sapaan, karena pengguna mengirim PERINTAH.
        if semua_hasil_alat:
            return _laporan_hasil_alat(user_call, semua_hasil_alat)
        return last_tool_result or f"Halo {user_call}! Ada yang bisa Harmoni bantu atau lanjutkan?"
    
    @staticmethod
    async def _process_gemini(provider, messages, tools, state, memory_broker, chat_id_override) -> str:
        """Process via Google Gemini API (cadangan terakhir)."""
        import google.generativeai as genai
        import uuid

        user_call = _get_user_call()
        teks_pengguna = _teks_pengguna_terakhir(messages)

        genai.configure(api_key=provider["api_key"])
        
        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            if msg["role"] == "system":
                gemini_messages.append({'role': 'user', 'parts': [f"[SYSTEM]: {msg['content']}"]})
                gemini_messages.append({'role': 'model', 'parts': ["Mengerti, saya akan mengikuti instruksi sistem tersebut."]})
            elif msg["role"] == "user":
                gemini_messages.append({'role': 'user', 'parts': [msg["content"]]})
            elif msg["role"] == "assistant":
                if msg.get("tool_calls"):
                    func_calls = []
                    for tc in msg["tool_calls"]:
                        func_calls.append({"function_call": {
                            "name": tc["function"]["name"],
                            "args": json.loads(tc["function"]["arguments"])
                        }})
                    gemini_messages.append({'role': 'model', 'parts': func_calls})
                else:
                    gemini_messages.append({'role': 'model', 'parts': [msg.get("content", "")]})
            elif msg["role"] == "tool":
                gemini_messages.append({
                    'role': 'user',
                    'parts': [{"function_response": {"name": msg["name"], "response": {"result": msg["content"]}}}]
                })
        
        func_declarations = [t["function"] for t in tools]
        gemini_tools = [{"function_declarations": func_declarations}] if tools else None
        model_name = provider.get("model", "gemini-2.5-flash")
        model = genai.GenerativeModel(model_name, tools=gemini_tools)
        
        max_loops = 5
        last_tool_result = ""
        
        for loop in range(max_loops):
            logger.info(f"[Gemini] LLM Call Loop {loop+1}/{max_loops}")
            
            if len(gemini_messages) > 100:
                gemini_messages = gemini_messages[:2] + gemini_messages[-98:]
            
            response = model.generate_content(gemini_messages)
            
            if response.parts:
                tool_parts = [part for part in response.parts if hasattr(part, "function_call") and part.function_call]
                if tool_parts:
                    # Simpan full model content asli (termasuk thought_signature) agar Gemini API tidak error 400
                    if response.candidates and response.candidates[0].content:
                        gemini_messages.append(response.candidates[0].content)
                    else:
                        gemini_messages.append({'role': 'model', 'parts': response.parts})

                    for part in tool_parts:
                        func_name = part.function_call.name
                        func_args = type(part.function_call.args).to_dict(part.function_call.args) if hasattr(part.function_call.args, "to_dict") else dict(part.function_call.args)
                        
                        if func_name in ["pasang_pengingat", "pasang_pengingat_suara"]:
                            func_name = "jadwalkan_tugas_otomatis"
                            jam = func_args.get("jam_atau_tanggal") or func_args.get("menit") or func_args.get("waktu") or "5"
                            if isinstance(jam, int) or (isinstance(jam, str) and str(jam).isdigit()):
                                from datetime import datetime, timedelta
                                jam = (datetime.now() + timedelta(minutes=int(jam))).strftime("%H:%M")
                            
                            fungsi_aksi = func_args.get("fungsi_aksi") or "putar_youtube"
                            param = func_args.get("parameter_json") or func_args.get("pesan") or func_args.get("teks") or "{}"
                            func_args = {
                                "jam_atau_tanggal": str(jam),
                                "fungsi_aksi": str(fungsi_aksi),
                                "parameter_json": str(param)
                            }
                        elif func_name in ["restart_komputer", "restart_pc", "restart", "reboot", "reboot_pc"]:
                            func_name = "atur_daya_pc"
                            func_args = {"aksi": "restart"}
                        elif func_name in ["matikan_komputer", "matikan_pc", "matikan", "shutdown", "shutdown_pc"]:
                            func_name = "atur_daya_pc"
                            func_args = {"aksi": "shutdown"}
                        
                        tc_id = str(uuid.uuid4())
                        logger.info(f"[Gemini] Tool: {func_name}")
                        
                        await memory_broker.append_event(state.person_id, "TOOL_CALLED", {
                            "id": tc_id, "name": func_name, "args": func_args
                        })
                        
                        tool_def = tool_registry.get_tool(func_name)
                        _langkah = None
                        if not tool_def:
                            result_str = f"Error: Alat '{func_name}' tidak ditemukan."
                        else:
                            try:
                                QualityGate.evaluate_action(state.person_id, func_name, func_args, teks_pengguna)
                                handler = tool_def["handler"]

                                _langkah = _notify_tool_step(chat_id_override, func_name, func_args)

                                import inspect
                                sig = inspect.signature(handler)
                                
                                # Filter pintar parameter untuk Gemini handler
                                valid_params = {}
                                has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                                if has_var_keyword:
                                    valid_params = func_args.copy()
                                else:
                                    for p_name, p_val in func_args.items():
                                        if p_name in sig.parameters:
                                            valid_params[p_name] = p_val

                                if "chat_id" in sig.parameters and chat_id_override:
                                    valid_params["chat_id"] = chat_id_override
                                result = handler(**valid_params)
                                result_str = str(result)
                            except PermissionDeniedError as pde:
                                result_str = f"Permission Denied: {str(pde)}"
                            except Exception as e:
                                result_str = f"Tool Error: {str(e)}"
                        
                        _hasil_ok = not result_str.startswith(("Error: ", "Tool Error: ", "Permission Denied: "))
                        _step_end(_langkah, result_str, ok=_hasil_ok)

                        last_tool_result = result_str
                        logger.info(f"[Gemini] Tool {func_name} result: {result_str[:100]}...")
                        
                        await memory_broker.append_event(state.person_id, "TOOL_RESULT", {
                            "tool_call_id": tc_id, "name": func_name, "content": result_str
                        })
                        
                        gemini_messages.append({
                            'role': 'user',
                            'parts': [{"function_response": {"name": func_name, "response": {"result": result_str}}}]
                        })

                    # Lanjutkan ke loop berikutnya agar Gemini merespons hasil tool
                    continue
                else:
                    try:
                        final_text = response.text
                    except Exception:
                        text_parts = [p.text for p in response.parts if hasattr(p, 'text') and p.text]
                        final_text = '\n'.join(text_parts) if text_parts else ''
                    if not final_text:
                        final_text = last_tool_result or "Halo! Ada yang bisa saya bantu atau lanjutkan?"
                    return final_text
            else:
                try:
                    return response.text
                except Exception:
                    return last_tool_result or "Halo! Ada yang bisa saya bantu atau lanjutkan?"
        
        return last_tool_result or "Maaf Kak, sistem berhenti otomatis."

