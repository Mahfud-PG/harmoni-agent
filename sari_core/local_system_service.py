"""
Harmoni Agent - Local System & Disk Service
Mengelola pencarian file, eksplorasi folder, pemantauan kapasitas disk, dan progress tugas lokal.

PENTING - dua kesalahan yang pernah membuat SELURUH alat lokal mati diam-diam:
  1. Skrip bantuan dihitung dari PROJECT_ROOT (folder DATA). Ketika aplikasi sudah
     terpasang, PROJECT_ROOT menunjuk %APPDATA%\\HarmoniAgent, sedangkan skripnya
     ada di folder PROGRAM - sehingga skrip tidak ditemukan dan stdout kosong.
  2. Perintah dijalankan lewat launcher "py" milik Windows. Launcher itu hanya ada
     kalau Python terpasang di komputer pengguna, padahal aplikasi ini membawa
     Python-nya sendiri.

Akibat gabungan keduanya: baca folder, cek disk, cari berkas, dan kelola berkas
mengembalikan teks KOSONG. Otak AI lalu tidak punya apa pun untuk dilaporkan,
sehingga menjawab "Berhasil" atau sapaan generik - padahal tidak ada yang berhasil.
"""

import os
import subprocess
import json
from pathlib import Path

from sari_core.paths import (
    PROJECT_ROOT, DATA_ROOT, PROGRAM_ROOT, DOWNLOADS_DIR,
    SKRIP_LOKAL_API, cari_python_console,
)

SISTEM_LOKAL_API_SCRIPT = str(SKRIP_LOKAL_API)
PROGRESS_JSON_PATH = str(PROJECT_ROOT / "progress.json")


def _jalankan_bantuan(argumen: list) -> str:
    """Jalankan skrip bantuan lokal dan kembalikan hasilnya.

    TIDAK PERNAH mengembalikan teks kosong. Ini disengaja: hasil kosong membuat
    otak AI tidak punya bahan untuk dilaporkan, sehingga ia mengarang jawaban
    ("Berhasil") atau membalas sapaan. Kegagalan HARUS berbentuk pesan jelas.
    """
    skrip = Path(SISTEM_LOKAL_API_SCRIPT)
    if not skrip.exists():
        return (f"Gagal: berkas bantuan '{skrip.name}' tidak ditemukan di {skrip.parent}. "
                f"Alat lokal tidak dapat dijalankan.")
    perintah = [cari_python_console(), str(skrip)] + [str(a) for a in argumen]
    # Beritahu skrip bantuan di mana folder DATA berada. Tanpa ini, skrip itu
    # menulis berkas progres ke folder yang salah (dulu malah ke alamat proyek
    # lama yang sudah dihapus) dan gagal tanpa pesan apa pun.
    lingkungan = os.environ.copy()
    lingkungan["HARMONI_DATA_DIR"] = str(DATA_ROOT)
    lingkungan["HARMONI_PROGRAM_DIR"] = str(PROGRAM_ROOT)
    try:
        hasil = subprocess.run(
            perintah, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120, env=lingkungan,
        )
    except subprocess.TimeoutExpired:
        return "Gagal: perintah lokal melebihi batas 120 detik."
    except Exception as e:
        return f"Gagal menjalankan perintah lokal: {e}"

    keluaran = (hasil.stdout or "").strip()
    if keluaran:
        return keluaran

    galat = (hasil.stderr or "").strip()
    if galat:
        return f"Gagal: {galat[:400]}"
    return f"Gagal: perintah lokal tidak menghasilkan apa pun (kode keluar {hasil.returncode})."


def cari_file_lokal(query: str, drive: str = "C:\\"):
    """Mencari file atau folder di dalam drive tertentu."""
    return _jalankan_bantuan(["--action", "cari", "--query", query, "--drive", drive])

def baca_isi_folder_lokal(path_folder: str):
    """Melihat daftar file dan subfolder di dalam direktori lokal."""
    return _jalankan_bantuan(["--action", "baca", "--src", path_folder])

