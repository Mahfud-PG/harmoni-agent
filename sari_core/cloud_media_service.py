"""
Sari AI Operating System - Cloud & Media Integration Service
Mengelola interaksi API YouTube (upload, komentar, analitik) dan Google Drive (unggah, bagikan, unduh, hapus).
"""

import os
import subprocess
import requests
from pathlib import Path
from sari_core.paths import (
    PROJECT_ROOT, DATA_ROOT, PROGRAM_ROOT, DOWNLOADS_DIR,
    SKRIP_YOUTUBE_API, SKRIP_DRIVE_API,
    cari_python_console,
)

# Skrip bantuan ada di folder PROGRAM, bukan folder data. Menghitungnya dari
# PROJECT_ROOT (= folder DATA saat aplikasi terpasang) membuat skrip tidak
# ditemukan dan setiap alat mengembalikan teks kosong.
YOUTUBE_API_SCRIPT = str(SKRIP_YOUTUBE_API)
DRIVE_API_SCRIPT = str(SKRIP_DRIVE_API)
CHAT_ID_TXT_PATH = str(PROJECT_ROOT / "chat_id.txt")


def _jalankan_skrip(skrip: str, argumen: list) -> str:
    """Jalankan skrip bantuan dan kembalikan hasilnya.

    TIDAK PERNAH mengembalikan teks kosong, supaya otak AI selalu punya bahan
    untuk dilaporkan dan tidak mengarang jawaban "Berhasil".
    """
    berkas = Path(skrip)
    if not berkas.exists():
        return (f"Gagal: berkas bantuan '{berkas.name}' tidak ditemukan di "
                f"{berkas.parent}.")
    perintah = [cari_python_console(), str(berkas)] + [str(a) for a in argumen]
    # Beritahu skrip bantuan di mana folder DATA berada (untuk berkas progres).
    lingkungan = os.environ.copy()
    lingkungan["HARMONI_DATA_DIR"] = str(DATA_ROOT)
    lingkungan["HARMONI_PROGRAM_DIR"] = str(PROGRAM_ROOT)
    try:
        hasil = subprocess.run(
            perintah, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300, env=lingkungan,
        )
    except subprocess.TimeoutExpired:
        return "Gagal: perintah melebihi batas 300 detik."
    except Exception as e:
        return f"Gagal menjalankan perintah: {e}"

    keluaran = (hasil.stdout or "").strip()
    if keluaran:
        return keluaran
    galat = (hasil.stderr or "").strip()
    if galat:
        return f"Gagal: {galat[:400]}"
    return f"Gagal: perintah tidak menghasilkan apa pun (kode keluar {hasil.returncode})."

def _kirim_notif_sync(teks: str):
    """Mengirim pesan notifikasi singkat ke Telegram secara sinkron."""
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = None
        if os.path.exists(CHAT_ID_TXT_PATH):
            with open(CHAT_ID_TXT_PATH, "r", encoding="utf-8") as f:
                chat_id = f.read().strip()
        if not chat_id:
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": teks}, timeout=10)
    except Exception:
        pass

# ==========================================
# 1. YOUTUBE API OPERATIONS
# ==========================================

def upload_youtube(jalur_video: str, judul: str, deskripsi: str, account: str, tags: str = "", thumbnail_path: str = ""):
    """Mengunggah video ke YouTube via API dengan status progress di latar belakang."""
    try:
        script_path = YOUTUBE_API_SCRIPT
        perintah = [cari_python_console(), script_path, "--action", "upload", "--account", account, "--file", jalur_video, "--title", judul, "--desc", deskripsi]
        if thumbnail_path:
            perintah.extend(["--thumb", thumbnail_path])
        if tags:
            perintah.extend(["--tags", tags])
            
        _kirim_notif_sync(f"🎬 Mulai proses unggah video ke YouTube: {judul}\nMohon tunggu...")
        subprocess.Popen(perintah, creationflags=subprocess.CREATE_NO_WINDOW)
        return "Proses upload video ke YouTube telah dimulai di latar belakang. Anda bisa ngobrol dengan saya sementara menunggu selesai. Jika ingin tahu prosesnya, tanyakan 'sudah berapa persen?'."
    except Exception as e:
        return f"Gagal mengunggah video: {str(e)}"

def cek_statistik_youtube(account: str):
    """Mengecek statistik channel YouTube (subscribers, total views, total video)."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "stat", "--account", account])
    except Exception as e:
        return f"Gagal cek statistik: {str(e)}"

def baca_komentar_youtube(account: str, maksimal: int = 5):
    """Membaca komentar-komentar terbaru dari video channel YouTube."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "get_comments", "--account", account, "--max", str(maksimal)])
    except Exception as e:
        return f"Gagal baca komentar: {str(e)}"

