import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path
import webview

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

    window = webview.create_window(
        title="Harmoni Agent",
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