def kelola_file_lokal(action: str, path_sumber: str, path_tujuan: str = ""):
    """Mengelola file (copy, move, delete)."""
    argumen = ["--action", "kelola", "--mode", action, "--src", path_sumber]
    if path_tujuan:
        argumen.extend(["--dst", path_tujuan])

    if action in ["copy", "move"]:
        # Salin/pindah bisa lama, jadi dijalankan di latar belakang.
        skrip = Path(SISTEM_LOKAL_API_SCRIPT)
        if not skrip.exists():
            return f"Gagal: berkas bantuan '{skrip.name}' tidak ditemukan."
        try:
            subprocess.Popen(
                [cari_python_console(), str(skrip)] + argumen,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return (f"Proses {action} sedang berjalan di latar belakang. "
                    f"Tanyakan 'udah berapa persen?' untuk memeriksa kemajuannya.")
        except Exception as e:
            return f"Gagal menjalankan {action}: {e}"

    # Hapus/aksi lain dijalankan sambil menunggu supaya hasilnya pasti diketahui.
    return _jalankan_bantuan(argumen)

def cek_disk_lokal(drive: str = "C:\\"):
    """Mengecek sisa ruang hard disk dan kapasitas total."""
    return _jalankan_bantuan(["--action", "cek_disk", "--drive", drive])

def buka_aplikasi_lokal(nama_aplikasi: str):
    """Membuka aplikasi lokal Windows."""
    try:
        from plugins.system_plugin import buka_aplikasi as system_buka_aplikasi
        return system_buka_aplikasi(nama_aplikasi)
    except Exception as e:
        return f"Gagal buka aplikasi: {str(e)}"

def cek_progress_tugas():
    """Mengecek progress tugas background seperti video render dan copy file."""
    try:
        hasil = []
        
        # 1. Progress Video Render (jika ada variabel global status_pekerjaan_video di modul utama)
        try:
            import bot_otomatis
            status_pekerjaan_video = getattr(bot_otomatis, 'status_pekerjaan_video', None)
            if status_pekerjaan_video and status_pekerjaan_video.get("aktif"):
                hasil.append(
                    f"🎬 **Render Video:** {status_pekerjaan_video.get('nama_tugas', 'Editing Video')}\n"
                    f"Status: {status_pekerjaan_video.get('keterangan', 'Sedang berjalan di latar belakang...')}"
                )
        except Exception:
            pass

        # 2. Progress File Copy / Background Tasks
        file_prog = PROGRESS_JSON_PATH
        if os.path.exists(file_prog):
            try:
                with open(file_prog, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    for tugas, persen in data.items():
                        if "100%" not in str(persen):
                            hasil.append(f"📦 **{tugas}:** {persen}")
            except Exception:
                pass

        if not hasil:
            return "☕ Sari sedang bersantai, tidak ada pekerjaan video render atau penyalinan file yang berjalan di latar belakang saat ini."
            
        return "📊 *Status Progres Latar Belakang saat ini:*\n\n" + "\n\n".join(hasil)
    except Exception as e:
        return f"Gagal mengecek progres: {str(e)}"

def putar_folder_musik_lokal(path_folder: str):
    """Memutar seluruh file audio dalam sebuah folder secara berurutan."""
    return _jalankan_bantuan(["--action", "putar_folder", "--src", path_folder])

def putar_lagu_lokal(kata_kunci: str):
    """Mencari lagu di folder Music Windows berdasarkan kata kunci dan langsung memutarnya."""
    try:
        musik_dir = os.path.join(os.path.expanduser("~"), "Music")
        if not os.path.exists(musik_dir):
            return "Folder Music default tidak ditemukan."
        
        found_file = None
        for root, dirs, files in os.walk(musik_dir):
            for file in files:
                if kata_kunci.lower() in file.lower() and file.lower().endswith(('.mp3', '.wav', '.flac', '.m4a')):
                    found_file = os.path.join(root, file)
                    break
            if found_file:
                break
            
        if found_file:
            os.startfile(found_file)
            return f"🎵 Sedang memutar lagu: {os.path.basename(found_file)}"
        else:
            return f"❌ Lagu dengan kata kunci '{kata_kunci}' tidak ditemukan di {musik_dir}"
    except Exception as e:
        return f"Gagal memutar lagu: {str(e)}"