def balas_komentar_youtube(account: str, comment_id: str, teks: str):
    """Membalas komentar di video YouTube."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "reply", "--account", account, "--comment_id", comment_id, "--text", teks])
    except Exception as e:
        return f"Gagal balas komentar: {str(e)}"

def edit_video_youtube(account: str, video_id: str, judul: str = "", deskripsi: str = "", tags: str = ""):
    """Mengedit judul, deskripsi, atau tags video YouTube."""
    try:
        cmd = [cari_python_console(), YOUTUBE_API_SCRIPT, "--action", "edit", "--account", account, "--video_id", video_id]
        if judul: cmd.extend(["--title", judul])
        if deskripsi: cmd.extend(["--desc", deskripsi])
        if tags: cmd.extend(["--tags", tags])
        hasil = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        return hasil.stdout.strip()
    except Exception as e:
        return f"Gagal edit video: {str(e)}"

def cari_id_video_youtube(account: str, query: str, maksimal: int = 3):
    """Mencari video di channel YouTube milik sendiri berdasarkan judul."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "search_mine", "--account", account, "--query", query, "--max", str(maksimal)])
    except Exception as e:
        return f"Gagal cari video: {str(e)}"

def buat_playlist_youtube(account: str, judul: str, deskripsi: str = ""):
    """Membuat playlist baru di YouTube."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "create_playlist", "--account", account, "--title", judul, "--desc", deskripsi])
    except Exception as e:
        return f"Gagal buat playlist: {str(e)}"

def tambah_video_playlist_youtube(account: str, playlist_id: str, video_id: str):
    """Menambahkan video tertentu ke dalam playlist YouTube."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "add_to_playlist", "--account", account, "--playlist_id", playlist_id, "--video_id", video_id])
    except Exception as e:
        return f"Gagal tambah playlist: {str(e)}"

def ganti_thumbnail_youtube(account: str, video_id: str, thumbnail_path: str):
    """Mengganti gambar thumbnail video YouTube."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "set_thumb", "--account", account, "--video_id", video_id, "--thumb", thumbnail_path])
    except Exception as e:
        return f"Gagal ganti thumbnail: {str(e)}"

def hapus_komentar_youtube(account: str, comment_id: str):
    """Menghapus komentar tertentu di YouTube."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "delete_comment", "--account", account, "--comment_id", comment_id])
    except Exception as e:
        return f"Gagal hapus komentar: {str(e)}"

def cek_video_terbaru_channel_youtube(account: str, channel_name: str, maksimal: int = 3):
    """Mengecek video terbaru dari channel YouTube orang lain."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "latest_from_channel", "--account", account, "--query", channel_name, "--max", str(maksimal)])
    except Exception as e:
        return f"Gagal cek video terbaru: {str(e)}"

def cek_video_terakhir_channel_sendiri(account: str = "utama"):
    """Mengecek video terakhir yang di-upload ke channel YouTube sendiri ('utama' / 'kedua')."""
    try:
        return _jalankan_skrip(YOUTUBE_API_SCRIPT, ["--action", "latest_my_video", "--account", account])
    except Exception as e:
        return f"Gagal mengecek video terakhir channel sendiri: {str(e)}"

# ==========================================
# 2. GOOGLE DRIVE API OPERATIONS
# ==========================================

def upload_drive(account: str, file_path: str, publik: bool = False):
    """Mengunggah file ke Google Drive dan memastikan berhasil (dengan bukti, bukan asumsi)."""
    try:
        if not os.path.exists(file_path):
            return f"❌ Berkas tidak ditemukan di PC: {file_path}"
        cmd = [cari_python_console(), DRIVE_API_SCRIPT, "--action", "upload", "--account", account, "--file", file_path]
        if publik:
            cmd.append("--public")
        hasil = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1800
        )
        keluaran = (hasil.stdout or "").strip()
        baris_bukti = ""
        for baris in keluaran.splitlines():
            if "SUKSES_UPLOAD_DRIVE" in baris:
                baris_bukti = baris.replace("SUKSES_UPLOAD_DRIVE:", "ID berkas:").strip()
                break
        if baris_bukti:
            status_teks = "publik (siapa saja dengan link)" if publik else "privat (aman)"
            kode_galat = [b for b in keluaran.splitlines() if "ERROR" in b.upper()]
            catatan = ("\n⚠️ Catatan teknis: " + kode_galat[0][:150]) if kode_galat else ""
            return f"✅ Berkas BENAR-BENAR terunggah ke Google Drive (status {status_teks}).\n{baris_bukti}{catatan}"
        sebab = keluaran[:300] or (hasil.stderr or "").strip()[:300] or "tidak ada keterangan"
        return f"❌ Upload ke Google Drive GAGAL. Tidak ada bukti keberhasilan dari server.\nSebab: {sebab}"
    except subprocess.TimeoutExpired:
        return "❌ Upload ke Google Drive melebihi batas waktu 30 menit. Berkas terlalu besar atau jaringan lambat."
    except Exception as e:
        return f"Gagal upload ke Drive: {str(e)}"

def cek_kapasitas_drive(account: str):
    """Mengecek sisa kapasitas ruang penyimpanan Google Drive."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "stat", "--account", account])
    except Exception as e:
        return f"Gagal cek kapasitas Drive: {str(e)}"

