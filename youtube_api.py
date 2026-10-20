import os
import sys
import argparse
import json
from pathlib import Path
import requests

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

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    from sari_core.paths import PROJECT_ROOT, CLIENT_SECRET_FILE, get_youtube_token_path
except ImportError:
    PROJECT_ROOT = _folder_data_cadangan()
    CLIENT_SECRET_FILE = PROJECT_ROOT / "client_secret.json"
    def get_youtube_token_path(acc): return PROJECT_ROOT / f"token_{acc}.json"

def update_progress(tugas, persen):
    file_prog = str(PROJECT_ROOT / "progress.json")
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
        chat_file = PROJECT_ROOT / "chat_id.txt"
        if not chat_id and chat_file.exists():
            try:
                with open(str(chat_file), "r", encoding="utf-8") as f:
                    chat_id = f.read().strip()
            except Exception:
                pass
        if token and chat_id:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": pesan}, timeout=10)
    except Exception as e:
        print(f"[YOUTUBE NOTIF ERROR] Gagal kirim notif Telegram: {e}")

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

def get_authenticated_service(account_name="utama"):
    creds = None
    token_file = str(get_youtube_token_path(account_name))
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
                print(f"Token YouTube ({account_name}) refresh gagal: {e_ref}. Hapus token lama...")
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
            
    return build('youtube', 'v3', credentials=creds)

def upload_video(youtube, file_path, title, description, tags, thumbnail_path=None):
    body = {
        'snippet': {'title': title, 'description': description, 'tags': tags, 'categoryId': "22"},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    media = MediaFileUpload(file_path, chunksize=1024*1024*5, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    update_progress("YouTube Upload", "0%")
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            update_progress("YouTube Upload", f"{pct}%")
    update_progress("YouTube Upload", "100% Selesai")
    video_id = response['id']
    
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()
            kirim_notif(f"Berhasil mengunggah video ke YouTube (dengan thumbnail)! Link: https://youtu.be/{video_id}")
            return f"SUKSES_UPLOAD: {video_id} (Dengan Thumbnail)"
        except Exception as e:
            return f"SUKSES_UPLOAD: {video_id} (Tapi Gagal set thumbnail: {str(e)})"
    msg = f"Berhasil mengunggah video ke YouTube! Link: https://youtu.be/{video_id}"
    kirim_notif(msg)
    return f"SUKSES_UPLOAD: {video_id}"

def get_stats(youtube):
    request = youtube.channels().list(part="statistics,snippet", mine=True)
    response = request.execute()
    if not response.get('items'): return "Channel tidak ditemukan."
    stat = response['items'][0]['statistics']
    snip = response['items'][0]['snippet']
    return f"Channel: {snip['title']}\nSubscribers: {stat.get('subscriberCount', 0)}\nTotal Views: {stat.get('viewCount', 0)}\nTotal Video: {stat.get('videoCount', 0)}"

def get_comments(youtube, max_results=5):
    req_channel = youtube.channels().list(part="id", mine=True)
    res_channel = req_channel.execute()
    if not res_channel.get('items'): return "Gagal membaca komentar: Channel tidak ditemukan."
    channel_id = res_channel['items'][0]['id']
    
    request = youtube.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=channel_id, order="time", maxResults=max_results)
    response = request.execute()
    comments = []
    for item in response.get("items", []):
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        comment_id = item["snippet"]["topLevelComment"]["id"]
        author = snippet["authorDisplayName"]
        text = snippet["textDisplay"]
        video_id = snippet.get("videoId", "Tidak diketahui")
        comments.append(f"ID: {comment_id} | Penulis: {author} | Video: {video_id} | Komentar: {text}")
    if not comments: return "Belum ada komentar terbaru."
    return "\n---\n".join(comments)

def reply_comment(youtube, comment_id, text):
    request = youtube.comments().insert(part="snippet", body={"snippet": {"parentId": comment_id, "textOriginal": text}})
    response = request.execute()
    return f"Berhasil membalas komentar! ID Balasan: {response['id']}"

def delete_comment(youtube, comment_id):
    youtube.comments().delete(id=comment_id).execute()
    return "Komentar berhasil dihapus permanen dari YouTube."

def edit_video(youtube, video_id, title=None, desc=None, tags=None):
    req_get = youtube.videos().list(part="snippet", id=video_id)
    res_get = req_get.execute()
    if not res_get.get('items'): return f"Video dengan ID {video_id} tidak ditemukan."
    snippet = res_get['items'][0]['snippet']
    if title: snippet['title'] = title
    if desc: snippet['description'] = desc
    if tags: snippet['tags'] = [t.strip() for t in tags.split(',')]
    req_update = youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet})
    res_update = req_update.execute()
    return f"Berhasil mengedit video. Judul baru: {res_update['snippet']['title']}"

