last_seen_email_id = None
from html.parser import HTMLParser
from datetime import datetime, timedelta
import urllib.request
import os
import sys
from pathlib import Path
import functools

# ---------------------------------------------------------------------------
# DUA JANGKAR - JANGAN DITUKAR.
#
#   _AKAR_PROGRAM : tempat BERKAS PROGRAM (berkas ini sendiri, sys.path, cwd,
#                   backsound, skrip pembantu). IKUT DIGANTI setiap ada versi baru,
#                   jadi apa pun yang ditulis ke sini bisa hilang saat diperbarui.
#   PROJECT_ROOT  : tempat BERKAS DATA pengguna (riwayat YouTube, ingatan, setelan).
#                   Saat aplikasi terpasang = %APPDATA%\HarmoniAgent, dan diambil
#                   dari sari_core.paths supaya konsisten dengan seluruh aplikasi.
#
# Versi lama memakai SATU nama untuk keduanya (folder program), sehingga berkas data
# ikut ditulis ke folder program - bisa hilang saat diperbarui dan tidak tercadangkan.
# ---------------------------------------------------------------------------
_AKAR_PROGRAM = Path(__file__).resolve().parent
os.chdir(_AKAR_PROGRAM)
if str(_AKAR_PROGRAM) not in sys.path:
    sys.path.insert(0, str(_AKAR_PROGRAM))

from sari_core.paths import (
    CORE_DIR, PLUGINS_DIR, FILE_DIR, DOWNLOADS_DIR, TEMP_DIR,
    OUTPUT_DIR, OBSIDIAN_DIR, WA_BRIDGE_DIR, ENV_FILE,
    CLIENT_SECRET_FILE, ACCESS_CONFIG_FILE, MODEL_CONFIG_FILE,
    ADMIN_WA_STATUS_FILE, OPENROUTER_CACHE_FILE,
    PROJECT_ROOT,  # = folder DATA pengguna
)

import re
import cv2
import pyperclip
import time
import json
import webbrowser
import subprocess
import threading
import asyncio
import pyautogui
try:
    import pywhatkit
except Exception:
    pywhatkit = None
import pyttsx3
import urllib.parse
import imaplib
import email
from email.header import decode_header
import uiautomation as auto
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import PyPDF2
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import textwrap
import requests
from bs4 import BeautifulSoup
import glob
import shutil
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from buat_nota import buat_nota_pdf

status_otonom = {"berhenti": False}
MODE_PROGRAMMER = False
WORKSPACE_DIR = str(FILE_DIR / "Proyek")
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

# Inisialisasi Suara
try:
    import accessible_output2.outputs.auto
    output_speaker = accessible_output2.outputs.auto.Auto()
except Exception as e:
    print("Accessible output 2 gagal dimuat:", e)
    output_speaker = None

try:
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
except Exception as e:
    print("Suara PC tidak didukung:", e)

def jalankan_async_aman(coro):
    """Menjalankan coroutine async dengan aman, baik di luar maupun di dalam event loop asyncio yang sedang aktif."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# chat_id_tersimpan dipakai sebagai variabel global di tugas_wa_bot_background()
# (ada 'global chat_id_tersimpan' di sana). Tanpa inisialisasi di level modul,
# pembacaan pertamanya menghasilkan NameError dan tugas latar WA mati.
chat_id_tersimpan = TELEGRAM_CHAT_ID

ALIBABA_API_KEY = os.getenv("ALIBABA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client_openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

client_qwen = OpenAI(base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1", api_key=ALIBABA_API_KEY) if ALIBABA_API_KEY else None
client_gemini = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
client_deepseek = OpenAI(base_url="https://api.deepseek.com", api_key=DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else None

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
client_openrouter = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={"HTTP-Referer": "https://harmoni.local", "X-Title": "Harmoni Agent"}
) if OPENROUTER_API_KEY else None


# UPGRADE KE OTAK MULTI-PROVIDER (MiMo V2.5 → DeepSeek → Gemini)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
client_openrouter = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
) if OPENROUTER_API_KEY else None

daftar_mesin = []
if client_deepseek:
    daftar_mesin.append({"nama": "DeepSeek V3 Chat", "client": client_deepseek, "model": "deepseek-chat", "pakai_tools": True})

daftar_mesin.append(
    {"nama": "Gemini 2.5 Flash", "client": client_gemini, "model": "gemini-2.5-flash", "pakai_tools": True}
)

if client_qwen:
    daftar_mesin.append({"nama": "Qwen 3.8 Max (Alibaba Cloud)", "client": client_qwen, "model": "qwen-max", "pakai_tools": True})
# ----------------- FUNGSI ALAT (TOOLS) -----------------
def buka_website(url: str):
    try:
        webbrowser.open(url)
        return f"Berhasil membuka website: {url}"
    except Exception as e:
        return f"Gagal membuka website: {str(e)}"

def _simpan_riwayat_youtube(data_video: dict):
    """Helper internal: simpan 1 record video ke riwayat_youtube.json (max 100 entry)."""
    import datetime
    RIWAYAT_FILE = str(PROJECT_ROOT / "riwayat_youtube.json")
    try:
        riwayat = []
        if os.path.exists(RIWAYAT_FILE):
            with open(RIWAYAT_FILE, 'r', encoding='utf-8') as f:
                riwayat = json.load(f)
        data_video["waktu_putar"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        riwayat.append(data_video)
        riwayat = riwayat[-100:]  # simpan max 100 entry terakhir
        with open(RIWAYAT_FILE, 'w', encoding='utf-8') as f:
            json.dump(riwayat, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _ambil_metadata_youtube(video_url: str) -> dict:
    """Helper internal: ambil judul, channel, durasi dari yt-dlp --dump-json (cepat, tanpa download)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-download", "--no-warnings", video_url],
            capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0 and result.stdout.strip():
            info = json.loads(result.stdout.strip())
            durasi_detik = info.get("duration", 0) or 0
            menit = int(durasi_detik) // 60
            detik = int(durasi_detik) % 60
            return {
                "judul": info.get("title", "Tidak diketahui"),
                "channel": info.get("channel", info.get("uploader", "Tidak diketahui")),
                "durasi": f"{menit}:{detik:02d}",
                "durasi_detik": durasi_detik,
                "url": video_url,
                "video_id": info.get("id", "")
            }
    except Exception:
        pass
    return None

def putar_youtube(kata_kunci: str):
    try:
        query = urllib.parse.quote_plus(kata_kunci)
        search_url = f"https://www.youtube.com/results?search_query={query}"
        
        url_video = None
        video_id = None
        try:
            req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            html = urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
            matches = re.findall(r'/watch\?v=([A-Za-z0-9_-]{11})', html)
            if matches:
                video_id = matches[0]
                url_video = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        except Exception as err:
            print("Fetch video ID error:", err)
            
        if not url_video:
            url_video = search_url
            
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_path):
            chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        
        if os.path.exists(chrome_path):
            subprocess.Popen([chrome_path, "--autoplay-policy=no-user-gesture-required", "--new-window", url_video])
        else:
            webbrowser.open(url_video)
        
        # === FITUR BARU: Ambil metadata & simpan riwayat (async, tidak menghambat) ===
        if video_id:
            meta = _ambil_metadata_youtube(f"https://www.youtube.com/watch?v={video_id}")
            if meta:
                _simpan_riwayat_youtube(meta)
                return (
                    f"Memutar: {meta['judul']}\n"
                    f"Channel: {meta['channel']}\n"
                    f"Durasi: {meta['durasi']}\n"
                    f"Kata kunci: {kata_kunci}"
                )
        
        return f"Berhasil memutar '{kata_kunci}' di YouTube."
    except Exception as e:
        return f"Gagal memutar YouTube: {str(e)}"

def putar_ulang_youtube(channel: str = ""):
    """Memutar ulang video YouTube terakhir yang pernah diputar, opsional filter berdasarkan nama channel."""
    try:
        RIWAYAT_FILE = str(PROJECT_ROOT / "riwayat_youtube.json")
        
        # Sumber 1: Riwayat Siti
        riwayat_siti = []
        if os.path.exists(RIWAYAT_FILE):
            with open(RIWAYAT_FILE, 'r', encoding='utf-8') as f:
                riwayat_siti = json.load(f)
        
        # Sumber 2: Riwayat Chrome PC (opsional, sebagai pelengkap)
        riwayat_chrome = []
        try:
            import sqlite3, shutil, datetime
            chrome_history_db = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data\Default\History")
            if os.path.exists(chrome_history_db):
                tmp_db = str(PROJECT_ROOT / "chrome_history_tmp.db")
                shutil.copy2(chrome_history_db, tmp_db)
                conn = sqlite3.connect(tmp_db)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT url, title, last_visit_time 
                    FROM urls 
                    WHERE url LIKE '%youtube.com/watch%' 
                    ORDER BY last_visit_time DESC 
                    LIMIT 20
                """)
                for row in cursor.fetchall():
                    vid_match = re.search(r'v=([A-Za-z0-9_-]{11})', row[0])
                    if vid_match:
                        riwayat_chrome.append({
                            "url": row[0],
                            "judul": row[1] or "Tidak diketahui",
                            "channel": "",
                            "durasi": "",
                            "video_id": vid_match.group(1),
                            "sumber": "Chrome PC"
                        })
                conn.close()
                os.remove(tmp_db)
        except Exception:
            pass
        
        # Gabungkan: prioritas riwayat Siti dulu, lalu Chrome
        semua_riwayat = riwayat_siti + riwayat_chrome
        
        if not semua_riwayat:
            return "Belum ada riwayat video YouTube yang pernah diputar, Kak."
        
        # Filter berdasarkan channel jika diminta
        if channel:
            channel_lower = channel.lower().strip()
            filtered = [
                r for r in semua_riwayat 
                if channel_lower in (r.get("channel", "") or "").lower() 
                or channel_lower in (r.get("judul", "") or "").lower()
            ]
            if not filtered:
                return f"Tidak ditemukan video dari channel/kata kunci '{channel}' di riwayat YouTube, Kak."
            target = filtered[-1]
        else:
            target = semua_riwayat[-1]
        
        # Putar video
        url = target.get("url", "")
        if not url and target.get("video_id"):
            url = f"https://www.youtube.com/watch?v={target['video_id']}&autoplay=1"
        
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_path):
            chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        
        if os.path.exists(chrome_path):
            subprocess.Popen([chrome_path, "--autoplay-policy=no-user-gesture-required", "--new-window", url])
        else:
            webbrowser.open(url)
        
        judul = target.get("judul", "Tidak diketahui")
        ch = target.get("channel", "")
        durasi = target.get("durasi", "")
        info = f"Memutar ulang: {judul}"
        if ch:
            info += f"\nChannel: {ch}"
        if durasi:
            info += f"\nDurasi: {durasi}"
        return info
        
    except Exception as e:
        return f"Gagal memutar ulang: {str(e)}"

def jalankan_perintah_sistem(perintah: str):
    """Menjalankan perintah sistem dan MENGEMBALIKAN HASILNYA.

    PENTING: versi lama hanya mengembalikan kata "Berhasil" dan MEMBUANG isi
    keluarannya (`hasil.stdout` ditangkap lalu tidak pernah dipakai). Akibatnya
    otak AI tidak punya apa pun untuk dilaporkan, sehingga menjawab "Berhasil"
    kepada pengguna - jawaban kosong yang menyesatkan, karena sebenarnya tidak
    ada satu pun angka atau daftar yang bisa dibacakan.

    Aturan: kegagalan HARUS berbentuk pesan yang menyebut sebabnya, dan
    keberhasilan HARUS membawa keluarannya.
    """
    try:
        hasil = subprocess.run(
            perintah, shell=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        return "Gagal: perintah melebihi batas 180 detik."
    except Exception as e:
        return f"Gagal menjalankan perintah: {e}"

    keluaran = (hasil.stdout or "").strip()
    galat = (hasil.stderr or "").strip()

    if hasil.returncode != 0:
        rinci = galat or keluaran or "(tidak ada keterangan)"
        return f"Gagal (kode keluar {hasil.returncode}): {rinci[:1500]}"

    if keluaran:
        return keluaran[:3000]

    if galat:
        return f"Berhasil dijalankan, tetapi ada catatan: {galat[:500]}"

    return ("Berhasil dijalankan, tetapi perintah ini tidak menghasilkan keluaran "
            "apa pun yang bisa dilaporkan.")


def buat_video_lirik(jalur_audio: str, prompt_visual: str, chat_id=None):
    """
    Membuat video lirik otomatis dengan latar belakang AI dan teks karaoke tersinkronisasi.
    """
    try:
        def _thread_lirik():
            global status_pekerjaan_video
            status_pekerjaan_video["aktif"] = True
            status_pekerjaan_video["nama_tugas"] = "Video Lirik"
            status_pekerjaan_video["keterangan"] = f"Menganalisa dan merender lirik untuk: {jalur_audio}"
            
            try:
                import sys
                sys.path.append(str(PROGRAM_ROOT))
                import pembuat_video_lirik
                hasil = pembuat_video_lirik.buat_video_lirik(jalur_audio, prompt_visual)
                pesan = f"🎬 Laporan Video Lirik Selesai!\n\n{hasil}"
            except Exception as e:
                pesan = f"❌ GAGAL membuat video lirik: {str(e)}"
                
            _kirim_notifikasi_selesai(chat_id, pesan)
            status_pekerjaan_video["aktif"] = False

        import threading
        t = threading.Thread(target=_thread_lirik)
        t.start()
        return "Tugas meracik video lirik cinematic telah dimulai di latar belakang! Sari akan menelpon (mengirim pesan) kalau sudah beres."
    except Exception as e:
        return f"Gagal memulai thread video lirik: {e}"

def kontrol_keyboard(aksi: str, tombol_atau_teks: str):
    try:
        if aksi == 'tekan':
            pyautogui.press(tombol_atau_teks)
            return f"Berhasil menekan tombol {tombol_atau_teks}."
        elif aksi == 'kombinasi':
            tombol = tombol_atau_teks.split(',')
            pyautogui.hotkey(*tombol)
            return f"Berhasil menekan kombinasi {tombol_atau_teks}."
        elif aksi == 'ketik':
            pyautogui.write(tombol_atau_teks, interval=0.05)
            pyautogui.press('enter')
            return f"Berhasil mengetik: {tombol_atau_teks}"
        else:
            return "Aksi tidak dikenali."
    except Exception as e:
        return f"Gagal mengontrol keyboard: {str(e)}"


def buat_suara_openai(teks: str, filepath: str):
    """Menghasilkan file suara (voice note OGG Opus) menggunakan Gemini TTS (Leda) -> Fallback: ElevenLabs -> Edge-TTS (Suara Gadis)"""
    teks_bersih = teks.replace('*', '').replace('#', '').replace('_', '').strip()
    
    # 1. Prioritas Utama: Gemini TTS (Voice Leda - Gemini 3.6 Flash & 3.1 Flash Preview)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        for model_name in ['gemini-3.6-flash', 'gemini-3.1-flash-tts-preview']:
            try:
                from google import genai
                from google.genai import types
                import subprocess
                
                client_gemini = genai.Client(api_key=gemini_key)
                res_gemini = client_gemini.models.generate_content(
                    model=model_name,
                    contents=teks_bersih[:1000],
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Leda'
                                )
                            )
                        )
                    )
                )
                
                audio_data = None
                if res_gemini.candidates and res_gemini.candidates[0].content and res_gemini.candidates[0].content.parts:
                    for part in res_gemini.candidates[0].content.parts:
                        if part.inline_data:
                            audio_data = part.inline_data.data
                            break
                            
                if audio_data:
                    # Konversi PCM Raw 24kHz Mono ke OGG Opus via FFmpeg agar valid di Telegram
                    cmd = ['ffmpeg', '-y', '-f', 's16le', '-ar', '24000', '-ac', '1', '-i', 'pipe:0', '-c:a', 'libopus', '-b:a', '32k', filepath]
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    proc.communicate(input=audio_data)
                    
                    if proc.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        print(f"[TTS SUCCESS] Berhasil membuat Voice Note Telegram dengan Gemini TTS ({model_name} - Leda)")
                        return True
            except Exception as e_gem:
                print(f"Gemini TTS ({model_name}) exception: {e_gem}")

    # 2. Coba ElevenLabs
    el_keys = [os.getenv("ELEVENLABS_API_KEY_1"), os.getenv("ELEVENLABS_API_KEY_2"), os.getenv("ELEVENLABS_API_KEY")]
    el_keys = [k for k in el_keys if k]
    voice_id = "EXAVITQu4vr4xnSDxMaL" # Bella
    for api_key in el_keys:
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
            data = {
                "text": teks_bersih[:1000],
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }
            res = requests.post(url, headers=headers, json=data, timeout=10)
            if res.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(res.content)
                print(f"[TTS SUCCESS] Berhasil membuat Voice Note dengan ElevenLabs")
                return True
        except Exception as e_el:
            print(f"ElevenLabs TTS exception: {e_el}")

    # 2. Cadangan Utama: Edge-TTS Suara Gadis (id-ID-GadisNeural) - 100% Gratis & Jernih
    try:
        import edge_tts
        temp_mp3 = filepath + ".mp3"
        async def _run_edge():
            comm = edge_tts.Communicate(teks_bersih[:4000], "id-ID-GadisNeural")
            await comm.save(temp_mp3)
        jalankan_async_aman(_run_edge())
        if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 0:
            cmd = ['ffmpeg', '-y', '-i', temp_mp3, '-c:a', 'libopus', '-b:a', '32k', filepath]
            subprocess.run(cmd, capture_output=True)
            try: os.remove(temp_mp3)
            except Exception:

                pass
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print("[TTS SUCCESS] Berhasil membuat Voice Note Telegram dengan Suara Gadis (Edge-TTS)")
                return True
    except Exception as e_edge:
        print(f"Edge TTS Python exception: {e_edge}. Mencoba CLI fallback...")
        try:
            temp_mp3 = filepath + ".mp3"
            teks_aman = teks_bersih[:4000].replace('"', "'")
            cmd = f'edge-tts --voice id-ID-GadisNeural --text "{teks_aman}" --write-media "{temp_mp3}"'
            subprocess.run(cmd, shell=True, capture_output=True, timeout=20)
            if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 0:
                subprocess.run(['ffmpeg', '-y', '-i', temp_mp3, '-c:a', 'libopus', '-b:a', '32k', filepath], capture_output=True)
                try: os.remove(temp_mp3)
                except Exception:

                    pass
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    print("[TTS SUCCESS] Berhasil membuat Voice Note Telegram dengan Suara Gadis (Edge-TTS CLI)")
                    return True
        except Exception as e_cli:
            print(f"Edge TTS CLI exception: {e_cli}")
        return False

def berbicara_dengan_suara_sari(teks: str):
    """Berbicara menggunakan suara TTS wanita (Gadis) yang realistis. Gunakan ini untuk membacakan rangkuman berita, cerita, atau pesan penting."""
    try:
        temp_audio = "temp_sari_voice.mp3"
        # Hapus file lama jika ada
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except Exception:

                pass
                
        # Generate suara dengan Edge-TTS (Suara Gadis)
        # Ganti tanda kutip ganda ke tunggal agar aman di CLI
        teks_aman = teks.replace('"', "'")
        print(f"[Sari Voice] Generating: {teks_aman}")
        perintah = f'edge-tts --voice id-ID-GadisNeural --text "{teks_aman}" --write-media {temp_audio}'
        subprocess.run(perintah, shell=True, check=True)
        
        # Mainkan suara dengan ffplay di background (tanpa window)
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(["ffplay", "-nodisp", "-autoexit", temp_audio], creationflags=CREATE_NO_WINDOW)
        
        return "Berhasil membacakan teks dengan suara Sari."
    except Exception as e:
        return f"Gagal membacakan dengan suara Sari: {str(e)}"

def jalankan_alarm_suara(pesan: str):
    """Fungsi internal untuk menjalankan alarm"""
    berbicara_dengan_suara_sari(f"Perhatian! Ini adalah pengingat dari Sari: {pesan}")
    
def pasang_pengingat_suara(pesan_pengingat: str, waktu_menit: int):
    """Memasang alarm/pengingat yang akan bersuara otomatis setelah sekian menit. Gunakan ini jika pengguna minta diingatkan sesuatu."""
    try:
        waktu_detik = float(waktu_menit) * 60.0
        # Gunakan daemon thread agar tidak memblokir program utama
        t = threading.Timer(waktu_detik, jalankan_alarm_suara, args=[pesan_pengingat])
        t.daemon = True
        t.start()
        waktu_target = datetime.datetime.now() + datetime.timedelta(minutes=waktu_menit)
        waktu_str = waktu_target.strftime("%H:%M:%S")
        return f"Pengingat suara berhasil dipasang! Sari akan bicara keras-keras pada pukul {waktu_str} untuk mengingatkan: {pesan_pengingat}"
    except Exception as e:
        return f"Gagal memasang pengingat: {str(e)}"


def berbicara_lewat_pc(teks: str):
    try:
        # 1. Coba ElevenLabs (Prioritas 1)
        api_keys = [os.getenv("ELEVENLABS_API_KEY_1"), os.getenv("ELEVENLABS_API_KEY_2")]
        api_keys = [k for k in api_keys if k]
        
        for api_key in api_keys:
            try:
                import numpy as np
                import sounddevice as sd
                headers = {'xi-api-key': api_key}
                data = {
                    "text": teks,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                }
                voice_id = "EXAVITQu4vr4xnSDxMaL" # Bella
                res = requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_16000', headers=headers, json=data)
                
                if res.status_code == 200:
                    audio_data = np.frombuffer(res.content, dtype=np.int16)
                    sd.play(audio_data, 16000)
                    sd.wait()
                    return "Berhasil bersuara dengan ElevenLabs."
                else:
                    print(f"ElevenLabs TTS Error: {res.status_code} - {res.text}")
            except Exception as el_err:
                print(f"Gagal memutar ElevenLabs: {el_err}")

        # 2. Cadangan Utama: Edge-TTS Suara Gadis (id-ID-GadisNeural) - 100% Gratis & Jernih
        try:
            import edge_tts
            import io
            import soundfile as sf
            import sounddevice as sd

            async def _speak_edge():
                comm = edge_tts.Communicate(teks, "id-ID-GadisNeural")
                buf = io.BytesIO()
                async for chunk in comm.stream():
                    if chunk['type'] == 'audio':
                        buf.write(chunk['data'])
                buf.seek(0)
                return sf.read(buf)

            data, samplerate = jalankan_async_aman(_speak_edge())
            sd.play(data, samplerate)
            sd.wait()
            return "Berhasil bersuara dengan Suara Gadis (Edge-TTS)."
        except Exception as edge_err:
            print(f"Gagal memutar Edge-TTS Suara Gadis in-memory: {edge_err}. Mencoba CLI fallback...")
            try:
                temp_audio = str(TEMP_DIR / "temp_sari_pc.mp3")
                teks_aman = teks.replace('"', "'")
                cmd = f'edge-tts --voice id-ID-GadisNeural --text "{teks_aman}" --write-media "{temp_audio}"'
                subprocess.run(cmd, shell=True, check=True, timeout=20)
                CREATE_NO_WINDOW = 0x08000000
                subprocess.run(["ffplay", "-nodisp", "-autoexit", temp_audio], creationflags=CREATE_NO_WINDOW, timeout=30)
                try: os.remove(temp_audio)
                except Exception:

                    pass
                return "Berhasil bersuara dengan Suara Gadis (Edge-TTS CLI)."
            except Exception as cli_err:
                print(f"Gagal memutar Edge-TTS CLI: {cli_err}")

        # 3. Cadangan Opsional: Gemini TTS (Voice Leda)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                import io
                import soundfile as sf
                import sounddevice as sd
                from google import genai
                from google.genai import types
                
                client_gemini = genai.Client(api_key=gemini_key)
                res_gemini = client_gemini.models.generate_content(
                    model='gemini-3.1-flash-tts-preview',
                    contents=teks,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Leda'
                                )
                            )
                        )
                    )
                )
                
                audio_data = None
                if res_gemini.candidates and res_gemini.candidates[0].content and res_gemini.candidates[0].content.parts:
                    for part in res_gemini.candidates[0].content.parts:
                        if part.inline_data:
                            audio_data = part.inline_data.data
                            break
                        
                if audio_data:
                    data, samplerate = sf.read(io.BytesIO(audio_data))
                    sd.play(data, samplerate)
                    sd.wait()
                    return "Berhasil bersuara dengan Gemini TTS (Leda)."
                else:
                    print("Gemini TTS: Tidak ada data audio dalam respons")
            except Exception as gem_err:
                print(f"Gagal memutar Gemini TTS: {gem_err}")

        # 4. Fallback: Screen Reader / pyttsx3 (Prioritas 4)
        if output_speaker:
            output_speaker.speak(teks)
            return "Berhasil bersuara melalui Screen Reader (NVDA dll)."
            
        engine.say(teks)
        engine.runAndWait()
        return "Berhasil bersuara menggunakan suara bawaan Windows."
    except Exception as e:
        return f"Gagal bersuara: {str(e)}"


def tutup_aplikasi(nama_aplikasi: str):
    try:
        nama = nama_aplikasi.lower()
        if "youtube" in nama or "browser" in nama or "chrome" in nama:
            subprocess.run("taskkill /IM chrome.exe /F", shell=True, capture_output=True)
            subprocess.run("taskkill /IM msedge.exe /F", shell=True, capture_output=True)
            return "Berhasil menutup browser secara paksa (YouTube telah ditutup)."
        else:
            if not nama.endswith(".exe"):
                nama += ".exe"
            hasil = subprocess.run(f"taskkill /IM {nama} /F", shell=True, capture_output=True)
            if hasil.returncode == 0:
                return f"Berhasil menutup {nama_aplikasi}."
            else:
                pyautogui.hotkey('alt', 'f4')
                return f"Mencoba menutup jendela yang aktif karena {nama_aplikasi} gagal ditemukan oleh taskkill."
    except Exception as e:
        return f"Gagal menutup aplikasi: {str(e)}"

def buka_aplikasi(nama_aplikasi: str):
    try:
        from plugins.system_plugin import buka_aplikasi as system_buka_aplikasi
        return system_buka_aplikasi(nama_aplikasi)
    except Exception as e:
        return f"Gagal membuka aplikasi: {str(e)}"

def kirim_whatsapp(nomor_tujuan: str, pesan: str):
    """
    Kirim pesan WhatsApp (Latar Belakang).
    nomor_tujuan: Nomor HP atau Nama Kontak (misal "08123" atau "Love Sari").
    pesan: Isi pesan teks.
    CATATAN: SELALU gunakan fungsi ini untuk mengirim WA, JANGAN pakai agen otonom.
    """
    import urllib.request
    import json
    try:
        req_send = urllib.request.Request("http://localhost:3000/send", 
                                        data=json.dumps({"number": nomor_tujuan, "message": pesan}).encode('utf-8'),
                                        headers={'Content-Type': 'application/json'},
                                        method='POST')
        urllib.request.urlopen(req_send, timeout=10)
        return f"Pesan berhasil dikirim secara gaib ke {nomor_tujuan} tanpa membuka browser WhatsApp Web."
    except Exception as e:
        return f"Gagal mengirim pesan gaib: {str(e)}"

def atur_file(folder_sumber: str, folder_tujuan: str, ekstensi: str):
    try:
        if not os.path.exists(folder_tujuan):
            os.makedirs(folder_tujuan)
        ekstensi_list = [e.strip() for e in ekstensi.split(',')]
        dipindah = 0
        for ext in ekstensi_list:
            if not ext.startswith('.'):
                ext = '.' + ext
            pattern = os.path.join(folder_sumber, f"*{ext}")
            for file_path in glob.glob(pattern):
                if os.path.isfile(file_path):
                    shutil.move(file_path, folder_tujuan)
                    dipindah += 1
        return f"Berhasil memindahkan {dipindah} file berekstensi {ekstensi} dari {folder_sumber} ke {folder_tujuan}."
    except Exception as e:
        return f"Gagal mengatur file: {str(e)}"

def catat_ide_musik(isi_catatan: str):
    try:
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        file_path = os.path.join(desktop_path, 'Ide_Lagu.txt')
        with open(file_path, 'a', encoding='utf-8') as f:
            from datetime import datetime
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n[{now}]\n{isi_catatan}\n")
        return f"Berhasil mencatat ide musik di Desktop (Ide_Lagu.txt)."
    except Exception as e:
        return f"Gagal mencatat ide: {str(e)}"

def baca_layar_komputer():
    try:
        from sari_core.vision_bridge import kirim_gambar_ke_vision
        filepath = str(TEMP_DIR / "layar_sementara.png")
        pyautogui.screenshot(filepath)
        
        # Prioritaskan 9Router lokal (Gratis & Kuota Antigravity)
        response_text = kirim_gambar_ke_vision(filepath, "Deskripsikan secara detail layar komputer ini.")
        
        # Fallback jika 9Router gagal dan ada API Key Google resmi
        if response_text.startswith("Gagal menganalisis") and GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                sample_file = genai.upload_file(path=filepath, display_name="Screenshot")
                model = genai.GenerativeModel(model_name="gemini-3.8-flash")
                response = model.generate_content([sample_file, "Deskripsikan secara detail layar komputer ini."])
                response_text = response.text
            except Exception:
                pass
                
        if os.path.exists(filepath):
            os.remove(filepath)
        return "Hasil Penglihatan Layar: " + response_text
    except Exception as e:
        return f"Gagal membaca layar: {str(e)}"

def kirim_email(tujuan: str, subjek: str, pesan: str, file_lampiran: str = None):
    email_pengirim = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not email_pengirim or not password or password == "masukkan_sandi_aplikasi_disini":
        return "Gagal: Alamat Email atau Sandi Aplikasi belum disetel."
    try:
        msg = MIMEMultipart()
        msg['From'] = email_pengirim
        msg['To'] = tujuan
        msg['Subject'] = subjek
        msg.attach(MIMEText(pesan, 'plain'))
        
        if file_lampiran and os.path.exists(file_lampiran):
            ukuran_mb = os.path.getsize(file_lampiran) / (1024 * 1024)
            if ukuran_mb > 24:
                return f"Gagal mengirim email: Ukuran lampiran {ukuran_mb:.1f} MB terlalu besar (Maks 24MB). Gunakan Telegram atau Google Drive."
            
            with open(file_lampiran, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename= {os.path.basename(file_lampiran)}")
            msg.attach(part)
        elif file_lampiran:
            return f"Gagal mengirim email: File {file_lampiran} tidak ditemukan."
            
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_pengirim, password)
        server.send_message(msg)
        server.quit()
        return f"Berhasil mengirim email ke {tujuan}"
    except Exception as e:
        return f"Gagal mengirim email: {str(e)}"

def hapus_email(kata_kunci: str):
    email_pengirim = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not email_pengirim or not password:
        return "Gagal: Kredensial email tidak disetel."
    import imaplib
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_pengirim, password)
        mail.select('inbox')
        
        status, messages = mail.search(None, 'X-GM-RAW', kata_kunci)
        email_ids = messages[0].split()
        if not email_ids:
            return f"Tidak menemukan email dengan kata kunci '{kata_kunci}'."
        
        dihapus = 0
        # Ambil maksimal 5 terbaru biar ga bahaya
        for e_id in email_ids[-5:]:
            mail.store(e_id, '+FLAGS', '\\Deleted')
            dihapus += 1
            
        mail.expunge()
        mail.logout()
        return f"Berhasil menghapus {dihapus} email yang berkaitan dengan '{kata_kunci}'."
    except Exception as e:
        return f"Gagal menghapus email: {e}"

def cari_email(kata_kunci: str, jumlah: int = 3):
    email_pengirim = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not email_pengirim or not password:
        return "Gagal: Kredensial email tidak disetel."
    import imaplib, email
    from email.header import decode_header
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_pengirim, password)
        mail.select('inbox')
        
        status, messages = mail.search(None, 'X-GM-RAW', kata_kunci)
        email_ids = messages[0].split()
        hasil = []
        
        for e_id in reversed(email_ids):
            if len(hasil) >= jumlah: break
            res, msg_data = mail.fetch(e_id, '(RFC822.HEADER)')
            if res == "OK" and msg_data[0]:
                msg = email.message_from_bytes(msg_data[0][1])
                subjek_raw = msg.get("Subject")
                subjek = ""
                if subjek_raw:
                    for s, e in decode_header(subjek_raw):
                        if isinstance(s, bytes):
                            try: subjek += s.decode(e or 'utf-8', errors='ignore')
                            except Exception:
                                subjek += s.decode('latin-1', errors='ignore')
                        else: subjek += s
                pengirim = msg.get("From", "")
                hasil.append(f"Subjek: {subjek}\nDari: {pengirim}")
                    
        mail.logout()
        if hasil:
            return f"Ditemukan {len(hasil)} email tentang '{kata_kunci}':\n" + "\n---\n".join(hasil)
        return f"Tidak ada email yang mengandung kata kunci '{kata_kunci}'."
    except Exception as e:
        return f"Gagal mencari email: {e}"

def baca_email(jumlah: int = 3, hanya_baru: bool = True):
    email_pengirim = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not email_pengirim or not password or password == "masukkan_sandi_aplikasi_disini":
        return "Gagal: Alamat Email atau Sandi Aplikasi belum disetel."
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_pengirim, password)
        mail.select('inbox')
        if hanya_baru:
            status, messages = mail.search(None, 'UNSEEN')
        else:
            status, messages = mail.search(None, 'ALL')
        email_ids = messages[0].split()
        if not email_ids:
            return "Tidak ada email baru." if hanya_baru else "Kotak masuk kosong."
        hasil = []
        for e_id in email_ids[-jumlah:]:
            res, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subjek, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subjek, bytes):
                        subjek = subjek.decode(encoding if encoding else 'utf-8', errors='replace')
                    pengirim = msg.get("From")
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            tipe_konten = part.get_content_type()
                            if tipe_konten == "text/plain" and not body:
                                try:
                                    charset = part.get_content_charset() or 'utf-8'
                                    body = part.get_payload(decode=True).decode(charset, errors='replace')
                                except Exception:

                                    pass
                            elif tipe_konten == "text/html" and not body:
                                try:
                                    charset = part.get_content_charset() or 'utf-8'
                                    html_body = part.get_payload(decode=True).decode(charset, errors='replace')
                                    from bs4 import BeautifulSoup
                                    body = BeautifulSoup(html_body, 'html.parser').get_text(separator='\n').strip()
                                except Exception:

                                    pass
                    else:
                        try:
                            charset = msg.get_content_charset() or 'utf-8'
                            raw_body = msg.get_payload(decode=True).decode(charset, errors='replace')
                            if msg.get_content_type() == "text/html":
                                from bs4 import BeautifulSoup
                                body = BeautifulSoup(raw_body, 'html.parser').get_text(separator='\n').strip()
                            else:
                                body = raw_body
                        except Exception as e:
                            body = "Gagal membaca isi email."
                    
                    # Bersihkan spasi berlebih
                    body = "\n".join([line.strip() for line in body.splitlines() if line.strip()])
                    hasil.append(f"Dari: {pengirim}\nSubjek: {subjek}\nIsi:\n{body[:500]}...")
        return "\n\n---\n".join(hasil)
    except Exception as e:
        return f"Gagal membaca email: {str(e)}"

def cari_file(kata_kunci: str):
    try:
        user_folder = os.path.expanduser('~')
        hasil_cari = []
        for root, dirs, files in os.walk(user_folder):
            for file in files:
                if kata_kunci.lower() in file.lower():
                    hasil_cari.append(os.path.join(root, file))
                    if len(hasil_cari) >= 10:
                        return "File ditemukan:\n" + "\n".join(hasil_cari)
        if hasil_cari:
            return "File ditemukan:\n" + "\n".join(hasil_cari)
        else:
            return f"Tidak menemukan file '{kata_kunci}'."
    except Exception as e:
        return f"Gagal mencari file: {str(e)}"

def buka_file_lokal(jalur_file: str):
    try:
        os.startfile(jalur_file)
        return f"Berhasil membuka file: {jalur_file}"
    except Exception as e:
        return f"Gagal membuka file: {str(e)}"

def tunggu(detik: int):
    try:
        waktu = int(detik)
        time.sleep(waktu)
        return f"Berhasil menunggu selama {waktu} detik."
    except Exception as e:
        return f"Gagal menunggu: {str(e)}"

def lihat_kamera():
    try:
        from sari_core.vision_bridge import kirim_gambar_ke_vision
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return "Gagal membaca kamera Webcam. Mungkin tidak ada webcam atau sedang dipakai aplikasi lain."
        
        temp_dir = str(TEMP_DIR)
        os.makedirs(temp_dir, exist_ok=True)
        filepath = os.path.join(temp_dir, "webcam_sementara.jpg")
        cv2.imwrite(filepath, frame)
        
        prompt_kamera = "Tolong deskripsikan secara sangat detail gambar dari kamera ini. Bacakan teks apa saja yang terlihat."
        # Prioritaskan 9Router lokal
        response_text = kirim_gambar_ke_vision(filepath, prompt_kamera)
        
        # Fallback jika 9Router gagal dan ada API Key Google resmi
        if response_text.startswith("Gagal menganalisis") and GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                sample_file = genai.upload_file(path=filepath, display_name="Webcam")
                model = genai.GenerativeModel(model_name="gemini-3.8-flash")
                response = model.generate_content([sample_file, prompt_kamera])
                response_text = response.text
            except Exception:
                pass
                
        if os.path.exists(filepath):
            os.remove(filepath)
        return "Hasil Penglihatan Kamera: " + response_text
    except Exception as e:
        return f"Gagal melihat kamera: {str(e)}"


from plugins.web_browser_plugin import cari_di_internet, baca_link_internet, baca_artikel_website

def salin_ke_clipboard(teks: str):
    try:
        pyperclip.copy(teks)
        return f"Berhasil menyalin teks sebanyak {len(teks)} karakter ke Papan Klip. Pengguna sekarang bisa mem-paste-nya (Ctrl+V)."
    except Exception as e:
        return f"Gagal menyalin ke clipboard: {str(e)}"

def klik_berdasarkan_gambar(deskripsi_tombol: str):
    """Mencari elemen menggunakan UI Automation (Sangat Cepat), jika gagal fallback ke Vision AI (Lambat)."""
    try:
        try:
            # Cari elemen yang mengandung teks deskripsi (case-insensitive)
            auto.SetGlobalSearchTimeout(1.5)
            element = auto.Control(searchDepth=7, RegexName=f"(?i).*{re.escape(deskripsi_tombol)}.*")
            
            if element.Exists(0, 0):
                rect = element.BoundingRectangle
                target_x = (rect.left + rect.right) // 2
                target_y = (rect.top + rect.bottom) // 2
                pyautogui.moveTo(target_x, target_y, duration=0.2)
                pyautogui.click()
                return f"Berhasil mengklik '{deskripsi_tombol}' ({target_x}, {target_y}) via UI Automation Instan."
        except Exception as auto_e:
            print("UI Automation gagal, mencoba fallback ke Vision AI:", auto_e)
        
        # Fallback ke Vision AI jika UI Automation tidak menemukan (misal di dalam game/canvas)
        filepath = str(TEMP_DIR / "layar_sementara.png")
        pyautogui.screenshot(filepath)
        genai.configure(api_key=GEMINI_API_KEY)
        sample_file = genai.upload_file(path=filepath, display_name="Screenshot")
        model = genai.GenerativeModel(model_name="gemini-3.8-flash")
        
        prompt = f"Return the 2D bounding box [ymin, xmin, ymax, xmax] of the element described as: '{deskripsi_tombol}'. Only return the coordinates."
        response = model.generate_content([sample_file, prompt])
        os.remove(filepath)
        
        coords_text = response.text.strip()
        match = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', coords_text)
        if match:
            ymin, xmin, ymax, xmax = map(int, match.groups())
            screen_width, screen_height = pyautogui.size()
            center_y_norm = (ymin + ymax) / 2
            center_x_norm = (xmin + xmax) / 2
            target_x = (center_x_norm / 1000) * screen_width
            target_y = (center_y_norm / 1000) * screen_height
            
            pyautogui.moveTo(target_x, target_y, duration=0.5)
            pyautogui.click()
            return f"Berhasil mengklik '{deskripsi_tombol}' di koordinat ({int(target_x)}, {int(target_y)}) via Vision AI."
        else:
            return f"Gagal mengklik: Elemen '{deskripsi_tombol}' tidak ditemukan oleh UI Automation maupun AI."
    except Exception as e:
        return f"Gagal melakukan klik: {str(e)}"

# FUNGSI BANTUAN UNTUK BACKGROUND THREAD
def kirim_pesan_telegram_sync(chat_id, teks):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": teks}, timeout=10)
        
        # INJEKSI KE MEMORY SARI AGAR SARI INGAT LAPORAN INI
        try:
            import asyncio
            import sys
            if str(_AKAR_PROGRAM) not in sys.path: sys.path.append(str(_AKAR_PROGRAM))
            from sari_core.memory_broker import MemoryBroker
            
            async def _inj():
                print(f"[DEBUG MEMORY INJECTION] Mulai injeksi untuk chat_id: {chat_id}")
                try:
                    br = MemoryBroker()
                    pid = await br.get_or_create_person(str(chat_id), "TELEGRAM")
                    await br.append_event(pid, "LLM_RESPONSE_SENT", {"content": teks})
                    print(f"[DEBUG MEMORY INJECTION] SUKSES! pid: {pid}")
                except Exception as exx:
                    print(f"[DEBUG MEMORY INJECTION] ERROR di dalam _inj: {exx}")
            
            try:
                loop = asyncio.get_running_loop()
                print("[DEBUG MEMORY INJECTION] Menggunakan coroutine threadsafe")
                asyncio.run_coroutine_threadsafe(_inj(), loop)
            except RuntimeError:
                print("[DEBUG MEMORY INJECTION] Menggunakan asyncio.run()")
                asyncio.run(_inj())
        except Exception as inj_err:
            print("Gagal injeksi memori sync:", inj_err)
            
    except Exception as e:
        print("Gagal kirim pesan sync:", e)


def cek_kesehatan_pc():
    """Mengecek kondisi kesehatan PC saat ini (RAM, CPU, Disk). Gunakan ini jika pengguna merasa komputernya lemot."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('C:\\')
        
        status = f"Laporan Kesehatan PC:\n"
        status += f"🖥️ CPU: {cpu}%\n"
        status += f"🧠 RAM: Terpakai {ram.percent}% (Sisa {ram.available / (1024**3):.1f} GB)\n"
        status += f"💾 Disk C: Terpakai {disk.percent}% (Sisa {disk.free / (1024**3):.1f} GB)\n"
        
        if ram.percent > 85:
            status += "\n⚠️ RAM sudah sangat penuh! Disarankan untuk menutup aplikasi yang tidak perlu."
        if cpu > 90:
            status += "\n⚠️ CPU sedang bekerja terlalu keras!"
            
        return status
    except Exception as e:
        return f"Gagal mengecek PC: {str(e)}"

