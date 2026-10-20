import os
import json
import logging
from sari_core.paths import ACCESS_CONFIG_FILE

logger = logging.getLogger("SariAccessControl")

CONFIG_PATH = str(ACCESS_CONFIG_FILE)
DEFAULT_OWNER_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def load_access_config() -> dict:
    """Memuat konfigurasi akses dari file JSON. Jika belum ada, dibuat otomatis."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "owner_id" in data and "allowed_users" in data:
                    return data
        except Exception as e:
            logger.error(f"Gagal membaca konfigurasi_akses.json: {e}")

    # Default fallback
    owner = os.getenv("TELEGRAM_OWNER_ID") or os.getenv("TELEGRAM_CHAT_ID") or DEFAULT_OWNER_ID
    default_config = {
        "owner_id": str(owner),
        "allowed_users": {
            str(owner): "Pemilik (utama)"
        }
    }
    save_access_config(default_config)
    return default_config

def save_access_config(config: dict):
    """Menyimpan konfigurasi akses secara aman."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Gagal menyimpan konfigurasi_akses.json: {e}")

def get_owner_id() -> str:
    """Mengembalikan ID Telegram pemilik utama."""
    cfg = load_access_config()
    return str(cfg.get("owner_id", DEFAULT_OWNER_ID))

def is_user_authorized(user_id: int | str) -> bool:
    """Memeriksa apakah ID Telegram pengguna terdaftar dan diizinkan mengakses bot."""
    if not user_id:
        return False
    uid = str(user_id).strip()
    cfg = load_access_config()
    owner_id = str(cfg.get("owner_id", ""))
    allowed = cfg.get("allowed_users", {})
    return uid == owner_id or uid in allowed

def add_allowed_user(target_id: int | str, label: str = "") -> tuple[bool, str]:
    """Mendaftarkan ID Telegram baru ke daftar akses resmi."""
    tid = str(target_id).strip()
    if not tid.isdigit():
        return False, "❌ Format ID tidak valid. ID Telegram harus berupa susunan angka (Contoh: `123456789`)."

    cfg = load_access_config()
    allowed = cfg.setdefault("allowed_users", {})

    if tid in allowed:
        current_label = allowed[tid]
        return False, f"⚠️ ID `{tid}` sudah terdaftar sebelumnya sebagai: **{current_label}**."

    label_clean = label.strip() if label else f"Pengguna Tambahan ({tid})"
    allowed[tid] = label_clean
    save_access_config(cfg)
    return True, f"✅ Berhasil mendaftarkan ID Telegram baru:\n🆔 **ID:** `{tid}`\n🏷️ **Keterangan:** {label_clean}\n\nSekarang akun tersebut memiliki akses penuh ke asisten Siti."

def remove_allowed_user(target_id: int | str) -> tuple[bool, str]:
    """Menghapus ID Telegram dari daftar akses resmi."""
    tid = str(target_id).strip()
    cfg = load_access_config()
    owner_id = str(cfg.get("owner_id", DEFAULT_OWNER_ID))

    if tid == owner_id:
        return False, "⛔ **Aksi Ditolak demi Keamanan:** ID Pemilik Utama (`" + tid + "`) diproteksi permanen dan tidak dapat dihapus."

    allowed = cfg.get("allowed_users", {})
    if tid not in allowed:
        return False, f"⚠️ ID `{tid}` tidak ditemukan di dalam daftar akses resmi."

    removed_label = allowed.pop(tid)
    save_access_config(cfg)
    return True, f"✅ Berhasil mencabut akses untuk:\n🆔 **ID:** `{tid}` ({removed_label})\n\nAkun tersebut tidak lagi dapat berinteraksi dengan Siti."

def format_access_menu() -> str:
    """Menghasilkan teks daftar akun resmi yang terdaftar untuk tampilan Telegram."""
    cfg = load_access_config()
    owner_id = str(cfg.get("owner_id", DEFAULT_OWNER_ID))
    allowed = cfg.get("allowed_users", {})

    lines = [
        "🛡️ **DAFTAR AKSES RESMI TELEGRAM SITI**",
        "Sistem proteksi aktif: Hanya akun terdaftar yang dapat berinteraksi dengan bot.",
        "",
        f"👑 **Pemilik Utama:** `{owner_id}` (pengguna)",
        "",
        "👥 **Daftar Akun yang Diizinkan:**"
    ]

    idx = 1
    for uid, lbl in allowed.items():
        is_owner_tag = " [👑 Owner]" if uid == owner_id else ""
        lines.append(f"   {idx}. `{uid}` — {lbl}{is_owner_tag}")
        idx += 1

    lines.extend([
        "",
        "📌 **Cara Mengelola Akses:**",
        "- **Tambah Akun:** `/tambah_id <id_telegram> [keterangan]`",
        "  *Contoh:* `/tambah_id 123456789 Akun Cadangan`",
        "- **Hapus Akun:** `/hapus_id <id_telegram>`",
        "  *Contoh:* `/hapus_id 123456789`",
        "- **Cek ID Akun Anda:** `/my_id` atau `/id`",
        "- *Atau obrolan santai:* 'Siti, tambah id 123456789 Akun Cadangan'"
    ])

    return "\n".join(lines)