def search_video(youtube, query, max_results=3):
    request = youtube.search().list(part="snippet", q=query, forMine=True, type="video", maxResults=max_results)
    response = request.execute()
    hasil = []
    for item in response.get("items", []):
        hasil.append(f"ID Video: {item['id']['videoId']} | Judul: {item['snippet']['title']}")
    if not hasil: return "Video tidak ditemukan di channel Anda."
    return "\n".join(hasil)

def set_thumbnail(youtube, video_id, thumbnail_path):
    """Ganti thumbnail, lalu PERIKSA apakah gambar yang tayang benar-benar berubah."""
    if not os.path.exists(thumbnail_path):
        return "File thumbnail tidak ditemukan di komputer Anda."
    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()

    # Verifikasi: unduh gambar yang sekarang tayang, bandingkan warna dengan berkas yang dikirim
    try:
        import io
        import time as _t
        import urllib.request
        from PIL import Image

        _t.sleep(6)
        info = youtube.videos().list(part="snippet", id=video_id).execute()
        thumbs = info["items"][0]["snippet"].get("thumbnails", {})
        pilih = thumbs.get("maxres") or thumbs.get("standard") or thumbs.get("high") or thumbs.get("medium")
        req = urllib.request.Request(pilih["url"], headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read()

        warna_kirim = Image.open(thumbnail_path).convert("RGB").resize((1, 1)).getpixel((0, 0))
        warna_tayang = Image.open(io.BytesIO(data)).convert("RGB").resize((1, 1)).getpixel((0, 0))
        selisih = sum(abs(a - b) for a, b in zip(warna_kirim, warna_tayang))

        if selisih <= 45:
            return "✅ Thumbnail BENAR-BENAR berubah (sudah diperiksa ulang dari server YouTube)."
        return (
            "⚠️ Permintaan ganti thumbnail DITOLAK diam-diam oleh YouTube: perintahnya tidak menghasilkan "
            "kesalahan, tetapi gambar yang tayang masih gambar lama.\n"
            "Biasanya karena channel belum diverifikasi untuk thumbnail kustom (bisa dipasang sendiri di "
            "YouTube Studio). Thumbnail TIDAK terganti."
        )
    except Exception as e:
        return f"⚠️ Thumbnail dikirim, tetapi gagal diverifikasi: {type(e).__name__}: {str(e)[:150]}"

def create_playlist(youtube, title, desc, privasi="private"):
    """Membuat playlist. Bawaan PRIVAT agar tidak tayang ke publik sebelum ditinjau."""
    res = youtube.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": desc},
        "status": {"privacyStatus": privasi},
    }).execute()
    # Verifikasi: baca ulang dari server
    cek = youtube.playlists().list(part="id,snippet,status", id=res["id"]).execute()
    if not cek.get("items"):
        return f"❌ Playlist dilaporkan dibuat (ID: {res['id']}) tapi tidak ditemukan saat dibaca ulang."
    p = cek["items"][0]
    return (f"✅ Playlist BENAR-BENAR dibuat.\n• Judul: {p['snippet']['title']}\n"
            f"• ID: {p['id']}\n• Status tayang: {p['status']['privacyStatus']}")

def add_to_playlist(youtube, playlist_id, video_id):
    youtube.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
    # Verifikasi: pastikan video benar-benar ada di dalam playlist
    cek = youtube.playlistItems().list(part="id,snippet", playlistId=playlist_id, videoId=video_id, maxResults=1).execute()
    if not cek.get("items"):
        return "❌ Video tidak ditemukan di dalam playlist setelah perintah dijalankan."
    return "✅ Video BENAR-BENAR masuk ke dalam playlist (sudah diperiksa ulang)."

def latest_videos_from_channel(youtube, channel_name, max_results=3):
    req1 = youtube.search().list(part="snippet", q=channel_name, type="channel", maxResults=1)
    res1 = req1.execute()
    if not res1.get("items"): return f"Channel YouTube dengan nama '{channel_name}' tidak ditemukan."
    channel_id = res1["items"][0]["snippet"]["channelId"]
    channel_title = res1["items"][0]["snippet"]["title"]
    req2 = youtube.search().list(part="snippet", channelId=channel_id, order="date", type="video", maxResults=max_results)
    res2 = req2.execute()
    hasil = [f"🎥 Video Terbaru dari Channel '{channel_title}':"]
    for item in res2.get("items", []):
        title = item["snippet"]["title"]
        vid_id = item["id"]["videoId"]
        pub = item["snippet"]["publishedAt"][:10]
        hasil.append(f"- {title} (Tgl: {pub}) | Link: https://youtu.be/{vid_id}")
