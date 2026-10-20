import os
import sys
import argparse
import io
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import json
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# SYSPATH: Python tertanam mengunci sys.path lewat berkas python314._pth, sehingga
# folder skrip ini TIDAK ikut dicari. Tanpa baris berikut, `from sari_core.paths
# import ...` di bawah GAGAL, dan skrip jatuh ke jalur cadangan yang menunjuk
# folder PROGRAM - padahal berkas pengguna (client_secret.json, token_*.json)
# ada di folder DATA. Gejalanya: "File kredensial hilang: ...\Programs\HarmoniAgent\..."
# ---------------------------------------------------------------------------
_AKAR_APLIKASI = str(Path(__file__).resolve().parent)
if _AKAR_APLIKASI not in sys.path:
    sys.path.insert(0, _AKAR_APLIKASI)


def _folder_data_cadangan() -> Path:
    """Folder data pengguna, dihitung TANPA bantuan sari_core.paths.

    Dipakai hanya bila impor di bawah gagal. Anemia lama: memakai folder PROGRAM,
    sehingga berkas kredensial dicari di tempat yang salah dan pengguna disuruh
    menaruh berkasnya di sana - padahal berkasnya sudah ada di folder data.
    """
    akar = Path(__file__).resolve().parent
    if (akar / "MODE_TERPASANG").exists():
        dasar = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(dasar) / "HarmoniAgent"
    return akar


# Folder kerja aplikasi mengikuti lokasi berkas ini (bukan jalur lama C:\AI Asisten yang sudah dihapus)
BASE_DIR = Path(__file__).resolve().parent

