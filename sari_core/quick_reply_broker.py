"""Harmoni Agent - Broker Balas Cepat Telegram ke Channel Eksternal.

Memungkinkan pengguna membalas pesan masuk dari berbagai saluran (WhatsApp, Email,
Facebook Messenger, dll) langsung dari obrolan Telegram via tombol interaktif.
"""

import time
import logging

logger = logging.getLogger(__name__)

# Registry penampung target balasan aktif:
# reply_id -> { "channel": ..., "to": ..., "name": ..., "subject": ..., "profile_id": ..., "timestamp": ... }
_PENDING_REPLIES = {}


def register_reply_target(channel: str, to: str, name: str = "", subject: str = "", profile_id: str = "") -> str:
    """Mendaftarkan target balasan baru dan menghasilkan reply_id ringkas (<64 bytes)."""
    now = time.time()
    # Bersihkan entri lama (> 24 jam)
    for rid in list(_PENDING_REPLIES.keys()):
        if now - _PENDING_REPLIES[rid].get("timestamp", 0) > 86400:
            _PENDING_REPLIES.pop(rid, None)

    reply_id = f"r_{int(now * 1000) % 100000000}_{len(_PENDING_REPLIES) + 1}"
    _PENDING_REPLIES[reply_id] = {
        "channel": str(channel).lower().strip(),
        "to": str(to).strip(),
        "name": str(name).strip() or str(to).strip(),
        "subject": str(subject).strip(),
        "profile_id": str(profile_id).strip(),
        "timestamp": now
    }
    return reply_id


def get_reply_target(reply_id: str) -> dict:
    """Mengambil informasi target balasan berdasarkan reply_id."""
    return _PENDING_REPLIES.get(reply_id, {})


def pop_reply_target(reply_id: str) -> dict:
    """Mengambil sekaligus menghapus target balasan (one-time use)."""
    return _PENDING_REPLIES.pop(reply_id, {})
