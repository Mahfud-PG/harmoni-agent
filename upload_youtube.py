import os
import sys
import argparse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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


try:
    from sari_core.paths import PROJECT_ROOT, CLIENT_SECRET_FILE, get_youtube_token_path
except ImportError:
    PROJECT_ROOT = _folder_data_cadangan()
    CLIENT_SECRET_FILE = PROJECT_ROOT / "client_secret.json"
    def get_youtube_token_path(acc): return PROJECT_ROOT / f"token_{acc}.json"

# Scope yang diizinkan (hanya upload video)
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service(account_name="default"):
    creds = None
    token_file = str(get_youtube_token_path(account_name))
    client_secret_file = str(CLIENT_SECRET_FILE)

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
    return build('youtube', 'v3', credentials=creds)

def upload_video(file_path, title, description, category_id="22", tags=None, account_name="default"):
    if tags is None:
        tags = []
        
    youtube = get_authenticated_service(account_name)
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )
    
    response = None
    print(f"Mulai mengunggah video: {title} ...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Progress: {int(status.progress() * 100)}%")
            
    print("Video berhasil diunggah!")
    return response['id']

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload video to YouTube")
    parser.add_argument("--file", required=True, help="Path ke file video")
    parser.add_argument("--title", required=True, help="Judul video")
    parser.add_argument("--desc", required=True, help="Deskripsi video")
    parser.add_argument("--tags", help="Tags dipisahkan dengan koma")
    parser.add_argument("--account", required=True, help="Nama akun YouTube target")
    
    args = parser.parse_args()
    
    tags = [tag.strip() for tag in args.tags.split(',')] if args.tags else []
    
    try:
        video_id = upload_video(args.file, args.title, args.desc, tags=tags, account_name=args.account)
        print(f"ID_VIDEO: {video_id}")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
