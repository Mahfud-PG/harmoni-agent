"""Harmoni Agent - Mesin Sinkronisasi Google Drive.

Menyalin dua arah antara satu folder di PC dan satu folder di Google Drive.

PERUBAHAN PENTING dibanding versi lama:
  * Tidak ada lagi alamat yang dipaku di kode (dulu `D:\\Siti_Drive_Sync` dan
    folder Drive `Siti_Sync`). Semua diambil dari `konfigurasi_sinkronisasi.json`
    sehingga pengguna bisa memindahkan folder tanpa menyentuh kode.
  * Ada MODE AMAN: berkas yang terhapus di satu sisi TIDAK ikut terhapus di sisi
    lain. Mode ini yang dipakai sebagai bawaan.
  * Daftar berkas Drive hanya diambil dari dalam folder sinkronisasi, bukan
    seluruh Drive. Jauh lebih cepat dan hemat jatah permintaan ke Google.
  * Mengembalikan laporan hasil (dict) supaya bisa ditampilkan di layar dan
    dikirim ke Telegram, bukan sekadar dicetak ke jendela hitam.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sari_core.paths import PROJECT_ROOT  # noqa: E402
from sari_core import sinkronisasi_config as cfg  # noqa: E402

STATE_FILE = str(PROJECT_ROOT / "drive_sync_state.json")
FOLDER_MIME = "application/vnd.google-apps.folder"
TOLERANSI_DETIK = 5  # beda waktu di bawah ini dianggap sama


# ---------------------------------------------------------------------------
# Akses Google Drive
# ---------------------------------------------------------------------------
def _layanan():
    from drive_api import get_authenticated_service
    return get_authenticated_service("utama")


def get_drive_folder_id(drive_service, name, parent_id=None):
    """Cari id folder di Drive berdasarkan nama (dipertahankan untuk modul lain)."""
    query = f"name='{name}' and mimeType='{FOLDER_MIME}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    hasil = drive_service.files().list(q=query, fields="files(id, name)").execute()
    berkas = hasil.get("files", [])
    return berkas[0]["id"] if berkas else None


def create_drive_folder(drive_service, name, parent_id=None):
    """Buat folder baru di Drive (dipertahankan untuk modul lain)."""
    isi = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        isi["parents"] = [parent_id]
    folder = drive_service.files().create(body=isi, fields="id").execute()
    return folder.get("id")


# ---------------------------------------------------------------------------
# Daftar keadaan (menyimpan berkas mana yang sudah pernah disinkronkan)
# ---------------------------------------------------------------------------
def load_state():
    """Muat daftar keadaan.

    Bentuknya:
        {"info": {"folder_lokal":..., "folder_drive":...},
         "berkas": {"nama berkas": {"l": waktu lokal, "d": waktu Drive}}}

    Format LAMA (hanya berisi nama berkas -> angka) sengaja dianggap kosong,
    karena isinya tidak menyimpan waktu sisi Drive sehingga tidak bisa dipakai
    untuk menilai perubahan dengan benar.
    """
    import json
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "berkas" in data:
                return {
                    "info": data.get("info") or {},
                    "berkas": data.get("berkas") or {},
                }
        except Exception:
            pass
    return {"info": {}, "berkas": {}}


def save_state(state):
    import json
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[DRIVE SYNC] Gagal menyimpan daftar keadaan: {e}")


# ---------------------------------------------------------------------------
# Pembacaan isi folder
# ---------------------------------------------------------------------------
def get_all_local_files(root_dir):
    """Daftar berkas lokal: {jalur_relatif: waktu_ubah}."""
    import json  # noqa: F401
    hasil = {}
    akar = Path(root_dir)
    if not akar.exists():
        akar.mkdir(parents=True, exist_ok=True)
        return hasil
    for dirpath, _, namafile in os.walk(akar):
        for nama in namafile:
            penuh = Path(dirpath) / nama
            try:
                rel = str(penuh.relative_to(akar)).replace("\\", "/")
                hasil[rel] = penuh.stat().st_mtime
            except (OSError, ValueError):
                continue
    return hasil


def get_all_drive_files(drive_service, root_folder_id):
    """Daftar berkas di DALAM folder sinkronisasi saja (beserta sub-foldernya).

    Mengembalikan (berkas, folder):
        berkas : {jalur_relatif: {"id":..., "mtime":..., "parent_id":...}}
        folder : {jalur_relatif: id_folder}
    """
    import dateutil.parser

    berkas = {}
    folder = {"": root_folder_id}

    def telusuri(folder_id, awalan):
        token = None
        while True:
            hasil = drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                pageToken=token,
                pageSize=1000,
            ).execute()
            for f in hasil.get("files", []):
                rel = f"{awalan}{f['name']}"
                if f.get("mimeType") == FOLDER_MIME:
                    folder[rel] = f["id"]
                    telusuri(f["id"], rel + "/")
                else:
                    try:
                        mtime = dateutil.parser.parse(f["modifiedTime"]).timestamp()
                    except Exception:
                        mtime = 0
                    berkas[rel] = {"id": f["id"], "mtime": mtime, "parent_id": folder_id}
            token = hasil.get("nextPageToken")
            if not token:
                break

    telusuri(root_folder_id, "")
    return berkas, folder


# ---------------------------------------------------------------------------
# Pemindahan berkas
# ---------------------------------------------------------------------------
def _cap(epoch: float) -> str:
    """Ubah waktu menjadi bentuk yang dimengerti Google Drive."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def upload_file(drive_service, local_path, parent_id, name, mtime: float | None = None):
    """Unggah berkas baru. Waktu ubah Drive DISAMAKAN dengan berkas lokal.

    PENTING: kalau waktu ubah Drive dibiarkan berbeda (Drive memakai waktu unggah),
    maka pada siklus berikutnya berkas itu terlihat "lebih baru di Drive" sehingga
    diunduh lagi, lalu naik lagi, lalu turun lagi - bolak-balik tanpa henti.
    Karena itu waktu ubahnya dipatok sama dengan berkas lokal.
    """
    from googleapiclient.http import MediaFileUpload

    body = {"name": name, "parents": [parent_id]}
    if mtime is not None:
        body["modifiedTime"] = _cap(mtime)
    media = MediaFileUpload(str(local_path), resumable=True)
    file = drive_service.files().create(
        body=body, media_body=media, fields="id, modifiedTime"
    ).execute()
    return file


