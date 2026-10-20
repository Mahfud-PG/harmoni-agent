"""Harmoni Agent - Pencadangan Lengkap dan Pemulihan.

Membungkus SELURUH folder data pengguna menjadi satu berkas ZIP, lalu bisa
dikembalikan utuh.

Kenapa ini perlu, sedangkan sudah ada tombol cadangan lama:
    Tombol lama hanya menyimpan 5 berkas (personalisasi, profil WhatsApp, email,
    YouTube, kontak). Yang TIDAK tersimpan justru bagian yang membuat aplikasi
    bisa hidup: kunci API, sesi WhatsApp, alat buatan sendiri (plugins_dinamis),
    riwayat obrolan, catatan Obsidian, token Google, dan hasil kerja di File/.
    Akibatnya pengguna merasa sudah bercadang, tapi setelah pasang ulang tetap
    harus menyetel dari hampir nol.

Dua nama berkas, sengaja dipisah:
    Cadangan_Harmoni_Terbaru.zip   -> di folder cadangan, IKUT disinkronkan ke
                                      Google Drive. Nama tetap supaya di Drive
                                      selalu DITIMPA, bukan menumpuk.
    Riwayat/Cadangan_Harmoni_*.zip -> salinan bertanggal, TIDAK disinkronkan
                                      (lihat kunci "abaikan" di pengaturan).
                                      Disimpan beberapa versi terakhir saja.
"""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sari_core.paths import DATA_ROOT  # noqa: E402
from sari_core import sinkronisasi_config as cfg  # noqa: E402

NAMA_UTAMA = cfg.NAMA_CADANGAN_DRIVE  # "Cadangan_Harmoni_Terbaru.zip"
NAMA_FOLDER_RIWAYAT = "Riwayat"
AKHIRAN_RIWAYAT = "_Cadangan_Harmoni_"
AKHIRAN_SEBELUM_PULIH = "Sebelum_Pulihkan_"

# Folder yang TIDAK perlu dicadangkan: isinya sampah atau bisa diunduh ulang.
# "node_modules" tidak pernah diperlukan di dalam data pengguna; kalau ikut
# terbawa, cadangan bisa membengkak ratusan MB tanpa guna.
KECUALI = (
    "File/Temp",
    "File/Downloads",
    "logs",
    "node_modules",
)

# Berkas database utama. Disalin dengan cara khusus supaya hasilnya tetap utuh
# walau aplikasi sedang berjalan dan sedang menulis ke database.
NAMA_DB = "sari_memory.db"

# Pemetaan cadangan JSON format LAMA -> nama berkasnya. Dipertahankan supaya
# berkas cadangan lama pengguna tetap bisa dipulihkan.
PETA_JSON = {
    "personalisasi": "personalisasi.json",
    "konfigurasi_multi_wa": "konfigurasi_multi_wa.json",
    "konfigurasi_email": "konfigurasi_email.json",
    "konfigurasi_youtube": "konfigurasi_youtube.json",
    "kontak_tersimpan": "kontak_tersimpan.json",
}


# ---------------------------------------------------------------------------
# Letak berkas
# ---------------------------------------------------------------------------
def folder_cadangan() -> Path:
    return Path(cfg.muat()["folder_lokal"])


def folder_riwayat() -> Path:
    return folder_cadangan() / NAMA_FOLDER_RIWAYAT


def berkas_utama() -> Path:
    return folder_cadangan() / NAMA_UTAMA


def _lewati(rel: str) -> bool:
    """Apakah berkas ini tidak perlu dicadangkan?

    PENTING: nama folder harus dicari di SEMUA tingkat, bukan hanya paling atas.
    Versi awal fungsi ini hanya memeriksa awal jalur, sehingga
    `wa_bridge/node_modules/...` (9.595 berkas) lolos masuk ke dalam cadangan.
    """
    rel = rel.replace("\\", "/")
    bagian = [b for b in rel.split("/") if b]
    for k in KECUALI:
        if "/" in k:
            # Folder bertingkat, misalnya "File/Temp"
            if rel == k or rel.startswith(k + "/"):
                return True
        elif k in bagian:
            return True
    return "__pycache__" in bagian or rel.endswith(".pyc")


