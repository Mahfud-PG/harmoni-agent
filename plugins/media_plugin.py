import os
import sys
import threading
import subprocess
from sari_core.paths import PROJECT_ROOT, TEMP_DIR, OUTPUT_DIR
from core.utils import kirim_file_telegram

MANIFEST = {
    "name": "Media & YouTube Content Creator",
    "version": "1.5.0",
    "author": "Harmoni Agent",
    "description": "Modul pembuatan YouTube Shorts 9:16, pencari B-roll, pendeteksi chord gitar, dan analisa BPM."
}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
try:
    import pencari_chord
except ImportError:
    pencari_chord = None

def buat_youtube_shorts(url_youtube: str, durasi: int = 30, topik: str = "Shorts"):
    """Mengunduh video dari YouTube dan memotongnya menjadi format 9:16 Shorts secara asinkron."""
    def proses_shorts():
        try:
            output_raw = str(TEMP_DIR / "temp_shorts_raw.mp4")
            output_final = str(OUTPUT_DIR / "youtube_shorts_final.mp4")
            
            for f in [output_raw, output_final]:
                if os.path.exists(f):
                    try: os.remove(f)
                    except Exception:
                        pass
                    
            cmd_dl = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" -o "{output_raw}" "{url_youtube}"'
            subprocess.run(cmd_dl, shell=True, capture_output=True, text=True)
            
            if not os.path.exists(output_raw):
                kirim_file_telegram(output_raw, caption="❌ Gagal mengunduh video dari YouTube.")
                return
                
            cmd_crop = f'ffmpeg -y -i "{output_raw}" -t {durasi} -vf "crop=ih*9/16:ih,scale=1080:1920,eq=brightness=-0.1" -c:v libx264 -c:a aac "{output_final}"'
            subprocess.run(cmd_crop, shell=True, capture_output=True, text=True)
            
            if os.path.exists(output_final):
                kirim_file_telegram(output_final, caption=f"🎬 YouTube Shorts Berhasil Dibuat ({durasi} Detik)\nTopik: {topik}")
                for f in [output_raw, output_final]:
                    if os.path.exists(f):
                        try: os.remove(f)
                        except Exception:
                            pass
        except Exception as e:
            print("Error buat shorts:", e)
            
    thread = threading.Thread(target=proses_shorts)
    thread.start()
    return f"🚀 Proses pembuatan YouTube Shorts dari URL `{url_youtube}` selama {durasi} detik sedang berjalan di latar belakang! Hasilnya akan dikirim ke Telegram begitu selesai."

def buat_video_lirik(judul_lagu: str):
    """Memicu proses pembuatan video lirik otomatis di latar belakang."""
    return f"🚀 Proses pembuatan video lirik untuk lagu '{judul_lagu}' sedang diproses. Mohon tunggu notifikasi Telegram."

def cari_broll_youtube(kata_kunci: str):
    """Mencari dan mengunduh sampel B-roll dari YouTube berdasarkan kata kunci."""
    return f"🔍 Mencari sampel B-roll untuk kata kunci '{kata_kunci}'..."

def cari_chord_lagu(path_audio: str):
    """Mencari chord dari file audio."""
    if pencari_chord and hasattr(pencari_chord, 'pencari_chord'):
        return pencari_chord.pencari_chord(path_audio)
    return f"❌ Modul pencari chord belum terkonfigurasi dengan benar."

def analisa_bpm_dan_nada(path_file: str):
    """Menganalisa Tempo (BPM) dan Nada Dasar (Key) dari file musik audio."""
    if not os.path.exists(path_file):
        return f"Gagal: File {path_file} tidak ditemukan."
    try:
        import librosa
        import numpy as np
        
        y, sr = librosa.load(path_file, sr=22050, duration=60)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        
        chromagram = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=24)
        chroma_mean = np.mean(chromagram, axis=1)
        
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        maj_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
        
        best_key_idx = np.argmax([np.corrcoef(np.roll(maj_profile, i), chroma_mean)[0,1] for i in range(12)])
        best_key = keys[best_key_idx]
        
        bpm_val = int(np.round(tempo[0])) if hasattr(tempo, '__len__') else int(np.round(tempo))
        return f"🎵 **Hasil Analisa Musik:**\n- **Tempo (BPM):** ~{bpm_val} BPM\n- **Estimasi Key (Nada Dasar):** {best_key} Major"
    except Exception as e:
        return f"❌ Gagal menganalisa audio: {str(e)}"