def update_file(drive_service, file_id, local_path, mtime: float | None = None):
    """Perbarui isi berkas di Drive, sekaligus menyamakan waktu ubahnya."""
    from googleapiclient.http import MediaFileUpload
    body = {}
    if mtime is not None:
        body["modifiedTime"] = _cap(mtime)
    media = MediaFileUpload(str(local_path), resumable=True)
    return drive_service.files().update(
        fileId=file_id, body=body, media_body=media, fields="id, modifiedTime"
    ).execute()


def download_file(drive_service, file_id, local_path, mtime: float | None = None):
    """Unduh berkas dari Drive. Waktu ubah lokal disamakan dengan Drive.

    Tanpa penyamaan ini, berkas yang baru diunduh akan terlihat "lebih baru di
    lokal" sehingga diunggah balik pada siklus berikutnya - bolak-balik.
    """
    from googleapiclient.http import MediaIoBaseDownload
    import io
    tujuan = Path(local_path)
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    permintaan = drive_service.files().get_media(fileId=file_id)
    with io.FileIO(str(tujuan), "wb") as fh:
        pengunduh = MediaIoBaseDownload(fh, permintaan)
        selesai = False
        while not selesai:
            _, selesai = pengunduh.next_chunk()
    if mtime:
        try:
            os.utime(tujuan, (mtime, mtime))
        except OSError:
            pass


def _pastikan_folder_drive(drive_service, folder_map, rel_folder, root_id):
    """Pastikan folder tujuan ada di Drive, buat bertingkat bila perlu."""
    if rel_folder in ("", None):
        return root_id
    if rel_folder in folder_map:
        return folder_map[rel_folder]

    bagian = rel_folder.split("/")
    induk = root_id
    jalan = ""
    for nama in bagian:
        jalan = f"{jalan}/{nama}" if jalan else nama
        if jalan in folder_map:
            induk = folder_map[jalan]
            continue
        baru = create_drive_folder(drive_service, nama, induk)
        folder_map[jalan] = baru
        induk = baru
    return induk


# ---------------------------------------------------------------------------
# Siklus utama
# ---------------------------------------------------------------------------
def _kosongkan_laporan():
    return {
        "berhasil": False,
        "diunggah": 0,
        "diunduh": 0,
        "diperbarui": 0,
        "dihapus_lokal": 0,
        "dihapus_drive": 0,
        "dilewati": 0,
        "mode": cfg.mode(),
        "folder_lokal": str(cfg.folder_lokal()),
        "folder_drive": cfg.folder_drive(),
        "pesan": "",
    }


def _diabaikan(rel_path: str, daftar_abaikan) -> bool:
    """Apakah berkas ini berada di dalam folder yang tidak ikut disinkronkan?"""
    if not daftar_abaikan:
        return False
    bagian = str(rel_path).split("/")
    return any(b in daftar_abaikan for b in bagian)


