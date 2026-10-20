"""
Harmoni Agent - Pengaturan Jalur Terpusat

Ada DUA jangkar folder yang harus dibedakan:

1. PROGRAM_ROOT  -> tempat programnya berada (sari_core/, plugins/, wa_bridge/,
                    templates/). Isinya diganti setiap ada versi baru.
2. DATA_ROOT     -> tempat data pengguna (obrolan, kontak, sesi WhatsApp, kunci API,
                    berkas hasil kerja). TIDAK PERNAH disentuh saat aplikasi diperbarui.

Saat masih dikembangkan langsung dari folder kerja, keduanya sama (DATA_ROOT = PROGRAM_ROOT)
sehingga tidak ada perilaku yang berubah. Saat sudah TERPASANG sebagai aplikasi,
sebuah penanda bernama MODE_TERPASANG membuat DATA_ROOT berpindah ke
%APPDATA%\\HarmoniAgent supaya data pengguna tetap aman.

PROJECT_ROOT sengaja tetap dipertahankan dan menunjuk ke DATA_ROOT, karena hampir
seluruh modul lama memakainya untuk berkas konfigurasi dan data.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Jangkar folder program
# ---------------------------------------------------------------------------
PROGRAM_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 2. Jangkar folder data pengguna
# ---------------------------------------------------------------------------
PENANDA_TERPASANG = PROGRAM_ROOT / "MODE_TERPASANG"

if PENANDA_TERPASANG.exists():
    # Mode terpasang: data pengguna hidup di %APPDATA%\HarmoniAgent
    _appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    DATA_ROOT = Path(_appdata) / "HarmoniAgent"
else:
    # Mode pengembangan: semuanya di folder kerja (perilaku lama, tidak berubah)
    DATA_ROOT = PROGRAM_ROOT

# Dipertahankan agar seluruh modul lama tetap bekerja tanpa diubah.
PROJECT_ROOT = DATA_ROOT

# ---------------------------------------------------------------------------
# 3. Sub-folder PROGRAM (ikut diganti saat ada versi baru)
# ---------------------------------------------------------------------------
CORE_DIR = PROGRAM_ROOT / "sari_core"
PLUGINS_DIR = PROGRAM_ROOT / "plugins"
WA_BRIDGE_DIR = PROGRAM_ROOT / "wa_bridge"
TEMPLATE_DIR = PROGRAM_ROOT / "templates"
RUNTIME_DIR = PROGRAM_ROOT / "runtime"

# ---------------------------------------------------------------------------
# 4. Sub-folder DATA (milik pengguna, tidak boleh hilang)
# ---------------------------------------------------------------------------
FILE_DIR = DATA_ROOT / "File"
DOWNLOADS_DIR = FILE_DIR / "Downloads"
TEMP_DIR = FILE_DIR / "Temp"
OUTPUT_DIR = FILE_DIR / "Output"
OBSIDIAN_DIR = DATA_ROOT / "Obsidian_Vault"

# Sesi WhatsApp ditulis oleh wa_bridge.js. Saat aplikasi SUDAH TERPASANG, sesi
# ditaruh di folder DATA supaya nomor yang sudah dipindai tidak perlu dipindai ulang
# setiap aplikasi diperbarui. Saat masih dikembangkan, lokasi lama dipertahankan
# supaya sesi WhatsApp yang sudah ada tidak hilang.
if PENANDA_TERPASANG.exists():
    WA_AUTH_DIR = DATA_ROOT / "baileys_auth"
else:
    WA_AUTH_DIR = WA_BRIDGE_DIR / "baileys_auth"

# Berkas konfigurasi dan kredensial utama (milik pengguna)
ENV_FILE = DATA_ROOT / ".env"
CLIENT_SECRET_FILE = DATA_ROOT / "client_secret.json"
ACCESS_CONFIG_FILE = DATA_ROOT / "konfigurasi_akses.json"
MODEL_CONFIG_FILE = DATA_ROOT / "konfigurasi_model.json"
ADMIN_WA_STATUS_FILE = DATA_ROOT / "admin_wa_status.json"
OPENROUTER_CACHE_FILE = DATA_ROOT / "openrouter_cache.json"

# Basis data obrolan. Dulu letaknya DI DALAM folder program (sari_core/), sehingga
# berisiko hilang saat aplikasi diperbarui. Sekarang di folder DATA pengguna.
DB_FILE = DATA_ROOT / "sari_memory.db"
LOG_DIR = DATA_ROOT / "logs"

# Letak lama basis data, dipakai sekali untuk memindahkan data pengguna yang sudah ada.
DB_FILE_LAMA = PROGRAM_ROOT / "sari_core" / "sari_memory.db"

# Browser Chromium bawaan untuk fitur TikTok (playwright). Tanpa penunjuk ini,
# playwright mencari di folder pengguna Windows dan tidak akan menemukannya.
MS_PLAYWRIGHT_DIR = RUNTIME_DIR / "python" / "ms-playwright"
if MS_PLAYWRIGHT_DIR.exists():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(MS_PLAYWRIGHT_DIR))

# Pastikan folder penyimpanan dasar selalu tersedia
for directory in [DATA_ROOT, FILE_DIR, DOWNLOADS_DIR, TEMP_DIR, OUTPUT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


def get_drive_token_path(account_name: str = "utama") -> Path:
    """Mengembalikan path token Google Drive untuk akun tertentu."""
    return DATA_ROOT / f"token_drive_{account_name}.json"


def get_youtube_token_path(account_name: str = "utama") -> Path:
    """Mengembalikan path token YouTube untuk akun tertentu."""
    return DATA_ROOT / f"token_{account_name}.json"


def env_bridge() -> dict:
    """Salinan lingkungan hidup untuk wa_bridge.js.

    Memberi tahu Node.js di mana folder DATA berada, supaya sesi WhatsApp dan
    konfigurasi multi-nomor tetap berada di folder pengguna (bukan folder program)
    ketika aplikasi sudah terpasang.
    """
    env = os.environ.copy()
    env["HARMONI_DATA_DIR"] = str(DATA_ROOT)
    env["HARMONI_WA_AUTH"] = str(WA_AUTH_DIR)
    return env


def cari_node() -> str:
    """Tentukan perintah Node.js yang dipakai.

    Di aplikasi terpasang, Node.js ikut dibundel di folder `runtime/`, jadi kita
    TIDAK bergantung pada Node.js yang dipasang di komputer pengguna.
    Kalau tidak ditemukan, jatuh kembali ke perintah "node" biasa.
    """
    if RUNTIME_DIR.exists():
        for kandidat in sorted(RUNTIME_DIR.rglob("node.exe")):
            return str(kandidat)
    return "node"


def cari_python_gui() -> str:
    """Python tanpa jendela hitam untuk menjalankan aplikasi dan daemon latar."""
    for nama in ("pythonw.exe", "python.exe"):
        kandidat = RUNTIME_DIR / "python" / nama
        if kandidat.exists():
            return str(kandidat)
    import sys
    return sys.executable


def cari_python_console() -> str:
    """Python untuk menjalankan skrip bantuan yang hasilnya DIBACA (stdout).

    Diutamakan python.exe (bukan pythonw.exe) karena skrip bantuan dimaksudkan
    untuk menulis hasil ke stdout; pythonw tidak menyediakan konsol.

    JANGAN memakai launcher `py` milik Windows: launcher itu hanya ada kalau
    Python terpasang di komputer pengguna, sedangkan aplikasi ini membawa
    Python-nya sendiri. Memakai `py` membuat seluruh alat lokal (baca folder,
    cek disk, cari berkas, kelola berkas) gagal diam-diam di komputer penerima.
    """
    for nama in ("python.exe", "pythonw.exe"):
        kandidat = RUNTIME_DIR / "python" / nama
        if kandidat.exists():
            return str(kandidat)
    import sys
    return sys.executable


# Skrip bantuan ada di folder PROGRAM (ikut diganti saat ada versi baru), BUKAN
# di folder data. Menghitungnya dari DATA_ROOT membuat skrip tidak ditemukan
# ketika aplikasi sudah terpasang, dan setiap alat mengembalikan teks kosong.
SKRIP_LOKAL_API = PROGRAM_ROOT / "sistem_lokal_api.py"
SKRIP_YOUTUBE_API = PROGRAM_ROOT / "youtube_api.py"
SKRIP_DRIVE_API = PROGRAM_ROOT / "drive_api.py"