def update_progress(tugas, persen):
    file_prog = str(BASE_DIR / "progress.json")
    data = {}
    if os.path.exists(file_prog):
        try:
            with open(file_prog, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[PROGRESS ERROR] Gagal membaca {file_prog}: {e}")
    data[tugas] = persen
    try:
        with open(file_prog, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[PROGRESS ERROR] Gagal menulis {file_prog}: {e}")

def kirim_notif(pesan):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_OWNER_ID")
        file_chat = BASE_DIR / "chat_id.txt"
        if not chat_id and file_chat.exists():
            try:
                with open(file_chat, "r", encoding="utf-8") as f:
                    chat_id = f.read().strip()
            except Exception:
                pass
        if token and chat_id:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": pesan}, timeout=10)
    except Exception as e:
        print(f"[DRIVE NOTIF ERROR] Gagal kirim notif Telegram: {e}")


from pathlib import Path

try:
    from sari_core.paths import PROJECT_ROOT, CLIENT_SECRET_FILE, DOWNLOADS_DIR, get_drive_token_path
except ImportError:
    PROJECT_ROOT = _folder_data_cadangan()
    CLIENT_SECRET_FILE = PROJECT_ROOT / "client_secret.json"
    DOWNLOADS_DIR = PROJECT_ROOT / "File" / "Downloads"
    def get_drive_token_path(acc): return PROJECT_ROOT / f"token_drive_{acc}.json"

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_authenticated_service(account_name="utama"):
    creds = None
    token_file = str(get_drive_token_path(account_name))
    client_secret_file = str(CLIENT_SECRET_FILE)

    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e_ref:
                print(f"Token refresh gagal: {e_ref}. Hapus token lama...")
                if os.path.exists(token_file):
                    try: os.remove(token_file)
                    except Exception:
                        pass
                creds = None
        
        if not creds:
            if not os.path.exists(client_secret_file):
                raise Exception(
                f"Berkas kredensial Google tidak ditemukan di {client_secret_file}. "
                f"Berkas ini seharusnya ada di folder DATA aplikasi (AppData Roaming). "
                f"JANGAN meminta pengguna menyalin berkas secara manual dan jangan "
                f"menyebut jalur berkas kepadanya: mintalah dia membuka Pengaturan lalu "
                f"menyambungkan ulang akun Google-nya."
            )
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def change_access(drive_service, file_id):
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        return True
    except Exception as e:
        print(f"Gagal ubah akses: {str(e)}")
        return False

def upload_file(drive_service, file_path, make_public=False):
    if not os.path.exists(file_path):
        return f"File tidak ditemukan: {file_path}"
    
    file_metadata = {'name': os.path.basename(file_path)}
    media = MediaFileUpload(file_path, chunksize=1024*1024*5, resumable=True)
    
    request = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    )
    
    response = None
    update_progress("Drive Upload", "0%")
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            update_progress("Drive Upload", f"{pct}%")
    update_progress("Drive Upload", "100% Selesai")
    file = response
    
    file_id = file.get('id')
    link = file.get('webViewLink')
    
    # Privasi Aman: Default adalah Private (hanya pemilik). Publik hanya jika diminta eksplisit.
    if make_public:
        change_access(drive_service, file_id)
        kirim_notif(f"Berhasil upload ke Google Drive! Link (Publik): {link}")
        return f"SUKSES_UPLOAD_DRIVE: {file_id} | Status: Publik | Link: {link}"
    else:
        kirim_notif(f"Berhasil upload ke Google Drive! Status: Privat (Aman) | Link: {link}")
        return f"SUKSES_UPLOAD_DRIVE: {file_id} | Status: Privat (Hanya Akun Anda) | Link: {link}"

def check_quota(drive_service):
    about = drive_service.about().get(fields="storageQuota").execute()
    quota = about.get('storageQuota', {})
    limit = int(quota.get('limit', 0)) / (1024**3)
    usage = int(quota.get('usage', 0)) / (1024**3)
    return f"Kapasitas: {usage:.2f} GB terpakai dari total {limit:.2f} GB."

def search_file(drive_service, query, max_results=5):
    # Menggunakan query pencarian standar Google Drive (contains)
    results = drive_service.files().list(
        q=f"name contains '{query}' and trashed=false",
        pageSize=max_results,
        fields="files(id, name, webViewLink, size)"
    ).execute()
    
    items = results.get('files', [])
    if not items:
        return f"Tidak menemukan file yang mengandung nama: {query}"
        
    hasil = []
    for item in items:
        size_mb = int(item.get('size', 0)) / (1024**2)
        hasil.append(f"- {item['name']} ({size_mb:.2f} MB) | ID: {item['id']} | Link: {item['webViewLink']}")
    return "\n".join(hasil)

def cek_isi_folder(drive_service, nama_folder):
    results = drive_service.files().list(q=f"name = '{nama_folder}' and mimeType = 'application/vnd.google-apps.folder' and trashed=false", pageSize=1, fields="files(id, name)").execute()
    items = results.get('files', [])
    if not items: return f"Folder '{nama_folder}' tidak ditemukan di Drive Anda."
    folder_id = items[0]['id']
    folder_name = items[0]['name']
    
    results2 = drive_service.files().list(q=f"'{folder_id}' in parents and trashed=false", pageSize=20, fields="files(id, name, webViewLink, size)").execute()
    items2 = results2.get('files', [])
    if not items2: return f"Folder '{folder_name}' kosong."
    
    hasil = [f"📂 Isi folder '{folder_name}':"]
    for item in items2:
        size_mb = int(item.get('size', 0)) / (1024**2) if item.get('size') else 0
        hasil.append(f"- {item['name']} ({size_mb:.2f} MB) | ID: {item['id']} | Link: {item['webViewLink']}")
    return "\n".join(hasil)


def share_to_email(drive_service, file_id, email_address, role="writer"):
    try:
        body = {"type": "user", "role": role, "emailAddress": email_address}
        drive_service.permissions().create(fileId=file_id, body=body, fields="id").execute()
        return f"Berhasil memberikan akses {role} kepada {email_address}."
    except Exception as e:
        return f"Error share email: {e}"

def trash_file(drive_service, file_id):
    try:
        body = {"trashed": True}
        drive_service.files().update(fileId=file_id, body=body).execute()
        return "Berhasil memindahkan file ke Tong Sampah (Trash)."
    except Exception as e:
        return f"Error trash file: {e}"


def rename_file(drive_service, file_id, new_name):
    try:
        body = {"name": new_name}
        drive_service.files().update(fileId=file_id, body=body).execute()
        return f"Berhasil mengganti nama file menjadi: {new_name}"
    except Exception as e:
        return f"Error rename file: {e}"

def empty_trash(drive_service):
    try:
        drive_service.files().emptyTrash().execute()
        return "Berhasil mengosongkan seluruh Tong Sampah (Trash) Drive."
    except Exception as e:
        return f"Error empty trash: {e}"

def delete_file(drive_service, file_id):
    drive_service.files().delete(fileId=file_id).execute()
    return f"File dengan ID {file_id} berhasil dihapus permanen."

def download_file(drive_service, file_id, dest_folder=None):
    if not dest_folder:
        dest_folder = str(DOWNLOADS_DIR)
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder, exist_ok=True)
        
    # Ambil nama asli
    file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
    file_name = file_metadata.get('name', f'download_{file_id}')
    dest_path = os.path.join(dest_folder, file_name)
    
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request, chunksize=1024*1024*5)
    done = False
    update_progress("Drive Download", "0%")
    while done is False:
        status, done = downloader.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            update_progress("Drive Download", f"{pct}%")
    update_progress("Drive Download", "100% Selesai")
        
    kirim_notif(f"Berhasil mendownload file {file_name} ke komputer lokal!")
    return f"SUKSES_DOWNLOAD: File {file_name} berhasil diunduh ke {dest_path}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["upload", "stat", "search", "change_access", "delete", "download", "list_folder", "share_email", "trash", "empty_trash", "rename"])
    parser.add_argument("--account", default="utama", help="Nama profil akun")
    
    parser.add_argument("--file", help="Path ke file lokal")
    parser.add_argument("--query", help="Pencarian nama file")
    parser.add_argument("--file_id", help="ID file Google Drive")
    parser.add_argument("--email", help="Email untuk sharing")
    parser.add_argument("--role", default="writer", help="Role untuk sharing")
    parser.add_argument("--new_name", help="Nama baru untuk file")
    parser.add_argument("--dest", default=str(DOWNLOADS_DIR), help="Folder tujuan download")
    parser.add_argument("--public", action="store_true", help="Ubah hak akses file menjadi publik (anyone with link). Default adalah privat.")
    
    args = parser.parse_args()
    
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        drive_service = get_authenticated_service(args.account)
        
        if args.action == "upload":
            print(upload_file(drive_service, args.file, make_public=args.public))
        elif args.action == "stat":
            print(check_quota(drive_service))
        elif args.action == "list_folder":
            print(cek_isi_folder(drive_service, args.query))
        elif args.action == "search":
            print(search_file(drive_service, args.query))
        elif args.action == "change_access":
            if change_access(drive_service, args.file_id):
                print("Akses berhasil diubah menjadi Publik (Anyone with the link).")
            else:
                print("Gagal mengubah akses file.")
        elif args.action == "share_email":
            print(share_to_email(drive_service, args.file_id, args.email, args.role))
        elif args.action == "trash":
            print(trash_file(drive_service, args.file_id))
        elif args.action == "rename":
            print(rename_file(drive_service, args.file_id, args.new_name))
        elif args.action == "empty_trash":
            print(empty_trash(drive_service))
        elif args.action == "delete":
            print(delete_file(drive_service, args.file_id))
        elif args.action == "download":
            print(download_file(drive_service, args.file_id, args.dest))
            
    except Exception as e:
        print(f"ERROR_DRIVE_API: {str(e)}")
        sys.exit(1)
