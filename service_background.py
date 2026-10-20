import os
import sys
import logging
import subprocess
from pathlib import Path

# ANTI-JENDELA HITAM: Pastikan semua subprocess/os.system tidak pernah memunculkan jendela konsol hitam (CMD/PowerShell)
if os.name == "nt":
    _orig_popen_init = subprocess.Popen.__init__
    def _silent_popen_init(self, *args, **kwargs):
        cf = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = cf | subprocess.CREATE_NO_WINDOW
        return _orig_popen_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _silent_popen_init

    def _silent_system(cmd):
        return subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW).returncode
    os.system = _silent_system

CURRENT_DIR = Path(__file__).parent.resolve()
# PENTING: folder program harus masuk sys.path DULU. Pada Python tertanam
# (yang memakai berkas ._pth), folder skrip tidak otomatis ikut sys.path.
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from sari_core.paths import DATA_ROOT  # folder data pengguna (bisa beda dari folder program)
AI_ASISTEN_DIR = DATA_ROOT

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# PENTING: kalau dijalankan tanpa jendela konsol (misalnya lewat skrip startup otomatis),
# sys.stdout / sys.stderr bernilai None. Uvicorn memanggil sys.stdout.isatty() saat menyusun
# konfigurasi log, sehingga gagal dan layanan mati dengan pesan "Unable to configure formatter".
# Karena itu keduanya dipastikan selalu ada sebelum uvicorn dinyalakan.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r", encoding="utf-8")

# Setup file logging agar status background bisa selalu dipantau
log_file = DATA_ROOT / "service.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("HarmoniService")
logger.info("Harmoni Background Service mulai berjalan...")

import uvicorn

# Konfigurasi log uvicorn yang aman: tidak memanggil deteksi warna terminal sama sekali,
# sehingga tetap bekerja baik dengan maupun tanpa jendela konsol.
LOG_CONFIG_AMAN = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"polos": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"}},
    "handlers": {"layar": {"class": "logging.StreamHandler", "formatter": "polos",
                           "stream": "ext://sys.stdout"}},
    "loggers": {
        "uvicorn": {"handlers": ["layar"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["layar"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["layar"], "level": "WARNING", "propagate": False},
    },
}


def _sudah_berjalan() -> bool:
    """Cek apakah gateway sudah hidup, supaya tidak ada dua layanan sekaligus."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    if _sudah_berjalan():
        logger.info("Layanan Harmoni sudah berjalan. Proses baru ini berhenti agar tidak dobel.")
        return
    try:
        from server_core import app
        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=8001,
            log_level="info",
            access_log=False,
            log_config=LOG_CONFIG_AMAN,
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        logger.error(f"Fatal error di Service Background: {e}", exc_info=True)


if __name__ == "__main__":
    main()