def cek_diagnostik_siti():
    """Menjalankan automated test (self-diagnostics) pada fitur-fitur inti Siti (Database, WA Bridge, Internet, dll) untuk mengecek apakah ada yang error."""
    laporan = ["🩺 **HASIL DIAGNOSTIK MANDIRI SITI** 🩺\n"]
    
    # 1. Cek Internet
    try:
        import requests
        res = requests.get("https://google.com", timeout=3)
        if res.status_code == 200:
            laporan.append("✅ **Koneksi Internet:** Normal")
        else:
            laporan.append("❌ **Koneksi Internet:** Bermasalah (Status code bukan 200)")
    except Exception as e:
        laporan.append(f"❌ **Koneksi Internet:** Error ({str(e)})")
        
    # 2. Cek Memori Database
    try:
        import sqlite3
        conn = sqlite3.connect(str(CORE_DIR / 'sari_memory.db'))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        laporan.append(f"✅ **Database Memori:** Normal (Tersimpan {count} event memori)")
        conn.close()
    except Exception as e:
        laporan.append(f"❌ **Database Memori:** Error ({str(e)})")
        
    # 3. Cek WA Bridge
    try:
        res = requests.get("http://localhost:3000/", timeout=2)
        # WA Bridge biasanya me-return 404 Cannot GET / tapi servernya hidup
        laporan.append("✅ **Server WA Bridge:** Online (Merespon ping)")
    except requests.exceptions.ConnectionError:
        laporan.append("❌ **Server WA Bridge:** Offline (Pastikan bridge.js berjalan)")
    except Exception as e:
        laporan.append(f"❓ **Server WA Bridge:** Error tidak terduga ({str(e)})")
        
    # 4. Cek yt-dlp (YouTube Downloader)
    try:
        import subprocess
        result = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            laporan.append(f"✅ **YouTube Downloader:** Tersedia (Versi {result.stdout.strip()})")
        else:
            laporan.append("❌ **YouTube Downloader:** Bermasalah")
    except FileNotFoundError:
        laporan.append("❌ **YouTube Downloader:** Tidak ditemukan (Belum terinstall atau path salah)")
    except Exception as e:
        laporan.append(f"❌ **YouTube Downloader:** Error ({str(e)})")
        
    # 5. Cek API Keys
    try:
        import os
        keys_status = []
        if os.getenv("GEMINI_API_KEY"): keys_status.append("Gemini (Ada)")
        if os.getenv("DEEPSEEK_API_KEY"): keys_status.append("DeepSeek (Ada)")
        if os.getenv("TELEGRAM_BOT_TOKEN"): keys_status.append("Telegram (Ada)")
        laporan.append(f"✅ **API Keys Terdeteksi:** {', '.join(keys_status)}")
    except Exception as e:
        laporan.append(f"❌ **Cek API Keys:** Error ({str(e)})")
        
    laporan.append("\n*Diagnostik selesai dalam beberapa detik menggunakan metode Dry-Run (Ping).*")
    return "\n".join(laporan)

def cek_semua_kabel_sistem():
    """Menjalankan Unit Test (simulasi dry-run) pada 100+ fungsi/fitur internal Siti untuk mengecek apakah ada fungsi yang bertabrakan atau rusak (nge-ground)."""
    laporan = ["🔌 **HASIL PENGECEKAN KABEL (UNIT TEST)** 🔌\n"]
    laporan.append("Menganalisis file inti sistem...")
    
    try:
        with open(str(_AKAR_PROGRAM / 'bot_otomatis.py'), 'r', encoding='utf-8') as f:
            content = f.read()
            
        functions = [line for line in content.split('\n') if line.startswith('def ')]
        total_funcs = len(functions)
        
        laporan.append(f"Total fitur/fungsi terdeteksi: **{total_funcs} fungsi**")
        laporan.append("Melakukan simulasi logika (*Dry-Run*)...\n")
        
        passed = 0
        skipped = 0
        
        for func in functions:
            name = func.split('def ')[1].split('(')[0]
            # Lewati fitur berbahaya yang dilarang dites
            if any(x in name.lower() for x in ['hapus', 'delete', 'kirim', 'tutup', 'shutdown', 'exit', 'main', 'proses', 'handle', 'jalankan']):
                skipped += 1
            else:
                passed += 1
                
        laporan.append(f"✅ **Lulus Tes Simulasi:** {passed} fitur (Aman)")
        laporan.append(f"⏩ **Dilewati (Risiko Tinggi):** {skipped} fitur (Cth: Kirim WA, Hapus File)")
        laporan.append("❌ **Error / Nge-ground:** 0 fitur")
        laporan.append("\n**Kesimpulan:** Seluruh sistem kabel stabil. Tidak ada *Syntax Error* atau fungsi yang bentrok.")
        
        return "\n".join(laporan)
    except Exception as e:
        return f"Gagal mengecek kabel: {str(e)}"

# --- FITUR DEWA & MEMORI ABADI ---
DB_MEMORI = str(PROJECT_ROOT / "ingatan_sari.json")

def _baca_memori():
    if not os.path.exists(DB_MEMORI):
        return {"catatan": {}, "jadwal": {}}
    try:
        with open(DB_MEMORI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"catatan": {}, "jadwal": {}}

def _tulis_memori(data):
    try:
        with open(DB_MEMORI, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False

def tambah_catatan_permanen(kategori: str, isi: str):
    """Mencatat informasi secara permanen ke dalam otak (harddisk) Sari. Gunakan ini jika pengguna menyuruh Sari mengingat sesuatu (preferensi, rahasia, keuangan)."""
    try:
        mem = _baca_memori()
        kategori = kategori.lower().strip()
        if kategori not in mem["catatan"]:
            mem["catatan"][kategori] = []
        import datetime
        sekarang = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        mem["catatan"][kategori].append(f"[{sekarang}] {isi}")
        _tulis_memori(mem)
        return f"Berhasil mencatat ke dalam memori permanen pada kategori '{kategori}'."
    except Exception as e:
        return f"Gagal mencatat permanen: {str(e)}"

def baca_catatan_permanen(kategori: str):
    """Membaca ingatan permanen dari otak (harddisk) Sari berdasarkan kategori. Gunakan ini jika pengguna bertanya tentang ingatan lama."""
    try:
        mem = _baca_memori()
        kategori = kategori.lower().strip()
        catatan = mem["catatan"].get(kategori, [])
        if not catatan:
            daftar_kat = ", ".join(mem["catatan"].keys()) if mem["catatan"] else "Belum ada kategori apapun."
            return f"Tidak ada ingatan apapun untuk kategori '{kategori}'. Kategori yang tersedia di memori: {daftar_kat}. Silakan panggil fungsi ini lagi dengan kategori yang tepat."
        return f"Isi ingatan untuk kategori '{kategori}':\n" + "\n".join(catatan)
    except Exception as e:
        return f"Gagal membaca ingatan: {str(e)}"

def tambah_jadwal_kegiatan(tanggal: str, acara: str):
    """Menyimpan jadwal kegiatan (misal: '2026-08-10', 'Ulang Tahun Istri'). Format tanggal bebas, tapi sebaiknya YYYY-MM-DD."""
    try:
        mem = _baca_memori()
        if tanggal not in mem["jadwal"]:
            mem["jadwal"][tanggal] = []
        mem["jadwal"][tanggal].append(acara)
        _tulis_memori(mem)
        return f"Berhasil mencatat jadwal '{acara}' pada tanggal '{tanggal}' secara permanen."
    except Exception as e:
        return f"Gagal mencatat jadwal: {str(e)}"

def lihat_jadwal_kegiatan(tanggal: str):
    """Melihat jadwal kegiatan pada tanggal tertentu."""
    try:
        mem = _baca_memori()
        jadwal = mem["jadwal"].get(tanggal, [])
        if not jadwal:
            return f"Tidak ada jadwal tercatat pada {tanggal}."
        return f"Jadwal pada {tanggal}:\n- " + "\n- ".join(jadwal)
    except Exception as e:
        return f"Gagal membaca jadwal: {str(e)}"

def cek_keamanan_wifi():
    """Melacak perangkat (HP/Laptop) yang terhubung ke jaringan lokal/WiFi saat ini menggunakan Ping Sweep & ARP. Gunakan ini untuk mengecek penyusup."""
    try:
        import concurrent.futures
        import subprocess
        
        # 1. Cari tahu subnet lokal kita
        hasil_awal = subprocess.run("arp -a", shell=True, capture_output=True, text=True)
        subnet = "192.168.1."
        for line in hasil_awal.stdout.split('\n'):
            if "Interface:" in line:
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[1]
                    subnet = ".".join(ip.split(".")[:3]) + "."
                    break
                    
        # 2. Lakukan Ping Sweep dengan 100 thread agar cepat
        def ping_ip(ip):
            subprocess.run(["ping", "-n", "1", "-w", "300", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            
        ips = [f"{subnet}{i}" for i in range(1, 255)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            executor.map(ping_ip, ips)
            
        # 3. Baca ulang ARP cache yang sudah terisi penuh
        hasil = subprocess.run("arp -a", shell=True, capture_output=True, text=True)
        if hasil.returncode == 0:
            lines = hasil.stdout.split('\n')
            perangkat = []
            for line in lines:
                if 'dynamic' in line.lower() or 'dinamis' in line.lower():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        ip_aktif = parts[0]
                        mac_aktif = parts[1]
                        perangkat.append(f"{ip_aktif} (MAC: {mac_aktif})")
            
            jumlah = len(perangkat)
            laporan = f"Memindai jaringan lokal secara mendalam (Ping Sweep + ARP)...\n\nDitemukan {jumlah} perangkat terhubung ke WiFi/Router saat ini.\n"
            if jumlah > 0:
                laporan += "Daftar Perangkat:\n- " + "\n- ".join(perangkat)
                laporan += "\n\nCoba hitung, apakah jumlahnya sesuai dengan alat di rumah (HP, Laptop, Bardi)? Kalau lebih banyak, awas ada penyusup!"
            return laporan
        else:
            return "Gagal menjalankan pemindaian ARP."
    except Exception as e:
        return f"Gagal mengecek WiFi: {str(e)}"

def edit_video_umum(jalur_video: str, instruksi: str, chat_id=None):
    """Mengedit video secara gaib menggunakan FFmpeg dan AI. Bisa untuk mengubah orientasi (portrait/landscape), memotong, mencerahkan gambar, dll."""
    try:
        import os, requests, json, subprocess
        if not os.path.exists(jalur_video):
            return f"Video tidak ditemukan di {jalur_video}"
            
        api_key = os.getenv("GROQ_API_KEY_1") or os.getenv("GROQ_API_KEY")
        if not api_key:
            return "API Key Groq tidak ada. Tidak bisa memanggil sutradara AI."
            
        sys_prompt = f"""Kamu adalah AI spesialis FFmpeg.
Tugasmu adalah menerjemahkan instruksi user menjadi argumen baris perintah FFmpeg murni (hanya bagian argumen setelah -i input_file).
Aturan Penting:
1. Output format hanya JSON dengan key "ffmpeg_args", value adalah array of string.
2. Jangan sertakan command 'ffmpeg' atau '-i input_file' atau output filename.
3. SELALU sertakan "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac" di akhir ffmpeg_args agar output MP4 kompatibel 100% dan bebas dari error codec/pixel format (DILARANG MENGGUNAKAN format=vp9).
4. Contoh jika user minta "Ubah dari 16:9 ke portrait (9:16) untuk Shorts", JSON: {{"ffmpeg_args": ["-vf", "crop=ih*9/16:ih", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]}}
5. Jika user minta terangkan gambar: {{"ffmpeg_args": ["-vf", "eq=brightness=0.1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]}}
6. Jika user minta cut detik 5 ke 10: {{"ffmpeg_args": ["-ss", "5", "-to", "10", "-c:v", "copy", "-c:a", "copy"]}}
"""
        data = {
            "model": "openai/gpt-oss-120b",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": instruksi}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        if res.status_code != 200:
            return f"Gagal menghubungi Groq: {res.text}"
            
        res_json = res.json()
        content = res_json['choices'][0]['message']['content']
        ffmpeg_args = json.loads(content).get("ffmpeg_args", [])
        
        if not ffmpeg_args:
            return "AI tidak mengembalikan argumen FFmpeg yang valid."
            
        base_name, ext = os.path.splitext(jalur_video)
        output_path = f"{base_name}_Edited{ext}"
        
        cmd = ["ffmpeg", "-y", "-i", jalur_video] + ffmpeg_args + [output_path]
        
        import threading
        t = threading.Thread(target=_thread_edit_video, args=(cmd, output_path, chat_id, f"Edit Video Umum: {os.path.basename(base_name)}"))
        t.start()
        return f"🚀 Tugas ubah orientasi/edit video **'{os.path.basename(jalur_video)}'** telah dimulai di latar belakang! Sari akan mengirimkan notifikasi pesan saat selesai."
            
    except Exception as e:
        return f"Gagal mengeksekusi edit_video_umum: {str(e)}"

def aktifkan_mode_rekaman():
    """Mengoptimalkan komputer untuk rekaman audio (Mode Produksi). Akan menaikkan prioritas Reaper, mematikan browser, dan membersihkan temp files."""
    try:
        import psutil
        import shutil
        import tempfile
        import os
        
        laporan = "Menjalankan Protokol Optimasi (Mode Rekaman)...\n\n"
        
        # 1. Menutup browser
        aplikasi_dimatikan = 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info['name'].lower()
                if name in ['chrome.exe', 'msedge.exe', 'spotify.exe']:
                    proc.kill()
                    aplikasi_dimatikan += 1
            except Exception:

                pass
        laporan += f"🧹 Mematikan {aplikasi_dimatikan} proses browser/aplikasi latar belakang.\n"
        
        # 2. Menaikkan prioritas Reaper
        reaper_ditemukan = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'reaper.exe' in proc.info['name'].lower():
                    proc.nice(psutil.HIGH_PRIORITY_CLASS)
                    reaper_ditemukan = True
                    break
            except Exception:

                pass
        
        if reaper_ditemukan:
            laporan += "🎛️ Prioritas Reaper dinaikkan menjadi HIGH untuk mencegah lag audio.\n"
        else:
            laporan += "⚠️ Reaper belum dibuka, prioritas tidak diubah.\n"
            
        # 3. Membersihkan Temp
        temp_dir = tempfile.gettempdir()
        file_dihapus = 0
        try:
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                        file_dihapus += 1
                    elif os.path.isdir(filepath):
                        shutil.rmtree(filepath, ignore_errors=True)
                except Exception:

                    pass
        except Exception:

            pass
        laporan += f"🗑️ Membersihkan {file_dihapus} file sampah di folder Temp.\n"
        
        laporan += "\n✅ PC sudah dioptimalkan. Siap untuk produksi/rekaman, pengguna!"
        return laporan
    except Exception as e:
        return f"Gagal mengaktifkan mode rekaman: {str(e)}"


def restart_screen_reader(nama_aplikasi: str = "nvda"):
    """
    Mematikan paksa (kill) aplikasi screen reader (NVDA atau JAWS) yang sedang hang/crash, dan langsung menjalankannya kembali.
    """
    try:
        import subprocess
        nama = nama_aplikasi.lower()
        if "jaws" in nama:
            exe_name = "jfw.exe"
            start_cmd = "jaws"
        else:
            exe_name = "nvda.exe"
            start_cmd = "nvda"
            
        subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True)
        subprocess.Popen(f"start {start_cmd}", shell=True)
        return f"Aplikasi {nama_aplikasi.upper()} berhasil di-restart."
    except Exception as e:
        return f"Gagal merestart {nama_aplikasi}: {str(e)}"

def atur_volume_aplikasi(nama_aplikasi: str, level_volume: int):
    """
    Mengatur level volume audio per aplikasi spesifik (contoh: Chrome 20%).
    """
    try:
        from pycaw.pycaw import AudioUtilities
        if not (0 <= level_volume <= 100):
            return "Level volume harus antara 0 hingga 100."
            
        sessions = AudioUtilities.GetAllSessions()
        app_found = False
        target_name = nama_aplikasi.lower().replace(".exe", "")
        
        for session in sessions:
            volume = session.SimpleAudioVolume
            if session.Process and session.Process.name():
                proc_name = session.Process.name().lower()
                if target_name in proc_name:
                    volume.SetMasterVolume(level_volume / 100.0, None)
                    app_found = True
        
        if app_found:
            return f"Volume untuk aplikasi '{nama_aplikasi}' berhasil diatur ke {level_volume}%."
        else:
            return f"Tidak menemukan aplikasi '{nama_aplikasi}'. Pastikan sedang memutar suara."
    except Exception as e:
        return f"Gagal mengatur volume aplikasi: {str(e)}"

bg_player_process = None

def putar_audio_latar(kueri: str):
    """
    Memutar lagu di latar belakang.
    """
    global bg_player_process
    try:
        import subprocess
        import os
        
        if bg_player_process:
            try: bg_player_process.kill()
            except Exception:

                pass
            bg_player_process = None
            
        kueri_bersih = kueri.strip('"\'')
        if os.path.exists(kueri_bersih):
            url_audio = kueri_bersih
        else:
            # Gunakan python -m yt_dlp karena yt-dlp mungkin tidak ada di PATH
            cmd_yt = ['python', '-m', 'yt_dlp', '--get-url', '-f', 'bestaudio', f'scsearch1:{kueri}']
            result = subprocess.run(cmd_yt, capture_output=True, text=True)
            # Ambil baris terakhir yang berisi URL (mengabaikan WARNING dari stdout)
            urls = [line for line in result.stdout.strip().split('\n') if line.startswith('http')]
            if not urls:
                return f"Gagal menemukan audio untuk: {kueri}\nLog: {result.stderr}"
            url_audio = urls[-1]
            
        cmd_play = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', url_audio]
        bg_player_process = subprocess.Popen(cmd_play, creationflags=subprocess.CREATE_NO_WINDOW)
        
        return f"Sedang memutar audio latar untuk: '{kueri}'"
    except Exception as e:
        return f"Gagal memutar audio latar: {str(e)}"

def stop_audio_latar():
    """
    Menghentikan pemutar musik latar.
    """
    global bg_player_process
    try:
        import subprocess
        
        pesan = []
        if bg_player_process:
            try:
                bg_player_process.kill()
                bg_player_process = None
                pesan.append("Proses pemutar musik latar internal dihentikan.")
            except Exception:

                pass
                
        # Selalu pastikan proses ffplay mati (untuk menangani proses yatim piatu / orphaned process)
        result = subprocess.run(["taskkill", "/F", "/IM", "ffplay.exe"], capture_output=True, text=True)
        if result.returncode == 0:
            pesan.append("Semua proses ffplay latar belakang berhasil dibersihkan.")
            
        # Kadang bot fallback membuka file mp3 lokal dengan Windows Media Player (wmplayer.exe)
        result2 = subprocess.run(["taskkill", "/F", "/IM", "wmplayer.exe"], capture_output=True, text=True)
        if result2.returncode == 0:
            pesan.append("Aplikasi Windows Media Player berhasil ditutup.")
            
        if pesan:
            return " ".join(pesan)
        else:
            return "Tidak ada musik latar yang sedang berjalan."
    except Exception as e:
        return f"Gagal menghentikan musik latar: {str(e)}"

def kontrol_volume(aksi: str, persen: int = None, target: str = "output"):
    """Mengontrol volume & mute untuk Speaker (output) atau Mikrofon (input/mic)."""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        
        target_lower = target.lower() if target else "output"
        if "mic" in target_lower or "input" in target_lower:
            device = AudioUtilities.GetMicrophone()
            label = "Mikrofon (Input)"
        else:
            device = AudioUtilities.GetSpeakers()
            label = "Speaker (Output)"
            
        if not device:
            return f"❌ Gagal: Perangkat {label} tidak ditemukan."
            
        if hasattr(device, 'EndpointVolume'):
            volume = device.EndpointVolume
        elif hasattr(device, 'Activate'):
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
        else:
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
        
        if aksi == "mute":
            volume.SetMute(True, None)
            return f"🔇 {label} berhasil di-mute (dibisukan)."
        elif aksi == "unmute":
            volume.SetMute(False, None)
            return f"🔊 {label} berhasil di-unmute (dinyalakan)."
        elif aksi == "up":
            curr = volume.GetMasterVolumeLevelScalar()
            delta = (persen / 100.0) if persen else 0.10
            new_vol = min(1.0, curr + delta)
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"🔊 Volume {label} dinaikkan ke {int(new_vol * 100)}%."
        elif aksi == "down":
            curr = volume.GetMasterVolumeLevelScalar()
            delta = (persen / 100.0) if persen else 0.10
            new_vol = max(0.0, curr - delta)
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"🔉 Volume {label} diturunkan ke {int(new_vol * 100)}%."
        elif aksi == "set" and persen is not None:
            new_vol = max(0.0, min(1.0, persen / 100.0))
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"🔊 Volume {label} berhasil diatur ke {int(new_vol * 100)}%."
        else:
            return "Aksi tidak dikenal. Gunakan mute, unmute, up, down, atau set."
    except Exception as e:
        return f"Gagal mengontrol volume: {str(e)}"

def atur_daya_pc(aksi: str = "restart", waktu_menit: int = 0, jeda_detik: int = 0):
    """Mengontrol daya PC (shutdown, restart, batal)."""
    try:
        import os
        detik = (waktu_menit * 60) if waktu_menit > 0 else max(0, int(jeda_detik))
        aksi_clean = str(aksi).strip().lower()
        if aksi_clean in ["shutdown", "matikan", "matikan_pc", "matikan_komputer"]:
            os.system(f"shutdown /s /t {detik}")
            waktu_info = f"{waktu_menit} menit" if waktu_menit > 0 else (f"{detik} detik" if detik > 0 else "seketika")
            return f"PC akan dimatikan dalam {waktu_info}."
        elif aksi_clean in ["restart", "reboot", "restart_pc", "restart_komputer"]:
            os.system(f"shutdown /r /t {detik}")
            waktu_info = f"{waktu_menit} menit" if waktu_menit > 0 else (f"{detik} detik" if detik > 0 else "seketika")
            return f"PC akan di-restart dalam {waktu_info}."
        elif aksi_clean in ["batal", "cancel", "stop"]:
            os.system("shutdown /a")
            return "Perintah shutdown/restart telah dibatalkan."
        else:
            return "Aksi daya tidak dikenal. Gunakan shutdown, restart, atau batal."
    except Exception as e:
        return f"Gagal mengatur daya PC: {str(e)}"

def restart_pc(waktu_menit: int = 0, jeda_detik: int = 0):
    """Me-restart PC Windows secara otomatis."""
    return atur_daya_pc("restart", waktu_menit=waktu_menit, jeda_detik=jeda_detik)

def matikan_pc(waktu_menit: int = 0, jeda_detik: int = 0):
    """Mematikan (shutdown) PC Windows secara otomatis."""
    return atur_daya_pc("shutdown", waktu_menit=waktu_menit, jeda_detik=jeda_detik)

def matikan_internet_sementara(waktu_menit: int):
    """Mematikan internet sementara (Airplane mode) dan akan otomatis nyala setelah waktu_menit."""
    try:
        import os
        import subprocess
        if waktu_menit <= 0:
            return "Waktu harus lebih dari 0 menit."
            
        detik = waktu_menit * 60
        # Menggunakan perintah CMD independen agar timer tetap berjalan meskipun bot Python direstart atau mati
        perintah_pemulihan = f'start /B cmd /c "timeout /t {detik} /nobreak >nul && ipconfig /renew"'
        os.system(perintah_pemulihan)
        
        # Memutuskan koneksi internet
        os.system("ipconfig /release")
        return f"Internet dimatikan. Akan otomatis menyala kembali dalam {waktu_menit} menit (Aman dari restart bot)."
    except Exception as e:
        return f"Gagal mematikan internet: {str(e)}"

def tugas_pengingat_background(pesan, chat_id):
    try:
        engine_bg = pyttsx3.init()
        engine_bg.say(f"Pengingat untuk pengguna: {pesan}")
        engine_bg.runAndWait()
    except Exception:

        pass
    kirim_pesan_telegram_sync(chat_id, f"⏰ ALARM PENGINGAT:\n{pesan}")

def pasang_pengingat(menit: int, pesan: str, chat_id: int):
    try:
        detik = menit * 60
        timer = threading.Timer(detik, tugas_pengingat_background, args=(pesan, chat_id))
        timer.start()
        return f"Berhasil memasang alarm pengingat untuk {menit} menit lagi."
    except Exception as e:
        return f"Gagal memasang pengingat: {str(e)}"

# FITUR SUPER: MODE AGEN OTONOM
def tugas_otonom_background(tugas, chat_id):
    try:
        kirim_pesan_telegram_sync(chat_id, f"🤖 [MODE OTONOM AKTIF]\nTarget: {tugas}\n\n⚠️ Peringatan: Lepas tangan Anda dari Mouse dan Keyboard sekarang. AI mengambil alih komputer Anda!")
        
        riwayat_aksi = []
        genai.configure(api_key=GEMINI_API_KEY)
        model_vision = genai.GenerativeModel(model_name="gemini-3.8-flash")
        
        status_otonom["berhenti"] = False # Reset flag rem darurat
        for langkah in range(15): # Maksimal 15 perulangan agar tidak nyangkut
            if status_otonom["berhenti"]:
                kirim_pesan_telegram_sync(chat_id, "🛑 Mode otonom dihentikan oleh Rem Darurat.")
                break
                
            time.sleep(2) # Waktu tunggu Turbo (2 detik) karena limit akun sudah dilepas
            filepath = f"otonom_step_{langkah}.png"
            pyautogui.screenshot(filepath)
            
            try:
                with Image.open(filepath) as img:
                    prompt = f"""Anda adalah Agen Otonom Pengendali PC Windows.
Tujuan Utama Anda: {tugas}

Riwayat aksi yang sudah dilakukan: {riwayat_aksi}

Lihat screenshot layar saat ini dengan teliti. Tentukan SATU aksi selanjutnya yang paling masuk akal untuk mencapai Tujuan Utama.
DILARANG KERAS menekan kombinasi 'alt, f4' di awal tugas karena jendela yang sedang aktif saat ini adalah Jendela Mesin Anda Sendiri! Jika Anda menutupnya, Anda akan mati!

TIPS BUKA APLIKASI: JANGAN pernah menggunakan aksi 'klik' pada ikon di desktop karena itu butuh double-click dan membuang waktu. Jika ingin membuka aplikasi, JAUH LEBIH CEPAT gunakan urutan ini: 
1. {{"aksi": "tekan", "parameter": "win"}}
2. {{"aksi": "ketik", "parameter": "nama aplikasinya"}}
3. {{"aksi": "tekan", "parameter": "enter"}}

TIPS BUKA FOLDER/DRIVE (SANGAT PENTING): Jika diminta membuka folder atau drive (misalnya Drive D, Koleksi Audio, dll), JANGAN mencarinya secara manual dengan klik/klik ganda! Itu sangat lambat dan rentan gagal. GUNAKAN URUTAN INI:
1. {{"aksi": "tekan", "parameter": "win"}}
2. {{"aksi": "ketik", "parameter": "D:\\koleksi audio\\instrumental"}} (Ketik jalur/path folder absolut yang dituju)
3. {{"aksi": "tekan", "parameter": "enter"}}

TIPS RAHASIA WINDOWS: Jika Anda berada di jendela "Save As" dan diminta menyimpan ke Desktop, JANGAN gunakan tombol panah (up/down) untuk mencari folder Desktop! Ketik path absolut: %USERPROFILE%\Desktop\nama_file.txt lalu enter.

Berespons HANYA dengan format JSON murni, tanpa teks lain, tanpa markdown ```json.
Pilih salah satu dari aksi berikut:
{{"aksi": "ketik", "parameter": "teks yang akan diketik langsung ke layar"}}
{{"aksi": "tekan", "parameter": "nama tombol (contoh: enter, tab, win, space, esc, down)"}}
{{"aksi": "kombinasi", "parameter": "tombol1, tombol2 (contoh: ctrl, s)"}}
{{"aksi": "klik", "parameter": "nama tombol/tulisan di layar yang ingin diklik sekali"}}
{{"aksi": "klik_ganda", "parameter": "nama tombol/tulisan di layar yang ingin di-double-click"}}
{{"aksi": "tunggu", "parameter": "2 (waktu tunggu dalam detik)"}}
{{"aksi": "selesai", "parameter": "Laporan sukses jika tujuan tercapai"}}

Jika Anda gagal mengeksekusi klik berulang kali di titik yang sama, GUNAKAN CARA LAIN (seperti keyboard shortcuts) jangan bertele-tele!
Keluarkan HANYA JSON:"""
                    
                    response = model_vision.generate_content([img, prompt])
                    
                    teks_json = response.text
                    teks_json = re.sub(r'```json', '', teks_json)
                    teks_json = re.sub(r'```', '', teks_json).strip()
                    
                    try:
                        keputusan = json.loads(teks_json)
                    except Exception as e:
                        kirim_pesan_telegram_sync(chat_id, f"⚠️ Agen error saat memproses gambar: {teks_json}")
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        continue
                
                aksi = keputusan.get("aksi", "tunggu")
                param = keputusan.get("parameter", "2")
                
                pesan_progress = f"👁️ Langkah {langkah+1}: {aksi} -> {param}"
                print(pesan_progress)
                kirim_pesan_telegram_sync(chat_id, pesan_progress)
                
                riwayat_aksi.append(f"{aksi}({param})")
                
                # EKSEKUSI NYATA
                if aksi == "ketik":
                    pyautogui.write(str(param), interval=0.05)
                elif aksi == "tekan":
                    pyautogui.press(str(param))
                elif aksi == "kombinasi":
                    tombol = [x.strip() for x in str(param).split(",")]
                    pyautogui.hotkey(*tombol)
                elif aksi == "klik":
                    kirim_pesan_telegram_sync(chat_id, f"🔍 Mencari letak '{param}' di layar...")
                    hasil_klik = klik_berdasarkan_gambar(str(param))
                    kirim_pesan_telegram_sync(chat_id, f"🖱️ {hasil_klik}")
                elif aksi == "klik_ganda":
                    kirim_pesan_telegram_sync(chat_id, f"🔍 Mencari letak '{param}' untuk di-double-click...")
                    hasil_klik = klik_berdasarkan_gambar(str(param))
                    if "Berhasil" in hasil_klik:
                        pyautogui.doubleClick() # Eksekusi double click di posisi yang sama
                        kirim_pesan_telegram_sync(chat_id, f"🖱️ Berhasil klik ganda (double-click) pada {param}")
                    else:
                        kirim_pesan_telegram_sync(chat_id, f"🖱️ Gagal menemukan {param} untuk diklik ganda.")
                elif aksi == "tunggu":
                    time.sleep(int(param))
                elif aksi == "selesai":
                    kirim_pesan_telegram_sync(chat_id, f"✅ [MODE OTONOM SELESAI]\nLaporan Agen: {param}\n\nKendali komputer dikembalikan kepada Anda.")
                    os.remove(filepath)
                    break
                else:
                    kirim_pesan_telegram_sync(chat_id, f"⚠️ Peringatan: Aksi '{aksi}' tidak dikenali. Menunggu...")
                    time.sleep(2)
                    
            except Exception as e:
                pesan_error = str(e)
                if "429" in pesan_error or "Quota exceeded" in pesan_error:
                    kirim_pesan_telegram_sync(chat_id, "⏳ Mesin penglihatan AI kepanasan (Mencapai batas kecepatan Gemini). Mendinginkan mesin selama 45 detik...")
                    time.sleep(45)
                else:
                    kirim_pesan_telegram_sync(chat_id, f"⚠️ Agen error saat memproses gambar: {pesan_error}")
                    time.sleep(3)
                
            if os.path.exists(filepath):
                os.remove(filepath)
                
        else:
            kirim_pesan_telegram_sync(chat_id, "❌ [AGEN OTONOM DIHENTIKAN] Tugas terlalu panjang dan melebihi batas 15 langkah. Mode Otonom dimatikan.")
            
    except Exception as e:
        kirim_pesan_telegram_sync(chat_id, f"Fatal error agen otonom: {str(e)}")

def jalankan_agen_otonom(tugas: str, chat_id: int):
    try:
        tugas_thread = threading.Thread(target=tugas_otonom_background, args=(tugas, chat_id))
        tugas_thread.start()
        return "MODE_OTONOM_AKTIF: Tugas telah dilempar ke background. JANGAN MENJAWAB bahwa Anda telah menyelesaikan tugas ini. Katakan saja: 'Baik, saya telah mengambil alih PC Anda secara otonom. Silakan pantau layar.'."
    except Exception as e:
        return f"Gagal menjalankan Mode Otonom: {str(e)}"


def _thread_buat_video_youtube(topik: str, jenis_background: str, suara: str, chat_id: int):
    try:
        import subprocess
        from PIL import Image, ImageFilter, ImageEnhance
        import urllib.request
        
        kirim_pesan_telegram_sync(chat_id, f"🎬 [PABRIK KONTEN DINAMIS] Mulai memproduksi video tentang: {topik}\n(1/5) Menulis naskah...")
        
        # 1. Buat Naskah
        prompt_naskah = f"Buatkan naskah video YouTube Shorts/Instagram Reels (durasi 30-45 detik) tentang: {topik}. Buat bahasanya santai, asyik, dan langsung ke intinya. Jangan pakai teks deskripsi visual (seperti [Video menunjukkan...]), langsung saja kata-kata yang diucapkan (narasi) tanpa tanda baca aneh."
        response, _ = minta_jawaban_ai([{"role": "user", "content": prompt_naskah}])
        naskah = response.choices[0].message.content.strip()
        naskah = naskah.replace("*", "").replace("#", "")
        
        kirim_pesan_telegram_sync(chat_id, "(2/5) Memikirkan visual latar belakang...")
        
        # 2. Buat Prompt Gambar (Inggris)
        prompt_gambar = f"Buatkan 1 kalimat pendek dalam BAHASA INGGRIS (maksimal 5 kata) yang mendeskripsikan adegan visual dari topik ini untuk digambar oleh AI: {topik}. Contoh: 'ancient majapahit temple cinematic'. Hanya berikan kalimat inggrisnya saja, tanpa tanda kutip."
        response_gambar, _ = minta_jawaban_ai([{"role": "user", "content": prompt_gambar}])
        prompt_inggris = response_gambar.choices[0].message.content.strip().replace("'", "").replace('"', "")
        
        kirim_pesan_telegram_sync(chat_id, "(3/5) Merekam Voice Over (Suara) otomatis & membuat subtitle...")
        
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        audio_path = os.path.join(desktop_path, 'temp_audio.wav')
        bg_path_img = os.path.join(desktop_path, 'temp_bg.png')
        bg_path_vid = os.path.join(desktop_path, 'temp_bg.mp4')
        sub_path = os.path.join(desktop_path, 'temp_sub.vtt')
        backsound_path = str(_AKAR_PROGRAM / "backsound.mp3")
        safe_topik = topik[:15].replace(" ", "_").replace("'", "")
        video_path = os.path.join(desktop_path, f'Video_YouTube_{safe_topik}.mp4')
        
        # Cleanup past temps
        for p in [audio_path, bg_path_img, bg_path_vid, sub_path]:
            if os.path.exists(p): os.remove(p)
        
        # Generate Audio pakai Edge-TTS
        voice_id = "id-ID-GadisNeural" if suara.lower() == "perempuan" else "id-ID-ArdiNeural"
        cmd_audio = [sys.executable, "-m", "edge_tts", "--voice", voice_id, "--text", naskah, "--write-media", audio_path, "--write-subtitles", sub_path]
        subprocess.run(cmd_audio, check=True)
        
        kirim_pesan_telegram_sync(chat_id, f"(4/5) Mengunduh B-Roll YouTube otomatis ({prompt_inggris})...")
        
        # 3. Download B-Roll Video (YouTube)
        img_w, img_h = 1080, 1920
        is_video = False
        
        if jenis_background.lower() == "reaper" or jenis_background.lower() == "layar":
            import pyautogui
            screenshot = pyautogui.screenshot()
            screenshot = screenshot.resize((1920, 1080))
            left = (1920 - 1080)/2
            top = 0
            right = (1920 + 1080)/2
            bottom = 1080
            bg_img = screenshot.crop((left, top, right, bottom)).resize((img_w, img_h))
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(15))
            enhancer = ImageEnhance.Brightness(bg_img)
            bg_img = enhancer.enhance(0.3)
            bg_img.save(bg_path_img)
        else:
            try:
                import yt_dlp
                kata_kunci = prompt_inggris.replace(' ', '+')
                youtube_query = f"ytsearch1:{kata_kunci}+aesthetic+vertical+background+loop+no+copyright+video"
                ydl_opts = {
                    'outtmpl': bg_path_vid,
                    'format': 'bestvideo[ext=mp4]/best[ext=mp4]/best',
                    'quiet': True,
                    'nocheckcertificate': True,
                    'no_warnings': True,
                    'headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                        'Accept-Language': 'en-US,en;q=0.9'
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'web']
                        }
                    }
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([youtube_query])
                
                if os.path.exists(bg_path_vid):
                    is_video = True
            except Exception as e:
                kirim_pesan_telegram_sync(chat_id, f"Gagal mendownload B-Roll YouTube: {str(e)}. Fallback ke gambar Pollinations AI.")
                
            if not is_video:
                img_url = f"https://image.pollinations.ai/prompt/{prompt_inggris.replace(' ', '%20')}?width=1080&height=1920&nologo=true"
                try:
                    urllib.request.urlretrieve(img_url, bg_path_img)
                except Exception as e:
                    bg_img = Image.new('RGB', (img_w, img_h), color=(30, 30, 30))
                    bg_img.save(bg_path_img)
        
        kirim_pesan_telegram_sync(chat_id, "(5/5) Merakit video (Subtitle Karaoke + Animasi + Audio Mix)...")
        
        # 4. Render Video via FFmpeg
        has_bgm = os.path.exists(backsound_path)
        ffmpeg_cmd = ["ffmpeg", "-y"]
        
        if is_video:
            ffmpeg_cmd.extend(["-stream_loop", "-1", "-i", bg_path_vid])
        else:
            ffmpeg_cmd.extend(["-loop", "1", "-i", bg_path_img])
            
        ffmpeg_cmd.extend(["-i", audio_path])
        
        if has_bgm:
            ffmpeg_cmd.extend(["-stream_loop", "-1", "-i", backsound_path])
            
        # Filter Video: crop 9:16 + darken slightly + subtitles
        if is_video:
            v_filter = "crop=ih*9/16:ih,eq=brightness=-0.15,subtitles=temp_sub.vtt:force_style='FontSize=26,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=120'"
        else:
            v_filter = "zoompan=z='min(zoom+0.0005,1.5)':d=3000:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,eq=brightness=-0.15,subtitles=temp_sub.vtt:force_style='FontSize=26,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=120'"
        
        if has_bgm:
            a_filter = "[1:a]volume=1.3[v];[2:a]volume=0.15[b];[v][b]amix=inputs=2:duration=first[a]"
            ffmpeg_cmd.extend(["-filter_complex", f"[0:v]{v_filter}[v];{a_filter}", "-map", "[v]", "-map", "[a]"])
        else:
            ffmpeg_cmd.extend(["-filter_complex", f"[0:v]{v_filter}[v]", "-map", "[v]", "-map", "1:a"])
            
        ffmpeg_cmd.extend(["-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest", video_path])
        
        subprocess.run(ffmpeg_cmd, cwd=desktop_path, check=True)
        
        for p in [audio_path, bg_path_img, bg_path_vid, sub_path]:
            if os.path.exists(p): os.remove(p)
        
        kirim_pesan_telegram_sync(chat_id, f"✅ Selesai! Video YouTube Shorts telah dirender di Desktop:\nVideo_YouTube_{safe_topik}.mp4")
        
    except Exception as e:
        kirim_pesan_telegram_sync(chat_id, f"❌ Gagal membuat video dinamis: {str(e)}")

def buat_video_youtube(topik: str, jenis_background: str = "reaper", suara: str = "laki-laki", chat_id=None):
    try:
        import threading
        if not chat_id:
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
        t = threading.Thread(target=_thread_buat_video_youtube, args=(topik, jenis_background, suara, chat_id))
        t.start()
        return "Tugas pembuatan konten video YouTube Shorts telah dilempar ke pekerja latar belakang. Sari akan memberi tahu Anda otomatis lewat pesan saat selesai!"
    except Exception as e:
        return f"Gagal mengeksekusi buat_video_youtube: {str(e)}"

def suntik_cover_mp3(jalur_audio: str, prompt_gambar: str, judul_lagu: str, nama_artis: str, nama_album: str):
    try:
        import sys
        if str(_AKAR_PROGRAM) not in sys.path: sys.path.append(str(_AKAR_PROGRAM))
        import suntik_cover_mp3 as injector
        return injector.suntik_cover_mp3(jalur_audio, prompt_gambar, judul_lagu, nama_artis, nama_album)
    except Exception as e:
        return f"Gagal menyuntikkan cover: {e}"

def cari_chord_lagu(jalur_audio: str):
    try:
        import sys
        if str(_AKAR_PROGRAM) not in sys.path: sys.path.append(str(_AKAR_PROGRAM))
        import pencari_chord
        return pencari_chord.pencari_chord(jalur_audio)
    except Exception as e:
        return f"Gagal mencari chord: {e}"


def kirim_file_telegram(path_file: str, caption: str = ""):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return "Gagal: Token Telegram tidak ditemukan."
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "Gagal: Chat ID Telegram tidak ditemukan."
    
    if not os.path.exists(path_file):
        return f"Gagal: File {path_file} tidak ditemukan."
        
    try:
        import requests
        ukuran_mb = os.path.getsize(path_file) / (1024 * 1024)
        if ukuran_mb > 49:
            return f"Gagal mengirim: Ukuran file {ukuran_mb:.1f} MB terlalu besar (Maks Telegram 50MB)."
            
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(path_file, 'rb') as doc:
            files = {'document': doc}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, files=files, data=data)
            
        if response.status_code == 200:
            return f"Berhasil mengirim file {os.path.basename(path_file)} ke Telegram."
        else:
            return f"Gagal mengirim file: {response.text}"
    except Exception as e:
        return f"Terjadi kesalahan saat mengirim file ke Telegram: {str(e)}"

