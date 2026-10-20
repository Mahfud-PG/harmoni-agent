import os
import shutil
import threading
from core.utils import kirim_pesan_telegram

MANIFEST = {
    "name": "Google Drive & Cloud Sync",
    "version": "1.1.0",
    "author": "Harmoni Agent",
    "description": "Modul penyalinan folder lokal ke Google Drive di latar belakang beserta pemantau progress."
}

UPLOAD_PROGRESS = {"status": "idle", "total_files": 0, "copied_files": 0, "current_file": ""}

def salin_folder_ke_drive(path_lokal: str):
    """Menyalin folder lokal ke lokasi Google Drive secara asinkron di latar belakang."""
    if not os.path.exists(path_lokal):
        return f"❌ Gagal: Folder asal `{path_lokal}` tidak ditemukan."

    drive_target = r"G:\My Drive\Koleksi AI"
    if not os.path.exists(drive_target):
        try: os.makedirs(drive_target)
        except Exception:
            pass

    folder_name = os.path.basename(os.path.normpath(path_lokal))
    dest_path = os.path.join(drive_target, folder_name)

    def proses_copy():
        global UPLOAD_PROGRESS
        try:
            all_files = []
            for root, dirs, files in os.walk(path_lokal):
                for file in files:
                    all_files.append(os.path.join(root, file))

            UPLOAD_PROGRESS["status"] = "uploading"
            UPLOAD_PROGRESS["total_files"] = len(all_files)
            UPLOAD_PROGRESS["copied_files"] = 0

            for src_file in all_files:
                rel_path = os.path.relpath(src_file, path_lokal)
                target_file = os.path.join(dest_path, rel_path)
                target_dir = os.path.dirname(target_file)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                
                UPLOAD_PROGRESS["current_file"] = rel_path
                shutil.copy2(src_file, target_file)
                UPLOAD_PROGRESS["copied_files"] += 1

            UPLOAD_PROGRESS["status"] = "finished"
            kirim_pesan_telegram(f"✅ *Upload Berhasil!*\nFolder `{folder_name}` telah selesai disalin ke Google Drive ({len(all_files)} file).")
        except Exception as e:
            UPLOAD_PROGRESS["status"] = "error"
            kirim_pesan_telegram(f"❌ *Gagal Upload Drive:* {str(e)}")

    thread = threading.Thread(target=proses_copy)
    thread.start()
    return f"🚀 Proses upload folder `{folder_name}` ke Google Drive dimulai di latar belakang! Gunakan perintah `pantau_progress_upload` untuk mengecek statusnya."

def buat_folder_drive(nama_folder: str):
    """Membuat folder baru di Google Drive lewat API resmi, lalu memastikan folder itu benar-benar ada."""
    try:
        from drive_api import get_authenticated_service
        from sari_core.drive_sync_engine import create_drive_folder, get_drive_folder_id

        svc = get_authenticated_service("utama")
        if get_drive_folder_id(svc, nama_folder):
            return f"📁 Folder `{nama_folder}` sudah ada di Google Drive (tidak dibuat ulang)."

        fid = create_drive_folder(svc, nama_folder)
        if not fid:
            return f"❌ Folder `{nama_folder}` gagal dibuat di Google Drive."

        # Verifikasi: baca ulang dari server
        if get_drive_folder_id(svc, nama_folder):
            return f"📁 Folder `{nama_folder}` BENAR-BENAR dibuat di Google Drive (ID: {fid})."
        return f"❌ Folder dilaporkan dibuat (ID: {fid}) tapi tidak ditemukan saat dibaca ulang."
    except Exception as e:
        return f"❌ Gagal membuat folder di Drive: {str(e)}"

def pantau_progress_upload():
    """Mengecek status dan progress penyalinan folder ke Google Drive."""
    status = UPLOAD_PROGRESS.get("status")
    if status == "idle":
        return "ℹ️ Tidak ada proses upload Google Drive yang sedang berjalan saat ini."
    elif status == "uploading":
        copied = UPLOAD_PROGRESS.get("copied_files", 0)
        total = UPLOAD_PROGRESS.get("total_files", 0)
        curr = UPLOAD_PROGRESS.get("current_file", "")
        persen = (copied / total * 100) if total > 0 else 0
        return f"📊 *Progress Upload Google Drive:*\n- **Status:** Sedang Mengunggah ({persen:.1f}%)\n- **Progress:** {copied} dari {total} file\n- **File Aktif:** `{curr}`"
    elif status == "finished":
        return f"✅ Upload Google Drive terakhir telah **SELESAI** sepenuhnya ({UPLOAD_PROGRESS.get('total_files')} file)."
    else:
        return "❌ Upload Google Drive mengalami kegagalan."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "salin_folder_ke_drive",
            "description": "Menyalin seluruh isi folder dari PC lokal ke Google Drive secara asinkron.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_lokal": {"type": "string", "description": "Path mutlak folder lokal yang akan diupload"}
                },
                "required": ["path_lokal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buat_folder_drive",
            "description": "Membuat folder baru di direktori Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_folder": {"type": "string", "description": "Nama folder baru yang akan dibuat"}
                },
                "required": ["nama_folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pantau_progress_upload",
            "description": "Mengecek persentase dan status penyalinan/upload folder ke Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

FUNCTIONS = {
    "salin_folder_ke_drive": salin_folder_ke_drive,
    "buat_folder_drive": buat_folder_drive,
    "pantau_progress_upload": pantau_progress_upload,
}