def _tambah_database_aman(zf: zipfile.ZipFile, db_path: Path, nama_dalam_zip: str) -> bool:
    """Masukkan database ke ZIP dengan cara aman (snapshot konsisten).

    Menyalin berkas database yang sedang terbuka bisa menghasilkan cadangan yang
    rusak. Karena itu dibuat salinan konsisten dulu lewat fitur backup bawaan
    SQLite, baru dimasukkan ke ZIP. Kalau cara itu gagal, baru disalin biasa.
    """
    import sqlite3

    sementara = Path(tempfile.mkdtemp(prefix="harmoni_db_"))
    tujuan = sementara / NAMA_DB
    try:
        sumber = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15)
        sasaran = sqlite3.connect(str(tujuan))
        try:
            with sasaran:
                sumber.backup(sasaran)
        finally:
            sumber.close()
            sasaran.close()
        zf.write(tujuan, nama_dalam_zip)
        return True
    except Exception as e:
        print(f"[CADANGAN] Snapshot database gagal ({e}), menyalin biasa.")
        try:
            zf.write(db_path, nama_dalam_zip)
            return True
        except Exception as e2:
            print(f"[CADANGAN] Database tidak bisa disalin: {e2}")
            return False
    finally:
        shutil.rmtree(sementara, ignore_errors=True)