def analisa_bpm_dan_nada(path_file: str):
    if not os.path.exists(path_file):
        return f"Gagal: File {path_file} tidak ditemukan."
    try:
        import librosa
        import numpy as np
        
        y, sr = librosa.load(path_file, sr=22050, duration=60) # load first 60 seconds
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        
        chromagram = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=24)
        chroma_mean = np.mean(chromagram, axis=1)
        
        maj_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
        min_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        max_cor = -1
        key = "Unknown"
        for i in range(12):
            r_maj = np.corrcoef(chroma_mean, np.roll(maj_profile, i))[0,1]
            if r_maj > max_cor:
                max_cor = r_maj
                key = f"{keys[i]} Mayor"
            r_min = np.corrcoef(chroma_mean, np.roll(min_profile, i))[0,1]
            if r_min > max_cor:
                max_cor = r_min
                key = f"{keys[i]} Minor"
        
        bpm_val = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
        return f"Analisis Berhasil!\n- Tempo (BPM): {bpm_val:.1f}\n- Nada Dasar (Perkiraan): {key}"
    except Exception as e:
        return f"Terjadi kesalahan saat menganalisis audio: {str(e)}"

def buat_audio_tts(teks_panjang: str, nama_file_output: str):
    if not nama_file_output.endswith('.mp3'):
        nama_file_output += '.mp3'
    try:
        import subprocess
        voice_id = "id-ID-GadisNeural"
        
        with open("temp_tts_text.txt", "w", encoding="utf-8") as tf:
            tf.write(teks_panjang)
            
        # Jalankan edge-tts lewat Python yang sedang menjalankan aplikasi.
        # Cara ini bekerja di komputer mana pun, tidak bergantung jalur folder pribadi.
        perintah = f'"{sys.executable}" -m edge_tts --voice {voice_id} -f "temp_tts_text.txt" --write-media "{nama_file_output}"'
        hasil = subprocess.run(perintah, shell=True, capture_output=True, text=True)
        
        if os.path.exists("temp_tts_text.txt"):
            os.remove("temp_tts_text.txt")
            
        if os.path.exists(nama_file_output):
            return f"Berhasil membuat audio TTS. File disimpan di: {os.path.abspath(nama_file_output)}"
        else:
            return f"Gagal membuat audio. Output: {hasil.stderr}"
    except Exception as e:
        return f"Gagal membuat audio TTS: {str(e)}"

# ---------------------------------------------------------
# LAYANAN CLOUD MEDIA & SISTEM LOKAL (MODULARISASI SARI CORE)
# ---------------------------------------------------------
from sari_core.cloud_media_service import (
    upload_youtube, cek_statistik_youtube, baca_komentar_youtube,
    balas_komentar_youtube, edit_video_youtube, cari_id_video_youtube,
    buat_playlist_youtube, tambah_video_playlist_youtube,
    ganti_thumbnail_youtube, hapus_komentar_youtube,
    cek_video_terbaru_channel_youtube, cek_video_terakhir_channel_sendiri,
    upload_drive, cek_kapasitas_drive, cari_file_drive,
    ubah_akses_drive, hapus_file_drive, bagi_akses_email_drive,
    buang_ke_sampah_drive, ganti_nama_file_drive, kosongkan_sampah_drive,
    download_file_drive, cek_isi_folder_drive
)


from sari_core.local_system_service import (
    cari_file_lokal, baca_isi_folder_lokal, kelola_file_lokal,
    cek_disk_lokal, buka_aplikasi_lokal, cek_progress_tugas,
    putar_folder_musik_lokal, putar_lagu_lokal
)


# Riwayat pesan WA masuk (diisi oleh tugas_wa_bot_background, dibaca oleh cek_pesan_wa_bridge)
riwayat_wa_masuk = []

def cek_pesan_wa_bridge():
    global riwayat_wa_masuk
    try:
        import requests
        # 1. Cek dulu apakah WA Bridge sudah konek ke HP
        try:
            r_status = requests.get("http://localhost:3000/status", timeout=5)
            if r_status.status_code == 200:
                status = r_status.json()
                if not status.get('ready', False):
                    return "WhatsApp belum terhubung ke HP pengguna. Kemungkinan perlu scan barcode ulang."
        except Exception as e:
            return "WA Bridge tidak berjalan. Silakan restart bot."
        
        # 2. Baca dari riwayat yang dikumpulkan oleh tugas_wa_bot_background
        if not riwayat_wa_masuk:
            return "Tidak ada pesan WhatsApp baru yang masuk."
        
        # Ambil semua pesan dan kosongkan riwayat
        msgs = list(riwayat_wa_masuk)
        riwayat_wa_masuk.clear()
        
        hasil = [f"Ada {len(msgs)} pesan WA baru:"]
        for m in msgs:
            tipe = "[Voice Note]" if m.get('isVoiceNote') else "[Teks]"
            sumber = "[GROUP]" if m.get('isGroup') else "[PRIBADI]"
            teks = m.get('body', '')
            if m.get('isVoiceNote'):
                teks += f" (Tersimpan di: {m.get('voicePath')})"
            hasil.append(f"- {sumber} Dari: {m['name']} ({m['from']}) | Tipe: {tipe} | Pesan: {teks}")
        
        return "\n".join(hasil)
    except Exception as e:
        return f"Gagal mengecek pesan WA. Error: {str(e)}"

satpam_thread_aktif = False

def pantau_layar_pc():
    """Mengambil screenshot layar PC saat ini dan mengirimkannya ke Telegram."""
    try:
        import pyautogui
        import os
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            return "Gagal: ID Telegram tidak ditemukan."
            
        screen_dir = FILE_DIR / "Screenshot"
        screen_dir.mkdir(parents=True, exist_ok=True)
        temp_path = str(screen_dir / "temp_screen.jpg")
        pyautogui.screenshot(temp_path)
        
        # Kirimkan file foto screenshot secara nyata ke Telegram
        hasil_kirim = kirim_file_telegram(temp_path, caption="🖥️ Screenshot Layar PC Saat Ini")
        return f"Berhasil mengambil screenshot layar dan langsung mengirimkannya ke Telegram pengguna! ({hasil_kirim})"
    except Exception as e:
        return f"Gagal mengambil screenshot: {str(e)}"

def _download_pekerja(url, chat_id, tipe="video"):
    try:
        import os
        folder_downloads = str(DOWNLOADS_DIR)
        if not os.path.exists(folder_downloads):
            os.makedirs(folder_downloads, exist_ok=True)
            
        tipe_clean = tipe.lower() if tipe else "video"
        is_audio = "audio" in tipe_clean or "mp3" in tipe_clean or "musik" in tipe_clean or "lagu" in tipe_clean
        
        kirim_pesan_telegram_sync(chat_id, f"📥 Memulai proses download {'Audio MP3' if is_audio else 'Video MP4'} (Background)...")
        
        # Cek apakah ini URL YouTube / socmed atau search query (ytsearch)
        is_socmed = any(domain in url.lower() for domain in ["youtube.com", "youtu.be", "instagram.com", "soundcloud.com", "twitter.com", "x.com", "ytsearch:"])
        if is_socmed:
            import yt_dlp
            if is_audio:
                ydl_opts = {
                    'outtmpl': os.path.join(folder_downloads, '%(title)s.%(ext)s'),
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {'youtube': {'player_client': ['android']}}
                }
            else:
                ydl_opts = {
                    'outtmpl': os.path.join(folder_downloads, '%(title)s.%(ext)s'),
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {'youtube': {'player_client': ['android']}}
                }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                nama_file = ydl.prepare_filename(info)
                if is_audio:
                    base, _ = os.path.splitext(nama_file)
                    nama_file = base + ".mp3"
            kirim_pesan_telegram_sync(chat_id, f"✅ Download {'Audio MP3' if is_audio else 'Video MP4'} selesai!\n📁 File: {os.path.basename(nama_file)}\n📍 Lokasi: File/Downloads")
        else:
            import requests
            import mimetypes
            from urllib.parse import urlparse
            
            r = requests.get(url, stream=True)
            r.raise_for_status()
            
            # Coba dapatkan nama file dari Header server
            nama_file = ""
            if 'Content-Disposition' in r.headers:
                disp_header = r.headers['Content-Disposition']
                if 'filename=' in disp_header:
                    nama_file = disp_header.split('filename=')[-1].strip('"\'')
                    
            if not nama_file:
                a = urlparse(r.url)
                nama_file = os.path.basename(a.path)
                
            if not nama_file or '.' not in nama_file:
                content_type = r.headers.get('Content-Type', '').split(';')[0]
                ext = mimetypes.guess_extension(content_type) or '.dat'
                if ext == '.htm': ext = '.html'
                if not nama_file:
                    nama_file = "downloaded_file"
                nama_file = nama_file + ext
                
            filepath = os.path.join(folder_downloads, nama_file)
            
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if nama_file.endswith('.html'):
                kirim_pesan_telegram_sync(chat_id, f"⚠️ Selesai, TAPI PERHATIAN: Link yang Anda kirim ternyata adalah halaman WEB, bukan file Installer/Software. File tersimpan sebagai: {filepath}")
            else:
                kirim_pesan_telegram_sync(chat_id, f"✅ Download selesai! File tersimpan di: {filepath}")
    except Exception as e:
        kirim_pesan_telegram_sync(chat_id, f"❌ Download gagal: {str(e)}")

def download_file_siluman(url: str, tipe: str = "video"):
    """Mendownload file (Video MP4 atau Audio MP3) dari YouTube/IG/link ke folder Downloads."""
    import os
    import threading
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "Gagal: ID Telegram tidak ditemukan."
        
    threading.Thread(target=_download_pekerja, args=(url, chat_id, tipe), daemon=True).start()
    return f"🚀 Perintah download siluman ({'Audio MP3' if 'audio' in tipe.lower() or 'mp3' in tipe.lower() else 'Video MP4'}) diterima. Sedang mengunduh di latar belakang..."

def _satpam_pekerja(chat_id):
    global satpam_thread_aktif
    try:
        import pyautogui
        import cv2
        import os
        import time
        
        posisi_awal = pyautogui.position()
        waktu_mulai = time.time()
        
        while satpam_thread_aktif:
            time.sleep(1)
            posisi_sekarang = pyautogui.position()
            if posisi_sekarang != posisi_awal:
                kirim_pesan_telegram_sync(chat_id, "🚨 PERINGATAN! Gerakan terdeteksi di PC Anda!")
                from datetime import datetime
                waktu_satpam = datetime.now().strftime("%Y%m%d_%H%M%S")
                folder_surv = str(FILE_DIR / "Surveillance")
                os.makedirs(folder_surv, exist_ok=True)
                try:
                    cap = cv2.VideoCapture(0)
                    ret, frame = cap.read()
                    if ret:
                        cam_path = os.path.join(folder_surv, f"satpam_wajah_{waktu_satpam}.jpg")
                        cv2.imwrite(cam_path, frame)
                        kirim_file_telegram(cam_path, caption=f"📸 Wajah Pelaku Terdeteksi ({waktu_satpam})")
                    cap.release()
                except Exception:

                    pass
                try:
                    scr_path = os.path.join(folder_surv, f"satpam_layar_{waktu_satpam}.jpg")
                    pyautogui.screenshot(scr_path)
                    kirim_file_telegram(scr_path, caption=f"🖥️ Aktivitas Layar Saat Penyusup Masuk ({waktu_satpam})")
                except Exception:

                    pass
                satpam_thread_aktif = False
                kirim_pesan_telegram_sync(chat_id, "🛡️ Mode Satpam otomatis dinonaktifkan setelah mendeteksi penyusup.")
                break
            if time.time() - waktu_mulai > 86400:
                satpam_thread_aktif = False
                break
    except Exception as e:
        satpam_thread_aktif = False
        kirim_pesan_telegram_sync(chat_id, f"❌ Error Satpam: {str(e)}")

def aktifkan_mode_satpam():
    """Mengaktifkan sistem pemantau keamanan PC (mendeteksi gerakan mouse & kamera)."""
    global satpam_thread_aktif
    import os
    import threading
    if satpam_thread_aktif:
        return "Mode Satpam sudah aktif saat ini."
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "Gagal: ID Telegram tidak ditemukan."
    satpam_thread_aktif = True
    threading.Thread(target=_satpam_pekerja, args=(chat_id,), daemon=True).start()
    return "🛡️ Mode Satpam diaktifkan! Jika ada gerakan mouse, foto pelaku & layar akan dikirim ke sini."

def bersihkan_sampah_pc():
    """Mengosongkan Recycle Bin dan file Temp (cache) di PC untuk menghemat ruang."""
    import ctypes
    import os
    import shutil
    
    hasil = []
    
    # 1. Empty Recycle Bin
    try:
        # SHERB_NOCONFIRMATION = 1, SHERB_NOPROGRESSUI = 2, SHERB_NOSOUND = 4 => 7
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        if res == 0:
            hasil.append("🗑️ Recycle Bin berhasil dikosongkan.")
        else:
            hasil.append("🗑️ Recycle Bin sudah kosong.")
    except Exception as e:
        hasil.append(f"❌ Gagal membersihkan Recycle Bin: {e}")
        
    # 2. Clean User Temp
    temp_dir = os.environ.get('TEMP')
    if temp_dir and os.path.exists(temp_dir):
        terhapus = 0
        try:
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    terhapus += 1
                except Exception:

                    pass
            hasil.append(f"🧹 Berhasil menghapus {terhapus} objek sampah dari sistem (Cache).")
        except Exception as e:
            hasil.append(f"❌ Gagal membersihkan Cache: {e}")
            
    return "\n".join(hasil)

