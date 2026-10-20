"""Harmoni Agent - Pengaturan Sinkronisasi Google Drive & Pencadangan.

Seluruh pilihan ada di SATU berkas: konfigurasi_sinkronisasi.json di folder DATA
pengguna. Tidak ada alamat yang dipaku di dalam kode, sehingga pengguna bisa
memindahkan folder sinkronisasi tanpa menyentuh kode sama sekali.

Isi berkas:
    aktif                 : sinkronisasi hidup atau mati (TAHAN restart)
    mode                  : "aman" (tidak pernah menghapus) atau "penuh"
    folder_lokal          : folder di PC yang disinkronkan ke Drive
    folder_drive          : nama folder di Google Drive
    interval_menit        : jarak pemeriksaan sinkronisasi
    cadangan_aktif        : membuat ZIP cadangan otomatis atau tidak
    cadangan_interval_jam : jarak pembuatan ZIP cadangan
    cadangan_simpan_versi : berapa versi ZIP lama yang disimpan di PC
"""

import json
import os
import sys
from pathlib import Path

# Penyangga: berkas ini harus bisa dipakai DUA cara - diimpor sebagai
# `sari_core.sinkronisasi_config` (cara aplikasi) DAN dijalankan langsung untuk
# pengujian. Tanpa baris ini, menjalankannya langsung gagal dengan
# "ModuleNotFoundError: No module named 'sari_core'".
_AKAR_PROYEK = Path(__file__).resolve().parent.parent
if str(_AKAR_PROYEK) not in sys.path:
    sys.path.insert(0, str(_AKAR_PROYEK))

from sari_core.paths import DATA_ROOT, PROGRAM_ROOT

NAMA_BERKAS = "konfigurasi_sinkronisasi.json"
BERKAS_PENGATURAN = DATA_ROOT / NAMA_BERKAS
BERKAS_CONTOH = PROGRAM_ROOT / "templates" / NAMA_BERKAS

# Nama berkas cadangan sengaja TETAP (tidak bertanggal) supaya di Google Drive
# selalu ditimpa, bukan menumpuk. Kalau bertanggal, mode "aman" tidak pernah
# menghapus apa pun sehingga Drive akan penuh dalam beberapa bulan.
NAMA_CADANGAN_DRIVE = "Cadangan_Harmoni_Terbaru.zip"

MODE_AMAN = "aman"
MODE_PENUH = "penuh"


def _drive_lain() -> Path | None:
    """Cari drive selain C: untuk menaruh cadangan, supaya tidak ikut hilang
    kalau Windows dipasang ulang."""
    for huruf in ("D", "E", "F"):
        akar = Path(f"{huruf}:\\")
        try:
            if akar.exists():
                return akar
        except OSError:
            continue
    return None


def folder_cadangan_bawaan() -> Path:
    """Folder cadangan bawaan. Diutamakan di drive selain C:."""
    drive = _drive_lain()
    if drive:
        return drive / "HarmoniAgent_Cadangan"
    return Path.home() / "Documents" / "HarmoniAgent_Cadangan"


def nama_asisten() -> str:
    """Nama asisten yang sedang dipakai pengguna (dari personalisasi.json)."""
    try:
        berkas = DATA_ROOT / "personalisasi.json"
        if berkas.exists():
            with open(berkas, "r", encoding="utf-8") as f:
                data = json.load(f)
            nama = (data.get("bot_name") or "").strip()
            if nama:
                return nama
    except Exception:
        pass
    return "Harmoni"


def _nilai_bawaan() -> dict:
    return {
        "aktif": False,
        "mode": MODE_AMAN,
        "folder_lokal": str(folder_cadangan_bawaan()),
        "folder_drive": f"{nama_asisten()}_Sync",
        "interval_menit": 10,
        # Nama folder yang TIDAK ikut disinkronkan ke Drive. "Riwayat" berisi
        # salinan cadangan lama; kalau ikut disinkronkan, mode aman tidak pernah
        # menghapusnya sehingga Drive akan penuh.
        "abaikan": ["Riwayat"],
        "cadangan_aktif": True,
        "cadangan_interval_jam": 24,
        "cadangan_simpan_versi": 3,
        "terakhir_sinkron": "",
        "terakhir_cadangan": "",
    }