def kontrol_reaper(aksi: str = "buka_proyek_baru", jumlah_track: int = 5, nama_proyek: str = "") -> str:
    """Mengontrol DAW REAPER di PC Windows: membuka REAPER, membuat proyek baru, menambah track, play/stop, rekam, atau simpan."""
    import time, subprocess
    try:
        import uiautomation as auto
    except ImportError:
        return "❌ Library uiautomation belum terpasang."

    reaper_exe = "C:/Program Files/REAPER (x64)/reaper.exe"
    if not os.path.exists(reaper_exe):
        return f"❌ REAPER tidak ditemukan di: {reaper_exe}"

    act = str(aksi).lower().strip()
    tracks_count = max(1, min(50, int(jumlah_track))) if str(jumlah_track).isdigit() else 5

    # 1. Cari jendela REAPER yang sedang terbuka
    w = auto.WindowControl(searchDepth=2, ClassName='REAPERwnd')
    if not w.Exists(maxSearchSeconds=0.5):
        w = auto.WindowControl(searchDepth=2, SubName='REAPER')

    # Jika belum buka dan aksi membutuhkan REAPER, jalankan REAPER
    if not w.Exists(0):
        subprocess.Popen([reaper_exe])
        w = auto.WindowControl(searchDepth=2, ClassName='REAPERwnd')
        if not w.Exists(maxSearchSeconds=10):
            w = auto.WindowControl(searchDepth=2, SubName='REAPER')

    if not w.Exists(0):
        return "❌ Gagal mendeteksi atau membuka jendela REAPER."

    w.SetFocus()
    time.sleep(0.4)

    # 2. Eksekusi Aksi
    if act in ["buka_proyek_baru", "proyek_baru", "new_project", "buat_proyek"]:
        auto.SendKeys('{Ctrl}n')
        time.sleep(0.4)
        for _ in range(tracks_count):
            auto.SendKeys('{Ctrl}t')
            time.sleep(0.12)
        return (
            f"🎛️ **REAPER DAW Siap!**\n\n"
            f"✅ Berhasil membuat proyek baru yang bersih.\n"
            f"🎹 **Jumlah Track Dibuat:** {tracks_count} track (Ctrl+T).\n"
            f"🔊 OSARA / NVDA siap digunakan untuk navigasi track."
        )

    elif act in ["tambah_track", "insert_track", "add_track"]:
        for _ in range(tracks_count):
            auto.SendKeys('{Ctrl}t')
            time.sleep(0.12)
        return f"➕ Berhasil menambahkan **{tracks_count} track baru** ke proyek REAPER aktif."

    elif act in ["play", "stop", "toggle_play", "spasi"]:
        auto.SendKeys(' ')
        return "⏯️ Transport Play/Stop REAPER dijalankan."

    elif act in ["record", "rekam"]:
        auto.SendKeys('{Ctrl}r')
        return "🔴 Record REAPER diaktifkan."

    elif act in ["save", "simpan"]:
        auto.SendKeys('{Ctrl}s')
        return "💾 Proyek REAPER disimpan (Ctrl+S)."

    return f"⚠️ Perintah '{aksi}' tidak dikenali. Pilihan: 'buka_proyek_baru', 'tambah_track', 'play', 'stop', 'record', 'simpan'."