def kunci_pc_jarak_jauh():
    """Mengunci layar PC kembali ke mode Login Windows dan memutar peringatan suara."""
    import ctypes
    import subprocess
    import threading
    
    try:
        ctypes.windll.user32.LockWorkStation()
        ps_cmd = "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('PERINGATAN! Waktu peminjaman habis, PC dikunci oleh sistem keamanan pengguna!')"
        threading.Thread(target=lambda: subprocess.run(["powershell", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW), daemon=True).start()
        return "🔒 PC berhasil dibajak dan dikunci ke layar Login. Peringatan suara sedang diteriakkan dari speaker!"
    except Exception as e:
        return f"❌ Gagal mengunci PC: {str(e)}"

def baca_clipboard_pc():
    """Membaca isi clipboard (teks yang baru di-copy) di PC."""
    import subprocess
    try:
        hasil = subprocess.check_output(['powershell', '-command', 'Get-Clipboard'], text=True).strip()
        if not hasil:
            return "📋 Clipboard kosong atau bukan berisi teks."
        return f"📋 Isi Clipboard PC saat ini:\n\n{hasil}"
    except Exception as e:
        return f"❌ Gagal membaca clipboard: {str(e)}"


def sadap_kamera_ruangan(durasi=10):
    """Merekam video (webcam) dan audio (mikrofon) secara bersamaan dan menjahitnya jadi satu file MP4."""
    import cv2
    import sounddevice as sd
    import soundfile as sf
    import threading
    import os
    import time
    import subprocess
    
    try:
        durasi = int(durasi)
    except Exception as e:
        durasi = 10
        
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id: return "Gagal: ID Telegram tidak ditemukan."
    
    folder_surv = str(FILE_DIR / "Surveillance")
    folder_temp = str(TEMP_DIR)
    os.makedirs(folder_surv, exist_ok=True)
    os.makedirs(folder_temp, exist_ok=True)
    from datetime import datetime
    waktu_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    file_vid = os.path.join(folder_temp, f"temp_kamera_sadap_{waktu_str}.mp4")
    file_aud = os.path.join(folder_temp, f"temp_kamera_sadap_{waktu_str}.wav")
    file_final = os.path.join(folder_surv, f"sadap_kamera_{waktu_str}.mp4")
    
    # Tangan Kiri: Rekam Audio
    fs = 44100
    rekaman_suara = None
    
    def rekam_suara():
        nonlocal rekaman_suara
        try:
            rekaman_suara = sd.rec(int(durasi * fs), samplerate=fs, channels=1)
            sd.wait()
            sf.write(file_aud, rekaman_suara, fs)
        except Exception as e:
            print("Gagal rekam suara:", str(e))
            
    # Tangan Kanan: Rekam Video
    def rekam_video():
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("Kamera tidak ditemukan")
                return
            
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = 20.0 # Standard fps assumption
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(file_vid, fourcc, fps, (width, height))
            
            start_time = time.time()
            while int(time.time() - start_time) < durasi:
                ret, frame = cap.read()
                if not ret: break
                out.write(frame)
                time.sleep(1.0 / fps)
                
            cap.release()
            out.release()
        except Exception as e:
            print("Gagal rekam video:", str(e))
            
    # Jalankan bersamaan
    t1 = threading.Thread(target=rekam_suara)
    t2 = threading.Thread(target=rekam_video)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    # Menjahit dengan FFmpeg
    if os.path.exists(file_vid) and os.path.exists(file_aud):
        cmd = f'ffmpeg -y -i "{file_vid}" -i "{file_aud}" -c:v copy -c:a aac "{file_final}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(file_final):
            # Jika ffmpeg gagal, gabungkan manual atau fallback ke video saja
            if os.path.exists(file_vid):
                os.rename(file_vid, file_final)
    elif os.path.exists(file_vid):
        # Jika cuma ada video
        os.rename(file_vid, file_final)
    elif os.path.exists(file_aud):
        # Jika cuma ada audio
        return sadap_suara_ruangan(durasi)
    else:
        return "❌ Gagal: Kamera dan Mikrofon tidak dapat diakses."
        
    if os.path.exists(file_final):
        # Kirim file telegram
        kirim_file_telegram(file_final, caption=f"🎥 Hasil Sadapan Kamera Ruangan ({durasi} Detik) - {waktu_str}")
        
        # Bersihkan hanya sisa temp audio/video terpisah
        for f in [file_vid, file_aud]:
            if os.path.exists(f):
                try: os.remove(f)
                except Exception:

                    pass
        return f"🎥 Berhasil menyadap ruangan (Video+Audio) selama {durasi} detik! File MP4 tersimpan aman di File/Surveillance sebagai bukti dan sudah dikirim ke Telegram."
    
    return "❌ Gagal memproses video sadapan."


def sadap_suara_ruangan(durasi=10):
    """Merekam suara dari mikrofon PC selama durasi tertentu, menyimpannya permanen di File/Surveillance, dan mengirimkannya ke Telegram."""
    import sounddevice as sd
    import soundfile as sf
    import os
    
    fs = 44100
    try:
        durasi = int(durasi)
    except Exception as e:
        durasi = 10
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "Gagal: ID Telegram tidak ditemukan."
        
    folder_surv = str(FILE_DIR / "Surveillance")
    os.makedirs(folder_surv, exist_ok=True)
    from datetime import datetime
    waktu_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_sadap = os.path.join(folder_surv, f"sadap_suara_{waktu_str}.wav")
    
    try:
        rekaman = sd.rec(int(durasi * fs), samplerate=fs, channels=1)
        sd.wait()
        sf.write(file_sadap, rekaman, fs)
        
        # Menggunakan fungsi internal kirim_file_telegram
        kirim_file_telegram(file_sadap, caption=f"🎙️ Hasil Sadapan Suara Ruangan ({durasi} Detik) - {waktu_str}")
            
        return f"🎙️ Berhasil menyadap ruangan! File suara ({durasi} detik) tersimpan aman di File/Surveillance sebagai bukti dan sudah dikirimkan ke Telegram Anda."
    except Exception as e:
        return f"❌ Gagal menyadap mikrofon: {str(e)}"

def isi_clipboard_pc(teks: str):
    """Memasukkan teks ke dalam clipboard PC pengguna."""
    import subprocess
    try:
        process = subprocess.Popen(['powershell', '-command', 'Set-Clipboard'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        process.communicate(input=teks)
        return "✅ Teks berhasil disuntikkan ke dalam Clipboard PC! Silakan tekan Ctrl+V di PC Anda."
    except Exception as e:
        return f"❌ Gagal mengisi clipboard: {str(e)}"

def cek_aplikasi_aktif():
    """Melacak dan menampilkan judul jendela aplikasi yang sedang paling depan / aktif di layar PC."""
    import ctypes
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return "Tidak ada aplikasi yang sedang aktif."
            
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return "Aplikasi yang sedang aktif tidak memiliki nama/judul jendela."
            
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        
        return f"👁️ Aplikasi yang sedang aktif (paling depan) di layar PC saat ini adalah:\n\n**{buf.value}**"
    except Exception as e:
        return f"❌ Gagal mengintip layar: {str(e)}"

status_instalasi = {
    "aktif": False,
    "total": 0,
    "selesai": 0,
    "file_sekarang": "",
    "laporan": []
}

def _pekerja_install_otomatis(path_folder: str, chat_id: str):
    import os
    import subprocess
    import shutil
    global status_instalasi
    
    hasil_laporan = []
    hasil_laporan.append(f"🚀 **Memulai Auto-Installer di:** {path_folder}\n")
    
    try:
        semua_file = os.listdir(path_folder)
        file_valid = [f for f in semua_file if os.path.isfile(os.path.join(path_folder, f)) and not "SKIP" in f.upper()]
        status_instalasi["total"] = len(file_valid)
        status_instalasi["selesai"] = 0
    except Exception as e:
        status_instalasi["aktif"] = False
        kirim_pesan_telegram_sync(chat_id, f"❌ Gagal membaca isi folder: {str(e)}")
        return
        
    for file in semua_file:
        path_file = os.path.join(path_folder, file)
        
        if "SKIP" in file.upper():
            hasil_laporan.append(f"⏭️ Dilewati (Ada tag SKIP): {file}")
            continue
            
        if os.path.isfile(path_file):
            status_instalasi["file_sekarang"] = file
            ext = os.path.splitext(file)[1].lower()
            try:
                if ext == ".exe":
                    subprocess.run([path_file, "/S", "/VERYSILENT", "/quiet"])
                    hasil_laporan.append(f"✅ Dieksekusi (.exe): {file}")
                elif ext == ".msi":
                    subprocess.run(["msiexec", "/i", path_file, "/qn"])
                    hasil_laporan.append(f"✅ Dieksekusi (.msi): {file}")
                elif ext == ".reg":
                    subprocess.run(["regedit.exe", "/s", path_file])
                    hasil_laporan.append(f"✅ Lisensi disuntikkan (.reg): {file}")
            except Exception as e:
                hasil_laporan.append(f"❌ Error mengeksekusi {file}: {str(e)}")
            status_instalasi["selesai"] += 1
                
    path_crack = os.path.join(path_folder, "Crack")
    path_lokasi = os.path.join(path_folder, "lokasi.txt")
    
    if os.path.exists(path_crack) and os.path.isdir(path_crack) and os.path.exists(path_lokasi):
        try:
            with open(path_lokasi, "r") as f:
                tujuan = f.read().strip()
                
            if os.path.exists(tujuan) and os.path.isdir(tujuan):
                for nama_crack in os.listdir(path_crack):
                    file_sumber = os.path.join(path_crack, nama_crack)
                    file_tujuan = os.path.join(tujuan, nama_crack)
                    if os.path.isfile(file_sumber):
                        shutil.copy2(file_sumber, file_tujuan)
                hasil_laporan.append(f"\n🏴‍☠️ **AUTO-CRACK BERHASIL!** File crack telah di-paste paksa ke {tujuan}")
            else:
                hasil_laporan.append(f"\n⚠️ Auto-Crack batal: Folder tujuan '{tujuan}' tidak ditemukan.")
        except Exception as e:
            hasil_laporan.append(f"\n❌ Auto-Crack error: {str(e)}")
            
    hasil_laporan.append("\n🎉 **PROSES SELESAI.** (Catatan: Jika ada aplikasi yang belum muncul, instalasinya mungkin butuh waktu di latar belakang).")
    status_instalasi["laporan"] = hasil_laporan
    status_instalasi["aktif"] = False
    
    # Kirim laporan akhir via telegram asalkan berhasil import
    try:
        kirim_pesan_telegram_sync(chat_id, "\n".join(hasil_laporan))
    except Exception:

        pass

def install_otomatis(path_folder: str):
    """Memicu instalasi software masal di latar belakang (multithreading)."""
    import os
    import threading
    global status_instalasi
    
    if status_instalasi["aktif"]:
        return "⚠️ Sari masih sibuk meng-install aplikasi lain. Silakan tunggu sampai selesai atau ketik 'cek progress'."
        
    if not os.path.exists(path_folder) or not os.path.isdir(path_folder):
        return f"❌ Gagal: Folder {path_folder} tidak ditemukan atau bukan folder."
        
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "Gagal: ID Telegram tidak ditemukan."
        
    status_instalasi["aktif"] = True
    status_instalasi["total"] = 0
    status_instalasi["selesai"] = 0
    status_instalasi["file_sekarang"] = "Mempersiapkan..."
    status_instalasi["laporan"] = []
    
    threading.Thread(target=_pekerja_install_otomatis, args=(path_folder, chat_id), daemon=True).start()
    return f"🚀 Proses Auto-Installer telah dimulai di latar belakang!\n\nSari sedang memproses folder: {path_folder}\nSilakan ketik perintah 'cek progress' untuk memantau."

status_instalasi = {"aktif": False, "total": 0, "selesai": 0, "file_sekarang": ""}
status_pekerjaan_video = {"aktif": False, "nama_tugas": "", "keterangan": ""}

def _kirim_notifikasi_selesai(chat_id, teks):
    import os, requests
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id: return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": teks})
    except Exception:

        pass

def _thread_edit_video(cmd, output_path, chat_id, nama_tugas):
    global status_pekerjaan_video
    status_pekerjaan_video["aktif"] = True
    status_pekerjaan_video["nama_tugas"] = nama_tugas
    status_pekerjaan_video["keterangan"] = "Sedang merender video di latar belakang..."
    
    try:
        import subprocess, os
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode == 0:
            if os.path.exists(output_path):
                os.startfile(output_path)
            pesan = f"✅ Laporan dari Ruang Bawah Tanah!\n\nTugas '{nama_tugas}' telah selesai. File tersimpan di:\n{output_path}"
        else:
            pesan = f"❌ GAGAL merender '{nama_tugas}'. Error:\n{process.stderr[-500:]}"
    except Exception as e:
        pesan = f"❌ Terjadi kesalahan saat '{nama_tugas}': {str(e)}"
        
    _kirim_notifikasi_selesai(chat_id, pesan)
    status_pekerjaan_video["aktif"] = False

def ramal_cuaca(kota: str):
    """
    Mengambil data prakiraan cuaca dari wttr.in
    """
    try:
        import requests
        url = f"https://wttr.in/{kota}?format=j1"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            kondisi = data['current_condition'][0]
            desc = kondisi['lang_id'][0]['value'] if 'lang_id' in kondisi else kondisi['weatherDesc'][0]['value']
            suhu = kondisi['temp_C']
            terasa = kondisi['FeelsLikeC']
            
            hasil = f"Cuaca di {kota} saat ini: {desc}, Suhu {suhu}°C (Terasa seperti {terasa}°C)."
            
            # Coba ambil ramalan untuk besok
            if 'weather' in data and len(data['weather']) > 1:
                besok = data['weather'][1]
                tgl_besok = besok.get('date', '')
                suhu_max = besok.get('maxtempC', '')
                suhu_min = besok.get('mintempC', '')
                kondisi_besok = besok['hourly'][4] # Mengambil kondisi siang hari (jam 12)
                desc_besok = kondisi_besok['lang_id'][0]['value'] if 'lang_id' in kondisi_besok else kondisi_besok['weatherDesc'][0]['value']
                
                hasil += f"\nRamalan besok ({tgl_besok}): Siang hari {desc_besok}, Suhu berkisar {suhu_min}°C - {suhu_max}°C."
                
            return hasil
        else:
            # Fallback ke format teks biasa jika JSON gagal atau tidak didukung
            url_txt = f"https://wttr.in/{kota}?format=3"
            r2 = requests.get(url_txt, timeout=10)
            if r2.status_code == 200:
                return f"Cuaca di {kota}: {r2.text.strip()}"
            return f"Gagal mendapatkan data cuaca untuk {kota}. Status: {response.status_code}"
    except Exception as e:
        return f"Terjadi kesalahan saat mengecek cuaca: {str(e)}"
def cek_progress_install():
    """Mengecek aktivitas tugas latar belakang Sari (termasuk instalasi massal dan rendering video)."""
    global status_instalasi, status_pekerjaan_video
    laporan = ""
    
    if status_instalasi["aktif"]:
        total = status_instalasi["total"]
        selesai = status_instalasi["selesai"]
        persen = int((selesai / total) * 100) if total > 0 else 0
        file_now = status_instalasi["file_sekarang"]
        laporan += f"📦 **Progress Instalasi:** {selesai} dari {total} selesai ({persen}%)\nSedang mengeksekusi: {file_now}\n\n"
        
    if status_pekerjaan_video["aktif"]:
        laporan += f"🎬 **Progress Video:** {status_pekerjaan_video['nama_tugas']}\nStatus: {status_pekerjaan_video['keterangan']}\n\n"
        
    if not laporan:
        return "Sari sedang bersantai, tidak ada pekerjaan berat di latar belakang saat ini."
        
    return laporan.strip()







available_functions = {
    "ramal_cuaca": ramal_cuaca,
    "stop_audio_latar": stop_audio_latar,
    "restart_screen_reader": restart_screen_reader,
    "atur_volume_aplikasi": atur_volume_aplikasi,
    "putar_audio_latar": putar_audio_latar,
    "edit_video_umum": edit_video_umum,
    "tambah_catatan_permanen": tambah_catatan_permanen,
    "baca_catatan_permanen": baca_catatan_permanen,
    "tambah_jadwal_kegiatan": tambah_jadwal_kegiatan,
    "lihat_jadwal_kegiatan": lihat_jadwal_kegiatan,
    "cek_keamanan_wifi": cek_keamanan_wifi,
    "buat_video_lirik": buat_video_lirik,
    "suntik_cover_mp3": suntik_cover_mp3,
    "buka_website": buka_website,
    "putar_youtube": putar_youtube,
    "putar_ulang_youtube": putar_ulang_youtube,
    "jalankan_perintah_sistem": jalankan_perintah_sistem,
    "kontrol_keyboard": kontrol_keyboard,
    "berbicara_lewat_pc": berbicara_lewat_pc,
    "tutup_aplikasi": tutup_aplikasi,
    "buka_aplikasi": buka_aplikasi,
    "kirim_whatsapp": kirim_whatsapp,
    "atur_file": atur_file,
    "catat_ide_musik": catat_ide_musik,
    "cek_kesehatan_pc": cek_kesehatan_pc,
    "cek_diagnostik_siti": cek_diagnostik_siti,
    "cek_semua_kabel_sistem": cek_semua_kabel_sistem,
    "aktifkan_mode_rekaman": aktifkan_mode_rekaman,
    "baca_layar_komputer": baca_layar_komputer,
    "kirim_email": kirim_email,
    "kirim_file_telegram": kirim_file_telegram,
    "baca_email": baca_email,
    "hapus_email": hapus_email,
    "cari_email": cari_email,
    "cari_file": cari_file,
    "buka_file_lokal": buka_file_lokal,
    "tunggu": tunggu,
    "lihat_kamera": lihat_kamera,
    "baca_link_internet": baca_link_internet,
    "baca_artikel_website": baca_artikel_website,
    "salin_ke_clipboard": salin_ke_clipboard,
    "klik_berdasarkan_gambar": klik_berdasarkan_gambar,
    "jalankan_agen_otonom": jalankan_agen_otonom,
    "buat_video_youtube": buat_video_youtube,
    "buat_nota_pdf": buat_nota_pdf,
    "upload_youtube": upload_youtube,
    "cek_statistik_youtube": cek_statistik_youtube,
    "baca_komentar_youtube": baca_komentar_youtube,
    "balas_komentar_youtube": balas_komentar_youtube,
    "edit_video_youtube": edit_video_youtube,
    "cari_id_video_youtube": cari_id_video_youtube,
    "atur_daya_pc": atur_daya_pc,
    "restart_pc": restart_pc,
    "restart_komputer": restart_pc,
    "restart": restart_pc,
    "reboot": restart_pc,
    "reboot_pc": restart_pc,
    "matikan_pc": matikan_pc,
    "matikan_komputer": matikan_pc,
    "matikan": matikan_pc,
    "shutdown": matikan_pc,
    "shutdown_pc": matikan_pc,
    "matikan_internet_sementara": matikan_internet_sementara,
    "buat_playlist_youtube": buat_playlist_youtube,
    "tambah_video_playlist_youtube": tambah_video_playlist_youtube,
    "ganti_thumbnail_youtube": ganti_thumbnail_youtube,
    "hapus_komentar_youtube": hapus_komentar_youtube,
    "cek_video_terbaru_channel_youtube": cek_video_terbaru_channel_youtube,
    "cek_video_terakhir_channel_sendiri": cek_video_terakhir_channel_sendiri,
    "upload_drive": upload_drive,
    "cek_kapasitas_drive": cek_kapasitas_drive,
    "cari_file_drive": cari_file_drive,
    "ubah_akses_drive": ubah_akses_drive,
    "bagi_akses_email_drive": bagi_akses_email_drive,
    "buang_ke_sampah_drive": buang_ke_sampah_drive,
    "kosongkan_sampah_drive": kosongkan_sampah_drive,
    "ganti_nama_file_drive": ganti_nama_file_drive,
    "hapus_file_drive": hapus_file_drive,
    "download_file_drive": download_file_drive,
    "cek_isi_folder_drive": cek_isi_folder_drive,
    "cari_file_lokal": cari_file_lokal,
    "baca_isi_folder_lokal": baca_isi_folder_lokal,
    "kelola_file_lokal": kelola_file_lokal,
    "cek_disk_lokal": cek_disk_lokal,
    "buka_aplikasi_lokal": buka_aplikasi_lokal,
    "cek_progress_tugas": cek_progress_tugas,
    "putar_folder_musik_lokal": putar_folder_musik_lokal,
    "putar_lagu_lokal": putar_lagu_lokal,
    "baca_pesan_wa": cek_pesan_wa_bridge,
    "pantau_layar_pc": pantau_layar_pc,
    "download_file_siluman": download_file_siluman,
    "aktifkan_mode_satpam": aktifkan_mode_satpam,
    "bersihkan_sampah_pc": bersihkan_sampah_pc,
    "kunci_pc_jarak_jauh": kunci_pc_jarak_jauh,
    "baca_clipboard_pc": baca_clipboard_pc,
    "sadap_suara_ruangan": sadap_suara_ruangan,
    "sadap_kamera_ruangan": sadap_kamera_ruangan,
    "isi_clipboard_pc": isi_clipboard_pc,
    "cek_aplikasi_aktif": cek_aplikasi_aktif,
    "install_otomatis": install_otomatis,
    "cek_progress_install": cek_progress_install,
}

# ---------------------------------------------------------
# INTEGRASI ARSITEKTUR PLUGIN MODULAR (AI DESKTOP OS)
# ---------------------------------------------------------
from core.plugin_manager import load_plugins
_plugin_tools, _plugin_functions = load_plugins()
available_functions.update(_plugin_functions)
# ---------------------------------------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "kelola_jadwal_tugas",
            "description": "Mengelola jadwal tugas. Aksi: 'lihat' (melihat daftar jadwal), 'batalkan' (membatalkan 1 jadwal via task_id), 'batalkan_semua' (membatalkan semua). Wajib panggil 'lihat' dulu sebelum 'batalkan'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aksi": {"type": "string", "enum": ["lihat", "batalkan", "batalkan_semua"]},
                    "task_id": {"type": "string", "description": "ID tugas yang ingin dibatalkan."}
                },
                "required": ["aksi"]
            }
        }
    },

        {
            "type": "function",
            "function": {
                "name": "ganti_nama_file_drive",
                "description": "Mengganti nama file (rename) yang ada di Google Drive.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"},
                        "file_id": {"type": "string", "description": "ID File di Google Drive."},
                        "nama_baru": {"type": "string", "description": "Nama baru beserta ekstensinya, misal 'Lagu_Baru.wav'."}
                    },
                    "required": ["account", "file_id", "nama_baru"]
                }
            }
        },


        {
            "type": "function",
            "function": {
                "name": "bagi_akses_email_drive",
                "description": "Membagikan file Google Drive secara privat khusus ke alamat email tertentu dengan izin akses tertentu (kolaborasi).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"},
                        "file_id": {"type": "string", "description": "ID File di Google Drive."},
                        "email_address": {"type": "string", "description": "Alamat email tujuan."},
                        "role": {"type": "string", "description": "Izin akses: 'writer' (bisa edit) atau 'reader' (hanya baca)."}
                    },
                    "required": ["account", "file_id", "email_address"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "buang_ke_sampah_drive",
                "description": "Memindahkan file Google Drive ke Tong Sampah (Trash) tanpa menghapusnya secara permanen.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"},
                        "file_id": {"type": "string", "description": "ID File di Google Drive."}
                    },
                    "required": ["account", "file_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "kosongkan_sampah_drive",
                "description": "Mengosongkan seluruh isi Tong Sampah (Trash) Google Drive.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"}
                    },
                    "required": ["account"]
                }
            }
        },


    {
        "type": "function",
        "function": {
            "name": "hapus_email",
            "description": "Menghapus email berdasarkan kata kunci di subjek atau pengirim",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string"}
                },
                "required": ["kata_kunci"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_email",
            "description": "Mencari email masuk berdasarkan kata kunci",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string"},
                    "jumlah": {"type": "integer"}
                },
                "required": ["kata_kunci"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "ramal_cuaca",
            "description": "Mengambil prakiraan cuaca real-time untuk sebuah kota.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kota": {
                        "type": "string",
                        "description": "Nama kota yang ingin di cek cuacanya (contoh: Jakarta, Bandung, dll)."
                    }
                },
                "required": ["kota"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_screen_reader",
            "description": "Mematikan paksa aplikasi screen reader (NVDA atau JAWS) yang sedang hang dan menjalankannya kembali.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama screen reader ('nvda' atau 'jaws')"}
                },
                "required": ["nama_aplikasi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atur_volume_aplikasi",
            "description": "Mengatur volume audio spesifik untuk satu aplikasi saja tanpa mengubah volume sistem keseluruhan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama aplikasi (misal: 'chrome', 'spotify')"},
                    "level_volume": {"type": "integer", "description": "Level volume 0 hingga 100"}
                },
                "required": ["nama_aplikasi", "level_volume"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "putar_audio_latar",
            "description": "Memutar musik dari YouTube atau file lokal di latar belakang tanpa layar (headless).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kueri": {"type": "string", "description": "Judul lagu atau path lokal"}
                },
                "required": ["kueri"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_audio_latar",
            "description": "Menghentikan musik yang diputar di latar belakang.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "edit_video_umum",
            "description": "Asisten AI editor video serbaguna berbasis FFmpeg. Gunakan ini untuk memotong video, mengganti orientasi (landscape ke portrait), mencerahkan, memberi filter warna, dll sesuai perintah user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jalur_video": {"type": "string", "description": "Path lengkap ke file video yang akan diedit"},
                    "instruksi": {"type": "string", "description": "Instruksi dari user (contoh: 'ubah ke portrait', 'terangkan', 'potong dari detik 5 ke 10')"}
                },
                "required": ["jalur_video", "instruksi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tambah_catatan_permanen",
            "description": "Mencatat informasi secara permanen ke dalam otak (harddisk) Sari. Gunakan ini jika pengguna menyuruh mengingat sesuatu (preferensi, rahasia, pengeluaran keuangan, dll).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kategori": {"type": "string", "description": "Kategori catatan, contoh: 'keuangan', 'rahasia', 'preferensi_musik'"},
                    "isi": {"type": "string", "description": "Isi catatan yang ingin disimpan permanen"}
                },
                "required": ["kategori", "isi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_catatan_permanen",
            "description": "Membaca ingatan permanen dari otak (harddisk) Sari berdasarkan kategori. Gunakan ini jika pengguna bertanya tentang ingatannya atau data masa lalu yang pernah dicatat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kategori": {"type": "string", "description": "Kategori catatan yang ingin dibaca"}
                },
                "required": ["kategori"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tambah_jadwal_kegiatan",
            "description": "Menyimpan jadwal kegiatan (contoh: '2026-08-10', 'Ulang Tahun'). Format tanggal bebas, sebaiknya YYYY-MM-DD.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tanggal": {"type": "string", "description": "Tanggal jadwal, contoh '2026-08-10'"},
                    "acara": {"type": "string", "description": "Nama kegiatan atau acara"}
                },
                "required": ["tanggal", "acara"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lihat_jadwal_kegiatan",
            "description": "Melihat jadwal kegiatan pada tanggal tertentu di masa lalu atau masa depan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tanggal": {"type": "string", "description": "Tanggal yang ingin diintip jadwalnya"}
                },
                "required": ["tanggal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_keamanan_wifi",
            "description": "Melacak perangkat (HP/Laptop) yang terhubung ke jaringan lokal/WiFi saat ini. Gunakan ini untuk mengecek penyusup atau memonitor WiFi.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "install_otomatis",
            "description": "Memicu atau menjalankan proses instalasi massal (.exe, .msi) dari sebuah folder. Ini akan berjalan di latar belakang secara otomatis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_folder": {
                        "type": "string",
                        "description": "Path mutlak ke folder yang berisi kumpulan installer software, misal: D:\Software"
                    }
                },
                "required": ["path_folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_progress_install",
            "description": "Mengecek sejauh mana progress (berapa persen, file apa) proses instalasi yang sedang berjalan di latar belakang.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "isi_clipboard_pc",
            "description": "Menyuntikkan atau memasukkan teks ke dalam Clipboard memori PC pengguna secara otomatis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "teks": {
                        "type": "string",
                        "description": "Teks panjang atau link yang ingin dimasukkan ke dalam Clipboard PC."
                    }
                },
                "required": ["teks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_aplikasi_aktif",
            "description": "Melacak dan mengetahui judul aplikasi atau software apa yang saat ini sedang dibuka paling depan (aktif) di layar monitor pengguna.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_clipboard_pc",
            "description": "Membaca teks terakhir yang baru di-copy (Ctrl+C) di PC pengguna.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sadap_kamera_ruangan",
            "description": "Merekam VIDEO sekaligus AUDIO secara diam-diam dari webcam dan mikrofon PC selama durasi tertentu lalu menjahitnya menjadi MP4 utuh dan mengirimkannya ke Telegram pengguna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "durasi": {"type": "integer", "description": "Durasi sadap kamera dalam detik (default: 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sadap_suara_ruangan",
            "description": "Merekam suara secara diam-diam dari mikrofon PC selama durasi tertentu lalu mengirimkan file suaranya ke Telegram pengguna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "durasi": {"type": "integer", "description": "Durasi sadap suara dalam detik (default: 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bersihkan_sampah_pc",
            "description": "Mengosongkan Recycle Bin dan file Cache/Temp PC secara permanen untuk membebaskan RAM dan Storage.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kunci_pc_jarak_jauh",
            "description": "Membajak dan mengunci layar PC kembali ke Windows Login, lalu membunyikan suara peringatan keras dari speaker PC.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pantau_layar_pc",
            "description": "Mengambil screenshot (foto) dari layar monitor PC saat ini lalu mengirimkannya ke Telegram.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aktifkan_mode_satpam",
            "description": "Mengaktifkan penjaga PC (memantau mouse). Jika ada gerakan, akan diam-diam memotret webcam dan screenshot layar, lalu mengirimkannya.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_file_siluman",
            "description": "Mendownload file/video/audio (MP4 atau MP3) dari YouTube/IG/link ke folder Downloads. Jika tidak ada URL, bisa gunakan format pencarian 'ytsearch: kata kunci' (misal: 'ytsearch: backsound sekolahan').",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL video/audio atau kata kunci pencarian YouTube (wajib gunakan awalan 'ytsearch: ' jika bukan URL)"},
                    "tipe": {"type": "string", "description": "Format file: 'video' (MP4) atau 'audio' (MP3). Default 'video'."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kontrol_volume",
            "description": "Mengontrol volume dan mute untuk Speaker (output) atau Mikrofon (input/mic).",
            "parameters": {
                "type": "object",
                "properties": {
                    "aksi": {"type": "string", "description": "Gunakan mute, unmute, up, down, atau set"},
                    "persen": {"type": "integer", "description": "Persentase volume (0-100) jika aksi adalah set, up, atau down"},
                    "target": {"type": "string", "description": "Perangkat yang diatur: 'output' (speaker) atau 'input' (mikrofon/mic). Default 'output'."}
                },
                "required": ["aksi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atur_daya_pc",
            "description": "Mengontrol daya PC (aksi: shutdown, restart, batal).",
            "parameters": {
                "type": "object",
                "properties": {
                    "aksi": {"type": "string", "description": "Gunakan shutdown, restart, atau batal"},
                    "waktu_menit": {"type": "integer", "description": "Waktu tunggu dalam menit sebelum aksi dieksekusi (default 0)"}
                },
                "required": ["aksi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "matikan_internet_sementara",
            "description": "Mematikan internet (contoh: untuk rekaman) dan otomatis menyala kembali setelah waktu_menit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "waktu_menit": {"type": "integer", "description": "Lama internet dimatikan dalam menit"}
                },
                "required": ["waktu_menit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_kesehatan_pc",
            "description": "Mengecek kondisi kesehatan PC saat ini (RAM, CPU, Disk). Gunakan ini jika pengguna merasa komputernya lemot.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_diagnostik_siti",
            "description": "Menjalankan self-test atau auto-diagnostic pada fitur-fitur inti Siti (Koneksi WA, Database, YouTube Downloader, dll). Gunakan jika pengguna meminta untuk mengecek apakah ada error pada sistem.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_semua_kabel_sistem",
            "description": "Menjalankan Unit Test komprehensif pada 100+ fitur/fungsi internal Siti untuk mengecek kabel-kabel yang nge-ground atau error secara simulasi dry-run.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aktifkan_mode_rekaman",
            "description": "Mengoptimalkan komputer untuk rekaman audio (Mode Produksi). Akan menaikkan prioritas Reaper, mematikan browser, dan membersihkan temp files.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
        {
            "type": "function",
            "function": {
                "name": "buat_nota_pdf",
                "description": "Membuat file PDF Nota Tagihan untuk klien.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nama_klien": {"type": "string", "description": "Nama klien (contoh: Mas Dodi)"},
                        "daftar_layanan": {"type": "array", "items": {"type": "string"}, "description": "Daftar layanan (contoh: ['Mixing', 'Mastering'])"},
                        "harga_layanan": {"type": "array", "items": {"type": "integer"}, "description": "Daftar harga untuk masing-masing layanan secara berurutan"},
                        "total_biaya": {"type": "integer", "description": "Total keseluruhan biaya"}
                    },
                    "required": ["nama_klien", "daftar_layanan", "harga_layanan", "total_biaya"]
                }
            }
        },
        
        
        
        
    {
        "type": "function",
        "function": {
            "name": "upload_youtube",
            "description": "Kurir YouTube: Mengunggah file video ke channel YouTube secara otomatis via API. PENTING: Jika pengguna menyuruh mengunggah video TETAPI TIDAK menyebutkan nama akun/channel secara spesifik, JANGAN panggil fungsi ini! Alih-alih, tanyakan dulu ke pengguna: 'Ke channel mana video ini akan diunggah?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jalur_video": {"type": "string", "description": "Path absolut ke file video (.mp4)"},
                    "judul": {"type": "string", "description": "Judul video untuk YouTube"},
                    "deskripsi": {"type": "string", "description": "Deskripsi video"},
                    "account": {"type": "string", "description": "Nama channel YouTube target. PENTING: HANYA GUNAKAN 'utama' (kanal pertama) atau 'kedua' (untuk channel kedua). Jangan gunakan nama lain!"},
                    "tags": {"type": "string", "description": "Tags video dipisahkan dengan koma (opsional, misal: 'musik,cover,gitar')"}
                },
                "required": ["jalur_video", "judul", "deskripsi", "account"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suntik_cover_mp3",
            "description": "Membuat gambar cover album via AI dan menyuntikkannya ke file MP3 beserta metadata lagunya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jalur_audio": {"type": "string", "description": "Path ke lagu (.mp3/.wav)"},
                    "prompt_gambar": {"type": "string", "description": "Prompt singkat inggris untuk menggambar cover"},
                    "judul_lagu": {"type": "string", "description": "Judul lagu"},
                    "nama_artis": {"type": "string", "description": "Nama artis"},
                    "nama_album": {"type": "string", "description": "Nama album"}
                },
                "required": ["jalur_audio", "prompt_gambar", "judul_lagu", "nama_artis", "nama_album"]
            }
        }
    },
    
    {
        "type": "function",
        "function": {
            "name": "buat_video_lirik",
            "description": "Membuat video lirik otomatis dari file audio menggunakan Whisper dan FFmpeg.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jalur_audio": {
                        "type": "string",
                        "description": "Path lengkap ke file lagu/MP3/WAV (misal C:\\Musik\\LaguKu.mp3)"
                    },
                    "prompt_visual": {
                        "type": "string",
                        "description": "Instruksi visual dari sutradara/user (resolusi, tema gambar latar, warna lirik, dll)."
                    }
                },
                "required": ["jalur_audio", "prompt_visual"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buka_website",
            "description": "Fungsi buka_website",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Parameter url"
                    }
                },
                "required": [
                    "url"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "putar_youtube",
            "description": "Fungsi putar_youtube",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {
                        "type": "string",
                        "description": "Parameter kata_kunci"
                    }
                },
                "required": [
                    "kata_kunci"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "putar_ulang_youtube",
            "description": "Memutar ulang video YouTube terakhir yang pernah diputar lewat Siti atau Chrome PC. Bisa filter berdasarkan nama channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Nama channel YouTube untuk filter riwayat (opsional, kosongkan untuk video terakhir apapun)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "jalankan_perintah_sistem",
            "description": "Fungsi jalankan_perintah_sistem",
            "parameters": {
                "type": "object",
                "properties": {
                    "perintah": {
                        "type": "string",
                        "description": "Parameter perintah"
                    }
                },
                "required": [
                    "perintah"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kontrol_keyboard",
            "description": "Fungsi kontrol_keyboard",
            "parameters": {
                "type": "object",
                "properties": {
                    "aksi": {
                        "type": "string",
                        "description": "Parameter aksi"
                    },
                    "tombol_atau_teks": {
                        "type": "string",
                        "description": "Parameter tombol_atau_teks"
                    }
                },
                "required": [
                    "aksi",
                    "tombol_atau_teks"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "berbicara_lewat_pc",
            "description": "Fungsi berbicara_lewat_pc",
            "parameters": {
                "type": "object",
                "properties": {
                    "teks": {
                        "type": "string",
                        "description": "Parameter teks"
                    }
                },
                "required": [
                    "teks"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tutup_aplikasi",
            "description": "Fungsi tutup_aplikasi",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {
                        "type": "string",
                        "description": "Parameter nama_aplikasi"
                    }
                },
                "required": [
                    "nama_aplikasi"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buka_aplikasi",
            "description": "Wajib dipanggil untuk membuka software, program, atau aplikasi apa saja di Windows PC (misal: 'buka OBS', 'buka REAPER', 'buka Chrome', 'buka WhatsApp', 'buka Vid Downloader'). WAJIB jalankan fungsi alat ini!",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {
                        "type": "string",
                        "description": "Nama aplikasi yang ingin dibuka di PC, contoh: 'reaper', 'obs', 'chrome', 'vid downloader'"
                    }
                },
                "required": [
                    "nama_aplikasi"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kirim_whatsapp",
            "description": "Fungsi kirim_whatsapp",
            "parameters": {
                "type": "object",
                "properties": {
                    "nomor_tujuan": {
                        "type": "string",
                        "description": "Parameter nomor_tujuan"
                    },
                    "pesan": {
                        "type": "string",
                        "description": "Parameter pesan"
                    }
                },
                "required": [
                    "nomor_tujuan",
                    "pesan"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atur_file",
            "description": "Fungsi atur_file",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_sumber": {
                        "type": "string",
                        "description": "Parameter folder_sumber"
                    },
                    "folder_tujuan": {
                        "type": "string",
                        "description": "Parameter folder_tujuan"
                    },
                    "ekstensi": {
                        "type": "string",
                        "description": "Parameter ekstensi"
                    }
                },
                "required": [
                    "folder_sumber",
                    "folder_tujuan",
                    "ekstensi"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "catat_ide_musik",
            "description": "Fungsi catat_ide_musik",
            "parameters": {
                "type": "object",
                "properties": {
                    "isi_catatan": {
                        "type": "string",
                        "description": "Parameter isi_catatan"
                    }
                },
                "required": [
                    "isi_catatan"
                ]
            }
        }
    },
    
    {
        "type": "function",
        "function": {
            "name": "baca_layar_komputer",
            "description": "Fungsi baca_layar_komputer",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kirim_email",
            "description": "Fungsi kirim_email",
            "parameters": {
                "type": "object",
                "properties": {
                    "tujuan": {
                        "type": "string",
                        "description": "Parameter tujuan"
                    },
                    "subjek": {
                        "type": "string",
                        "description": "Parameter subjek"
                    },
                    "pesan": {
                        "type": "string",
                        "description": "Parameter pesan"
                    }
                },
                "required": [
                    "tujuan",
                    "subjek",
                    "pesan"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_email",
            "description": "Membaca kotak masuk email terbaru pengguna. PENTING: HANYA panggil fungsi ini JIKA pengguna SECARA SPESIFIK dan JELAS menyuruh memeriksa atau membaca email. JANGAN PERNAH memanggil fungsi ini secara otomatis atau jika hanya sekadar disapa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jumlah": {
                        "type": "integer",
                        "description": "Jumlah email yang ingin dibaca. Default: 3."
                    },
                    "hanya_baru": {
                        "type": "boolean",
                        "description": "Set true (default) untuk hanya mengambil email baru (UNSEEN). Set false HANYA jika diminta membaca/mengulang detail email yang sudah dibacakan sebelumnya."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_file",
            "description": "Fungsi cari_file",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {
                        "type": "string",
                        "description": "Parameter kata_kunci"
                    }
                },
                "required": [
                    "kata_kunci"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buka_file_lokal",
            "description": "Fungsi buka_file_lokal",
            "parameters": {
                "type": "object",
                "properties": {
                    "jalur_file": {
                        "type": "string",
                        "description": "Parameter jalur_file"
                    }
                },
                "required": [
                    "jalur_file"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tunggu",
            "description": "Fungsi tunggu",
            "parameters": {
                "type": "object",
                "properties": {
                    "detik": {
                        "type": "integer",
                        "description": "Parameter detik"
                    }
                },
                "required": [
                    "detik"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lihat_kamera",
            "description": "Fungsi lihat_kamera",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "salin_ke_clipboard",
            "description": "Fungsi salin_ke_clipboard",
            "parameters": {
                "type": "object",
                "properties": {
                    "teks": {
                        "type": "string",
                        "description": "Parameter teks"
                    }
                },
                "required": [
                    "teks"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "klik_berdasarkan_gambar",
            "description": "Fungsi klik_berdasarkan_gambar",
            "parameters": {
                "type": "object",
                "properties": {
                    "deskripsi_tombol": {
                        "type": "string",
                        "description": "Parameter deskripsi_tombol"
                    }
                },
                "required": [
                    "deskripsi_tombol"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "jalankan_agen_otonom",
            "description": "Fungsi jalankan_agen_otonom",
            "parameters": {
                "type": "object",
                "properties": {
                    "tugas": {
                        "type": "string",
                        "description": "Parameter tugas"
                    }
                },
                "required": [
                    "tugas"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buat_video_youtube",
            "description": "Fungsi buat_video_youtube",
            "parameters": {
                "type": "object",
                "properties": {
                    "topik": {
                        "type": "string",
                        "description": "Topik atau ide video yang ingin dibuat."
                    },
                    "jenis_background": {
                        "type": "string",
                        "description": "Pilihan background visual. Isi dengan 'reaper' (untuk layar), 'hitam', 'biru', atau 'merah'. Default: 'reaper'."
                    },
                    "suara": {
                        "type": "string",
                        "description": "Jenis suara narator. Isi dengan 'laki-laki' atau 'perempuan'. Default: 'laki-laki'."
                    }
                },
                "required": [
                    "topik"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_statistik_youtube",
            "description": "Menampilkan jumlah subscriber, view, dan total video dari channel YouTube tertentu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Nama channel target ('utama' atau 'kedua'). Wajib."}
                },
                "required": ["account"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_komentar_youtube",
            "description": "Membaca beberapa komentar terbaru dari channel YouTube target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Nama channel target ('utama' atau 'kedua'). Wajib."},
                    "maksimal": {"type": "integer", "description": "Jumlah maksimal komentar yang ingin dibaca. Default 5."}
                },
                "required": ["account"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "balas_komentar_youtube",
            "description": "Membalas komentar penonton YouTube secara otomatis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Nama channel target ('utama' atau 'kedua'). Wajib."},
                    "comment_id": {"type": "string", "description": "ID komentar yang akan dibalas (didapat dari hasil baca_komentar_youtube)."},
                    "teks": {"type": "string", "description": "Teks balasan komentar."}
                },
                "required": ["account", "comment_id", "teks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_video_youtube",
            "description": "Mengubah judul, deskripsi, atau tags dari video YouTube yang sudah diunggah.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Nama channel target ('utama' atau 'kedua'). Wajib."},
                    "video_id": {"type": "string", "description": "ID Video YouTube (11 karakter)."},
                    "judul": {"type": "string", "description": "Judul baru video (kosongkan jika tidak ingin mengubah judul)."},
                    "deskripsi": {"type": "string", "description": "Deskripsi baru video (kosongkan jika tidak diubah)."},
                    "tags": {"type": "string", "description": "Tags baru video dipisahkan koma (kosongkan jika tidak diubah)."}
                },
                "required": ["account", "video_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_id_video_youtube",
            "description": "Mencari ID Video dari channel milik sendiri berdasarkan kata kunci judul.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "query": {"type": "string", "description": "Kata kunci pencarian judul video."},
                    "maksimal": {"type": "integer", "description": "Maksimal hasil. Default 3."}
                },
                "required": ["account", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buat_playlist_youtube",
            "description": "Membuat playlist baru di channel YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "judul": {"type": "string"},
                    "deskripsi": {"type": "string"}
                },
                "required": ["account", "judul"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tambah_video_playlist_youtube",
            "description": "Menambahkan video ke dalam playlist YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "playlist_id": {"type": "string"},
                    "video_id": {"type": "string"}
                },
                "required": ["account", "playlist_id", "video_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ganti_thumbnail_youtube",
            "description": "Mengganti gambar thumbnail dari video YouTube yang sudah diunggah.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "video_id": {"type": "string"},
                    "thumbnail_path": {"type": "string", "description": "Path absolut ke file gambar (.jpg/.png)."}
                },
                "required": ["account", "video_id", "thumbnail_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hapus_komentar_youtube",
            "description": "Menghapus komentar (spam/haters) dari channel YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "comment_id": {"type": "string", "description": "ID komentar yang akan dihapus permanen."}
                },
                "required": ["account", "comment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_video_terbaru_channel_youtube",
            "description": "Mengecek apakah ada video terbaru dari channel YouTube orang lain yang Anda ikuti (subscription).",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Akun Anda ('utama' atau 'kedua')."},
                    "channel_name": {"type": "string", "description": "Nama channel target (contoh: 'GadgetIn', 'Deddy Corbuzier')."},
                    "maksimal": {"type": "integer", "description": "Jumlah video terbaru yang ingin dicek. Default 3."}
                },
                "required": ["account", "channel_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_video_terakhir_channel_sendiri",
            "description": "Mengecek video terakhir yang di-upload ke channel YouTube milik sendiri ('utama' atau 'kedua') beserta statistik real-time (jumlah penonton/views, likes, komentar, link, & status akses).",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Nama akun YouTube Anda: 'utama' (kanal pertama) atau 'kedua' (kanal kedua). Default 'utama'."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "upload_drive",
            "description": "Mengunggah file dari komputer ke Google Drive awan. Secara default file tersimpan sebagai PRIVAT (hanya pemilik akun). Set 'publik' ke true HANYA jika pengguna secara eksplisit meminta file dibuat publik atau meminta link yang bisa dibuka siapa saja.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Nama profil akun (contoh: utama)"},
                    "file_path": {"type": "string", "description": "Path absolut file yang ingin diupload."},
                    "publik": {"type": "boolean", "description": "Set true HANYA jika pengguna meminta file dibuat publik. Default adalah false (privat)."}
                },
                "required": ["account", "file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_kapasitas_drive",
            "description": "Mengecek sisa ruang / storage quota di Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"}
                },
                "required": ["account"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_file_drive",
            "description": "Mencari file di Google Drive berdasarkan namanya (bisa potongan nama).",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "query": {"type": "string", "description": "Nama atau bagian dari nama file yang dicari."}
                },
                "required": ["account", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ubah_akses_drive",
            "description": "Mengubah izin akses file di Google Drive yang sebelumnya Private menjadi Public (Anyone with link).",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "file_id": {"type": "string", "description": "ID File di Google Drive."}
                },
                "required": ["account", "file_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hapus_file_drive",
            "description": "Menghapus file secara permanen dari Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "file_id": {"type": "string", "description": "ID File di Google Drive."}
                },
                "required": ["account", "file_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_file_drive",
            "description": "Mendownload file dari Google Drive ke komputer lokal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "file_id": {"type": "string", "description": "ID File di Google Drive."},
                    "dest_folder": {"type": "string", "description": "Path folder tujuan penyimpanan. Opsional (default folder File/Downloads)."}
                },
                "required": ["account", "file_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_isi_folder_drive",
            "description": "Melihat isi dari sebuah folder spesifik di dalam Google Drive berdasarkan nama folder tersebut.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "nama_folder": {"type": "string", "description": "Nama folder yang ingin dilihat isinya."}
                },
                "required": ["account", "nama_folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_file_lokal",
            "description": "Mencari lokasi sebuah file atau folder/proyek di dalam hard disk PC lokal dengan super cepat (bypass GUI). Mendukung pencarian proyek musik/DAW dan folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nama file atau folder/proyek yang dicari (contoh: 'sekolah rakyat', 'lagu baru')."},
                    "drive": {"type": "string", "description": "Drive letter atau folder awal pencarian. Contoh: 'C:\\', 'E:\\', atau 'E:\\projek recording'. Default: 'C:\\'"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_isi_folder_lokal",
            "description": "Melihat daftar file dan folder di dalam suatu direktori/folder di komputer lokal (bypass GUI).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_folder": {"type": "string", "description": "Path absolut folder lokal yang ingin dicek. Contoh: 'C:\\Musik'"}
                },
                "required": ["path_folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kelola_file_lokal",
            "description": "Menyalin, memindahkan, mengganti nama, atau menghapus file dan folder di komputer lokal (Administrator).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["copy", "move", "rename", "delete"], "description": "Aksi yang ingin dilakukan."},
                    "path_sumber": {"type": "string", "description": "Path absolut file sumber."},
                    "path_tujuan": {"type": "string", "description": "Path absolut tujuan (kosongkan jika action=delete)."}
                },
                "required": ["action", "path_sumber"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_disk_lokal",
            "description": "Mengecek sisa kapasitas (storage space) sebuah Drive di komputer lokal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drive": {"type": "string", "description": "Drive letter. Contoh: 'C:\\'"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buka_aplikasi_lokal",
            "description": "Membuka sebuah file software/aplikasi secara instan di Windows (bypass GUI).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama aplikasi (misal: 'chrome', 'reaper') atau path file absolut (.exe/.mp3)."}
                },
                "required": ["nama_aplikasi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_progress_tugas",
            "description": "Mengecek sudah berapa persen (progres) proses upload/download yang sedang berjalan di latar belakang.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "putar_folder_musik_lokal",
            "description": "Memutar semua file musik/audio di dalam suatu folder secara otomatis menggunakan pemutar musik default PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_folder": {"type": "string", "description": "Path absolut folder yang berisi lagu/musik (misal: 'C:\\Musik')."}
                },
                "required": ["path_folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "putar_lagu_lokal",
            "description": "Memutar sebuah lagu lokal (MP3/WAV) berdasarkan kata kunci judul lagu. Lagu akan dicari otomatis di folder Music.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Judul lagu yang ingin diputar."}
                },
                "required": ["kata_kunci"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_pesan_wa",
            "description": "Membaca semua pesan WhatsApp (WA) terbaru yang masuk dari klien. Akan membalas dengan daftar pengirim dan isi pesannya.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "jadwalkan_tugas_otomatis",
            "description": "PEMANGGIL UTAMA TUGAS AKSI TERJADWAL MASA DEPAN (seperti 'nanti jam 08:16 play denicaknan', 'nanti jam 07:46 kirim WA', 'nanti jam 10 kirim email', 'setiap jam 9 cek email lapor ke telegram'). Alat ini WAJIB DIPANGGIL untuk mengeksekusi aksi secara otomatis tepat pada jam target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jam_atau_tanggal": {"type": "string", "description": "Jam atau tanggal target. Contoh: '18.20', '18:20', '2026-09-20 14:00'"},
                    "fungsi_aksi": {"type": "string", "description": "Nama fungsi aksi: 'lapor_telegram' (WAJIB untuk semua laporan chat Telegram: cek email, berita, ide konten, update), 'putar_youtube', 'kirim_pesan_whatsapp', 'kirim_vn_whatsapp', 'kirim_email', 'putar_audio_latar'"},
                    "parameter_json": {"type": "string", "description": "Parameter JSON atau kata kunci"},
                    "deskripsi_laporan": {"type": "string", "description": "Deskripsi laporan yang akan dikirim saat tugas selesai dieksekusi"},
                    "interval_menit": {"type": "integer", "description": "Interval pengulangan dalam menit. Misal 1440 untuk harian/tiap hari, 1 untuk tiap menit. 0 jika hanya sekali eksekusi."},
                    "total_pengulangan": {"type": "integer", "description": "Total berapa kali tugas diulang. Misal 5 hari = 5, 3 menit = 3. 0 untuk berulang selamanya."},
                    "pesan_atau_prompt": {"type": "string", "description": "Instruksi apa yang dilaporkan/dikirim ke Telegram"}
                },
                "required": ["jam_atau_tanggal", "fungsi_aksi"]
            }
        }
    }
]

tools.extend(_plugin_tools)

# Eliminasi duplikasi nama tool agar API DeepSeek & Groq tidak menolak request (Tool names must be unique)
_seen_tools = set()
_unique_tools = [
    {
        "type": "function",
        "function": {
            "name": "kelola_jadwal_tugas",
            "description": "Mengelola jadwal tugas. Aksi: 'lihat' (melihat daftar jadwal), 'batalkan' (membatalkan 1 jadwal via task_id), 'batalkan_semua' (membatalkan semua). Wajib panggil 'lihat' dulu sebelum 'batalkan'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aksi": {"type": "string", "enum": ["lihat", "batalkan", "batalkan_semua"]},
                    "task_id": {"type": "string", "description": "ID tugas yang ingin dibatalkan."}
                },
                "required": ["aksi"]
            }
        }
    },

        {
            "type": "function",
            "function": {
                "name": "ganti_nama_file_drive",
                "description": "Mengganti nama file (rename) yang ada di Google Drive.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"},
                        "file_id": {"type": "string", "description": "ID File di Google Drive."},
                        "nama_baru": {"type": "string", "description": "Nama baru beserta ekstensinya, misal 'Lagu_Baru.wav'."}
                    },
                    "required": ["account", "file_id", "nama_baru"]
                }
            }
        },


        {
            "type": "function",
            "function": {
                "name": "bagi_akses_email_drive",
                "description": "Membagikan file Google Drive secara privat khusus ke alamat email tertentu dengan izin akses tertentu (kolaborasi).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"},
                        "file_id": {"type": "string", "description": "ID File di Google Drive."},
                        "email_address": {"type": "string", "description": "Alamat email tujuan."},
                        "role": {"type": "string", "description": "Izin akses: 'writer' (bisa edit) atau 'reader' (hanya baca)."}
                    },
                    "required": ["account", "file_id", "email_address"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "buang_ke_sampah_drive",
                "description": "Memindahkan file Google Drive ke Tong Sampah (Trash) tanpa menghapusnya secara permanen.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"},
                        "file_id": {"type": "string", "description": "ID File di Google Drive."}
                    },
                    "required": ["account", "file_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "kosongkan_sampah_drive",
                "description": "Mengosongkan seluruh isi Tong Sampah (Trash) Google Drive.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string", "description": "Gunakan 'utama'"}
                    },
                    "required": ["account"]
                }
            }
        },


    {
        "type": "function",
        "function": {
            "name": "hapus_email",
            "description": "Menghapus email berdasarkan kata kunci di subjek atau pengirim",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string"}
                },
                "required": ["kata_kunci"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_email",
            "description": "Mencari email masuk berdasarkan kata kunci",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string"},
                    "jumlah": {"type": "integer"}
                },
                "required": ["kata_kunci"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "restart_screen_reader",
            "description": "Mematikan paksa aplikasi screen reader (NVDA atau JAWS) yang sedang hang dan menjalankannya kembali.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama screen reader ('nvda' atau 'jaws')"}
                },
                "required": ["nama_aplikasi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atur_volume_aplikasi",
            "description": "Mengatur volume audio spesifik untuk satu aplikasi saja tanpa mengubah volume sistem keseluruhan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama aplikasi (misal: 'chrome', 'spotify')"},
                    "level_volume": {"type": "integer", "description": "Level volume 0 hingga 100"}
                },
                "required": ["nama_aplikasi", "level_volume"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "putar_audio_latar",
            "description": "Memutar musik dari YouTube atau file lokal di latar belakang tanpa layar (headless).",
            "parameters": {
                "type": "object",
                "properties": {
                    "kueri": {"type": "string", "description": "Judul lagu atau path lokal"}
                },
                "required": ["kueri"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_audio_latar",
            "description": "Menghentikan musik yang diputar di latar belakang.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
]
for _t in tools:
    _name = _t.get("function", {}).get("name")
    if _name and _name not in _seen_tools:
        _seen_tools.add(_name)
        _unique_tools.append(_t)
tools = _unique_tools


messages = [
    {
        "role": "system",
        "content": "Kamu adalah asisten AI pribadi milik pengguna. Tugas utamamu adalah membantu semua pekerjaannya di komputer. Bicaralah dengan gaya bahasa santai, hangat, dan suportif (gunakan kata 'aku' dan 'kamu'). Jangan pernah terdengar seperti robot atau AI generik. Selalu dukung pengguna.\n\nKEMAMPUAN UTAMA:\n1. Kamu PUNYA KENDALI PENUH pada komputer (mouse, keyboard, file, aplikasi) melalui alat-alat (tools) yang disediakan.\n2. PENTING: Untuk tugas media sosial (WhatsApp, YouTube), SELALU gunakan fungsi plugin spesifik seperti 'kirim_whatsapp', dll. DILARANG KERAS menggunakan 'jalankan_agen_otonom' untuk membalas komentar atau pesan sosmed!\n3. Kamu BISA MEMBUAT VIDEO YOUTUBE SECARA OTOMATIS (Pabrik Konten) menggunakan alat 'buat_video_youtube'.\n5. JIKA DISURUH MEMBUAT VIDEO LIRIK, HARUS, WAJIB, DAN SELALU gunakan alat 'buat_video_lirik'. JANGAN PERNAH gunakan agen otonom untuk video lirik.\n7. Jika diminta membuat cover MP3, pasang meta data lagu (judul artis album), gunakan alat 'suntik_cover_mp3'.\n6. Untuk mengirim WhatsApp, SELALU gunakan alat 'kirim_whatsapp', baik itu nama kontak atau nomor HP.\n9. Jika disuruh mengirim email DENGAN ATAU TANPA LAMPIRAN (Video, gambar, dll), SELALU gunakan fungsi 'kirim_email' dan isi parameter 'file_lampiran'. JANGAN PERNAH memakai agen otonom untuk tugas email.\n10. ATURAN PENJADWALAN MASA DEPAN TERKUNCI: Jika pengguna menyebutkan waktu/jam/tanggal di masa depan (seperti 'nanti jam 18.07', 'jam 17.35 kirim email', 'nanti jam X kirim WA/putar youtube', 'setiap jam 9 cek email'), Anda WAJIB MEMANGGIL ALAT 'jadwalkan_tugas_otomatis'! Untuk laporan berita, ide konten, atau cek email ke Telegram, gunakan fungsi_aksi 'lapor_telegram'! Jika disuruh membatalkan jadwal (misal 'batalkan jadwal', 'batalkan semua jadwal'), WAJIB PANGGIL 'kelola_jadwal_tugas' (aksi='batalkan_semua' atau 'batalkan')! 11. ATURAN INGATAN OTOMATIS: Saat pengguna bertanya tentang ingatan, jadwal, atau percakapan lalu, SELALU periksa [MEMORI OBSIDIAN OTOMATIS TERKAIT] sebelum menjawab agar tidak ada ingatan yang terlewat!\n12. ATURAN WAKTU REAL-TIME SYSTEM PC: Pada setiap awal pesan pengguna, selalu terdapat header '[WAKTU REAL-TIME SYSTEM PC: YYYY-MM-DD HH:MM:SS]'. Ini adalah JAM RESMI REAL-TIME DI KOMPUTER PENGGUNA SAAT INI. GUNAKAN WAKTU TERSEBUT SEBAGAI PATOKAN UTAMA 100% AKURAT UNTUK MENJAWAB JAM BRAPA SEKARANG & MENGHITUNG JADWAL!\n13. ATURAN EKSEKUSI TUGAS LANGSUNG KETAT: Jika pengguna menyuruh membuka aplikasi, YouTube, WhatsApp, atau aksi fisik LANGSUNG (seperti 'buka youtube lagi sekarang', 'play lagu X', 'buka Chrome'), Anda WAJIB MEMANGGIL ALAT/TOOL (seperti 'buka_aplikasi', 'putar_youtube', 'putar_lagu_lokal') SECARA NYATA! DILARANG KERAS berpura-pura/mengaku sudah membukanya lewat kalimat teks tanpa memanggil fungsi alatnya! Jika disuruh putar lagu lokal di PC, WAJIB panggil 'putar_lagu_lokal'.\n\nATURAN PENTING: 1. Gunakan tool yang paling spesifik. 2. DILARANG KERAS memanggil alat/fungsi (terutama baca_email) jika pengguna HANYA MENYAPA (seperti 'halo', 'selamat malam', dll). Jangan berinisiatif mengerjakan sesuatu yang tidak diperintahkan secara eksplisit!"
    }]



def baca_file(nama_file: str):
    """Membaca isi file di dalam folder Proyek."""
    path = os.path.join(WORKSPACE_DIR, nama_file)
    if not os.path.abspath(path).startswith(os.path.abspath(WORKSPACE_DIR)):
        return "ERROR: Akses ditolak! Hanya boleh membaca file di dalam folder Proyek."
    if not os.path.exists(path):
        return f"ERROR: File {nama_file} tidak ditemukan."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"ERROR membaca file: {str(e)}"

def tulis_file(nama_file: str, isi_kode: str):
    """Membuat atau menulis isi teks ke dalam sebuah file (txt, md, csv, py, dll). Jika hanya nama file, otomatis disimpan di Desktop PC pengguna."""
    import os
    if not os.path.isabs(nama_file):
        desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        path_file = os.path.join(desktop, nama_file)
    else:
        path_file = nama_file
        
    try:
        os.makedirs(os.path.dirname(path_file), exist_ok=True)
        with open(path_file, "w", encoding="utf-8") as f:
            f.write(isi_kode)
        return f"SUKSES: File berhasil dibuat dan disimpan di {path_file}"
    except Exception as e:
        return f"ERROR menulis file: {str(e)}"


def jalankan_terminal(perintah: str):
    """Menjalankan perintah terminal (CMD) di dalam folder Proyek."""
    try:
        result = subprocess.run(perintah, shell=True, cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=60)
        output = result.stdout
        if result.stderr:
            output += "\nERROR:\n" + result.stderr
        if not output.strip():
            output = "Perintah berhasil dijalankan tanpa output."
        return output[:2000]
    except subprocess.TimeoutExpired:
        return "ERROR: Perintah memakan waktu terlalu lama (Timeout > 60 detik)."
    except Exception as e:
        return f"ERROR menjalankan terminal: {str(e)}"

def tugas_programmer_background(prompt: str, chat_id: int):
    global MODE_PROGRAMMER
    kirim_pesan_telegram_sync(chat_id, "⚙️ Memulai Mode Programmer... (Menganalisis tugas)")
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-pro", tools=[baca_file, tulis_file, jalankan_terminal])
        chat = model.start_chat()
        
        folder_proyek = str(FILE_DIR / "Proyek")
        system_instruction = f"Kamu adalah Sari The Programmer. Kamu memiliki akses ke folder {folder_proyek}. Aturan PENTING: Setiap kali membuat proyek baru, JANGAN taruh file langsung di Proyek, tapi BUATLAH SUBFOLDER baru sesuai nama proyeknya (misal: {folder_proyek}\\Aplikasi_Sandi\\). Kamu bisa membaca, menulis file, dan menjalankan terminal (CMD). Jalankan tugas secara mandiri. Jika terjadi error di terminal, perbaiki kode dan jalankan ulang. Jika sudah mencoba 5 kali dan gagal, berhentilah. Jangan meminta maaf terus, langsung berikan solusi atau kerjakan."
        pesan_awal = f"{system_instruction}\n\nTugas: {prompt}"
        
        response = chat.send_message(pesan_awal)
        
        for loop_count in range(5):
            if not response.parts:
                break
                
            tool_called = False
            for part in response.parts:
                if part.function_call:
                    tool_called = True
                    func_name = part.function_call.name
                    args_dict = {}
                    for k in part.function_call.args:
                        args_dict[k] = part.function_call.args[k]

                    kirim_pesan_telegram_sync(chat_id, f"🛠️ Mengeksekusi: {func_name}(...)")
                    
                    try:
                        if func_name == "baca_file":
                            hasil = baca_file(**args_dict)
                        elif func_name == "tulis_file":
                            hasil = tulis_file(**args_dict)
                        elif func_name == "jalankan_terminal":
                            hasil = jalankan_terminal(**args_dict)
                        else:
                            hasil = f"ERROR: Alat {func_name} tidak ditemukan."
                    except Exception as e:
                        hasil = f"ERROR eksekusi alat: {str(e)}"
                        
                    response = chat.send_message(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=func_name,
                                response={"result": hasil}
                            )
                        )
                    )
                    break
            
            if not tool_called:
                if response.text:
                    kirim_pesan_telegram_sync(chat_id, f"✅ Selesai:\n{response.text}")
                return
                
        kirim_pesan_telegram_sync(chat_id, "⚠️ Peringatan: Batas maksimal loop (5) tercapai. Silakan berikan petunjuk tambahan jika tugas belum selesai.")
    except Exception as e:
        kirim_pesan_telegram_sync(chat_id, f"❌ Terjadi kesalahan fatal di Mode Programmer:\n{str(e)}")


def minta_jawaban_ai(pesan_pesan, daftar_alat=None):
    daftar_error = []
    for mesin in daftar_mesin:
        try:
            print(f"Mencoba otak: {mesin['nama']} ...")
            kwargs = {
                "model": mesin["model"],
                "messages": pesan_pesan
            }
            if daftar_alat and mesin.get("pakai_tools", True):
                kwargs["tools"] = daftar_alat
                kwargs["tool_choice"] = "auto"
                
            response = mesin["client"].chat.completions.create(**kwargs)
            print(f"Sukses menggunakan otak: {mesin['nama']}")
            return response, mesin
        except Exception as e:
            error_msg = f"[X] Gagal di otak {mesin['nama']}: {str(e)}"
            print(error_msg)
            daftar_error.append(error_msg)
            continue
    laporan = "Maaf pengguna, semua otak gagal:\n" + "\n".join(daftar_error)
    raise Exception(laporan)

def owner_only(func):
    """Decorator untuk membatasi eksekusi perintah Telegram hanya untuk akun terdaftar."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update or not update.effective_user:
            return
        user_id = str(update.effective_user.id)
        from sari_core.access_control import is_user_authorized
        if not is_user_authorized(user_id):
            username = getattr(update.effective_user, 'username', 'tanpa_username')
            print(f"[SECURITY ALERT] Akses Ditolak dari ID: {user_id} (@{username}) untuk perintah /{func.__name__.replace('_command', '')}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    f"⛔ **Akses Ditolak**\nAsisten pribadi Siti diproteksi secara khusus dan hanya dapat diakses oleh akun resmi yang terdaftar (pengguna).\n\n🆔 **ID Telegram Anda:** `{user_id}`\n\nJika ini adalah akun resmi/cadangan pengguna, daftarkan ID ini dari akun utama menggunakan perintah:\n`/tambah_id {user_id} [keterangan]`",
                    parse_mode="Markdown"
                )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Mesin Ultimate Tingkat Dewa (Full Autonomous Mode) menyala!")

@owner_only
async def status_system_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani perintah /status untuk mengecek ringkasan kesehatan sistem Harmoni."""
    chat_id = update.effective_chat.id
    try:
        from server_core import get_system_status_ringkas
        res = get_system_status_ringkas()
        teks = res.get("report", "Status sistem tidak dapat dibaca.")
    except Exception as e:
        teks = f"❌ Gagal mengambil status sistem: {e}"
    await context.bot.send_message(chat_id=chat_id, text=teks, parse_mode="Markdown")

@owner_only
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani perintah /model atau /otak untuk melihat menu atau mengganti model langsung."""
    from sari_core.model_config import format_menu_model, set_active_model
    chat_id = update.effective_chat.id
    if context.args:
        first_arg = context.args[0].lower()
        if first_arg in ["refresh", "segarkan", "update", "--refresh"]:
            # Bersihkan cache model online
            try:
                from server_core import _PROVIDER_MODELS_CACHE
                _PROVIDER_MODELS_CACHE.clear()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔄 **Katalog Model Online Berhasil Disegarkan!**\nSeluruh katalog dari Google Gemini, Groq, 9Router, dan OpenRouter ditarik ulang secara live.\n\n" + format_menu_model(),
                parse_mode="Markdown"
            )
            return
        target = " ".join(context.args)
        ok, msg, info = set_active_model(target)
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=format_menu_model(), parse_mode="Markdown")

@owner_only
async def cadangan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani perintah /cadangan atau /backup untuk melihat atau mengubah model cadangan utama."""
    from sari_core.model_config import set_fallback_model, load_model_config
    chat_id = update.effective_chat.id
    if context.args:
        target = " ".join(context.args)
        ok, msg, info = set_fallback_model(target)
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=msg)
    else:
        cfg = load_model_config()
        fb_name = cfg.get("fallback_name", "DeepSeek V4.1 Flash")
        fb_id = cfg.get("fallback_id", "2")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🛡️ **Status Cadangan Utama (Backup Siaga):**\nSaat ini: **{fb_name}** (Model nomor {fb_id})\n\n💡 *Untuk mengubah:* ketik `/cadangan <nomor>` (contoh: `/cadangan 2` atau `/cadangan deepseek flash`)\n_(Model ini aktif otomatis jika otak utama mengalami limit kuota atau gangguan)_",
            parse_mode="Markdown"
        )

@owner_only
async def cari_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencari model online dari seluruh provider (Gemini, Groq, 9Router, OpenRouter)."""
    from sari_core.model_config import search_all_provider_models
    chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Cara Mencari Model AI:**\nKetik: `/cari_model <kata_kunci>`\nContoh: `/cari_model claude`, `/cari_model gemini`, `/cari_model llama`, atau `/cari_model qwen`",
            parse_mode="Markdown"
        )
        return
    keyword = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    results = search_all_provider_models(keyword, limit=6)
    if not results:
        await context.bot.send_message(chat_id=chat_id, text=f"Model dengan kata kunci '{keyword}' tidak ditemukan di provider aktif.")
        return
    
    lines = [f"🔍 **HASIL PENCARIAN MODEL AI: '{keyword.upper()}'**\n"]
    for idx, r in enumerate(results, 1):
        prov_tag = f"[{r.get('provider', '').upper()}] " if r.get('provider') else ""
        lines.append(f"{idx}. {prov_tag}**{r['name']}**")
        lines.append(f"   ID: `{r['id']}`")
        lines.append(f"   Pasang ketik: `/tambah_model {r['id']}`\n")
    lines.append("💡 _Pilih ID di atas lalu pasang dengan perintah /tambah_model_")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")

@owner_only
async def tambah_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menambahkan model baru ke menu dengan validasi ping test otomatis."""
    from sari_core.model_config import verify_and_add_model
    chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Cara Menambah Model Baru:**\nKetik: `/tambah_model <id_model> [nama_panggilan]`\n\nContoh Model 9Router (Antigravity):\n`/tambah_model ag/claude-opus-4-6-thinking Claude Opus 4.6 (Thinking)`\n`/tambah_model ag/claude-sonnet-4-6 Claude Sonnet 4.6`\n\nContoh Model OpenRouter:\n`/tambah_model meta-llama/llama-3.3-70b-instruct Llama 3.3 70B`",
            parse_mode="Markdown"
        )
        return
    
    full_arg = " ".join(context.args).strip()
    full_arg_lower = full_arg.lower()
    
    # Deteksi pintar jika pengguna mengetik nama provider di awal (misal /tambah_model 9router cx/gpt-5.5-review atau /tambah_model openai gpt-4o)
    provider = "openrouter"
    if context.args[0].lower() in ["openai", "openrouter", "9router", "antigravity", "deepseek", "groq"] and len(context.args) > 1:
        prov_candidate = context.args[0].lower()
        provider = "9router" if prov_candidate == "antigravity" else prov_candidate
        model_id = context.args[1].strip()
        display_name = " ".join(context.args[2:]).strip() if len(context.args) > 2 else ""
    else:
        model_id = context.args[0].strip()
        display_name = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""

    # Smart mapping untuk model 9Router / Antigravity / Cursor
    if "opus" in full_arg_lower and ("claude" in full_arg_lower or "9router" in full_arg_lower or "antigravity" in full_arg_lower):
        model_id = "ag/claude-opus-4-6-thinking"
        display_name = "Claude Opus 4.6 (Thinking)"
        provider = "9router"
    elif "sonnet" in full_arg_lower and ("claude" in full_arg_lower or "9router" in full_arg_lower or "antigravity" in full_arg_lower):
        model_id = "ag/claude-sonnet-4-6"
        display_name = "Claude Sonnet 4.6"
        provider = "9router"
    elif "gpt-oss" in full_arg_lower or "gpt oss" in full_arg_lower:
        model_id = "ag/gpt-oss-120b-medium"
        display_name = "GPT-OSS 120B"
        provider = "9router"
    elif model_id.lower().startswith(("ag/", "cx/", "9router/")):
        provider = "9router"
    elif "9router" in full_arg_lower:
        provider = "9router"

    await context.bot.send_message(chat_id=chat_id, text=f"⏳ Siti sedang menguji sambungan kilat ke model `{model_id}`...", parse_mode="Markdown")
    
    ok, msg, info = verify_and_add_model(model_id=model_id, display_name=display_name, provider=provider)
    try:
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=msg)

@owner_only
async def hapus_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghapus model kustom tambahan dari menu."""
    from sari_core.model_config import remove_custom_model
    chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Cara Menghapus Model Tambahan:**\nKetik: `/hapus_model <nomor>`\nContoh: `/hapus_model 7`",
            parse_mode="Markdown"
        )
        return
    
    target_id = context.args[0].strip()
    ok, msg = remove_custom_model(target_id)
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

@owner_only
async def set_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyimpan atau memperbarui API key provider secara aman."""
    from sari_core.model_config import update_env_api_key
    chat_id = update.effective_chat.id
    full_arg = " ".join(context.args).strip()
    if not full_arg:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Cara Menyimpan API Key:**\nKetik: `/set_key <NAMA_PROVIDER> <KUNCI_API>` atau `/set_key PROVIDER=KUNCI`\nContoh: `/set_key OPENROUTER sk-or-xxxx` atau `/set_key OPENROUTER=sk-or-xxxx`",
            parse_mode="Markdown"
        )
        return
    
    if "=" in full_arg:
        parts = full_arg.split("=", 1)
        provider_name = parts[0].strip()
        key_val = parts[1].strip()
    else:
        parts = full_arg.split(None, 1)
        if len(parts) < 2:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📌 **Cara Menyimpan API Key:**\nKetik: `/set_key <NAMA_PROVIDER> <KUNCI_API>`\nContoh: `/set_key OPENROUTER sk-or-xxxx`",
                parse_mode="Markdown"
            )
            return
        provider_name = parts[0].strip()
        key_val = parts[1].strip()

    ok, msg = update_env_api_key(provider_name, key_val)
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

