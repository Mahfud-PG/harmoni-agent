"""
Harmoni Agent - Pemuat Profil WhatsApp Multi-Nomor
Menyediakan identitas usaha yang BENAR sesuai nomor WA yang sedang aktif,
sehingga asisten tidak lagi tertukar antara profil nomor 1, nomor 2, dan seterusnya.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from sari_core.paths import PROJECT_ROOT
except Exception:  # pragma: no cover
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Kata kunci untuk mendeteksi jenis usaha "studio musik / rekaman"
_KATA_KUNCI_RECORDING = [
    "studio", "rekaman", "recording", "mixing", "mastering", "minus one",
    "backing track", "cover", "lagu", "musik", "song", "jingle",
]


def deteksi_jenis_usaha(profil: dict) -> str:
    """Menebak jenis usaha dari nama usaha + info tambahan + label profil."""
    gabung = " ".join(
        str(profil.get(kunci, "") or "")
        for kunci in ("business_name", "custom_info", "label", "portfolio_links")
    ).lower()
    if any(k in gabung for k in _KATA_KUNCI_RECORDING):
        return "recording"
    return "umum"


def _default_profil() -> dict:
    return {
        "profile_id": "nomor_1",
        "bot_name": "Admin",
        "business_name": "Layanan Kami",
        "business_address": "",
        "tone": "formal",
        "custom_info": "",
        "portfolio": "",
        "vip_numbers": "",
        "owner_name": "",
        "notify_telegram": True,
        "auto_transcribe_vn": False,
        "admin_wa_enabled": True,
        "jenis_usaha": "umum",
        "attachments": [],
        "auto_reply_mode": "off",
        "auto_reply_text": "",
        "business_hours_open": "09:00",
        "business_hours_close": "18:00",
        "quick_replies": [],
    }


def _normalisasi(pdata: dict, profile_id: str) -> dict:
    profil = _default_profil()
    profil.update({
        "profile_id": profile_id or pdata.get("id") or "nomor_1",
        "bot_name": pdata.get("wa_bot_name") or pdata.get("bot_name") or "Admin",
        "business_name": pdata.get("business_name") or pdata.get("studio_name") or "Layanan Kami",
        "business_address": pdata.get("business_address") or pdata.get("studio_address") or "",
        "tone": pdata.get("wa_tone") or "formal",
        "custom_info": pdata.get("custom_info") or pdata.get("custom_studio_info") or "",
        "portfolio": pdata.get("portfolio_links") or "",
        "vip_numbers": pdata.get("owner_name") or pdata.get("vip_numbers") or "",
        "owner_name": pdata.get("owner_name") or pdata.get("vip_numbers") or "",
        "notify_telegram": pdata.get("notify_telegram", True),
        "auto_transcribe_vn": pdata.get("auto_transcribe_vn", False),
        "admin_wa_enabled": pdata.get("admin_wa_enabled", True),
        "attachments": pdata.get("attachments", []) or [],
        "auto_reply_mode": pdata.get("auto_reply_mode", "off"),
        "auto_reply_text": pdata.get("auto_reply_text", ""),
        "business_hours_open": pdata.get("business_hours_open", "09:00"),
        "business_hours_close": pdata.get("business_hours_close", "18:00"),
        "quick_replies": pdata.get("quick_replies", []) or [],
    })
    profil["jenis_usaha"] = deteksi_jenis_usaha(profil)
    return profil


def muat_profil_wa(profile_id: str = None) -> dict:
    """
    Memuat profil WhatsApp yang aktif (atau profil tertentu bila profile_id diberikan).

    Urutan sumber:
      1. konfigurasi_multi_wa.json  -> profil aktif / profil yang diminta
      2. konfigurasi_wa.json        -> berkas lama (fallback)
      3. Nilai bawaan aman          -> identitas netral tanpa data pribadi
    """
    multi_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
    legacy_file = PROJECT_ROOT / "konfigurasi_wa.json"

    # 1. Multi-profil
    if multi_file.exists():
        try:
            with open(multi_file, "r", encoding="utf-8") as f:
                m_all = json.load(f)
            semua_profil = m_all.get("profiles", {}) or {}
            target = profile_id or m_all.get("active_profile") or (next(iter(semua_profil), None))
            if target and target in semua_profil:
                return _normalisasi(semua_profil[target], target)
        except Exception as e:
            logger.warning(f"[WA Profil] Gagal membaca konfigurasi_multi_wa.json: {e}")

    # 2. Berkas lama
    if legacy_file.exists():
        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            return _normalisasi(legacy, profile_id or "nomor_1")
        except Exception as e:
            logger.warning(f"[WA Profil] Gagal membaca konfigurasi_wa.json: {e}")

    # 3. Bawaan aman
    return _default_profil()


def muat_profil_wa_aktif() -> dict:
    """Pintasan: memuat profil WhatsApp yang sedang aktif."""
    return muat_profil_wa(None)