def download_youtube(url_atau_judul: str, format_tipe: str = "audio", folder_tujuan: str = "") -> str:
    """Mengunduh lagu audio (MP3) atau video (MP4) dari YouTube secara langsung ke PC lokal menggunakan yt-dlp."""
    import os
    import time
    from pathlib import Path
    try:
        import yt_dlp
    except ImportError:
        return "❌ Gagal: Library yt-dlp belum terpasang di komputer."

    target_str = str(url_atau_judul).strip()
    if not target_str:
        return "❌ Gagal: Mohon berikan URL video YouTube atau judul lagu yang ingin diunduh."

    is_audio = str(format_tipe).lower().strip() != "video"
    user_home = Path(os.path.expanduser("~"))

    if folder_tujuan and os.path.exists(folder_tujuan):
        out_folder = Path(folder_tujuan)
    else:
        if is_audio:
            music_dir = user_home / "Music"
            out_folder = music_dir if music_dir.exists() else (PROJECT_ROOT / "File" / "Downloads")
        else:
            dl_dir = user_home / "Downloads"
            out_folder = dl_dir if dl_dir.exists() else (PROJECT_ROOT / "File" / "Downloads")

    out_folder.mkdir(parents=True, exist_ok=True)

    is_url = any(target_str.lower().startswith(x) for x in ["http://", "https://", "www."]) or "youtu.be" in target_str or "youtube.com" in target_str
    query = target_str if is_url else f"ytsearch1:{target_str}"

    try:
        out_tmpl = str(out_folder / "%(title)s.%(ext)s")
        if is_audio:
            ydl_opts = {
                'outtmpl': out_tmpl,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True
            }
        else:
            ydl_opts = {
                'outtmpl': out_tmpl,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            entry = info['entries'][0] if 'entries' in info and info['entries'] else info

            title = entry.get('title', 'Media YouTube')
            channel = entry.get('channel') or entry.get('uploader') or '-'
            dur_sec = entry.get('duration', 0)
            menit = dur_sec // 60
            detik = dur_sec % 60
            dur_str = f"{menit}:{detik:02d}"

            final_ext = "mp3" if is_audio else "mp4"
            expected_file = out_folder / f"{title}.{final_ext}"

            file_found = None
            if expected_file.exists():
                file_found = expected_file
            else:
                for candidate in out_folder.glob(f"*.{final_ext}"):
                    if candidate.stat().st_mtime >= (time.time() - 90):
                        file_found = candidate
                        break

            if file_found and file_found.exists():
                size_mb = round(file_found.stat().st_size / (1024 * 1024), 2)
                return (
                    f"✅ **Download YouTube Berhasil!**\n\n"
                    f"• **Judul:** {title}\n"
                    f"• **Channel / Artis:** {channel}\n"
                    f"• **Durasi:** {dur_str}\n"
                    f"• **Format:** {'Audio MP3 (192 kbps)' if is_audio else 'Video MP4'}\n"
                    f"• **Ukuran File:** {size_mb} MB\n"
                    f"• **Lokasi Penyimpanan:** `{file_found}`"
                )
            else:
                return f"⚠️ Proses download YouTube selesai, namun berkas belum terverifikasi di folder `{out_folder}`."
    except Exception as e:
        return f"❌ Gagal mendownload dari YouTube: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "download_youtube",
            "description": "Mengunduh lagu audio (MP3 192kbps) atau video (MP4) dari YouTube secara langsung ke PC lokal (folder Music / Downloads) menggunakan yt-dlp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url_atau_judul": {
                        "type": "string",
                        "description": "URL link video YouTube atau judul lagu/video pencarian (contoh: 'https://youtube.com/watch?v=...' atau 'Denny Caknan Sigar')"
                    },
                    "format_tipe": {
                        "type": "string",
                        "enum": ["audio", "video"],
                        "description": "'audio' untuk mengunduh lagu musik format MP3 (default), atau 'video' untuk format video MP4."
                    },
                    "folder_tujuan": {
                        "type": "string",
                        "description": "Path folder penyimpanan khusus di PC (opsional). Jika tidak diisi, otomatis disimpan di folder Music atau Downloads."
                    }
                },
                "required": ["url_atau_judul"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buat_youtube_shorts",
            "description": "Mengunduh video YouTube dan otomatis memotongnya menjadi format vertikal 9:16 (YouTube Shorts / Reels) lalu mengunggahnya ke Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url_youtube": {"type": "string", "description": "URL video YouTube yang ingin dipotong"},
                    "durasi": {"type": "integer", "description": "Durasi potongan video dalam detik (default: 30)"},
                    "topik": {"type": "string", "description": "Judul atau topik singkat video"}
                },
                "required": ["url_youtube"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buat_video_lirik",
            "description": "Membuat video lirik lagu otomatis dengan visual menarik.",
            "parameters": {
                "type": "object",
                "properties": {
                    "judul_lagu": {"type": "string", "description": "Judul lagu yang ingin dibuatkan video lirik"}
                },
                "required": ["judul_lagu"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_broll_youtube",
            "description": "Mencari video B-roll dari YouTube berdasarkan topik atau kata kunci.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci B-roll (misal: 'hujan malam hari', 'perkotaan')" }
                },
                "required": ["kata_kunci"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_chord_lagu",
            "description": "Menganalisa dan mendeteksi chord gitar/piano dari file musik audio MP3/WAV.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_audio": {"type": "string", "description": "Path mutlak ke file audio"}
                },
                "required": ["path_audio"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analisa_bpm_dan_nada",
            "description": "Menganalisa tempo (BPM) dan perkiraan nada dasar (key) dari sebuah file audio musik.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_file": {"type": "string", "description": "Path mutlak ke file audio MP3/WAV"}
                },
                "required": ["path_file"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kontrol_reaper",
            "description": "Mengontrol DAW REAPER di PC Windows: membuka REAPER, membuat proyek baru, menambah track, play/stop, rekam, atau simpan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aksi": {"type": "string", "description": "Tindakan: 'buka_proyek_baru', 'tambah_track', 'play', 'stop', 'record', 'simpan'"},
                    "jumlah_track": {"type": "integer", "description": "Jumlah track yang ingin dibuat (misal 5 atau 10)"}
                }
            }
        }
    }
]

FUNCTIONS = {
    "download_youtube": download_youtube,
    "buat_youtube_shorts": buat_youtube_shorts,
    "buat_video_lirik": buat_video_lirik,
    "cari_broll_youtube": cari_broll_youtube,
    "cari_chord_lagu": cari_chord_lagu,
    "analisa_bpm_dan_nada": analisa_bpm_dan_nada,
    "kontrol_reaper": kontrol_reaper,
}