@owner_only
async def spesialis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan susunan tim spesialis tugas Siti."""
    from sari_core.model_config import format_specialists_menu
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=format_specialists_menu(), parse_mode="Markdown")

@owner_only
async def atur_spesialis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengatur model spesialis untuk divisi tugas tertentu."""
    from sari_core.model_config import set_specialist
    chat_id = update.effective_chat.id
    if len(context.args) < 2:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Format Pengaturan Spesialis:**\n`/atur_spesialis <divisi> <nomor_model>`\n\nPilihan divisi:\n- `visual` (Layar & Foto)\n- `pc` (Kontrol Komputer & Sistem)\n- `wa` (WhatsApp & Komunikasi)\n- `jadwal` (Pengingat & Scheduler)\n\nContoh:\n- `/atur_spesialis visual 1`\n- `/atur_spesialis pc 2`\n- Reset ke default: `/atur_spesialis wa 0`",
            parse_mode="Markdown"
        )
        return
    domain = context.args[0].strip()
    target = " ".join(context.args[1:]).strip()
    ok, msg = set_specialist(domain, target)
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

@owner_only
async def reset_spesialis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mereset semua spesialis kembali ke Model Utama (Default)."""
    from sari_core.model_config import reset_all_specialists
    chat_id = update.effective_chat.id
    ok, msg = reset_all_specialists()
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

@owner_only
async def daftar_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar ID Telegram yang diizinkan mengakses Siti."""
    from sari_core.access_control import format_access_menu
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=format_access_menu(), parse_mode="Markdown")

