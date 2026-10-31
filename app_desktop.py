import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path
import webview

APP_VERSION = "1.0.1"  # Keep aligned with the installer and release tag.


class DesktopUpdateAPI:
    """Only expose explicit updater operations to the local desktop WebView."""

    def __init__(self, data_dir):
        self.manager = UpdateManager(data_dir)
        self.available = None
        self.staged = None

    def settings(self):
        return {"auto_check": self.manager.enabled(), "version": APP_VERSION}

    def set_auto_check(self, enabled):
        return {"auto_check": self.manager.set_enabled(enabled is True)}

    def check(self):
        self.available = None
        self.staged = None
        try:
            self.available = self.manager.check(APP_VERSION)
            return {"available": self.available}
        except Exception as exc:
            return {"error": str(exc)}

    def download(self):
        if not self.available:
            return {"error": "Periksa pembaruan terlebih dahulu."}
        try:
            self.staged = self.manager.download(self.available)
            return {"ready": True, "version": self.available["version"]}
        except Exception as exc:
            self.staged = None
            return {"error": str(exc)}

    def install(self):
        if not self.staged or not self.available:
            return {"error": "Unduh dan verifikasi installer terlebih dahulu."}
        try:
            self.manager.install(self.staged, self.available["sha256"])
            self.staged = None  # Prevent a second launch without another download.
            return {"launched": True}
        except Exception as exc:
            return {"error": str(exc)}


CURRENT_DIR = Path(__file__).parent.resolve()

# PENTING: folder program harus masuk sys.path DULU.
# Python tertanam (runtime/ di aplikasi terpasang) memakai berkas python314._pth
# yang mengunci sys.path, sehingga folder skrip ini TIDAK otomatis ikut dicari.
# Tanpa baris berikut, `from sari_core.paths import ...` di bawah gagal dengan
# ModuleNotFoundError - dan karena jendela dijalankan tanpa konsol (pythonw),
# pengguna hanya melihat "tidak terjadi apa-apa" saat menekan pintasan.
# Kejadiannya hanya saat layanan belum hidup (ensure_backend_alive harus
# menyalakannya); kalau layanan sudah jalan, baris itu tidak pernah tersentuh.
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from update_manager import UpdateManager


def ensure_backend_alive():
    """Cek apakah service background sudah hidup. Jika belum, nyalakan."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/", timeout=1.5) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    # Jalankan background service jika belum aktif tanpa jendela konsol.
    # Di aplikasi terpasang, Python ikut dibundel di folder runtime/ sehingga
    # kita tidak bergantung pada Python yang dipasang di komputer pengguna.
    from sari_core.paths import cari_python_gui, env_bridge
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([cari_python_gui(), "service_background.py"],
                     cwd=str(CURRENT_DIR), creationflags=flags, env=env_bridge())
    # Beri waktu lebih panjang: di komputer baru, penyalaan pertama bisa memakan
    # waktu karena harus menyiapkan folder data, berkas pengaturan, dan memuat 150-an alat.
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8001/", timeout=2.0) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
    return False

def main():
    ensure_backend_alive()
    ui_html_path = CURRENT_DIR / "index.html"

    # Pemasangan pertama: kalau panduan belum pernah diselesaikan, buka panduannya dulu.
    # Dengan begitu pengguna baru langsung dipandu mengisi kunci AI dan fitur lainnya.
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/pemasangan/status", timeout=5) as r:
            import json as _json
            st = _json.loads(r.read().decode("utf-8"))
        # Hanya muncul kalau pemasangan memang BELUM ditandai selesai (nilai persis false).
        # Kalau kuncinya tidak ada sama sekali (aplikasi lama yang diperbarui), panduan
        # tidak dimunculkan supaya pengguna lama tidak terganggu.
        if st.get("selesai") is False:
            panduan = CURRENT_DIR / "pemasangan_pertama.html"
            if panduan.exists():
                ui_html_path = panduan
    except Exception:
        pass

    user_data = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "HarmoniAgent"
    window = webview.create_window(
        title="Harmoni Agent",
        js_api=DesktopUpdateAPI(user_data),
        url=str(ui_html_path),
        width=1000,
        height=720,
        min_size=(680, 500),
        background_color="#0f1115",
        text_select=True,
        zoomable=True
    )
    webview.start(debug=False)

if __name__ == "__main__":
    main()