def _susun_zip(tujuan: Path, akar: Path | None = None) -> dict:
    """Bangun berkas ZIP dari folder data. Mengembalikan ringkasan.

    `akar` sengaja dibaca saat dipanggil (bukan disimpan sebagai nilai bawaan),
    supaya pengujian bisa mengarahkannya ke folder percobaan tanpa menyentuh
    data pengguna yang sebenarnya.
    """
    jumlah = 0
    dilewati = 0
    akar = Path(akar) if akar is not None else Path(DATA_ROOT)
    tujuan = Path(tujuan)
    tujuan.parent.mkdir(parents=True, exist_ok=True)

    # Daftar lebih dulu supaya kemajuan bisa dilaporkan
    daftar = []
    for dirpath, _, namafile in os.walk(akar):
        for nama in namafile:
            penuh = Path(dirpath) / nama
            try:
                rel = str(penuh.relative_to(akar)).replace("\\", "/")
            except ValueError:
                continue
            if _lewati(rel):
                dilewati += 1
                continue
            # Jangan pernah memasukkan berkas cadangan ke dalam cadangan
            if penuh.name == NAMA_UTAMA or AKHIRAN_RIWAYAT in penuh.name:
                dilewati += 1
                continue
            if penuh.resolve() == tujuan.resolve():
                continue
            daftar.append((penuh, rel))

    with zipfile.ZipFile(tujuan, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for penuh, rel in daftar:
            try:
                if penuh.name == NAMA_DB:
                    if _tambah_database_aman(zf, penuh, rel):
                        jumlah += 1
                    else:
                        dilewati += 1
                    continue
                zf.write(penuh, rel)
                jumlah += 1
            except (OSError, ValueError) as e:
                # Berkas sedang dipakai atau hilang di tengah jalan: lewati saja,
                # jangan sampai seluruh pencadangan gagal karenanya.
                print(f"[CADANGAN] Dilewati {rel}: {e}")
                dilewati += 1

    return {"berkas": jumlah, "dilewati": dilewati, "jalur": str(tujuan)}


def _rapikan_riwayat(simpan: int) -> None:
    """Simpan hanya beberapa berkas riwayat terbaru, sisanya dibuang."""
    tempat = folder_riwayat()
    if not tempat.exists():
        return
    berkas = sorted(
        (p for p in tempat.glob("*.zip")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for lama in berkas[simpan:]:
        try:
            lama.unlink()
            print(f"[CADANGAN] Riwayat lama dibuang: {lama.name}")
        except OSError:
            pass


def buat_cadangan() -> dict:
    """Buat cadangan lengkap. Mengembalikan laporan (dict)."""
    pengaturan = cfg.muat()
    simpan_versi = int(pengaturan.get("cadangan_simpan_versi") or 3)
    hasil = {"berhasil": False, "pesan": "", "jalur": "", "ukuran_mb": 0.0}

    if not DATA_ROOT.exists():
        hasil["pesan"] = f"Folder data tidak ditemukan: {DATA_ROOT}"
        return hasil

    try:
        utama = berkas_utama()
        ringkas = _susun_zip(utama)
        hasil["jalur"] = str(utama)
        hasil["ukuran_mb"] = round(utama.stat().st_size / (1024 * 1024), 1)

        # Salinan bertanggal untuk riwayat lokal (tidak ikut ke Drive)
        try:
            riwayat = folder_riwayat()
            riwayat.mkdir(parents=True, exist_ok=True)
            stempel = datetime.now().strftime("%Y-%m-%d_%H%M")
            shutil.copy2(utama, riwayat / f"{stempel}{AKHIRAN_RIWAYAT}lengkap.zip")
            _rapikan_riwayat(simpan_versi)
        except OSError as e:
            print(f"[CADANGAN] Riwayat tidak tersimpan: {e}")

        hasil["berhasil"] = True
        hasil["pesan"] = (
            f"Cadangan selesai: {ringkas['berkas']} berkas, "
            f"{hasil['ukuran_mb']} MB"
        )
        cfg.simpan({
            "terakhir_cadangan": datetime.now().strftime("%d %b %Y %H:%M"),
        })
        print(f"[CADANGAN] {hasil['pesan']} -> {hasil['jalur']}")

    except Exception as e:
        hasil["pesan"] = f"Gagal mencadangkan: {e}"
        print(f"[CADANGAN] {hasil['pesan']}")

    return hasil


def cadangan_perlu_dibuat() -> bool:
    """Apakah sudah waktunya membuat cadangan baru?"""
    pengaturan = cfg.muat()
    if not pengaturan.get("cadangan_aktif", True):
        return False
    utama = berkas_utama()
    if not utama.exists():
        return True
    try:
        jarak_jam = float(pengaturan.get("cadangan_interval_jam") or 24)
    except (TypeError, ValueError):
        jarak_jam = 24.0
    umur_jam = (datetime.now().timestamp() - utama.stat().st_mtime) / 3600.0
    return umur_jam >= jarak_jam


def daftar_cadangan() -> list:
    """Daftar berkas cadangan yang tersedia (untuk dipulihkan)."""
    hasil = []
    for tempat in (folder_cadangan(), folder_riwayat()):
        if not tempat.exists():
            continue
        for p in sorted(tempat.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            hasil.append({
                "nama": p.name,
                "jalur": str(p),
                "ukuran_mb": round(p.stat().st_size / (1024 * 1024), 1),
                "waktu": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %Y %H:%M"),
            })
    return hasil


# ---------------------------------------------------------------------------
# Pemulihan
# ---------------------------------------------------------------------------
def _pengaman_sebelum_pulih() -> str:
    """Cadangkan keadaan SEKARANG dulu, supaya pemulihan bisa dibatalkan."""
    sementara = Path(tempfile.mkdtemp(prefix="harmoni_aman_"))
    tujuan = sementara / "sebelum_pulih.zip"
    try:
        _susun_zip(tujuan)
        simpan = folder_riwayat()
        simpan.mkdir(parents=True, exist_ok=True)
        stempel = datetime.now().strftime("%Y-%m-%d_%H%M")
        pindah = simpan / f"{AKHIRAN_SEBELUM_PULIH}{stempel}.zip"
        shutil.move(str(tujuan), str(pindah))
        _rapikan_riwayat(int(cfg.muat().get("cadangan_simpan_versi") or 3))
        return str(pindah)
    except Exception as e:
        print(f"[CADANGAN] Pengaman gagal dibuat: {e}")
        return ""
    finally:
        shutil.rmtree(sementara, ignore_errors=True)


def _pulihkan_dari_zip(berkas: Path) -> dict:
    jumlah = 0
    with zipfile.ZipFile(berkas, "r") as zf:
        for info in zf.infolist():
            nama = info.filename.replace("\\", "/")
            if nama.endswith("/") or _lewati(nama):
                continue
            # Jangan biarkan isi ZIP menulis ke luar folder data
            tujuan = (DATA_ROOT / nama).resolve()
            if not str(tujuan).startswith(str(DATA_ROOT.resolve())):
                continue
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(info) as sumber, open(tujuan, "wb") as keluar:
                    shutil.copyfileobj(sumber, keluar)
                jumlah += 1
            except Exception as e:
                print(f"[CADANGAN] Gagal memulihkan {nama}: {e}")
    return {"berhasil": True, "berkas": jumlah, "jenis": "zip"}


def _pulihkan_dari_json(berkas: Path) -> dict:
    with open(berkas, "r", encoding="utf-8") as f:
        mentah = json.load(f)
    isi = mentah.get("data") if isinstance(mentah, dict) else None
    if not isinstance(isi, dict):
        isi = mentah if isinstance(mentah, dict) else {}

    dipulihkan = []
    for kunci, nama_berkas in PETA_JSON.items():
        if kunci in isi and isinstance(isi[kunci], (dict, list)):
            tujuan = DATA_ROOT / nama_berkas
            try:
                with open(tujuan, "w", encoding="utf-8") as f:
                    json.dump(isi[kunci], f, ensure_ascii=False, indent=2)
                dipulihkan.append(nama_berkas)
            except Exception as e:
                print(f"[CADANGAN] Gagal memulihkan {nama_berkas}: {e}")

    return {
        "berhasil": bool(dipulihkan),
        "berkas": len(dipulihkan),
        "jenis": "json",
        "rincian": dipulihkan,
    }


def pulihkan(berkas: str | Path) -> dict:
    """Pulihkan dari berkas cadangan. Menerima ZIP (format baru) MAUPUN JSON
    (format lama) - jenisnya dideteksi otomatis."""
    berkas = Path(berkas)
    if not berkas.exists():
        return {"berhasil": False, "pesan": f"Berkas tidak ditemukan: {berkas}"}

    pengaman = _pengaman_sebelum_pulih()
    try:
        if zipfile.is_zipfile(berkas):
            hasil = _pulihkan_dari_zip(berkas)
        else:
            hasil = _pulihkan_dari_json(berkas)
    except Exception as e:
        return {"berhasil": False, "pesan": f"Gagal memulihkan: {e}", "pengaman": pengaman}

    if hasil.get("berhasil"):
        hasil["pesan"] = f"{hasil['berkas']} berkas dikembalikan dari {berkas.name}"
        if hasil.get("jenis") == "json":
            hasil["pesan"] = (
                f"Pengaturan lama dikembalikan ({hasil['berkas']} bagian). "
                "Catatan: format JSON lama tidak memuat kunci API dan sesi WhatsApp."
            )
    else:
        hasil["pesan"] = "Tidak ada yang bisa dipulihkan dari berkas itu."

    hasil["pengaman"] = pengaman
    if pengaman:
        hasil["pesan"] += f" Keadaan sebelum pemulihan disimpan di: {pengaman}"
    return hasil


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Cadangan Harmoni")
    p.add_argument("aksi", choices=["buat", "daftar", "pulihkan", "cek"])
    p.add_argument("berkas", nargs="?")
    a = p.parse_args()

    if a.aksi == "buat":
        print(json.dumps(buat_cadangan(), indent=2, ensure_ascii=False))
    elif a.aksi == "daftar":
        print(json.dumps(daftar_cadangan(), indent=2, ensure_ascii=False))
    elif a.aksi == "cek":
        print("perlu dibuat:", cadangan_perlu_dibuat())
    elif a.aksi == "pulihkan":
        if not a.berkas:
            print("Sebutkan berkas cadangannya.")
        else:
            print(json.dumps(pulihkan(a.berkas), indent=2, ensure_ascii=False))