def cari_file_drive(account: str, query: str):
    """Mencari file di Google Drive berdasarkan nama file."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "search", "--account", account, "--query", query])
    except Exception as e:
        return f"Gagal cari file di Drive: {str(e)}"

def ubah_akses_drive(account: str, file_id: str):
    """Mengubah izin akses file di Google Drive."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "change_access", "--account", account, "--file_id", file_id])
    except Exception as e:
        return f"Gagal ubah akses Drive: {str(e)}"

def hapus_file_drive(account: str, file_id: str):
    """Menghapus file secara permanen dari Google Drive."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "delete", "--account", account, "--file_id", file_id])
    except Exception as e:
        return f"Gagal hapus file dari Drive: {str(e)}"

def bagi_akses_email_drive(account: str, file_id: str, email_address: str, role: str = "writer"):
    """Membagikan akses file Google Drive langsung ke alamat email penerima."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "share_email", "--account", account, "--file_id", file_id, "--email", email_address, "--role", role])
    except Exception as e:
        return f"Gagal bagi akses email Drive: {str(e)}"

def buang_ke_sampah_drive(account: str, file_id: str):
    """Memindahkan file ke tong sampah Google Drive (Trash)."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "trash", "--account", account, "--file_id", file_id])
    except Exception as e:
        return f"Gagal buang ke sampah Drive: {str(e)}"

def ganti_nama_file_drive(account: str, file_id: str, nama_baru: str):
    """Mengganti nama file (rename) di Google Drive."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "rename", "--account", account, "--file_id", file_id, "--new_name", nama_baru])
    except Exception as e:
        return f"Gagal ganti nama file Drive: {str(e)}"

def kosongkan_sampah_drive(account: str):
    """Mengosongkan tempat sampah Google Drive secara permanen."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "empty_trash", "--account", account])
    except Exception as e:
        return f"Gagal mengosongkan sampah Drive: {str(e)}"

def download_file_drive(account: str, file_id: str, dest_folder: str = ""):
    """Mendownload file dari Google Drive lalu memastikan berkasnya benar-benar ada di PC."""
    try:
        if not dest_folder:
            dest_folder = str(DOWNLOADS_DIR)
        os.makedirs(dest_folder, exist_ok=True)
        sebelum = set(os.listdir(dest_folder))
        hasil = subprocess.run(
            [cari_python_console(), DRIVE_API_SCRIPT, "--action", "download", "--account", account, "--file_id", file_id, "--dest", dest_folder],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1800,
        )
        keluaran = (hasil.stdout or "").strip()
        sesudah = set(os.listdir(dest_folder))
        baru = sorted(sesudah - sebelum)
        if baru:
            return f"✅ Berkas BENAR-BENAR terunduh ke {dest_folder}:\n- " + "\n- ".join(baru[:5])
        return f"❌ Download TIDAK menghasilkan berkas baru di {dest_folder}.\nKeluaran: {keluaran[:300] or (hasil.stderr or '').strip()[:300]}"
    except subprocess.TimeoutExpired:
        return "❌ Download melebihi batas waktu 30 menit. Berkas terlalu besar atau jaringan lambat."
    except Exception as e:
        return f"Gagal download file Drive: {str(e)}"

def cek_isi_folder_drive(account: str, nama_folder: str):
    """Melihat daftar file di dalam folder Google Drive."""
    try:
        return _jalankan_skrip(DRIVE_API_SCRIPT, ["--action", "list_folder", "--account", account, "--query", nama_folder])
    except Exception as e:
        return f"Gagal cek isi folder: {str(e)}"