def muat() -> dict:
    """Muat pengaturan. Kunci yang belum ada diisi nilai bawaan."""
    hasil = _nilai_bawaan()
    sumber = BERKAS_PENGATURAN if BERKAS_PENGATURAN.exists() else BERKAS_CONTOH
    if sumber.exists():
        try:
            with open(sumber, "r", encoding="utf-8") as f:
                isi = json.load(f)
            if isinstance(isi, dict):
                for kunci, nilai in isi.items():
                    # Nilai kosong dari contoh TIDAK menimpa nilai bawaan yang
                    # sudah dihitung (mis. folder_lokal dikosongkan di contoh).
                    if nilai in ("", None) and kunci in hasil:
                        continue
                    hasil[kunci] = nilai
        except Exception:
            pass

    # Folder yang masih kosong atau tidak bisa dipakai -> pakai bawaan
    lokal = str(hasil.get("folder_lokal") or "").strip()
    if not lokal:
        hasil["folder_lokal"] = str(folder_cadangan_bawaan())
    if not str(hasil.get("folder_drive") or "").strip():
        hasil["folder_drive"] = f"{nama_asisten()}_Sync"

    # Nilai angka dijaga tetap waras
    try:
        hasil["interval_menit"] = max(1, int(hasil.get("interval_menit") or 10))
    except (TypeError, ValueError):
        hasil["interval_menit"] = 10
    try:
        hasil["cadangan_interval_jam"] = max(1, int(hasil.get("cadangan_interval_jam") or 24))
    except (TypeError, ValueError):
        hasil["cadangan_interval_jam"] = 24
    try:
        hasil["cadangan_simpan_versi"] = max(1, int(hasil.get("cadangan_simpan_versi") or 3))
    except (TypeError, ValueError):
        hasil["cadangan_simpan_versi"] = 3

    if str(hasil.get("mode") or "").lower() not in (MODE_AMAN, MODE_PENUH):
        hasil["mode"] = MODE_AMAN

    return hasil


def simpan(pengaturan: dict) -> bool:
    """Tulis pengaturan ke folder DATA pengguna."""
    try:
        BERKAS_PENGATURAN.parent.mkdir(parents=True, exist_ok=True)
        gabung = muat()
        gabung.update(pengaturan)
        with open(BERKAS_PENGATURAN, "w", encoding="utf-8") as f:
            json.dump(gabung, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[SINKRONISASI] Gagal menyimpan pengaturan: {e}")
        return False


def perbarui(**perubahan) -> dict:
    """Ubah sebagian pengaturan saja, lalu kembalikan hasil lengkapnya."""
    gabung = muat()
    gabung.update(perubahan)
    simpan(gabung)
    return muat()


def folder_lokal() -> Path:
    return Path(muat()["folder_lokal"])


def folder_drive() -> str:
    return str(muat()["folder_drive"]).strip()


def mode() -> str:
    return str(muat()["mode"]).lower()


def aktif() -> bool:
    return bool(muat().get("aktif"))


def ringkas() -> str:
    """Ringkasan singkat untuk dibacakan / dikirim ke Telegram."""
    p = muat()
    kondisi = "NYALA" if p.get("aktif") else "MATI"
    mode_teks = "Aman (tidak menghapus)" if p.get("mode") == MODE_AMAN else "Penuh (dua arah termasuk hapus)"
    baris = [
        f"Sinkronisasi Drive: {kondisi}",
        f"Mode: {mode_teks}",
        f"Folder di PC: {p.get('folder_lokal')}",
        f"Folder di Drive: {p.get('folder_drive')}",
        f"Jarak pemeriksaan: {p.get('interval_menit')} menit",
    ]
    if p.get("terakhir_sinkron"):
        baris.append(f"Terakhir sinkron: {p['terakhir_sinkron']}")
    return "\n".join(baris)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "baca":
        print(json.dumps(muat(), indent=4, ensure_ascii=False))
    else:
        print(ringkas())