def run_sync_cycle():
    """Jalankan satu siklus sinkronisasi. Mengembalikan laporan (dict)."""
    laporan = _kosongkan_laporan()
    pengaturan = cfg.muat()
    mode_aman = pengaturan.get("mode") == cfg.MODE_AMAN

    folder_lokal = Path(pengaturan["folder_lokal"])
    nama_drive = pengaturan["folder_drive"]

    print(f"[DRIVE SYNC] Mulai. Mode: {pengaturan['mode']}. Lokal: {folder_lokal}")

    try:
        svc = _layanan()

        root_id = get_drive_folder_id(svc, nama_drive)
        if not root_id:
            root_id = create_drive_folder(svc, nama_drive)
            print(f"[DRIVE SYNC] Folder Drive '{nama_drive}' dibuat.")

        folder_lokal.mkdir(parents=True, exist_ok=True)

        state = load_state()

        # Kalau folder yang disinkronkan berbeda dari catatan sebelumnya, catatan
        # lama TIDAK BERLAKU lagi dan harus dimulai dari kosong. Tanpa pemeriksaan
        # ini, mengganti folder sinkronisasi membuat berkas-berkas di folder baru
        # dianggap "sudah pernah disinkronkan" sehingga tidak pernah diunggah, dan
        # dalam mode aman dilaporkan sebagai "dilewati" terus-menerus.
        info_lama = state.get("info") or {}
        if (info_lama.get("folder_lokal") != str(folder_lokal)
                or info_lama.get("folder_drive") != nama_drive):
            if info_lama:
                print("[DRIVE SYNC] Folder berbeda dari catatan lama -> catatan direset.")
            state = {"info": {}, "berkas": {}}
        state = state.get("berkas") or {}

        daftar_abaikan = pengaturan.get("abaikan") or []
        berkas_lokal = {
            r: m for r, m in get_all_local_files(folder_lokal).items()
            if not _diabaikan(r, daftar_abaikan)
        }
        berkas_drive, folder_drive = get_all_drive_files(svc, root_id)
        berkas_drive = {
            r: i for r, i in berkas_drive.items()
            if not _diabaikan(r, daftar_abaikan)
        }
        if daftar_abaikan:
            print(f"[DRIVE SYNC] Folder yang dilewati: {', '.join(daftar_abaikan)}")

        state_baru = {}
        ada_perubahan = False

        def cabang(rel):
            return str((rel.rsplit("/", 1)[0]) if "/" in rel else "")

        def lama(rel, kunci):
            """Waktu yang tercatat pada siklus sebelumnya (None kalau belum ada).

            Catatan siklus lama hanya berupa angka biasa (bukan dict), sehingga
            dianggap belum diketahui - aman, karena berarti berkas itu akan
            dinilai ulang seluruhnya.
            """
            nilai = state.get(rel)
            if isinstance(nilai, dict):
                nilai = nilai.get(kunci)
            return None if nilai is None else float(nilai)

        def catat(rel, mtime_lokal, mtime_drive):
            state_baru[rel] = {"l": mtime_lokal, "d": mtime_drive}

        # ---- 1. Telusuri berkas lokal ----
        for rel, mtime_lokal in berkas_lokal.items():
            penuh = folder_lokal / rel.replace("/", os.sep)

            if rel not in berkas_drive:
                if rel in state:
                    # Dulu ada di Drive, sekarang tidak -> terhapus di sisi Drive
                    if mode_aman:
                        print(f"[DRIVE SYNC] Dilewati (mode aman): {rel}")
                        laporan["dilewati"] += 1
                        catat(rel, mtime_lokal, None)
                    else:
                        print(f"[DRIVE SYNC] Menghapus lokal (sudah dihapus di Drive): {rel}")
                        try:
                            penuh.unlink()
                            laporan["dihapus_lokal"] += 1
                        except OSError:
                            pass
                        ada_perubahan = True
                else:
                    print(f"[DRIVE SYNC] Mengunggah berkas baru: {rel}")
                    induk = _pastikan_folder_drive(svc, folder_drive, cabang(rel), root_id)
                    upload_file(svc, penuh, induk, rel.split("/")[-1], mtime=mtime_lokal)
                    # Waktu di Drive sudah disamakan dengan berkas lokal, jadi
                    # kedua sisi mencatat waktu yang sama -> siklus berikutnya
                    # tidak akan memindahkannya bolak-balik.
                    catat(rel, mtime_lokal, mtime_lokal)
                    laporan["diunggah"] += 1
                    ada_perubahan = True
            else:
                info = berkas_drive[rel]
                l_lama = lama(rel, "l")
                d_lama = lama(rel, "d")

                # Dibandingkan dengan waktu yang TERCATAT, bukan sekadar mana yang
                # lebih besar. Cara ini yang membuat sinkronisasi dua arah andal:
                # berkas yang tidak berubah tidak akan dipindahkan lagi.
                l_berubah = l_lama is None or abs(mtime_lokal - l_lama) > TOLERANSI_DETIK
                d_berubah = d_lama is None or abs(info["mtime"] - d_lama) > TOLERANSI_DETIK

                if l_berubah and d_berubah:
                    # Dua-duanya berubah sejak siklus terakhir -> yang lebih baru menang
                    if mtime_lokal >= info["mtime"]:
                        print(f"[DRIVE SYNC] Dua sisi berubah, lokal lebih baru -> naik: {rel}")
                        update_file(svc, info["id"], penuh, mtime=mtime_lokal)
                        catat(rel, mtime_lokal, mtime_lokal)
                        laporan["diperbarui"] += 1
                        ada_perubahan = True
                    else:
                        print(f"[DRIVE SYNC] Dua sisi berubah, Drive lebih baru -> turun: {rel}")
                        download_file(svc, info["id"], penuh, mtime=info["mtime"])
                        catat(rel, penuh.stat().st_mtime, info["mtime"])
                        laporan["diunduh"] += 1
                        ada_perubahan = True
                elif l_berubah:
                    print(f"[DRIVE SYNC] Memperbarui di Drive: {rel}")
                    update_file(svc, info["id"], penuh, mtime=mtime_lokal)
                    catat(rel, mtime_lokal, mtime_lokal)
                    laporan["diperbarui"] += 1
                    ada_perubahan = True
                elif d_berubah:
                    print(f"[DRIVE SYNC] Mengunduh perubahan dari Drive: {rel}")
                    try:
                        download_file(svc, info["id"], penuh, mtime=info["mtime"])
                        catat(rel, penuh.stat().st_mtime, info["mtime"])
                        laporan["diunduh"] += 1
                        ada_perubahan = True
                    except Exception as e:
                        print(f"[DRIVE SYNC] Gagal unduh {rel}: {e}")
                        catat(rel, mtime_lokal, info["mtime"])
                else:
                    # Tidak ada yang berubah di kedua sisi
                    catat(rel, mtime_lokal, info["mtime"])

        # ---- 2. Telusuri berkas Drive yang tidak ada di lokal ----
        for rel, info in berkas_drive.items():
            if rel in berkas_lokal:
                continue
            penuh = folder_lokal / rel.replace("/", os.sep)
            if rel in state:
                if mode_aman:
                    print(f"[DRIVE SYNC] Dilewati (mode aman, tidak menghapus dari Drive): {rel}")
                    laporan["dilewati"] += 1
                    catat(rel, None, info["mtime"])
                else:
                    print(f"[DRIVE SYNC] Menghapus dari Drive (sudah dihapus lokal): {rel}")
                    try:
                        svc.files().update(fileId=info["id"], body={"trashed": True}).execute()
                        laporan["dihapus_drive"] += 1
                        ada_perubahan = True
                    except Exception:
                        pass
            else:
                print(f"[DRIVE SYNC] Mengunduh berkas baru dari Drive: {rel}")
                try:
                    download_file(svc, info["id"], penuh, mtime=info["mtime"])
                    catat(rel, penuh.stat().st_mtime, info["mtime"])
                    laporan["diunduh"] += 1
                    ada_perubahan = True
                except Exception as e:
                    print(f"[DRIVE SYNC] Gagal unduh {rel}: {e}")

        save_state({
            "info": {
                "folder_lokal": str(folder_lokal),
                "folder_drive": nama_drive,
                "waktu": datetime.now().strftime("%d %b %Y %H:%M"),
            },
            "berkas": state_baru,
        })

        laporan["berhasil"] = True
        laporan["pesan"] = (
            f"{laporan['diunggah']} naik, {laporan['diunduh']} turun, "
            f"{laporan['diperbarui']} diperbarui"
        )
        if laporan["dilewati"]:
            laporan["pesan"] += f", {laporan['dilewati']} dilewati (mode aman)"
        print(f"[DRIVE SYNC] Selesai. {laporan['pesan']}")

    except Exception as e:
        laporan["pesan"] = f"Gagal: {e}"
        print(f"[DRIVE SYNC] Error: {e}")

    # Catat waktu sinkron terakhir
    try:
        cfg.simpan({
            "terakhir_sinkron": datetime.now().strftime("%d %b %Y %H:%M"),
            "terakhir_hasil": laporan["pesan"],
        })
    except Exception:
        pass

    return laporan


def sinkron_sekarang():
    """Dipanggil dari tombol 'Sinkronkan Sekarang' atau perintah Telegram."""
    return run_sync_cycle()


if __name__ == "__main__":
    hasil = run_sync_cycle()
    print()
    for k, v in hasil.items():
        print(f"  {k}: {v}")
