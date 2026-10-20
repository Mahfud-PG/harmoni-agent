import os
import time
import cv2
import sounddevice as sd
import soundfile as sf
import threading
import subprocess
from sari_core.paths import FILE_DIR, TEMP_DIR
from core.utils import kirim_file_telegram

MANIFEST = {
    "name": "Surveillance & CCTV Ruangan",
    "version": "2.0.0",
    "author": "Harmoni Agent",
    "description": "Modul penyadapan kamera webcam (video MP4) dan mikrofon audio studio secara bersamaan."
}

def _izin_penyadapan():
    """MEMERIKSA IZIN PENYADAPAN (JANGAN DIHAPUS).

    Sakelar di Pengaturan harus benar-benar mengikat, bukan hanya menyembunyikan
    alat dari daftar AI. Kalau plugin ini sedang dimatikan, fungsi perekaman
    WAJIB menolak berjalan -- termasuk bila dipanggil lewat jalur lain
    (impor langsung dari modul lain atau tugas terjadwal).
    """
    try:
        from core.plugin_manager import get_disabled_plugins
        if "surveillance_plugin" in get_disabled_plugins():
            return False, ("🔒 Penyadapan ruangan sedang DIMATIKAN di Pengaturan. "
                           "Nyalakan dulu plugin 'Surveillance & CCTV Ruangan' kalau memang diperlukan.")
    except Exception:
        pass
    return True, ""


def sadap_suara_ruangan(durasi=10):
    """Merekam suara dari mikrofon PC selama durasi tertentu, menyimpannya permanen di File/Surveillance, dan mengirimkannya ke Telegram."""
    boleh, pesan_tolak = _izin_penyadapan()
    if not boleh:
        return pesan_tolak
    try:
        durasi = int(durasi)
    except Exception as e:
        durasi = 10
        
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "Gagal: ID Telegram tidak ditemukan."
        
    folder_surveillance = str(FILE_DIR / "Surveillance")
    os.makedirs(folder_surveillance, exist_ok=True)
    from datetime import datetime
    waktu_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_sadap = os.path.join(folder_surveillance, f"sadap_suara_{waktu_str}.wav")

    try:
        fs = 44100
        rekaman = sd.rec(int(durasi * fs), samplerate=fs, channels=1)
        sd.wait()
        sf.write(file_sadap, rekaman, fs)
        
        kirim_file_telegram(file_sadap, caption=f"🎙️ Hasil Sadapan Suara Ruangan ({durasi} Detik) - {waktu_str}")
            
        return f"🎙️ Berhasil menyadap ruangan! File rekaman suara ({durasi} detik) tersimpan aman di File/Surveillance sebagai bukti dan sudah dikirimkan ke Telegram Anda."
    except Exception as e:
        return f"❌ Gagal menyadap suara: {str(e)}"

def sadap_kamera_ruangan(durasi=10):
    """Merekam video (webcam) dan audio (mikrofon) secara bersamaan, menyimpannya permanen di File/Surveillance, dan mengirimkannya ke Telegram."""
    boleh, pesan_tolak = _izin_penyadapan()
    if not boleh:
        return pesan_tolak
    try:
        durasi = int(durasi)
    except Exception as e:
        durasi = 10
        
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id: return "Gagal: ID Telegram tidak ditemukan."
    
    folder_surveillance = str(FILE_DIR / "Surveillance")
    folder_temp = str(TEMP_DIR)
    os.makedirs(folder_surveillance, exist_ok=True)
    os.makedirs(folder_temp, exist_ok=True)
    from datetime import datetime
    waktu_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    file_vid = os.path.join(folder_temp, f"temp_kamera_sadap_{waktu_str}.mp4")
    file_aud = os.path.join(folder_temp, f"temp_kamera_sadap_{waktu_str}.wav")
    file_final = os.path.join(folder_surveillance, f"sadap_kamera_{waktu_str}.mp4")
    
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
            fps = 20.0
            
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
            
    t1 = threading.Thread(target=rekam_suara)
    t2 = threading.Thread(target=rekam_video)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    if os.path.exists(file_vid) and os.path.exists(file_aud):
        cmd = f'ffmpeg -y -i "{file_vid}" -i "{file_aud}" -c:v copy -c:a aac "{file_final}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(file_final):
            if os.path.exists(file_vid):
                os.rename(file_vid, file_final)
    elif os.path.exists(file_vid):
        os.rename(file_vid, file_final)
    elif os.path.exists(file_aud):
        return sadap_suara_ruangan(durasi)
    else:
        return "❌ Gagal: Kamera dan Mikrofon tidak dapat diakses."
        
    if os.path.exists(file_final):
        kirim_file_telegram(file_final, caption=f"🎥 Hasil Sadapan Kamera Ruangan ({durasi} Detik) - {waktu_str}")
        # Hapus hanya file sementara
        for f in [file_vid, file_aud]:
            if os.path.exists(f):
                try: os.remove(f)
                except Exception:
                    pass
        return f"🎥 Berhasil menyadap ruangan (Video+Audio) selama {durasi} detik! File MP4 tersimpan aman di File/Surveillance sebagai bukti dan sudah dikirim ke Telegram."
    
    return "❌ Gagal memproses video sadapan."

TOOLS = [
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
    }
]

FUNCTIONS = {
    "sadap_kamera_ruangan": sadap_kamera_ruangan,
    "sadap_suara_ruangan": sadap_suara_ruangan,
}