def latest_my_video(youtube):
    """Mengecek video terakhir yang di-upload ke channel YouTube sendiri beserta statistik real-time (views, likes, comments)."""
    try:
        res_channel = youtube.channels().list(part='contentDetails,snippet', mine=True).execute()
        if not res_channel.get('items'):
            return "Channel tidak ditemukan."
            
        channel_title = res_channel['items'][0]['snippet']['title']
        uploads_playlist_id = res_channel['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        res_items = youtube.playlistItems().list(part='snippet,contentDetails', playlistId=uploads_playlist_id, maxResults=1).execute()
        if not res_items.get('items'):
            return f"Channel '{channel_title}' belum memiliki video yang di-upload."
            
        item = res_items['items'][0]
        vid_id = item['contentDetails']['videoId']
        vid_title = item['snippet']['title']
        pub_at = item['snippet']['publishedAt'][:10]
        
        res_vid = youtube.videos().list(part='statistics,status,snippet', id=vid_id).execute()
        if res_vid.get('items'):
            stats = res_vid['items'][0]['statistics']
            status = res_vid['items'][0]['status']
            views = stats.get('viewCount', 0)
            likes = stats.get('likeCount', 0)
            comments = stats.get('commentCount', 0)
            privacy = status.get('privacyStatus', 'public')
            desc = res_vid['items'][0]['snippet'].get('description', '')[:150]
            
            return (
                f"🎥 *VIDEO TERAKHIR DI-UPLOAD DI CHANNEL '{channel_title.upper()}':*\n\n"
                f"📌 **Judul:** {vid_title}\n"
                f"🆔 **ID Video:** `{vid_id}`\n"
                f"📅 **Tanggal Upload:** `{pub_at}`\n"
                f"🔒 **Status Akses:** `{privacy.upper()}`\n\n"
                f"📊 **STATISTIK REAL-TIME:**\n"
                f"👁️ **Penonton (Views):** `{views}` kali\n"
                f"👍 **Menyukai (Likes):** `{likes}` suka\n"
                f"💬 **Komentar:** `{comments}` komentar\n\n"
                f"🔗 **Link Nonton:** https://youtu.be/{vid_id}\n\n"
                f"📝 **Deskripsi:** {desc}..."
            )
        return f"Video terakhir: {vid_title} (https://youtu.be/{vid_id})"
    except Exception as e:
        return f"Gagal mengecek video terakhir: {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--file", help="Path video")
    parser.add_argument("--thumb", help="Path thumbnail")
    parser.add_argument("--title", help="Judul")
    parser.add_argument("--desc", help="Deskripsi")
    parser.add_argument("--tags", help="Tags")
    parser.add_argument("--comment_id", help="ID komentar")
    parser.add_argument("--text", help="Teks")
    parser.add_argument("--video_id", help="ID video")
    parser.add_argument("--playlist_id", help="ID playlist")
    parser.add_argument("--query", help="Pencarian")
    parser.add_argument("--max", type=int, default=5)
    
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        youtube = get_authenticated_service(args.account)
        
        if args.action == "upload":
            tags_list = [t.strip() for t in args.tags.split(',')] if args.tags else []
            print(upload_video(youtube, args.file, args.title, args.desc, tags_list, args.thumb))
        elif args.action == "stat": print(get_stats(youtube))
        elif args.action == "get_comments": print(get_comments(youtube, args.max))
        elif args.action == "reply": print(reply_comment(youtube, args.comment_id, args.text))
        elif args.action == "delete_comment": print(delete_comment(youtube, args.comment_id))
        elif args.action == "edit": print(edit_video(youtube, args.video_id, args.title, args.desc, args.tags))
        elif args.action == "search_mine": print(search_video(youtube, args.query, args.max))
        elif args.action == "set_thumb": print(set_thumbnail(youtube, args.video_id, args.thumb))
        elif args.action == "create_playlist": print(create_playlist(youtube, args.title, args.desc))
        elif args.action == "add_to_playlist": print(add_to_playlist(youtube, args.playlist_id, args.video_id))
        elif args.action == "latest_from_channel": print(latest_videos_from_channel(youtube, args.query, args.max))
        elif args.action == "latest_my_video": print(latest_my_video(youtube))
    except Exception as e:
        print(f"ERROR_YOUTUBE_API: {str(e)}")
        sys.exit(1)
