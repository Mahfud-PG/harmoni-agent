"""
Harmoni Agent - Penyiapan Berkas Awal (First Run)

Tujuan: aplikasi bisa dijalankan di komputer mana pun tanpa membawa data pribadi.

Cara kerja:
- Berkas rahasia/pribadi TIDAK ikut dibungkus ke paket publik (lihat PACKAGING_EXCLUDE.txt).
- Sebagai gantinya, folder `templates/` memuat versi kosong yang aman.
- Saat aplikasi pertama kali dijalankan, berkas yang belum ada akan disalin dari `templates/`.
- Berkas yang SUDAH ada tidak pernah ditimpa, jadi data pengguna tetap aman.
"""

import json
import logging
import shutil
from pathlib import Path

from sari_core.paths import DATA_ROOT, TEMPLATE_DIR

logger = logging.getLogger(__name__)

# Berkas konfigurasi yang boleh dibuat otomatis dari template.
BERKAS_TEMPLATE = [
    "personalisasi.json",
    "konfigurasi_wa.json",
    "konfigurasi_multi_wa.json",
    "konfigurasi_otak.json",
    "konfigurasi_email.json",
    "konfigurasi_youtube.json",
    "kontak_tersimpan.json",
    "pending_wa_sends.json",
    "admin_wa_status.json",
    "riwayat_youtube.json",
    "progress.json",
    "ingatan_sari.json",
    # Pengaturan sinkronisasi Google Drive & pencadangan. Nilai folder bawaan
    # sengaja dibiarkan kosong; diisi otomatis mengikuti drive yang tersedia dan
    # nama asisten pengguna (lihat sari_core/sinkronisasi_config.py).
    "konfigurasi_sinkronisasi.json",
    # Kredensial OAuth gerbang desktop bawaan untuk otorisasi Google Drive & YouTube
    "client_secret.json",
]

# Nama bawaan kalau templatenya pun tidak ada.
BAWAAN = {
    "personalisasi.json": {
        "bot_name": "Harmoni",
        "user_call_name": "",
        "tone": "santai",
        "enthusiasm": "sedang",
        "emoji_level": "sedikit",
        "format_style": "ringkas",
        "custom_instructions": "",
        "voice_provider": "edge",
        "voice_type": "wanita",
        "voice_rate": "1.0",
        "elevenlabs_voice_id": "",
        "google_voice_name": "",
        "app_language": "en",
    },
    "konfigurasi_wa.json": {"admin_wa_enabled": False, "wa_bot_name": "Admin"},
    "konfigurasi_multi_wa.json": {"active_profile": None, "profiles": []},
    "konfigurasi_email.json": {"admin_email_enabled": False, "notify_telegram": False},
    "konfigurasi_youtube.json": {"satpam_youtube_enabled": False, "notify_telegram": False},
    "kontak_tersimpan.json": {},
    "pending_wa_sends.json": {},
    "admin_wa_status.json": {"admin_wa": False},
    "riwayat_youtube.json": [],
    "progress.json": {},
    "ingatan_sari.json": {"catatan": [], "jadwal": []},
}


def berkas_awal_belum_ada() -> bool:
    """True bila aplikasi ini belum pernah disiapkan (belum ada personalisasi)."""
    return not (DATA_ROOT / "personalisasi.json").exists()


def siapkan_berkas_awal() -> list:
    """Buat berkas konfigurasi yang belum ada. Kembalikan daftar berkas yang dibuat."""
    dibuat = []
    for nama in BERKAS_TEMPLATE:
        tujuan = DATA_ROOT / nama
        if tujuan.exists():
            continue  # JANGAN pernah menimpa data yang sudah ada

        sumber = TEMPLATE_DIR / nama
        try:
            if sumber.exists():
                shutil.copy2(sumber, tujuan)
            else:
                isi = BAWAAN.get(nama, {})
                tujuan.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding="utf-8")
            dibuat.append(nama)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Gagal menyiapkan berkas awal '{nama}': {e}")

    if dibuat:
        logger.info(f"Penyiapan berkas awal selesai. Dibuat: {', '.join(dibuat)}")

    # Berkas .env kosong supaya aplikasi tidak gagal saat membaca kunci yang belum diisi.
    env_file = DATA_ROOT / ".env"
    if not env_file.exists():
        try:
            env_file.write_text(
                "# Simpan kunci API di sini, atau lewat Panduan Pemasangan di dalam aplikasi.\n",
                encoding="utf-8",
            )
            dibuat.append(".env")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Gagal membuat berkas .env: {e}")

    # Pindahkan basis data obrolan dari lokasi LAMA (di dalam folder program) ke folder
    # DATA pengguna. Disalin, bukan dipindah, supaya berkas lama tetap ada sebagai jaring
    # pengaman. Ini yang membuat riwayat obrolan lama tidak hilang.
    try:
        from sari_core.paths import DB_FILE, DB_FILE_LAMA
        if DB_FILE_LAMA.exists() and DB_FILE_LAMA != DB_FILE:
            # Berkas di lokasi baru dianggap "belum ada" kalau memang tidak ada
            # ATAU kosong (0 byte), supaya berkas kosong tidak menghalangi pemindahan.
            berkas_baru_kosong = (not DB_FILE.exists()) or DB_FILE.stat().st_size == 0
            if berkas_baru_kosong and DB_FILE_LAMA.stat().st_size > 0:
                shutil.copy2(DB_FILE_LAMA, DB_FILE)
                logger.info(f"Basis data obrolan dipindahkan ke folder data: {DB_FILE}")
                dibuat.append("sari_memory.db (dipindahkan)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Gagal memindahkan basis data obrolan: {e}")

    return dibuat