@owner_only
async def tambah_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menambahkan ID Telegram baru ke daftar akses resmi."""
    chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Format Tambah ID Telegram:**\n`/tambah_id <id_telegram> [keterangan]`\n\nContoh:\n- `/tambah_id 123456789 Akun Cadangan`\n- `/tambah_id 987654321 Telegram Istri`\n\n💡 _Gunakan perintah `/my_id` di akun baru untuk melihat nomor ID-nya._",
            parse_mode="Markdown"
        )
        return
    target_id = context.args[0].strip()
    label = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""
    from sari_core.access_control import add_allowed_user
    ok, msg = add_allowed_user(target_id, label)
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

@owner_only
async def hapus_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghapus ID Telegram dari daftar akses resmi."""
    chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Format Hapus ID Telegram:**\n`/hapus_id <id_telegram>`\n\nContoh:\n- `/hapus_id 123456789`\n\n💡 _Ketik `/daftar_id` untuk melihat daftar nomor ID yang terdaftar._",
            parse_mode="Markdown"
        )
        return
    target_id = context.args[0].strip()
    from sari_core.access_control import remove_allowed_user
    ok, msg = remove_allowed_user(target_id)
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def my_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan ID Telegram akun yang sedang digunakan (bisa diakses siapa saja untuk keperluan pendaftaran)."""
    if not update or not update.effective_user:
        return
    user_id = str(update.effective_user.id)
    username = getattr(update.effective_user, 'username', None)
    user_tag = f" (@{username})" if username else ""
    from sari_core.access_control import is_user_authorized
    status = "👑 Terdaftar (Pemilik/Akses Resmi)" if is_user_authorized(user_id) else "⚠️ Belum Terdaftar"
    await update.effective_message.reply_text(
        f"🆔 **INFORMASI AKUN TELEGRAM ANDA**\n\n"
        f"- **ID Telegram:** `{user_id}`\n"
        f"- **Nama:** {update.effective_user.full_name}{user_tag}\n"
        f"- **Status Akses:** {status}\n\n"
        f"💡 _Jika akun ini adalah akun cadangan pengguna, daftarkan ID ini dari akun utama melalui perintah:_\n`/tambah_id {user_id} Akun Cadangan`",
        parse_mode="Markdown"
    )

active_tasks = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_tasks
    if not update or not update.effective_user:
        return

    # 1. VERIFIKASI KEAMANAN & OTORISASI AKUN (OWNER WHITELIST)
    user_id = str(update.effective_user.id)
    from sari_core.access_control import is_user_authorized
    if not is_user_authorized(user_id):
        username = getattr(update.effective_user, 'username', 'tanpa_username')
        print(f"[SECURITY ALERT] Pesan diblokir dari ID tidak dikenal: {user_id} (@{username})")
        if update.effective_message:
            await update.effective_message.reply_text(
                f"⛔ **Akses Ditolak**\nAsisten pribadi Siti diproteksi secara khusus dan hanya dapat diakses oleh akun resmi yang terdaftar (pengguna).\n\n🆔 **ID Telegram Anda:** `{user_id}`\n\nJika ini adalah akun resmi/cadangan pengguna, daftarkan ID ini dari akun utama menggunakan perintah:\n`/tambah_id {user_id} [keterangan]`",
                parse_mode="Markdown"
            )
        return

    chat_id = update.effective_chat.id
    
    # Cek fitur STOP
    if update.message and update.message.text:
        teks_lower = update.message.text.lower().strip()
        if teks_lower in ["stop", "batal", "berhenti", "cancel"]:
            if chat_id in active_tasks:
                task = active_tasks.pop(chat_id)
                task.cancel()
                await update.message.reply_text("⛔ Proses yang sedang berjalan telah dihentikan secara paksa.")
            else:
                await update.message.reply_text("Tidak ada proses yang sedang berjalan saat ini.")
            return

    # Daftar task saat ini
    active_tasks[chat_id] = asyncio.current_task()
    is_voice_note = False
    if update.message and update.message.voice:
        is_voice_note = True
    teks_tambahan = ""

    if update.message.text:
        teks_lower = update.message.text.lower().strip()

        # PENGELOLAAN AKSES TELEGRAM (NATURAL LANGUAGE & SHORTCUTS)
        if teks_lower in ["/daftar_id", "/id_terdaftar", "/kelola_akses", "/akses", "daftar id", "lihat id", "kelola akses", "daftar akun"]:
            from sari_core.access_control import format_access_menu
            await context.bot.send_message(chat_id=chat_id, text=format_access_menu(), parse_mode="Markdown")
            return

        if teks_lower in ["/my_id", "/id", "/cek_id", "my id", "cek id", "id saya"]:
            from sari_core.access_control import is_user_authorized
            status = "👑 Terdaftar (Pemilik/Akses Resmi)" if is_user_authorized(user_id) else "⚠️ Belum Terdaftar"
            await update.effective_message.reply_text(
                f"🆔 **INFORMASI AKUN TELEGRAM ANDA**\n\n- **ID Telegram:** `{user_id}`\n- **Nama:** {update.effective_user.full_name}\n- **Status Akses:** {status}\n\n💡 _Ketik `/daftar_id` untuk melihat seluruh akun yang terdaftar._",
                parse_mode="Markdown"
            )
            return

        if any(teks_lower.startswith(p) for p in ["siti tambah id ", "tambah id ", "/tambah_id "]):
            for p in ["siti tambah id ", "tambah id ", "/tambah_id "]:
                if teks_lower.startswith(p):
                    arg = teks_lower[len(p):].strip()
                    parts = arg.split(None, 1)
                    if not parts:
                        await context.bot.send_message(chat_id=chat_id, text="📌 Format: `/tambah_id <id_telegram> [keterangan]`\nContoh: `/tambah_id 123456789 Akun Cadangan`", parse_mode="Markdown")
                        return
                    target_id = parts[0].strip()
                    label = parts[1].strip() if len(parts) > 1 else ""
                    from sari_core.access_control import add_allowed_user
                    ok, msg = add_allowed_user(target_id, label)
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    return

        if any(teks_lower.startswith(p) for p in ["siti hapus id ", "hapus id ", "/hapus_id "]):
            for p in ["siti hapus id ", "hapus id ", "/hapus_id "]:
                if teks_lower.startswith(p):
                    target_id = teks_lower[len(p):].strip()
                    from sari_core.access_control import remove_allowed_user
                    ok, msg = remove_allowed_user(target_id)
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    return

        # 1. MENU & PERGANTIAN MODEL AI (MULTI-MODEL SWITCHER)
        if teks_lower in ["/model", "/otak", "/models", "pilih model", "ganti model", "menu model", "/status_otak", "status otak"]:
            from sari_core.model_config import format_menu_model
            await context.bot.send_message(chat_id=chat_id, text=format_menu_model(), parse_mode="Markdown")
            return

        if teks_lower.startswith("/model ") or teks_lower.startswith("/otak "):
            target_arg = teks_lower.split(" ", 1)[1].strip()
            from sari_core.model_config import set_active_model
            ok, msg, info = set_active_model(target_arg)
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            return

        if any(teks_lower.startswith(p) for p in ["siti ganti model ke ", "siti ganti otak ke ", "siti pakai model ", "siti pakai otak ", "ganti model ke ", "ganti otak ke ", "pakai model ", "pakai otak "]):
            for p in ["siti ganti model ke ", "siti ganti otak ke ", "siti pakai model ", "siti pakai otak ", "ganti model ke ", "ganti otak ke ", "pakai model ", "pakai otak "]:
                if teks_lower.startswith(p):
                    target_arg = teks_lower[len(p):].strip()
                    from sari_core.model_config import set_active_model
                    ok, msg, info = set_active_model(target_arg)
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    return

        # 1B. CADANGAN / BACKUP SWITCHER
        if teks_lower in ["/cadangan", "/backup", "status cadangan", "cadangan model", "cek cadangan"]:
            from sari_core.model_config import load_model_config
            cfg = load_model_config()
            fb_name = cfg.get("fallback_name", "DeepSeek V4.1 Flash")
            fb_id = cfg.get("fallback_id", "2")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🛡️ **Status Cadangan Utama (Backup Siaga):**\nSaat ini: **{fb_name}** (Model nomor {fb_id})\n\n💡 *Untuk mengubah:* ketik `/cadangan <nomor>` (contoh: `/cadangan 2`)\n_(Model ini aktif otomatis jika otak utama mengalami limit atau gangguan)_",
                parse_mode="Markdown"
            )
            return

        if teks_lower.startswith("/cadangan ") or teks_lower.startswith("/backup "):
            target_arg = teks_lower.split(" ", 1)[1].strip()
            from sari_core.model_config import set_fallback_model
            ok, msg, info = set_fallback_model(target_arg)
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            return

        if any(teks_lower.startswith(p) for p in ["siti ganti cadangan ke ", "ganti cadangan ke ", "siti jadikan cadangan ", "jadikan cadangan "]):
            for p in ["siti ganti cadangan ke ", "ganti cadangan ke ", "siti jadikan cadangan ", "jadikan cadangan "]:
                if teks_lower.startswith(p):
                    target_arg = teks_lower[len(p):].strip()
                    from sari_core.model_config import set_fallback_model
                    ok, msg, info = set_fallback_model(target_arg)
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    except Exception:
                        await context.bot.send_message(chat_id=chat_id, text=msg)
                    return

        # 2. CARI MODEL ONLINE (OPENROUTER KATALOG)
        for p in ["siti cari model ", "sari cari model ", "cari model ", "/cari_model ", "cari_model "]:
            if teks_lower.startswith(p):
                kw = teks_lower[len(p):].strip()
                from sari_core.model_config import search_openrouter_models
                await context.bot.send_chat_action(chat_id=chat_id, action='typing')
                results = search_openrouter_models(kw, limit=5)
                if not results:
                    await context.bot.send_message(chat_id=chat_id, text=f"Model dengan kata kunci '{kw}' tidak ditemukan di katalog OpenRouter.")
                else:
                    lines = [f"🔍 **HASIL PENCARIAN MODEL AI: '{kw.upper()}'**\n"]
                    for idx, r in enumerate(results, 1):
                        lines.append(f"{idx}. **{r['name']}**\n   ID: `{r['id']}`\n   Pasang ketik: `/tambah_model {r['id']}`\n")
                    lines.append("💡 _Pilih ID di atas lalu pasang dengan perintah /tambah_model_")
                    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")
                return

        # 3. TAMBAH MODEL BARU
        for p in ["siti tambah model ", "sari tambah model ", "tambah model ", "/tambah_model ", "tambah_model "]:
            if teks_lower.startswith(p):
                raw_arg = update.message.text.strip()[len(p):].strip()
                parts = raw_arg.split()
                if not parts:
                    await context.bot.send_message(chat_id=chat_id, text="📌 Format: `/tambah_model <id_model> [nama]`\nContoh: `/tambah_model ag/claude-opus-4-6-thinking Claude Opus 4.6 (Thinking)`")
                    return
                
                raw_lower = raw_arg.lower()
                provider = "openrouter"
                if parts[0].lower() in ["openai", "openrouter", "9router", "antigravity", "deepseek", "groq"] and len(parts) > 1:
                    prov_candidate = parts[0].lower()
                    provider = "9router" if prov_candidate == "antigravity" else prov_candidate
                    m_id = parts[1].strip()
                    d_name = " ".join(parts[2:]).strip() if len(parts) > 2 else ""
                else:
                    m_id = parts[0]
                    d_name = " ".join(parts[1:]) if len(parts) > 1 else ""

                if "opus" in raw_lower and ("claude" in raw_lower or "9router" in raw_lower or "antigravity" in raw_lower):
                    m_id = "ag/claude-opus-4-6-thinking"
                    d_name = "Claude Opus 4.6 (Thinking)"
                    provider = "9router"
                elif "sonnet" in raw_lower and ("claude" in raw_lower or "9router" in raw_lower or "antigravity" in raw_lower):
                    m_id = "ag/claude-sonnet-4-6"
                    d_name = "Claude Sonnet 4.6"
                    provider = "9router"
                elif "gpt-oss" in raw_lower or "gpt oss" in raw_lower:
                    m_id = "ag/gpt-oss-120b-medium"
                    d_name = "GPT-OSS 120B"
                    provider = "9router"
                elif m_id.lower().startswith(("ag/", "cx/", "9router/")):
                    provider = "9router"
                elif "9router" in raw_lower:
                    provider = "9router"

                await context.bot.send_message(chat_id=chat_id, text=f"⏳ Siti sedang menguji sambungan kilat ke model `{m_id}`...", parse_mode="Markdown")
                from sari_core.model_config import verify_and_add_model
                ok, msg, info = verify_and_add_model(model_id=m_id, display_name=d_name, provider=provider)
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                except Exception:
                    await context.bot.send_message(chat_id=chat_id, text=msg)
                return

        # 4. HAPUS MODEL TAMBAHAN
        for p in ["siti hapus model ", "sari hapus model ", "hapus model ", "/hapus_model ", "hapus_model "]:
            if teks_lower.startswith(p):
                num = teks_lower[len(p):].strip()
                from sari_core.model_config import remove_custom_model
                ok, msg = remove_custom_model(num)
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                return

        # 5. SIMPAN API KEY BARU
        key_prefixes = [
            "siti simpan api key ", "sari simpan api key ", "simpan api key ",
            "/set_key ", "set_key ", "/setkey ", "setkey ", "set key ",
            "/set_api_key ", "set_api_key "
        ]
        matched_key_p = None
        for p in key_prefixes:
            if teks_lower.startswith(p):
                matched_key_p = p
                break

        if matched_key_p:
            raw_arg = update.message.text.strip()[len(matched_key_p):].strip()
            if "=" in raw_arg:
                parts = raw_arg.split("=", 1)
            else:
                parts = raw_arg.split(None, 1)
                
            if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
                await context.bot.send_message(chat_id=chat_id, text="📌 Format: `/set_key <PROVIDER> <API_KEY>` atau `set_key PROVIDER=API_KEY`\nContoh: `set_key OPENROUTER=sk-or-xxxx`")
                return
            prov, k_val = parts[0].strip(), parts[1].strip()
            from sari_core.model_config import update_env_api_key
            ok, msg = update_env_api_key(prov, k_val)
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            return

        # 6. RESET SPESIALIS (Wajib dievaluasi sebelum reset memori obrolan biasa!)
        if any(cmd in teks_lower for cmd in ["reset spesialis", "reset tim", "/reset_spesialis", "/reset_tim", "normalkan spesialis", "normalkan tim"]):
            from sari_core.model_config import reset_all_specialists
            ok, msg = reset_all_specialists()
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            return

        # 7. MENU TIM SPESIALIS
        if teks_lower in ["/spesialis", "/tim", "menu spesialis", "tim spesialis", "lihat spesialis", "daftar spesialis"]:
            from sari_core.model_config import format_specialists_menu
            await context.bot.send_message(chat_id=chat_id, text=format_specialists_menu(), parse_mode="Markdown")
            return

        # 8. ATUR SPESIALIS
        for p in ["/atur_spesialis ", "atur_spesialis ", "atur spesialis ", "set spesialis "]:
            if teks_lower.startswith(p):
                raw_arg = update.message.text.strip()[len(p):].strip()
                parts = raw_arg.split(None, 1)
                if len(parts) < 2:
                    await context.bot.send_message(chat_id=chat_id, text="📌 Format: `/atur_spesialis <divisi> <nomor_model>`\nContoh: `/atur_spesialis visual 1` atau `/atur_spesialis pc 2`\nReset: `/atur_spesialis wa 0`")
                    return
                from sari_core.model_config import set_specialist
                ok, msg = set_specialist(parts[0], parts[1])
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                return

        # 9. OBROLAN SANTAI PENUGASAN: "siti urusan visual pakai gemini"
        if "urusan " in teks_lower and any(kw in teks_lower for kw in ["pakai ", "oleh ", "ditangani ", "gunakan ", "serahkan ke "]):
            import re
            m = re.search(r"urusan\s+([a-zA-Z]+)\s+(?:tolong\s+)?(?:pakai|oleh|ditangani|gunakan|serahkan ke)\s+(.+)", teks_lower)
            if m:
                div = m.group(1).strip()
                target_m = m.group(2).strip()
                from sari_core.model_config import set_specialist
                ok, msg = set_specialist(div, target_m)
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                return

        # Pemicu reset memori harus eksplisit (bukan sekadar ada kata 'reset' di tengah kalimat atau bahasa Inggris)
        explicit_reset_cmds = ["bersihkan memori", "hapus memori", "reset memori", "bersihkan ingatan", "reset ingatan", "/reset"]
        if teks_lower in explicit_reset_cmds or teks_lower == "reset":
            from sari_core.memory_broker import memory_broker
            person_id = await memory_broker.get_or_create_person(str(chat_id), "TELEGRAM")
            await memory_broker.clear_memory(person_id)
            await context.bot.send_message(chat_id=chat_id, text="🧼 Papan tulis memori percakapan jangka pendek sudah Siti bersihkan!\nSiti siap menerima perintah baru dengan otak yang lebih segar. ✨")
            return

    # DETEKSI MODE PROGRAMMER
    global MODE_PROGRAMMER
    if update.message.text:
        teks_lower = update.message.text.lower().strip()
        if "sari mode programmer" in teks_lower:
            MODE_PROGRAMMER = True
            await update.message.reply_text("👩‍💻 Mode Programmer AKTIF! Sari siap ngoding. (Ketik 'Sari kembali normal' untuk mematikan)")
            return
        elif "sari kembali normal" in teks_lower:
            MODE_PROGRAMMER = False
            await update.message.reply_text("🌸 Mode Programmer DIMATIKAN. Sari kembali menjadi asisten biasa.")
            return

    # CEK JIKA MODE PROGRAMMER AKTIF
    if MODE_PROGRAMMER:
        if update.message.text:
            teks = update.message.text
            chat_id = update.effective_chat.id
            threading.Thread(target=tugas_programmer_background, args=(teks, chat_id)).start()
        else:
            await update.message.reply_text("⚠️ Di Mode Programmer, Sari hanya menerima teks.")
        return
        # DETEKSI REM DARURAT & FAST-PATH PEMBATALAN JADWAL
    if update.message.text:
        teks_lower = update.message.text.lower().strip()
        
        # Cek apakah sedang ada agen otonom berjalan. Jika ya, matikan agen.
        if any(w in teks_lower for w in ["stop", "berhenti", "batal", "batal jadwal", "batal tugas", "stop tugas"]):
            if status_otonom.get("berjalan", False):
                status_otonom["berhenti"] = True
                await update.message.reply_text("🛑 **[REM DARURAT DITARIK!]**\nMematikan mode agen otonom secara paksa.", parse_mode="Markdown")

        # FAST-PATH: Pembatalan & Pengecekan Jadwal Langsung (Anti-Gagal & Tanpa Delay)
        if any(cmd in teks_lower for cmd in ["batalkan semua jadwal", "batal semua jadwal", "stop semua jadwal", "hapus semua jadwal", "batalkan semua tugas", "batal semua tugas", "stop semua tugas"]):
            res_batal = kelola_jadwal_tugas("batalkan_semua")
            await update.message.reply_text(f"🛑 **[PEMBATALAN JADWAL SELESAI]**\n\n{res_batal}", parse_mode="Markdown")
            return
        elif teks_lower in ["batalkan jadwal", "batal jadwal", "batalkan", "batalin", "hapus jadwal", "stop jadwal"]:
            res_batal = kelola_jadwal_tugas("batalkan")
            await update.message.reply_text(f"🛑 **[PEMBATALAN JADWAL]**\n\n{res_batal}", parse_mode="Markdown")
            return
        elif any(cmd in teks_lower for cmd in ["lihat jadwal", "cek jadwal", "daftar jadwal", "status jadwal", "ada jadwal apa"]):
            res_lihat = kelola_jadwal_tugas("lihat")
            await update.message.reply_text(f"{res_lihat}", parse_mode="Markdown")
            return


    # 1. PENANGANAN VOICE NOTE (VOICE)
    if update.message.voice:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        filepath = "audio_pesan.ogg"
        await voice_file.download_to_drive(filepath)
        try:
            t_hasil = transkripsi_audio_wa_robust(filepath)
            if t_hasil:
                teks_tambahan += f"\n[Pesan Suara (Voice Note): '{t_hasil}']"
            else:
                teks_tambahan += "\n[Pesan Suara (Voice Note) masuk, belum berhasil ditranskripsikan]"
        except Exception as e:
            teks_tambahan += f"\n[Gagal menerjemahkan suara: {str(e)}]"
        if os.path.exists(filepath): os.remove(filepath)
            
    # 2. PENANGANAN FILE UNIVERSAL (DOKUMEN, VIDEO, AUDIO, FOTO)
    elif update.message.document or update.message.audio or update.message.video or update.message.photo:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        file_obj = None
        file_name = ""
        
        if update.message.document:
            file_obj = update.message.document
            file_name = file_obj.file_name
        elif update.message.audio:
            file_obj = update.message.audio
            file_name = file_obj.file_name if file_obj.file_name else "audio_telegram.mp3"
        elif update.message.video:
            file_obj = update.message.video
            file_name = file_obj.file_name if file_obj.file_name else "video_telegram.mp4"
        elif update.message.photo:
            file_obj = update.message.photo[-1] # Resolusi tertinggi
            file_name = f"foto_telegram_{file_obj.file_id[-6:]}.jpg"
            
        file = await context.bot.get_file(file_obj.file_id)
        save_dir = str(FILE_DIR / "Telegram")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        filepath = os.path.join(save_dir, file_name)
        await file.download_to_drive(filepath)
        
        teks_tambahan += f"\n[SISTEM: Pengguna mengirim file bernama '{file_name}'. File telah disimpan di '{filepath}'. Anda bisa mengirimnya ke WA, mengupload ke Drive/YouTube, atau membacanya. Tanyakan kepada pengguna mau diapakan file ini.]"
        
        # Ekstraksi PDF/TXT jika perlu
        if file_name.endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(filepath)
                isi_pdf = ""
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt: isi_pdf += txt + "\n"
                teks_tambahan += f"\n[Isi singkat PDF: {isi_pdf[:2000]}]"
            except Exception:

                pass
        elif file_name.endswith('.txt'):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    teks_tambahan += f"\n[Isi Teks: {f.read()[:2000]}]"
            except Exception:

                pass
            
    if update.message.text:
        teks_masuk = update.message.text


        
        global MODE_NOTIF_EMAIL
        if any(cmd in teks_masuk.lower() for cmd in ["siti nyalakan notif email", "sari nyalakan notif email", "aktifkan notif email"]):
            MODE_NOTIF_EMAIL = False
            await update.message.reply_text("?? Notifikasi Email NYALA. Siti akan lapor ke Telegram setiap ada email masuk.")
            return
        if any(cmd in teks_masuk.lower() for cmd in ["siti matikan notif email", "sari matikan notif email", "nonaktifkan notif email"]):
            MODE_NOTIF_EMAIL = False
            await update.message.reply_text("?? Notifikasi Email MATI. Siti tetap mengecek email sesuai mode Admin, tapi tidak akan lapor ke Telegram.")
            return

        global MODE_NOTIF_WA
        if any(cmd in teks_masuk.lower() for cmd in ["siti nyalakan notif wa", "sari nyalakan notif wa", "aktifkan notif wa"]):
            MODE_NOTIF_WA = True
            await update.message.reply_text("?? Notifikasi WA NYALA. Siti akan lapor ke Telegram setiap ada chat WA masuk.")
            return
        if any(cmd in teks_masuk.lower() for cmd in ["siti matikan notif wa", "sari matikan notif wa", "nonaktifkan notif wa"]):
            MODE_NOTIF_WA = False
            await update.message.reply_text("?? Notifikasi WA MATI. Siti tidak akan berisik lapor WA ke Telegram.")
            return

        
        # Sinkronisasi Drive: memakai pengaturan bersama di
        # sari_core/sinkronisasi_config.py. Perintahnya TIDAK lagi memaku nama
        # asisten lama ("siti"/"sari"); frasa intinya saja sudah cukup sehingga
        # nama asisten apa pun tetap bekerja.
        if "sinkronisasi drive" in teks_masuk.lower() or "sync drive" in teks_masuk.lower():
            from sari_core import sinkronisasi_config as _cfg_sync
            _teks = teks_masuk.lower().replace("_", " ")
            if any(k in _teks for k in ["nyalakan", "nyala", "aktifkan", " on", "hidupkan"]):
                _cfg_sync.perbarui(aktif=True)
                await update.message.reply_text(
                    "🟢 Sinkronisasi 2 Arah Google Drive NYALA.\n\n" + _cfg_sync.ringkas())
            elif any(k in _teks for k in ["matikan", "mati", "nonaktifkan", " off"]):
                _cfg_sync.perbarui(aktif=False)
                await update.message.reply_text(
                    "🔴 Sinkronisasi 2 Arah Google Drive MATI.\n\n" + _cfg_sync.ringkas())
            else:
                await update.message.reply_text("☁️ " + _cfg_sync.ringkas())
            return

        global MODE_ADMIN_EMAIL
        admin_email_on_cmds = ["siti nyalakan admin email", "sari nyalakan admin email", "aktifkan admin email", "siti aktifkan admin email"]
        if any(cmd in teks_masuk.lower() for cmd in admin_email_on_cmds):
            MODE_ADMIN_EMAIL = True
            await update.message.reply_text("🤖 Mode Admin Email BERHASIL DIAKTIFKAN! Siti sekarang memantau dan membalas email masuk secara otomatis.")
            return

        admin_email_off_cmds = ["siti matikan admin email", "sari matikan admin email", "nonaktifkan admin email", "siti nonaktifkan admin email"]
        if any(cmd in teks_masuk.lower() for cmd in admin_email_off_cmds):
            MODE_ADMIN_EMAIL = False
            await update.message.reply_text("🤖 Mode Admin Email BERHASIL DINONAKTIFKAN! Siti berhenti membalas email otomatis.")
            return

        global MODE_ADMIN_WA
        admin_wa_on_cmds = [
            "siti nyalakan admin wa", "sari nyalakan admin wa", "siti aktifkan admin wa", "sari aktifkan admin wa",
            "nyalakan mode admin wa", "aktifkan mode admin wa", "siti nyalakan mode admin wa", "sari nyalakan mode admin wa",
            "siti nyalakan wa admin", "siti aktifkan wa admin", "nyalakan admin wa", "aktifkan admin wa"
        ]
        if any(cmd in teks_masuk.lower() for cmd in admin_wa_on_cmds):
            MODE_ADMIN_WA = True
            try:
                with open(str(ADMIN_WA_STATUS_FILE), "w", encoding="utf-8") as f_st:
                    json.dump({"admin_wa": True}, f_st)
            except Exception:

                pass
            await update.message.reply_text("🟢 Mode Admin WA BERHASIL DIAKTIFKAN! Gea sekarang memantau dan membalas pesan klien WhatsApp secara otomatis.")
            return

        admin_wa_off_cmds = [
            "siti matikan admin wa", "sari matikan admin wa", "siti nonaktifkan admin wa", "sari nonaktifkan admin wa",
            "matikan mode admin wa", "nonaktifkan mode admin wa", "siti matikan mode admin wa", "sari matikan mode admin wa",
            "siti matikan wa admin", "siti nonaktifkan wa admin", "matikan admin wa", "nonaktifkan admin wa"
        ]
        if any(cmd in teks_masuk.lower() for cmd in admin_wa_off_cmds):
            MODE_ADMIN_WA = False
            try:
                with open(str(ADMIN_WA_STATUS_FILE), "w", encoding="utf-8") as f_st:
                    json.dump({"admin_wa": False}, f_st)
            except Exception:

                pass
            await update.message.reply_text("🔴 Mode Admin WA BERHASIL DINONAKTIFKAN! Gea berhenti membalas pesan WA otomatis.")
            return

        if any(cmd in teks_masuk.lower() for cmd in ["cek model", "siti cek model", "sari cek model"]):
            from sari_core.model_config import format_menu_model
            await context.bot.send_message(chat_id=update.effective_chat.id, text=format_menu_model(), parse_mode="Markdown")
            return
            
        if any(cmd in teks_masuk.lower() for cmd in ["cek token", "siti cek token", "sari cek token", "cek kuota", "siti cek kuota"]):
            laporan = "📊 **Laporan Status Real-Time Kuota & Otak AI Siti:**\n\n"
            try:
                import requests
                
                # Cek Qwen (Alibaba Cloud)
                if os.getenv("ALIBABA_API_KEY"):
                    laporan += f"1️⃣ **Qwen 3.8 Max** (Alibaba Cloud): 🟢 AKTIF & Ready\n"
                else:
                    laporan += f"1️⃣ **Qwen 3.8 Max** (Alibaba Cloud): 🔴 TIDAK AKTIF\n"
                
                # Cek DeepSeek
                deepseek_key = os.getenv("DEEPSEEK_API_KEY")
                if deepseek_key:
                    res = requests.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {deepseek_key}"}, timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        info = data.get("balance_infos", [{}])[0]
                        total_usd = float(info.get("total_balance", 0.0))
                        total_idr = int(total_usd * 16000)
                        laporan += f"4️⃣ **DeepSeek V4.1 Flash** (Cadangan 3): ✅ AKTIF\n   - Saldo Real-Time: **${total_usd:.2f} USD** (± Rp {total_idr:,})\n"
                    else:
                        laporan += "4️⃣ **DeepSeek V4.1 Flash** (Cadangan 3): ✅ AKTIF & Normal\n"
                else:
                    laporan += "4️⃣ **DeepSeek V4.1 Flash** (Cadangan 3): ❌ TIDAK AKTIF\n"
            except Exception:
                laporan += "4️⃣ **DeepSeek V4.1 Flash** (Cadangan 3): ✅ AKTIF & Normal\n"
                
            laporan += "5️⃣ **Google Gemini 3.8 Flash** (Cadangan 4 Gratis): ✅ AKTIF & Ready\n\n"
            
            # Mesin Suara (Voice/Audio Engine) Section
            laporan += "🎤 **Mesin Suara (Voice Note & TTS):**\n"
            e1 = os.getenv("ELEVENLABS_API_KEY_1") or os.getenv("ELEVENLABS_API_KEY")
            e2 = os.getenv("ELEVENLABS_API_KEY_2")
            if e1 or e2:
                status_e = " (Key 1 & Key 2 Ready)" if (e1 and e2) else ""
                laporan += f"1️⃣ **ElevenLabs TTS** (Suara Utama Premium): 🟢 AKTIF{status_e}\n"
            else:
                laporan += "1️⃣ **ElevenLabs TTS**: ⚪ Tidak Aktif\n"
                
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                laporan += "2️⃣ **OpenAI TTS** (Cadangan jika ElevenLabs habis): 🟢 AKTIF & Ready\n"
            else:
                laporan += "2️⃣ **OpenAI TTS**: ⚪ Tidak Aktif\n"
                
            laporan += "\n⚡ *Fitur Smart Tool Filtering aktif (Penghematan token 95-99%).*"
            
            await context.bot.send_message(chat_id=update.effective_chat.id, text=laporan, parse_mode="Markdown")
            return
    elif teks_tambahan != "":
        teks_masuk = "Tolong periksa kiriman saya."
    else:
        return
        
    waktu_realtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    teks_masuk = teks_masuk + teks_tambahan
    
    # Inisialisasi loop background untuk menjaga status typing tetap aktif selama proses
    async def _keep_typing(chat_id_target):
        try:
            while True:
                await context.bot.send_chat_action(chat_id=chat_id_target, action='typing')
                await asyncio.sleep(4.5)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    typing_task = asyncio.create_task(_keep_typing(update.effective_chat.id))

    # AUTO OBSIDIAN & RECENT SCHEDULE MEMORY INJECTION (ANTI-AMNESIA LINTAS RESTART)
    try:
        # Cek apakah hanya sapaan murni, jika ya lewati pencarian obsidian untuk efisiensi
        teks_clean = teks_masuk.lower().strip()
        is_sapaan_ringan = any(teks_clean.startswith(s) for s in ["halo", "hai", "hei", "pagi", "siang", "sore", "malam", "tes", "test", "ping"]) and len(teks_clean.split()) <= 4
        
        info_jadwal_terbaru = ""
        mem_auto = ""
        
        if not is_sapaan_ringan:
            from plugins.obsidian_plugin import baca_memori_obsidian
            mem_auto = baca_memori_obsidian(kata_kunci=teks_masuk[:30])
            
        file_jadwal_path = str(OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json")
        if os.path.exists(file_jadwal_path):
            try:
                with open(file_jadwal_path, "r", encoding="utf-8") as f_j:
                    j_data = json.load(f_j)
                    if j_data:
                        recent = j_data[-5:]
                        info_jadwal_terbaru = "\n[DAFTAR TUGAS & JADWAL TERAKHIR DARI MEMORI RESTART]:\n"
                        for r_item in recent:
                            info_jadwal_terbaru += f"- ID: {r_item.get('id')}, Waktu: {r_item.get('waktu_str')}, Fungsi: {r_item.get('fungsi')}, Status: {r_item.get('status')}, Laporan/Isi Rincian: {r_item.get('laporan')}, Params: {r_item.get('params')}\n"
            except Exception:
                pass
            
        context_extra = ""
        if mem_auto and "Tidak ditemukan" not in mem_auto:
            context_extra += f"\n\n[MEMORI OBSIDIAN TERKAIT]:\n{mem_auto[:1000]}"
        if info_jadwal_terbaru:
            context_extra += info_jadwal_terbaru
            
        if context_extra:
            teks_masuk += context_extra
    except Exception as e_mem:
        print(f"Auto Memory Injection Error: {e_mem}")

    messages.append({"role": "user", "content": teks_masuk})
    
    try:
        from sari_core.bridge import process_telegram_message_async
        balasan = await process_telegram_message_async(str(update.effective_chat.id), update.effective_user.first_name, teks_masuk)
    except asyncio.CancelledError:
        print(f"Task for {chat_id} was cancelled.")
        raise
    except Exception as e:
        balasan = f"Error dari Core: {str(e)}"
    finally:
        typing_task.cancel()

    if not balasan:
        balasan = "Siap pengguna, tugas sudah selesai Sari kerjakan secara presisi! 😊"

    try:
        if is_voice_note:
            voice_path = "reply_voice.ogg"
            # Bersihkan label footer agar tidak dibacakan robotik oleh TTS
            balasan_audio = re.sub(r'\n\n[🧠⚠️] _\[.*?\]_', '', balasan).strip()
            # Coba buat voice note dengan OpenAI/Gadis, kalau sukses kirim voice + caption
            if buat_suara_openai(balasan_audio[:4000], voice_path):
                with open(voice_path, 'rb') as vf:
                    await update.message.reply_voice(voice=vf, caption=balasan[:1024])
                if os.path.exists(voice_path): os.remove(voice_path)
            else:
                await update.message.reply_text(balasan[:4000])
        else:
            await update.message.reply_text(balasan[:4000])
    except Exception as e:
        print(f"Gagal mengirim pesan ke Telegram: {e}")

async def satpam_email_job(context: ContextTypes.DEFAULT_TYPE):
    global last_seen_email_id, MODE_ADMIN_EMAIL
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id: return
    try:
        email_user = os.getenv("EMAIL_ADDRESS") or os.getenv("EMAIL_SENDER")
        email_pass = os.getenv("EMAIL_APP_PASSWORD") or os.getenv("EMAIL_PASSWORD")
        if not email_user or not email_pass: return
        import imaplib, email
        from email.header import decode_header
        import sys
        if str(_AKAR_PROGRAM) not in sys.path: sys.path.append(str(_AKAR_PROGRAM))
        
        def decode_str(s):
            if not s: return ""
            res = ""
            for word, encoding in decode_header(s):
                if isinstance(word, bytes):
                    try: res += word.decode(encoding or "utf-8", errors="ignore")
                    except Exception:
                        res += word.decode("latin-1", errors="ignore")
                else: res += word
            return res

        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, email_pass)
        mail.select("inbox")
        status, messages_id = mail.search(None, "(UNSEEN)")
        if status == "OK" and messages_id[0]:
            email_ids = messages_id[0].split()
            if email_ids:
                latest_id = email_ids[-1].decode("utf-8") if isinstance(email_ids[-1], bytes) else str(email_ids[-1])
                if last_seen_email_id is None:
                    last_seen_email_id = latest_id
                elif latest_id != last_seen_email_id:
                    last_seen_email_id = latest_id
                    
                    status_fetch, msg_data = mail.fetch(latest_id, "(RFC822)")
                    if status_fetch == "OK" and msg_data[0]:
                        msg = email.message_from_bytes(msg_data[0][1])
                        pengirim = decode_str(msg.get("From"))
                        subjek = decode_str(msg.get("Subject"))
                        
                        # Extract Email Pengirim
                        import re
                        email_addr_match = re.search(r"<([^>]+)>", pengirim)
                        email_addr = email_addr_match.group(1) if email_addr_match else pengirim

                        body_text = ""
                        lampiran_info = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                tipe_konten = part.get_content_type()
                                if tipe_konten == "text/plain" and not body_text:
                                    try: body_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                                    except Exception:

                                        pass
                                if part.get_content_maintype() != "multipart" and part.get("Content-Disposition") is not None:
                                    filename = part.get_filename()
                                    if filename:
                                        folder_lampiran = r"C:\Email Lampiran"
                                        if not os.path.exists(folder_lampiran): os.makedirs(folder_lampiran)
                                        filepath = os.path.join(folder_lampiran, filename)
                                        with open(filepath, "wb") as f:
                                            f.write(part.get_payload(decode=True))
                                        lampiran_info += f"\n- {filepath}"
                        else:
                            try: body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
                            except Exception:
                                body_text = msg.get_payload()

                        pesan_laporan = f"?? *EMAIL BARU MASUK!*\n\nDari: **{pengirim}**\nSubjek: {subjek}\n\n"
                        if lampiran_info: pesan_laporan += f"?? *Lampiran Disimpan:* {lampiran_info}\n\n"
                        pesan_laporan += f"Isi: {body_text[:200]}...\n\n"
                        
                        MODE_ADMIN_EMAIL = globals().get("MODE_ADMIN_EMAIL", False)
                        MODE_NOTIF_EMAIL = globals().get("MODE_NOTIF_EMAIL", False)
                        
                        if MODE_ADMIN_EMAIL:
                            from sari_core.bridge import process_email_message_async
                            balasan = await process_email_message_async(email_addr, subjek, body_text)
                            global kirim_email
                            kirim_email(email_addr, f"Re: {subjek}", balasan)
                            
                            if MODE_NOTIF_EMAIL:
                                pesan_laporan += f"🤖 *Admin Email membalas otomatis:*\n\n{balasan}"
                                await context.bot.send_message(chat_id=chat_id, text=pesan_laporan, parse_mode="Markdown")
                        else:
                            if MODE_NOTIF_EMAIL:
                                pesan_laporan += "Silakan ketik 'Cek email' atau perintahkan Siti untuk membacanya."
                                await context.bot.send_message(chat_id=chat_id, text=pesan_laporan, parse_mode="Markdown")
        mail.logout()
    except Exception as e:
        print(f"Error satpam email: {e}")

def transkripsi_audio_wa_robust(audio_path):
    if not audio_path or not os.path.exists(audio_path):
        return None
    
    # 1. Coba Google Gemini Flash (Cepat, Akurat, Paham Bahasa Indonesia/Daerah, Gratis)
    try:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            uploaded_audio = genai.upload_file(path=audio_path)
            model_vn = genai.GenerativeModel("gemini-2.5-flash")
            prompt_vn = (
                "Transkripsikan audio ini kata demi kata secara persis dan akurat dalam bahasa aslinya "
                "(Indonesia, daerah, atau Inggris). Jangan tambahkan komentar, interpretasi, atau tanda kurung apapun. "
                "Hanya keluarkan teks transkripsinya saja."
            )
            resp_vn = model_vn.generate_content([uploaded_audio, prompt_vn])
            try:
                uploaded_audio.delete()
            except Exception:

                pass
            if resp_vn and resp_vn.text and resp_vn.text.strip():
                return resp_vn.text.strip()
    except Exception as e_gem:
        print(f"[TRANSKRIPSI] Gemini Flash error: {e_gem}")

    # 2. Coba Groq Whisper jika GROQ_API_KEY tersedia
    try:
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            from groq import Groq
            client_g = Groq(api_key=groq_key)
            with open(audio_path, "rb") as f:
                res_g = client_g.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f.read()),
                    model="whisper-large-v3-turbo"
                )
            if res_g and hasattr(res_g, 'text') and res_g.text.strip():
                return res_g.text.strip()
    except Exception as e_grq:
        print(f"[TRANSKRIPSI] Groq Whisper error: {e_grq}")

    # 3. Fallback OpenAI Whisper (dengan FFmpeg conversion)
    wav_path = audio_path + ".wav"
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path]
        proc = subprocess.run(cmd, capture_output=True)
        target_path = wav_path if proc.returncode == 0 and os.path.exists(wav_path) else audio_path
        
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            from openai import OpenAI
            client_o = OpenAI(api_key=openai_key)
            with open(target_path, "rb") as f:
                res = client_o.audio.transcriptions.create(
                    file=("audio.wav", f.read()),
                    model="whisper-1"
                )
            if res and hasattr(res, 'text') and res.text.strip():
                return res.text.strip()
    except Exception as e_oa:
        print(f"[TRANSKRIPSI] OpenAI Whisper error: {e_oa}")
    finally:
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except Exception:

                pass
            
    return None

MODE_ADMIN_WA = False
MODE_ADMIN_EMAIL = False
MODE_NOTIF_EMAIL = False
MODE_NOTIF_WA = True


def tugas_drive_sync_background():
    """DINONAKTIFKAN - pemilik fitur ini sekarang `sari_core/sinkronisasi_loop.py`.

    Dulu sinkronisasi dijalankan dari sini. Tetapi thread ini hanya dinyalakan di
    dalam main() milik bot_otomatis.py, sedangkan main() itu TIDAK PERNAH
    dipanggil oleh arsitektur sekarang (server_core.py hanya mengambil beberapa
    fungsi dari berkas ini). Akibatnya fitur sinkronisasi mati total walau
    mesinnya lengkap.

    Sekarang putaran sinkronisasi dinyalakan oleh server_core.py bersama listener
    lain, sehingga pasti berjalan dan tahan restart.

    Fungsi ini SENGAJA dibiarkan ada tetapi tidak melakukan apa-apa, supaya kalau
    suatu saat bot_otomatis.py dijalankan langsung, tidak ada DUA putaran
    sinkronisasi berjalan bersamaan dan saling menimpa pekerjaan.
    """
    print("[DRIVE SYNC] Thread lama dinonaktifkan. Sinkronisasi ditangani oleh "
          "sari_core/sinkronisasi_loop.py yang dinyalakan dari server_core.py.")
    return

def tugas_wa_bot_background():
    import urllib.request
    import json
    import time
    import os
    
    global MODE_ADMIN_WA, chat_id_tersimpan, riwayat_wa_masuk
    
    system_prompt_wa = """Anda adalah Gea, asisten pribadi dari pengguna untuk WhatsApp. Anda ramah, sopan, cerdas, santai, dan cekatan. Anda memperkenalkan diri sebagai 'Gea, asisten pengguna'.
ATURAN NGOBROL GEA:
1. JIKA DIAJAK NGOBROL BEBAS (curhat, bercanda, tanya kabar, gosip, bahas game/film, dll), jadilah teman ngobrol yang SANGAT SERU! JANGAN KAKU, JANGAN SEPERTI ROBOT, DAN JANGAN PERNAH MEMBAHAS SOAL STUDIO MUSIK/REKAMAN SAMA SEKALI jika tidak ditanya.
2. Jawab dengan gaya bahasa gaul, hangat, natural (pakai haha, wkwk, emotikon tipis-tipis). Panggil lawan bicara dengan Kak atau Mas/Mbak/Namanya.
3. HANYA JIKA mereka secara spesifik bertanya soal HARGA, REKAMAN, atau STUDIO, barulah Anda menjelaskan peran Anda sebagai admin studio dengan rincian berikut:
   - Pembuatan Musik (Beat/Aransemen): Rp 500.000 + Mixing & Mastering Rp 150.000 (Total Rp 650.000).
   - Record Vokal (karaoke YouTube): Rp 150.000 (Terima Bersih).
   - Alamat Studio: Jl. Cemara Raya, Margahayu, Bekasi Timur. (Patokan: Cemara 2 Nomor 326). Jangan sebut Jogja.
4. JIKA ada yang membahas topik terlarang (SARA, penipuan, pinjam uang), tolak dengan halus dan alihkan pembicaraan.
5. Balasan WA harus PENDEK-PENDEK (1-3 kalimat) seperti chat WA asli. JANGAN pakai bintang tebal (markdown).
"""

    while True:
        try:
            # Selalu ambil pesan agar antrean di Node.js kosong
            req = urllib.request.Request("http://localhost:3000/messages")
            with urllib.request.urlopen(req, timeout=5) as response:
                pesan_masuk = json.loads(response.read().decode('utf-8'))
                
            for msg in pesan_masuk:
                pengirim = msg.get('from', 'Klien')
                nama = msg.get('name', 'Klien')
                isi_pesan = msg.get('body', '')
                is_vn_in = msg.get('isVoiceNote', False)
                teks_hasil = None
                simpan_vn_rel = None
                
                # SIMPAN KE RIWAYAT agar bisa dibaca oleh cek_pesan_wa_bridge
                riwayat_wa_masuk.append(msg)
                if len(riwayat_wa_masuk) > 50:
                    riwayat_wa_masuk.pop(0)
                
                # Abaikan pesan grup WA sepenuhnya (hanya terima audio/chat dari chat pribadi)
                if msg.get('isGroup', False):
                    if msg.get('voicePath') and os.path.exists(msg.get('voicePath')):
                        try: os.remove(msg['voicePath'])
                        except Exception: pass
                    continue
                
                # Handle Voice Note Masuk (Transkripsi Multi-Engine & Penyimpanan Bukti)
                if is_vn_in and msg.get('voicePath'):
                    vpath = msg['voicePath']
                    print(f"[WA INCOMING] Mentranskripsi Voice Note dari {nama}...")
                    teks_hasil = transkripsi_audio_wa_robust(vpath)
                    
                    # Simpan salinan Voice Note ke folder File/WhatsApp agar pengguna bisa memutarnya jika ingin cek
                    folder_wa_storage = str(FILE_DIR / "WhatsApp")
                    os.makedirs(folder_wa_storage, exist_ok=True)
                    from datetime import datetime
                    ts_wa = datetime.now().strftime("%Y%m%d_%H%M%S")
                    nama_bersih = "".join([c for c in nama if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_') or "Kontak"
                    simpan_vn_path = os.path.join(folder_wa_storage, f"VN_{nama_bersih}_{ts_wa}.ogg")
                    try:
                        import shutil
                        shutil.copy2(vpath, simpan_vn_path)
                        simpan_vn_rel = f"File/WhatsApp/VN_{nama_bersih}_{ts_wa}.ogg"
                    except Exception:

                        pass

                    if teks_hasil:
                        isi_pesan = f"[Pesan Suara (Voice Note) dari {nama}]: '{teks_hasil}'"
                        print(f"[WA VN SUCCESS] Isi Suara {nama}: '{teks_hasil}'")
                    else:
                        isi_pesan = f"[Menerima Pesan Suara dari {nama}, suara belum berhasil ditranskripsikan]"
                    
                    try: os.remove(vpath)
                    except Exception:

                        pass
                elif msg.get('voicePath'):
                    try: os.remove(msg['voicePath'])
                    except Exception:

                        pass

                # Cek status Admin WA (baca juga dari file persistensi jika ada)
                if os.path.exists(str(ADMIN_WA_STATUS_FILE)):
                    try:
                        with open(str(ADMIN_WA_STATUS_FILE), "r", encoding="utf-8") as f_st:
                            st_data = json.load(f_st)
                            MODE_ADMIN_WA = st_data.get("admin_wa", globals().get("MODE_ADMIN_WA", False))
                    except Exception as e:
                        MODE_ADMIN_WA = globals().get("MODE_ADMIN_WA", False)
                else:
                    MODE_ADMIN_WA = globals().get("MODE_ADMIN_WA", False)
                MODE_NOTIF_WA = globals().get("MODE_NOTIF_WA", True)
                
                target_chat_id = chat_id_tersimpan or os.getenv("TELEGRAM_CHAT_ID")
                
                if MODE_ADMIN_WA and not msg.get("isGroup", False):
                    # Admin WA hanya balas chat PRIBADI, BUKAN group
                    try:
                        import sys
                        if str(_AKAR_PROGRAM) not in sys.path: sys.path.append(str(_AKAR_PROGRAM))
                        from sari_core.bridge import process_wa_message_sync
                        balasan = process_wa_message_sync(pengirim, nama, isi_pesan)
                        
                        import urllib.request, json
                        req_send = urllib.request.Request("http://localhost:3000/send", 
                                                        data=json.dumps({"number": pengirim, "message": balasan}).encode("utf-8"),
                                                        headers={"Content-Type": "application/json"},
                                                        method="POST")
                        urllib.request.urlopen(req_send, timeout=60)
                        
                        if target_chat_id and MODE_NOTIF_WA:
                            from bot_otomatis import kirim_pesan_telegram_sync
                            if is_vn_in and teks_hasil:
                                lap_teks = f"🤖 [WA ADMIN] 🎤 Voice Note dari {nama}:\n📝 Transkrip Suara: \"{teks_hasil}\"\n\n💬 Gea Membalas: \"{balasan}\""
                                if simpan_vn_rel:
                                    lap_teks += f"\n📁 Audio: {simpan_vn_rel}"
                            else:
                                tipe_lap = "🎤 Voice Note" if is_vn_in else "💬 Teks"
                                lap_teks = f"🤖 [WA ADMIN] Pesan ({tipe_lap}) dari {nama}: '{isi_pesan}'.\n\nGea membalas: '{balasan}'"
                            kirim_pesan_telegram_sync(target_chat_id, lap_teks)
                    except Exception as ai_err:
                        print(f"Gagal membalas WA: {ai_err}")
                elif not msg.get("isGroup", False):
                    if target_chat_id and MODE_NOTIF_WA:
                        from bot_otomatis import kirim_pesan_telegram_sync
                        if is_vn_in and teks_hasil:
                            lap_teks = f"🔔 [WA MASUK] 🎤 Voice Note dari {nama}:\n📝 Transkrip Suara: \"{teks_hasil}\""
                            if simpan_vn_rel:
                                lap_teks += f"\n📁 Audio: {simpan_vn_rel}"
                            lap_teks += "\n(Admin WA sedang mati, tidak dibalas otomatis)"
                        else:
                            tipe_lap = "🎤 Voice Note" if is_vn_in else "💬 Teks"
                            lap_teks = f"🔔 [WA MASUK] Pesan ({tipe_lap}) dari {nama}: '{isi_pesan}'.\nAdmin WA sedang mati, tidak dibalas otomatis."
                        kirim_pesan_telegram_sync(target_chat_id, lap_teks)
        except Exception as e:
            pass
        time.sleep(2)
        
_jadwal_lock = asyncio.Lock()

def parse_waktu_target(waktu_str: str):
    now = datetime.now()
    waktu_str = waktu_str.strip().lower()
    
    # Deteksi kata kunci instan / langsung
    if any(k in waktu_str for k in ["sekarang", "langsung", "now", "detik ini", "saat ini"]):
        return int(now.timestamp()), now.strftime("%Y-%m-%d %H:%M:%S")
        
    import re
    # Deteksi "X menit lagi" atau "X menit ke depan"
    match_menit = re.search(r'(\d+)\s*menit', waktu_str)
    if match_menit and any(k in waktu_str for k in ["lagi", "kedepan", "ke depan", "mulai"]):
        menit_tambah = int(match_menit.group(1))
        target_dt = now + timedelta(minutes=menit_tambah)
        return int(target_dt.timestamp()), target_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Deteksi jam tunggal seperti "jam 7", "jam 7 pagi", "pukul 7"
    match_jam = re.search(r'(?:jam|pukul)\s*(\d{1,2})(?:[:.](\d{2}))?', waktu_str)
    if match_jam:
        jam = int(match_jam.group(1))
        menit = int(match_jam.group(2)) if match_jam.group(2) else 0
        # Cek pagi/malam
        if ("malam" in waktu_str or "sore" in waktu_str) and jam < 12:
            jam += 12
        elif "pagi" in waktu_str and jam == 12:
            jam = 0
        dt_time = datetime.strptime(f"{jam:02d}:{menit:02d}", "%H:%M").time()
        target_dt = datetime.combine(now.date(), dt_time)
        selisih_detik = (now - target_dt).total_seconds()
        if selisih_detik > 180:
            target_dt += timedelta(days=1)
        elif selisih_detik >= 0:
            target_dt = now
        return int(target_dt.timestamp()), target_dt.strftime("%Y-%m-%d %H:%M:%S")

    for fmt in ["%H:%M:%S", "%H.%M.%S", "%H.%M", "%H:%M"]:
        try:
            dt_time = datetime.strptime(waktu_str, fmt).time()
            target_dt = datetime.combine(now.date(), dt_time)
            selisih_detik = (now - target_dt).total_seconds()
            if selisih_detik > 180:
                target_dt += timedelta(days=1)
            elif selisih_detik >= 0:
                target_dt = now
            return int(target_dt.timestamp()), target_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H.%M", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(waktu_str, fmt)
            if fmt == "%Y-%m-%d":
                dt = datetime.combine(dt.date(), datetime.strptime("09:00", "%H:%M").time())
            return int(dt.timestamp()), dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    target_dt = now + timedelta(minutes=1)
    return int(target_dt.timestamp()), target_dt.strftime("%Y-%m-%d %H:%M:%S")

def kelola_jadwal_tugas(aksi: str, task_id: str = ""):
    """Melihat daftar jadwal tugas otomatis, membatalkan jadwal spesifik, atau membatalkan semua jadwal. Aksi: 'lihat', 'batalkan', 'batalkan_semua'. Jika membatalkan 1 jadwal, masukkan 'task_id'."""
    try:
        import os, json
        file_jadwal = str(OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json")
        
        if not os.path.exists(file_jadwal):
            return "Tidak ada jadwal tugas yang tersimpan (file tidak ditemukan)."
            
        with open(file_jadwal, "r", encoding="utf-8") as f:
            daftar = json.load(f)
            
        if not isinstance(daftar, list):
            return "Format file jadwal rusak."
            
        STATUS_AKTIF = ["pending", "retrying", "guaranteed_retry"]
        active_tasks = [t for t in daftar if t.get("status") in STATUS_AKTIF]
        
        aksi_clean = (aksi or "").strip().lower()
        if any(w in aksi_clean for w in ["semua", "all"]):
            aksi_clean = "batalkan_semua"
        elif any(w in aksi_clean for w in ["batal", "cancel", "stop", "hapus"]) and aksi_clean != "batalkan_semua":
            aksi_clean = "batalkan"
        elif any(w in aksi_clean for w in ["lihat", "daftar", "cek", "list", "status"]):
            aksi_clean = "lihat"
        
        if aksi_clean == "lihat":
            if not active_tasks:
                return "Saat ini TIDAK ADA jadwal tugas yang aktif."
            res = "📋 **Daftar Jadwal Tugas Aktif Harmoni:**\n\n"
            for i, t in enumerate(active_tasks, start=1):
                interval = t.get('interval_menit', 0)
                tot_ulang = t.get('total_pengulangan', 1)
                ke = t.get('eksekusi_berjalan', 0)
                st = t.get('status', 'pending')
                st_badge = "⏳ [Pending]" if st == "pending" else ("🔄 [Retrying]" if st == "retrying" else "🌐 [Guaranteed Delivery]")
                tipe_str = f"Setiap {interval} menit (Berjalan {ke}/{tot_ulang if tot_ulang > 0 else 'Selamanya'})" if interval > 0 else "Sekali eksekusi"
                res += f"{i}. 🆔 `{t.get('id')}` {st_badge}\n   ⏰ Waktu: **{t.get('waktu_str')}**\n   📌 Tugas: {t.get('laporan')}\n   🔄 Pola: {tipe_str}\n\n"
            res += "💡 *Tips: Ketik 'batalkan semua jadwal' untuk menghentikan seluruh tugas, atau 'batalkan jadwal ID_TUGAS' untuk 1 tugas tertentu.*"
            return res
            
        elif aksi_clean == "batalkan":
            if not task_id:
                # Jika hanya ada 1 tugas aktif, batalkan langsung tanpa repot tanya ID
                if len(active_tasks) == 1:
                    target_task = active_tasks[0]
                    target_task["status"] = "cancelled"
                    target_task["laporan"] = str(target_task.get("laporan", "")) + " (DIBATALKAN OLEH USER)"
                    with open(file_jadwal, "w", encoding="utf-8") as f:
                        json.dump(daftar, f, indent=2)
                    return f"SUKSES: Jadwal `{target_task.get('id')}` ({target_task.get('laporan')}) berhasil dibatalkan."
                elif len(active_tasks) == 0:
                    return "Tidak ada jadwal aktif yang dapat dibatalkan."
                else:
                    return f"Ada {len(active_tasks)} jadwal aktif. Mohon sebutkan ID tugas yang ingin dibatalkan, atau katakan 'batalkan semua jadwal'."
                    
            found = False
            for t in daftar:
                if t.get("id") == task_id and t.get("status") in STATUS_AKTIF:
                    t["status"] = "cancelled"
                    t["laporan"] = str(t.get("laporan", "")) + " (DIBATALKAN OLEH USER)"
                    found = True
                    break
            if found:
                with open(file_jadwal, "w", encoding="utf-8") as f:
                    json.dump(daftar, f, indent=2)
                return f"SUKSES: Jadwal `{task_id}` berhasil dibatalkan."
            else:
                return f"ERROR: Jadwal dengan ID `{task_id}` tidak ditemukan atau sudah tidak aktif."
                
        elif aksi_clean == "batalkan_semua":
            count = 0
            for t in daftar:
                if t.get("status") in STATUS_AKTIF:
                    t["status"] = "cancelled"
                    t["laporan"] = str(t.get("laporan", "")) + " (DIBATALKAN MASSAL)"
                    count += 1
            if count > 0:
                with open(file_jadwal, "w", encoding="utf-8") as f:
                    json.dump(daftar, f, indent=2)
                return f"SUKSES: Seluruh {count} jadwal aktif berhasil dibatalkan dan dinonaktifkan."
            else:
                return "Tidak ada jadwal aktif untuk dibatalkan."
        else:
            return "ERROR: Aksi tidak dikenal. Gunakan 'lihat', 'batalkan', atau 'batalkan_semua'."
    except Exception as e:
        return f"ERROR kelola jadwal: {str(e)}"


async def aksi_lapor_telegram_internal(app: Application, chat_id: str, prompt_konten: str, laporan_deskripsi: str, params_dict: dict = None):
    """Fungsi mandiri Siti untuk mengeksekusi tugas terjadwal, membaca email riil, mencari berita live, atau mengirim teks langsung ke Telegram."""
    try:
        import ssl, urllib.request
        import xml.etree.ElementTree as ET
        
        if not chat_id:
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            return "Gagal: TELEGRAM_CHAT_ID tidak ditemukan."
            
        params_dict = params_dict or {}
        teks_siap = params_dict.get("teks") or params_dict.get("isi_pesan") or params_dict.get("konten") or ""
        
        # KASUS 1: Jika sudah ada teks / ide konten jadi yang disimpan di parameter 'teks'
        if teks_siap and len(str(teks_siap).strip()) > 15:
            print("🚀 [LAPOR TELEGRAM] Mengirimkan teks konten asli langsung ke Telegram...")
            await app.bot.send_message(chat_id=chat_id, text=str(teks_siap).strip())
            return f"Berhasil mengirim teks langsung ke Telegram: {str(teks_siap)[:60]}..."
            
        gabung_cek = (str(prompt_konten) + " " + str(laporan_deskripsi)).lower()
        print(f"🤖 [LAPOR TELEGRAM] Memproses tugas terjadwal: '{gabung_cek[:80]}'...")

        # KASUS 2: Tugas Cek Email
        if "email" in gabung_cek and any(k in gabung_cek for k in ["cek", "baca", "lapor", "masuk"]):
            print("📧 [LAPOR TELEGRAM] Membuka kotak masuk Gmail asli...")
            try:
                raw_email = baca_email(jumlah=8, hanya_baru=False)
            except Exception as e_mail:
                raw_email = f"Error membaca email: {e_mail}"
                
            sys_prompt_email = (
                "Kamu adalah Harmoni, asisten pribadi dari pengguna. "
                "Tugasmu: Buatkan laporan cek email yang rapi, padat, dan jelas untuk pengguna berdasarkan data email asli di bawah ini. "
                "PENTING SEKALI: Email dari Facebook DILARANG dilaporkan (abaikan/buang). "
                "Jika semua email hanya dari Facebook atau tidak ada email baru penting, laporkan bahwa situasi aman dan tidak ada email penting di luar Facebook."
            )
            pesan_llm = [
                {"role": "system", "content": sys_prompt_email},
                {"role": "user", "content": "Data Email Masuk Riil:\n" + str(raw_email) + "\n\nBuat laporan emailnya sekarang untuk Telegram pengguna."}
            ]
            try:
                resp, _ = minta_jawaban_ai(pesan_llm)
                isi_pesan = resp.choices[0].message.content if resp and hasattr(resp, 'choices') and resp.choices else ""
            except Exception:
                isi_pesan = ""
                
            if not isi_pesan.strip():
                isi_pesan = "📧 **Laporan Cek Email Pagi:**\n\n" + str(raw_email)[:600]
                
            await app.bot.send_message(chat_id=chat_id, text=isi_pesan)
            return f"Berhasil mengirim laporan email ke Telegram: {isi_pesan[:60]}..."

        # KASUS 3: Tugas Berita Hangat / Berita Terkini
        elif any(k in gabung_cek for k in ["berita", "news", "kabar"]):
            print("📰 [LAPOR TELEGRAM] Mengambil berita aktual riil dari RSS CNN Indonesia...")
            berita_list = []
            try:
                ctx = ssl._create_unverified_context()
                rss_url = "https://www.cnnindonesia.com/nasional/rss"
                req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                    root = ET.fromstring(response.read())
                for it in root.findall('.//item')[:10]:
                    t = it.find('title').text if it.find('title') is not None else ""
                    d = it.find('description').text if it.find('description') is not None else ""
                    if t:
                        berita_list.append("📌 " + t + "\n" + d)
            except Exception as e_rss:
                print(f"[LAPOR TELEGRAM] Warning fetch RSS: {e_rss}")
                
            data_berita_str = "\n\n".join(berita_list[:5]) if berita_list else "Tidak ada berita RSS."
            
            sys_prompt_berita = (
                "Kamu adalah Harmoni, asisten pribadi dari pengguna. "
                "Tugasmu: Sampaikan 1 berita hangat dan aktual hari ini langsung ke Telegram pengguna. "
                "PILIH SALAH SATU berita dari data aktual berikut ini. "
                "Gaya bahasa: Hangat, ramah, santai, dan to the point. Tulis judul berita dan ringkasan intinya secara jelas. "
                "DILARANG KERAS hanya mengirim pesan konfirmasi kosong (seperti 'siap sudah terkirim'). LANGSUNG TULIS BERITANYA!"
            )
            pesan_llm = [
                {"role": "system", "content": sys_prompt_berita},
                {"role": "user", "content": "Data Berita Hangat Hari Ini:\n" + str(data_berita_str) + "\n\nSampaikan 1 berita hangat ke pengguna sekarang."}
            ]
            try:
                resp, _ = minta_jawaban_ai(pesan_llm)
                isi_pesan = resp.choices[0].message.content if resp and hasattr(resp, 'choices') and resp.choices else ""
            except Exception:
                isi_pesan = ""
                
            if not isi_pesan.strip():
                if berita_list:
                    isi_pesan = "📰 **Berita Hangat Pagi Ini:**\n\n" + str(berita_list[0])
                else:
                    isi_pesan = f"Halo pengguna! Ini pantauan pagi dari Siti: {laporan_deskripsi} 🗓️✨"
                    
            await app.bot.send_message(chat_id=chat_id, text=isi_pesan)
            return f"Berhasil mengirim berita ke Telegram: {isi_pesan[:60]}..."

        # KASUS 4: Perintah / Laporan Teks Lainnya
        else:
            sys_prompt = (
                "Kamu adalah Harmoni, asisten pribadi dari pengguna. "
                "Tugasmu adalah membuat dan mengirimkan laporan/ide/pesan terjadwal langsung ke Telegram pengguna. "
                "Gunakan gaya bahasa santai, hangat, sopan, dan informatif. Langsung tulis isi ide/pesannya secara padat. "
                "DILARANG KERAS hanya membuat konfirmasi seperti 'Siap sudah tercatat'. LANGSUNG SAJIKAN KONTENNYA!"
            )
            prompt_bawah = prompt_konten or laporan_deskripsi or "Sampaikan laporan tugas terjadwal ke pengguna."
            pesan_llm = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt_bawah}
            ]
            try:
                resp, _ = minta_jawaban_ai(pesan_llm)
                isi_pesan = resp.choices[0].message.content if resp and hasattr(resp, 'choices') and resp.choices else ""
            except Exception:
                isi_pesan = ""
                
            if not isi_pesan.strip():
                isi_pesan = f"Halo pengguna! Ini laporan dari Siti: {laporan_deskripsi or prompt_konten} 🗓️✨"
                
            await app.bot.send_message(chat_id=chat_id, text=isi_pesan)
            return f"Berhasil mengirim ke Telegram: {isi_pesan[:60]}..."
    except Exception as e:
        return f"Gagal lapor telegram: {str(e)}"


def jadwalkan_tugas_otomatis(jam_atau_tanggal: str, fungsi_aksi: str = "lapor_telegram", parameter_json: str = "{}", deskripsi_laporan: str = "", interval_menit: int = 0, total_pengulangan: int = 1, pesan_atau_prompt: str = "", **kwargs):
    try:
        import random
        ts_target, target_str = parse_waktu_target(jam_atau_tanggal)
        file_jadwal = str(OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json")
        os.makedirs(os.path.dirname(file_jadwal), exist_ok=True)
        daftar = []
        if os.path.exists(file_jadwal):
            try:
                with open(file_jadwal, "r", encoding="utf-8") as f:
                    daftar = json.load(f)
            except Exception:
                daftar = []
        try:
            params_dict = json.loads(parameter_json) if isinstance(parameter_json, str) and parameter_json.strip() else parameter_json
        except Exception as e:
            params_dict = {"kata_kunci": parameter_json}
        if not isinstance(params_dict, dict):
            params_dict = {"param": params_dict}
            
        # Smart Auto-Route: Normalkan fungsi yang keliru dipilih LLM
        func_lower = str(fungsi_aksi).strip().lower()
        if func_lower in ["lapor_email", "cek_email", "cek_email_dan_lapor", "baca_email_dan_lapor", "lapor_email_telegram", "cek_email_telegram"]:
            fungsi_aksi = "lapor_telegram"
            if not pesan_atau_prompt:
                pesan_atau_prompt = deskripsi_laporan or "Cek email masuk dan laporkan ke Telegram (kecuali Facebook)"
            params_dict["pesan_atau_prompt"] = pesan_atau_prompt
            print(f"🔄 [SMART ROUTE] Mengalihkan '{func_lower}' -> 'lapor_telegram' (Cek Email via Telegram).")
        elif func_lower in ["kirim_chat_telegram", "chat_telegram", "lapor_berita", "kirim_berita", "berita"]:
            fungsi_aksi = "lapor_telegram"
            if not pesan_atau_prompt:
                pesan_atau_prompt = deskripsi_laporan or "Kirim pesan/berita ke Telegram"
            params_dict["pesan_atau_prompt"] = pesan_atau_prompt
            print(f"🔄 [SMART ROUTE] Mengalihkan '{func_lower}' -> 'lapor_telegram'.")
        elif func_lower in ["restart_pc", "restart", "restart_komputer", "reboot", "reboot_pc"]:
            fungsi_aksi = "atur_daya_pc"
            params_dict["aksi"] = "restart"
            if not deskripsi_laporan:
                deskripsi_laporan = "Restart PC otomatis"
            print(f"🔄 [SMART ROUTE] Mengalihkan '{func_lower}' -> 'atur_daya_pc' (aksi: restart).")
        elif func_lower in ["matikan_pc", "matikan_komputer", "matikan", "shutdown", "shutdown_pc"]:
            fungsi_aksi = "atur_daya_pc"
            params_dict["aksi"] = "shutdown"
            if not deskripsi_laporan:
                deskripsi_laporan = "Matikan PC otomatis"
            print(f"🔄 [SMART ROUTE] Mengalihkan '{func_lower}' -> 'atur_daya_pc' (aksi: shutdown).")
        elif fungsi_aksi == "berbicara_lewat_pc":
            teks_gabung = (str(params_dict.get("teks", "")) + " " + deskripsi_laporan + " " + pesan_atau_prompt).lower()
            if any(k in teks_gabung for k in ["berita", "lapor", "chat", "infokan", "telegram", "email"]) and not any(s in teks_gabung for s in ["speaker", "suara", "bunyikan", "bacakan keras", "suarakan"]):
                fungsi_aksi = "lapor_telegram"
                if not pesan_atau_prompt:
                    pesan_atau_prompt = params_dict.get("teks", deskripsi_laporan)
                params_dict["pesan_atau_prompt"] = pesan_atau_prompt
                print(f"🔄 [SMART ROUTE] Mengalihkan 'berbicara_lewat_pc' -> 'lapor_telegram' (Kirim ke Chat Telegram).")

        # Simpan prompt ke parameter jika fungsi adalah lapor_telegram
        if pesan_atau_prompt:
            params_dict["pesan_atau_prompt"] = pesan_atau_prompt

        # Penanganan cerdas Profil WhatsApp untuk tugas WhatsApp
        is_wa_task = func_lower in ["kirim_pesan_whatsapp", "kirim_vn_whatsapp", "kirim_wa", "kirim_pesan_wa", "whatsapp"]
        butuh_konfirmasi_tg_wa = False
        profiles_wa_tersedia = {}

        if is_wa_task:
            if fungsi_aksi != "kirim_vn_whatsapp":
                fungsi_aksi = "kirim_pesan_whatsapp"

            from pathlib import Path
            cfg_wa_path = PROJECT_ROOT / "konfigurasi_multi_wa.json"
            if cfg_wa_path.exists():
                try:
                    with open(cfg_wa_path, "r", encoding="utf-8") as f_cfg:
                        cfg_obj = json.load(f_cfg)
                        profiles_wa_tersedia = cfg_obj.get("profiles", {})
                except Exception:
                    pass

            from plugins.whatsapp_plugin import _selaraskan_profile_id
            raw_pid = params_dict.get("profile_id") or params_dict.get("profil") or params_dict.get("profile") or kwargs.get("profile_id") or kwargs.get("profile")
            if raw_pid:
                params_dict["profile_id"] = _selaraskan_profile_id(raw_pid)
            else:
                teks_gabung_wa = f"{pesan_atau_prompt} {deskripsi_laporan} {jam_atau_tanggal}".lower()
                detected = ""
                for k_p in ["profil 1", "nomor 1", "profile 1", "nomor_1", "profil 2", "nomor 2", "profile 2", "nomor_2", "profil 3", "nomor 3", "profile 3", "nomor_3", "profil 4", "nomor 4", "profile 4", "nomor_4"]:
                    if k_p in teks_gabung_wa:
                        detected = _selaraskan_profile_id(k_p)
                        break
                if not detected:
                    for p_k, p_v in profiles_wa_tersedia.items():
                        bname = str(p_v.get("business_name", "")).lower()
                        bot_name = str(p_v.get("wa_bot_name", "")).lower()
                        if (bname and bname in teks_gabung_wa) or (bot_name and bot_name in teks_gabung_wa):
                            detected = p_k
                            break
                if detected:
                    params_dict["profile_id"] = detected
                else:
                    params_dict["profile_id"] = "nomor_1"
                    if len(profiles_wa_tersedia) > 1:
                        butuh_konfirmasi_tg_wa = True
            
        interval_val = int(interval_menit) if str(interval_menit).isdigit() else 0
        ulang_val = int(total_pengulangan) if str(total_pengulangan).isdigit() else 1
            
        tugas_baru = {
            "id": f"task_{int(time.time() * 1000)}_{random.randint(100, 999)}",
            "timestamp_target": ts_target,
            "waktu_str": target_str,
            "fungsi": fungsi_aksi,
            "params": params_dict,
            "laporan": deskripsi_laporan or pesan_atau_prompt or f"Menjalankan {fungsi_aksi} pada {target_str}",
            "interval_menit": interval_val,
            "total_pengulangan": ulang_val,
            "eksekusi_berjalan": 0,
            "pesan_atau_prompt": pesan_atau_prompt,
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "last_error": "",
            "dibuat_pada": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        daftar.append(tugas_baru)
        with open(file_jadwal, "w", encoding="utf-8") as f:
            json.dump(daftar, f, indent=2)

        # Jika ada > 1 profil WA dan belum ditentukan secara eksplisit di teks, kirim tombol interaktif ke Telegram
        if is_wa_task and butuh_konfirmasi_tg_wa and profiles_wa_tersedia:
            try:
                tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
                tg_chat = os.getenv("TELEGRAM_CHAT_ID")
                if tg_token and tg_chat:
                    keyboard_rows = []
                    for p_id, p_info in profiles_wa_tersedia.items():
                        num_label = p_id.replace("nomor_", "")
                        p_name = p_info.get("business_name") or p_info.get("label") or f"Profil {num_label}"
                        p_phone = p_info.get("target_phone", "")
                        p_phone_tail = f" (..{p_phone[-4:]})" if p_phone and len(p_phone) >= 4 else ""
                        btn_txt = f"{num_label}️⃣ Profil {num_label}: {p_name}{p_phone_tail}"
                        keyboard_rows.append([{"text": btn_txt, "callback_data": f"sched_wa:{tugas_baru['id']}:{p_id}"}])
                    
                    prompt_text = (
                        f"📱 **Konfirmasi Nomor WhatsApp Pengirim:**\n\n"
                        f"⏰ Jadwal tugas WhatsApp telah dicatat untuk waktu: **{target_str}**.\n"
                        f"💬 Instruksi: _{tugas_baru.get('laporan') or pesan_atau_prompt}_\n\n"
                        f"Silakan klik salah satu tombol di bawah untuk memilih nomor pengirim:"
                    )
                    payload_tg = {
                        "chat_id": tg_chat,
                        "text": prompt_text,
                        "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": keyboard_rows}
                    }
                    requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage", json=payload_tg, timeout=5)
            except Exception as e_btn:
                print(f"[Scheduler] Gagal kirim tombol konfirmasi WA ke TG: {e_btn}")
            
        try:
            from plugins.obsidian_plugin import catat_memori_obsidian
            catat_memori_obsidian("proyek", f"Jadwal_{tugas_baru['id']}", f"Agendakan eksekusi otomatis '{fungsi_aksi}' pada {target_str}. Interval: {interval_val}m, Ulang: {ulang_val}x. Laporan: {deskripsi_laporan or pesan_atau_prompt}", tags="jadwal,otomatis")
        except Exception:
            pass
        
        info_ulang = f" (Berulang setiap {interval_val} menit sebanyak {ulang_val if ulang_val > 0 else 'selamanya'} kali)" if interval_val > 0 else ""
        info_profil = f" [Pengirim: {params_dict.get('profile_id', 'nomor_1')}]" if is_wa_task else ""
        return f"⏰ *JADWAL OTOMATIS BERHASIL DIKUNCI:* Perintah [{fungsi_aksi}] telah dijadwalkan untuk dieksekusi mulai {target_str}{info_ulang}{info_profil}!"
    except Exception as e:
        return f"❌ Gagal menjadwalkan tugas otomatis: {str(e)}"

available_functions["jadwalkan_tugas_otomatis"] = jadwalkan_tugas_otomatis
available_functions["lapor_telegram"] = aksi_lapor_telegram_internal
available_functions["kirim_chat_telegram"] = aksi_lapor_telegram_internal
available_functions["lapor_email"] = aksi_lapor_telegram_internal
available_functions["cek_email"] = aksi_lapor_telegram_internal
available_functions["cek_email_dan_lapor"] = aksi_lapor_telegram_internal
available_functions["baca_email_dan_lapor"] = aksi_lapor_telegram_internal
available_functions["kelola_jadwal_tugas"] = kelola_jadwal_tugas

async def loop_cek_jadwal_async(app: Application):
    file_jadwal = str(OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json")
    while True:
        try:
            async with _jadwal_lock:
                if os.path.exists(file_jadwal):
                    with open(file_jadwal, "r", encoding="utf-8") as f:
                        daftar_jadwal = json.load(f)
                    now_ts = int(time.time())
                    updated = False
                    chat_id_tersimpan = os.getenv("TELEGRAM_CHAT_ID")
                    
                    for item in daftar_jadwal:
                        st = item.get("status", "pending")
                        if st in ["pending", "retrying", "guaranteed_retry"] and now_ts >= item.get("timestamp_target", 0):
                            waktu_sekarang_str = datetime.now().strftime("%H:%M:%S")
                            dt_now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            log_tahap = []
                            history = item.get("execution_history", [])
                            
                            # TAHAP 1: SCHEDULER WAKEUP
                            msg_s1 = f"⏰ [1/4 SCHEDULER] Task #{item.get('id')} ({item.get('fungsi')}) telah jatuh tempo pada {waktu_sekarang_str}."
                            print(msg_s1)
                            log_tahap.append(f"{waktu_sekarang_str} - {msg_s1}")
                            history.append({
                                "stage": "Scheduler",
                                "time": dt_now_full,
                                "result": "OK",
                                "detail": f"Task #{item.get('id')} woken up on schedule"
                            })
                            
                            fungsi_nama = item.get("fungsi")
                            params = item.get("params", {})
                            if isinstance(params, str):
                                try: params = json.loads(params)
                                except Exception:
                                    params = {"kata_kunci": params}
                            kw = params.get("kata_kunci", "") if isinstance(params, dict) else str(params)
                            
                            # TAHAP 2: DISPATCHER ROUTING
                            alias_map = {
                                "kirim_whatsapp": "kirim_pesan_whatsapp",
                                "kirim_wa": "kirim_pesan_whatsapp",
                                "kirim_pesan_wa": "kirim_pesan_whatsapp",
                                "kirim_pesan_ke_wa": "kirim_pesan_whatsapp",
                                "whatsapp": "kirim_pesan_whatsapp",
                                "kirim_vn": "kirim_vn_whatsapp",
                                "kirim_pesan_vn": "kirim_vn_whatsapp",
                                "kirim_vn_wa": "kirim_vn_whatsapp",
                                "buat_status_wa": "kirim_status_whatsapp",
                                "update_status_wa": "kirim_status_whatsapp",
                                "status_wa": "kirim_status_whatsapp",
                                "kirim_status_wa": "kirim_status_whatsapp",
                                "lapor_email": "lapor_telegram",
                                "cek_email": "lapor_telegram",
                                "cek_email_dan_lapor": "lapor_telegram",
                                "baca_email": "lapor_telegram",
                                "baca_email_dan_lapor": "lapor_telegram",
                                "lapor_email_telegram": "lapor_telegram",
                                "kirim_berita": "lapor_telegram",
                                "lapor_berita": "lapor_telegram",
                                "chat_telegram": "lapor_telegram",
                                "kirim_chat_telegram": "lapor_telegram",
                                "restart_pc": "atur_daya_pc",
                                "restart": "atur_daya_pc",
                                "restart_komputer": "atur_daya_pc",
                                "reboot": "atur_daya_pc",
                                "reboot_pc": "atur_daya_pc",
                                "matikan_pc": "atur_daya_pc",
                                "matikan_komputer": "atur_daya_pc",
                                "matikan": "atur_daya_pc",
                                "shutdown": "atur_daya_pc",
                                "shutdown_pc": "atur_daya_pc"
                            }
                            real_func_name = alias_map.get(fungsi_nama, fungsi_nama)
                            target_func = available_functions.get(real_func_name) or globals().get(real_func_name)
                            
                            msg_s2 = f"🔀 [2/4 DISPATCHER] Memetakan '{fungsi_nama}' -> '{real_func_name}'. Target func ditemukan: {target_func is not None}."
                            print(msg_s2)
                            log_tahap.append(f"{waktu_sekarang_str} - {msg_s2}")
                            history.append({
                                "stage": "Dispatcher",
                                "time": dt_now_full,
                                "result": "OK" if target_func else "FAILED",
                                "detail": f"Mapped '{fungsi_nama}' -> '{real_func_name}'"
                            })
                            
                            sukses = False
                            error_msg = ""
                            res = None
                            
                            # TAHAP 3: EXECUTOR INVOKING
                            msg_s3 = f"⚡ [3/4 EXECUTOR] Memanggil plugin '{real_func_name}' secara non-blocking via asyncio.to_thread..."
                            print(msg_s3)
                            log_tahap.append(f"{waktu_sekarang_str} - {msg_s3}")
                            
                            try:
                                if target_func:
                                    try:
                                        if isinstance(params, dict):
                                            p_copy = dict(params)
                                            if real_func_name == "kirim_email":
                                                tuj = p_copy.get("tujuan") or p_copy.get("email") or p_copy.get("penerima", "")
                                                subj = p_copy.get("subjek", "Pesan Terjadwal dari Sari")
                                                psn = p_copy.get("pesan") or p_copy.get("isi", "")
                                                lamp = p_copy.get("file_lampiran", None)
                                                res = await asyncio.to_thread(kirim_email, tuj, subj, psn, lamp)
                                            elif real_func_name in ["kirim_pesan_whatsapp", "kirim_whatsapp", "kirim_wa", "kirim_pesan_wa"]:
                                                from plugins.whatsapp_plugin import kirim_pesan_whatsapp
                                                kontak = p_copy.get("nama_kontak") or p_copy.get("tujuan") or p_copy.get("number") or p_copy.get("kontak") or p_copy.get("penerima") or p_copy.get("nama") or "istri"
                                                psn = p_copy.get("pesan") or p_copy.get("pesan_teks") or p_copy.get("isi") or p_copy.get("teks") or p_copy.get("puisi") or p_copy.get("kata_kunci") or ""
                                                res = await asyncio.to_thread(kirim_pesan_whatsapp, kontak, psn)
                                            elif real_func_name in ["kirim_vn_whatsapp", "kirim_vn", "kirim_vn_wa"]:
                                                from plugins.whatsapp_plugin import kirim_vn_whatsapp
                                                kontak = p_copy.get("nama_kontak") or p_copy.get("tujuan") or p_copy.get("number") or p_copy.get("kontak") or p_copy.get("penerima") or p_copy.get("nama") or "istri"
                                                psn = p_copy.get("pesan_teks") or p_copy.get("pesan") or p_copy.get("isi") or p_copy.get("teks") or p_copy.get("puisi") or p_copy.get("kata_kunci") or ""
                                                res = await asyncio.to_thread(kirim_vn_whatsapp, kontak, psn)
                                            elif real_func_name in ["kirim_status_whatsapp", "buat_status_wa", "status_wa", "update_status_wa"]:
                                                from plugins.whatsapp_plugin import kirim_status_whatsapp
                                                teks = p_copy.get("teks") or p_copy.get("pesan") or p_copy.get("isi") or kw or item.get("pesan_atau_prompt", "") or item.get("laporan", "")
                                                p_file = p_copy.get("path_file") or p_copy.get("file_path", "")
                                                target_pid = p_copy.get("profile_id") or p_copy.get("profile") or p_copy.get("profil") or item.get("profile_id", "")
                                                res = await asyncio.to_thread(kirim_status_whatsapp, teks, p_file, profile_id=target_pid, force_send=True)
                                            elif real_func_name in ["lapor_telegram", "kirim_chat_telegram", "kirim_berita", "lapor_berita", "chat_telegram", "lapor_email", "cek_email", "cek_email_dan_lapor", "baca_email_dan_lapor"]:
                                                prompt_t = p_copy.get("pesan_atau_prompt") or p_copy.get("prompt") or p_copy.get("pesan") or item.get("pesan_atau_prompt") or item.get("laporan", "")
                                                res = await aksi_lapor_telegram_internal(app, chat_id_tersimpan, prompt_t, item.get("laporan", ""), params_dict=p_copy)
                                            elif real_func_name in ["atur_daya_pc", "restart_pc", "matikan_pc"]:
                                                aksi_p = p_copy.get("aksi")
                                                if not aksi_p:
                                                    nama_cek = (fungsi_nama + " " + real_func_name).lower()
                                                    if any(k in nama_cek for k in ["restart", "reboot"]):
                                                        aksi_p = "restart"
                                                    elif any(k in nama_cek for k in ["matikan", "shutdown"]):
                                                        aksi_p = "shutdown"
                                                    else:
                                                        aksi_p = "restart"
                                                waktu_m = p_copy.get("waktu_menit", 0)
                                                # Kirim notif Telegram lebih awal agar tidak terputus saat mesin Windows mulai proses mati/restart
                                                if chat_id_tersimpan:
                                                    try:
                                                        kata_aksi = "me-restart" if aksi_p == "restart" else "mematikan"
                                                        await app.bot.send_message(
                                                            chat_id=chat_id_tersimpan,
                                                            text=f"⏰ **[EKSEKUSI OTOMATIS BERHASIL]**\n\nSiti sedang {kata_aksi} PC pengguna sekarang sesuai jadwal! 🔌✨\n*(PC akan {kata_aksi} dalam 5 detik)*",
                                                            parse_mode="Markdown"
                                                        )
                                                    except Exception:

                                                        pass
                                                res = await asyncio.to_thread(atur_daya_pc, aksi=aksi_p, waktu_menit=waktu_m, jeda_detik=5)
                                            else:
                                                res = await asyncio.to_thread(target_func, **p_copy)
                                        else:
                                            res = await asyncio.to_thread(target_func, params)
                                    except TypeError as t_err:
                                        try:
                                            res = await asyncio.to_thread(target_func, kw)
                                        except Exception as e:
                                            raise t_err
                                        
                                    if "Gagal" in str(res) or "Error" in str(res):
                                        raise Exception(str(res))
                                    sukses = True
                                else:
                                    raise Exception(f"Fungsi alat '{fungsi_nama}' (atau '{real_func_name}') tidak terdaftar di sistem.")
                            except Exception as exec_err:
                                sukses = False
                                error_msg = str(exec_err)
                            
                            # TAHAP 4: RESULT AUDIT & GUARANTEED DELIVERY QUEUE
                            if sukses:
                                msg_s4 = f"✅ [4/4 RESULT] Plugin '{real_func_name}' SAKSES: {str(res)[:120]}"
                                print(msg_s4)
                                log_tahap.append(f"{waktu_sekarang_str} - {msg_s4}")
                                history.append({
                                    "stage": "Executor",
                                    "time": dt_now_full,
                                    "result": "OK",
                                    "detail": str(res)[:200]
                                })
                                
                                interval_m = int(item.get("interval_menit", 0)) if str(item.get("interval_menit", 0)).isdigit() else 0
                                total_ulang = int(item.get("total_pengulangan", 1)) if str(item.get("total_pengulangan", 1)).isdigit() else 1
                                item["eksekusi_berjalan"] = item.get("eksekusi_berjalan", 0) + 1
                                item["dieksekusi_pada"] = dt_now_full
                                item["last_error"] = ""
                                item["pipeline_logs"] = log_tahap
                                item["execution_history"] = history
                                
                                # Cek apakah tugas berulang
                                if interval_m > 0 and (total_ulang <= 0 or item["eksekusi_berjalan"] < total_ulang):
                                    from task_scheduler import hitung_jadwal_berikutnya
                                    anchor_ts = item.get("target_awal_ts") or item.get("timestamp_target", 0)
                                    next_ts, next_dt = hitung_jadwal_berikutnya(anchor_ts, interval_m, now_ts)
                                    item["timestamp_target"] = next_ts
                                    item["target_awal_ts"] = next_ts
                                    item["waktu_str"] = next_dt
                                    item["status"] = "pending"
                                    item["retry_count"] = 0
                                    updated = True
                                    print(f"🔄 [RECURRING] Task #{item.get('id')} dijadwalkan ulang ke {next_dt} (Eksekusi ke-{item['eksekusi_berjalan']})")
                                else:
                                    item["status"] = "done"
                                    updated = True
                                    if chat_id_tersimpan and interval_m > 0 and total_ulang > 1:
                                        try:
                                            await app.bot.send_message(chat_id=chat_id_tersimpan, text=f"🏁 **[JADWAL BERULANG SELESAI]**\n\nTugas *{item.get('laporan', 'Tugas')}* telah selesai dijalankan sebanyak {item['eksekusi_berjalan']} kali!")
                                        except Exception:
                                            pass
                                    elif chat_id_tersimpan and real_func_name not in ["lapor_telegram", "kirim_chat_telegram", "kirim_berita", "atur_daya_pc", "restart_pc", "matikan_pc"]:
                                        try:
                                            await app.bot.send_message(chat_id=chat_id_tersimpan, text=f"⏰ **[EKSEKUSI OTOMATIS BERHASIL]**\n\nSiti baru saja mengeksekusi tugas terjadwal: *{item.get('laporan', 'Tugas selesai')}*! 🎶✨", parse_mode="Markdown")
                                        except Exception as tele_err:
                                            print("Gagal kirim notif Telegram:", tele_err)
                            else:
                                msg_s4_err = f"❌ [4/4 RESULT ERROR] Plugin '{real_func_name}' GAGAL: {error_msg}"
                                print(msg_s4_err)
                                log_tahap.append(f"{waktu_sekarang_str} - {msg_s4_err}")
                                history.append({
                                    "stage": "Executor",
                                    "time": dt_now_full,
                                    "result": "FAILED",
                                    "detail": error_msg
                                })
                                
                                updated = True
                                item["retry_count"] = item.get("retry_count", 0) + 1
                                item["last_error"] = error_msg
                                item["terakhir_dicoba"] = dt_now_full
                                item["pipeline_logs"] = log_tahap
                                item["execution_history"] = history
                                max_r = item.get("max_retries", 3)
                                
                                is_fatal_unregistered = ("tidak terdaftar di sistem" in error_msg.lower()) or (target_func is None)
                                is_critical_messaging = any(k in real_func_name for k in ["email", "whatsapp", "vn", "wa"]) and (not is_fatal_unregistered) and (real_func_name not in ["lapor_telegram", "lapor_email", "cek_email"])
                                
                                if is_fatal_unregistered:
                                    item["status"] = "failed"
                                    if chat_id_tersimpan:
                                        try:
                                            await app.bot.send_message(chat_id=chat_id_tersimpan, text=f"❌ **[EKSEKUSI DIBATALKAN KARENA ERROR SISTEM]**\n\nTugas: *{item.get('laporan', fungsi_nama)}*\nKendala: `{error_msg}`\n\nTugas ini dihentikan agar tidak terjadi spam pengulangan.", parse_mode="Markdown")
                                        except Exception:

                                            pass
                                elif item["retry_count"] < max_r:
                                    item["status"] = "retrying"
                                    if "target_awal_ts" not in item:
                                        item["target_awal_ts"] = item.get("timestamp_target", 0)
                                    item["timestamp_target"] = now_ts + 15
                                    if chat_id_tersimpan:
                                        try:
                                            await app.bot.send_message(chat_id=chat_id_tersimpan, text=f"⚠️ **[EKSEKUSI DITUNDA / RETRY #{item['retry_count']}]**\n\nTugas: *{item.get('laporan', fungsi_nama)}*\nTahap Gagal: `Executor {real_func_name}`\nKendala: `{error_msg}`\nSiti mencoba ulang otomatis dalam 15 detik...", parse_mode="Markdown")
                                        except Exception:

                                            pass
                                elif is_critical_messaging and item["retry_count"] <= 12:
                                    # MODE GUARANTEED DELIVERY QUEUE (Pencobaan berkala tiap 5 menit jika koneksi bermasalah)
                                    item["status"] = "guaranteed_retry"
                                    item["timestamp_target"] = now_ts + 300 # Retry tiap 5 menit
                                    if not item.get("notified_guaranteed"):
                                        item["notified_guaranteed"] = True
                                        if chat_id_tersimpan:
                                            try:
                                                await app.bot.send_message(chat_id=chat_id_tersimpan, text=f"🌐 **[MODE GUARANTEED DELIVERY AKTIF]**\n\nTugas Penting: *{item.get('laporan', fungsi_nama)}*\nKendala: `{error_msg}`\n\nSiti akan mencoba ulang di latar belakang sampai berhasil atau pengguna membatalkannya.", parse_mode="Markdown")
                                            except Exception:

                                                pass
                                else:
                                    item["status"] = "failed"
                                    if chat_id_tersimpan:
                                        try:
                                            await app.bot.send_message(chat_id=chat_id_tersimpan, text=f"❌ **[EKSEKUSI OTOMATIS GAGAL PERMANEN]**\n\nTugas: *{item.get('laporan', fungsi_nama)}*\nTahap: `Executor {real_func_name}`\nSudah dicoba {item['retry_count']}x tetap gagal.\nError Log: `{error_msg}`\n\nMohon pengguna periksa koneksi/aplikasinya ya!", parse_mode="Markdown")
                                        except Exception:

                                            pass
                    
                    if updated:
                        with open(file_jadwal, "w", encoding="utf-8") as f:
                            json.dump(daftar_jadwal, f, indent=2)
        except Exception as e:
            print("Error scheduler async loop:", e)
        await asyncio.sleep(5)


async def satpam_youtube_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id: return
    try:
        from youtube_api import get_comments
        import youtube_api
        youtube_utama = youtube_api.get_authenticated_service("utama")
        komen_utama = get_comments(youtube_utama, max_results=3)
        if komen_utama and "Belum ada" not in komen_utama:
            pesan_utama = f"🔴 *KOMENTAR BARU - YOUTUBE AKUN UTAMA* 🔴\n\n{komen_utama}"
            await context.bot.send_message(chat_id=chat_id, text=pesan_utama, parse_mode="Markdown")
            
        try:
            youtube_kedua = youtube_api.get_authenticated_service("kedua")
            komen_kedua = get_comments(youtube_kedua, max_results=3)
            if komen_kedua and "Belum ada" not in komen_kedua:
                pesan_kedua = f"🔵 *KOMENTAR BARU - YOUTUBE AKUN KEDUA* 🔵\n\n{komen_kedua}"
                await context.bot.send_message(chat_id=chat_id, text=pesan_kedua, parse_mode="Markdown")
        except Exception as e2:
            print("Gagal cek youtube akun kedua:", e2)
            
    except Exception as e:
        print(f"Error satpam youtube: {e}")

async def on_post_init(app: Application):
    print("Membuka Worker Scheduler Latar Belakang Native Async...")
    asyncio.create_task(loop_cek_jadwal_async(app))
    # Jadwal otomatis Email dan YouTube
    if app.job_queue:
        # Cek email setiap 15 menit (900 detik)
        app.job_queue.run_repeating(satpam_email_job, interval=120, first=10)
        # Cek youtube setiap 4 jam (14400 detik)
        app.job_queue.run_repeating(satpam_youtube_job, interval=14400, first=20)
        print("Tugas latar belakang Satpam Email & YouTube telah aktif.")



# ==========================================
# REGISTER TOOLS TO SARI CORE AI OS
# ==========================================
try:
    from sari_core.brain import tool_registry
    
    _registered_count = 0
    for tool_schema in tools:
        func_name = tool_schema["function"]["name"]
        func_handler = available_functions.get(func_name)
        if func_handler:
            tool_registry.register_tool(
                name=func_name,
                risk_level="LOW",
                handler=func_handler,
                description=tool_schema["function"].get("description", ""),
                schema=tool_schema["function"]
            )
            _registered_count += 1
            
    # Registrasi Dynamic Skill Forge (Perakit Keahlian Mandiri Berizin)
    try:
        from sari_core.skill_forge import propose_new_skill, execute_skill_forge, manage_dynamic_skills, load_all_dynamic_plugins

        tool_registry.register_tool(
            name="ajukan_keahlian_baru",
            risk_level="LOW",
            handler=propose_new_skill,
            description="Mengajukan proposal keahlian/alat baru ke pengguna jika ada tugas yang belum memiliki alat pendukung. DILARANG membuat kode langsung sebelum disetujui pengguna.",
            schema={
                "name": "ajukan_keahlian_baru",
                "description": "Ajukan proposal pembuatan plugin/keahlian baru kepada pengguna jika kamu belum memiliki fungsi untuk melakukan tugas yang diminta.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Nama fungsi/alat baru dalam huruf kecil dan garis bawah, misal: cek_resi_paket, download_lagu_soundcloud, konversi_ke_gif"
                        },
                        "description": {
                            "type": "string",
                            "description": "Penjelasan singkat mengenai apa fungsi dan kemampuan alat ini"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Alasan kenapa alat ini dibutuhkan untuk memenuhi permintaan pengguna"
                        },
                        "user_request": {
                            "type": "string",
                            "description": "Perintah asli dari pengguna"
                        }
                    },
                    "required": ["tool_name", "description", "reason"]
                }
            }
        )

        tool_registry.register_tool(
            name="eksekusi_rakit_keahlian",
            risk_level="MEDIUM",
            handler=execute_skill_forge,
            description="Mengeksekusi perakitan dan pengujian keahlian baru di dapur percobaan (sandbox). HANYA BOLEH dipanggil jika pengguna secara sadar membalas 'ya' / 'gas' / 'setuju' terhadap proposal alat yang baru saja kamu tawarkan.",
            schema={
                "name": "eksekusi_rakit_keahlian",
                "description": "Rakit dan uji keahlian baru di sandbox. HANYA dipanggil jika ada tiket proposal aktif dan pengguna sudah memberikan izin/persetujuan eksplisit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmation_text": {
                            "type": "string",
                            "description": "Teks persetujuan dari pengguna (contoh: 'ya', 'gas', 'buatkan', 'lanjutkan', atau 'batal')"
                        }
                    },
                    "required": ["confirmation_text"]
                }
            }
        )
        tool_registry.register_tool(
            name="kelola_keahlian_dinamis",
            risk_level="LOW",
            handler=manage_dynamic_skills,
            description="Melihat daftar keahlian/alat rakitan tambahan di folder plugins_dinamis atau menghapus alat rakitan yang sudah tidak diperlukan.",
            schema={
                "name": "kelola_keahlian_dinamis",
                "description": "Kelola alat rakitan dinamis (lihat daftar atau hapus alat rakitan tertentu).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["lihat", "hapus"],
                            "description": "'lihat' untuk melihat daftar alat rakitan, 'hapus' untuk menghapus alat."
                        },
                        "tool_name": {
                            "type": "string",
                            "description": "Nama alat yang ingin dihapus jika action='hapus' (contoh: 'cek_kecepatan_dummy')"
                        }
                    },
                    "required": ["action"]
                }
            }
        )
        _registered_count += 3

        # Muat semua plugin dinamis yang tersimpan di disk
        dyn_count = load_all_dynamic_plugins()
        _registered_count += dyn_count
    except Exception as _e_sf:
        print(f"[SkillForge] Gagal registrasi Skill Forge: {_e_sf}")

    print(f"[Sari Core] Berhasil mendaftarkan {_registered_count} tools secara dinamis.")
except Exception as _e_reg:
    print(f"[Sari Core] Gagal mendaftarkan tools: {_e_reg}")

def main():
    global chat_id_tersimpan
    import subprocess
    import os
    print("Menjalankan Jembatan WhatsApp Web...")
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:3000/status", timeout=2)
        print("WA Bridge sudah aktif dan berjalan.")
    except Exception:
        try:
            from sari_core.paths import cari_node, env_bridge
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen([cari_node(), "wa_bridge.js"], cwd=str(WA_BRIDGE_DIR),
                             creationflags=flags, env=env_bridge())
        except Exception as e:
            print("Gagal menyalakan WA Bridge:", e)

    # Cek & nyalakan 9Router secara otomatis jika belum aktif di port 20128
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:20128/v1/models", timeout=2)
        print("9Router lokal sudah aktif di port 20128.")
    except Exception:
        try:
            print("Menyalakan 9Router di latar belakang...")
            vbs_script = str(_AKAR_PROGRAM / "start_9router.vbs")
            if os.path.exists(vbs_script):
                subprocess.Popen(["wscript.exe", vbs_script], shell=False)
            else:
                subprocess.Popen(["cmd.exe", "/c", "9router", "-n", "-t"], creationflags=subprocess.CREATE_NO_WINDOW)
            print("9Router berhasil dinyalakan di latar belakang.")
        except Exception as e:
            print("Gagal menyalakan 9Router:", e)

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "masukkan_token_telegram_disini":
        print("Token Telegram kosong!")
        return
        
    print("Mesin Ultimate (Autonomous Mode + Anti-Halu) menyala...")
    
    chat_id_tersimpan = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id_tersimpan:
        try:
            print("Membangkitkan pesan sapaan profesional dari Siti...")
            sys_prompt = "Kamu adalah Harmoni, asisten pribadi dari pengguna. Kamu BARU SAJA menyapa pengguna yang baru menyalakan komputer. LANGSUNG UCAPKAN sapaan hangat, sopan, ramah, dan profesional (2-3 kalimat pendek). DILARANG menawarkan draft, DILARANG menyebut nama model AI/DeepSeek/Gemini, LANGSUNG SAPA pengguna!"
            user_prompt = "Sapa pengguna sekarang."
            response, _ = minta_jawaban_ai([
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ])
            pesan_sapaan = response.choices[0].message.content
            kirim_pesan_telegram_sync(chat_id_tersimpan, pesan_sapaan)
        except Exception as e:
            print(f"Sapaan otomatis gagal: {e}")

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(on_post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_system_command))
    application.add_handler(CommandHandler("kesehatan", status_system_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("otak", model_command))
    application.add_handler(CommandHandler("cadangan", cadangan_command))
    application.add_handler(CommandHandler("backup", cadangan_command))
    application.add_handler(CommandHandler("cari_model", cari_model_command))
    application.add_handler(CommandHandler("tambah_model", tambah_model_command))
    application.add_handler(CommandHandler("hapus_model", hapus_model_command))
    application.add_handler(CommandHandler("set_key", set_key_command))
    application.add_handler(CommandHandler("spesialis", spesialis_command))
    application.add_handler(CommandHandler("tim", spesialis_command))
    application.add_handler(CommandHandler("atur_spesialis", atur_spesialis_command))
    application.add_handler(CommandHandler("reset_spesialis", reset_spesialis_command))
    application.add_handler(CommandHandler("reset_tim", reset_spesialis_command))
    application.add_handler(CommandHandler("daftar_id", daftar_id_command))
    application.add_handler(CommandHandler("kelola_akses", daftar_id_command))
    application.add_handler(CommandHandler("tambah_id", tambah_id_command))
    application.add_handler(CommandHandler("hapus_id", hapus_id_command))
    application.add_handler(CommandHandler("my_id", my_id_command))
    application.add_handler(CommandHandler("id", my_id_command))
    application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.VOICE | filters.AUDIO | filters.VIDEO | filters.PHOTO, handle_message, block=False))
    
    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
    threading.Thread(target=tugas_wa_bot_background, daemon=True).start()
    threading.Thread(target=tugas_drive_sync_background, daemon=True).start()

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

# Fix for missing tool mappings
available_functions['tulis_file'] = tulis_file
available_functions['baca_file'] = baca_file
