import os
import sys
import shutil
import subprocess
import argparse
import re
import time
from pathlib import Path


def _folder_data():
    """Folder data aplikasi, diberitahu lewat HARMONI_DATA_DIR.

    Dulu di sini tertulis alamat tetap proyek lama yang sudah dihapus, sehingga
    berkas progres ditulis ke folder yang tidak ada dan penulisannya gagal
    diam-diam tanpa pesan apa pun.
    """
    dari_env = os.environ.get("HARMONI_DATA_DIR")
    if dari_env:
        return dari_env
    return os.path.dirname(os.path.abspath(__file__))


DATA_DIR = _folder_data()

import json

def update_progress(tugas, persen):
    file_prog = os.path.join(DATA_DIR, "progress.json")
    data = {}
    if os.path.exists(file_prog):
        try:
            with open(file_prog, "r") as f: data = json.load(f)
        except Exception:
            pass
    data[tugas] = persen
    with open(file_prog, "w") as f: json.dump(data, f)

def kirim_notif(pesan):
    try:
        import urllib.request, urllib.parse
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id_file = os.path.join(DATA_DIR, "chat_id.txt")
        if os.path.exists(chat_id_file):
            with open(chat_id_file, "r") as f:
                chat_id = f.read().strip()
            if token and chat_id:
                data = urllib.parse.urlencode({"chat_id": chat_id, "text": pesan}).encode()
                urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=5)
    except Exception:
        pass

def get_total_size(path):
    if os.path.isfile(path): return os.path.getsize(path)
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp): total += os.path.getsize(fp)
    return total

def copy_with_progress(src, dst, task_name):
    total_size = get_total_size(src)
    copied = 0
    update_progress(task_name, "0%")
    
    def copy_file_chunked(src_file, dst_file):
        nonlocal copied
        with open(src_file, 'rb') as fsrc, open(dst_file, 'wb') as fdst:
            while True:
                buf = fsrc.read(1024*1024*10) # 10MB chunks
                if not buf: break
                fdst.write(buf)
                copied += len(buf)
                if total_size > 0:
                    pct = int((copied / total_size) * 100)
                    update_progress(task_name, f"{pct}%")
        try:
            shutil.copystat(src_file, dst_file)
        except Exception:
            pass

    if os.path.isfile(src):
        if os.path.isdir(dst): dst = os.path.join(dst, os.path.basename(src))
        copy_file_chunked(src, dst)
    else:
        if not os.path.exists(dst): os.makedirs(dst)
        for dirpath, _, filenames in os.walk(src):
            rel_path = os.path.relpath(dirpath, src)
            target_dir = os.path.join(dst, rel_path) if rel_path != "." else dst
            if not os.path.exists(target_dir): os.makedirs(target_dir)
            for f in filenames:
                src_file = os.path.join(dirpath, f)
                dst_file = os.path.join(target_dir, f)
                copy_file_chunked(src_file, dst_file)
                
    update_progress(task_name, "100% Selesai")

def cari_file_lokal(query, drive="C:\\", max_results=25, max_depth=6, timeout=15.0):
    """Mencari file atau folder di drive/folder tertentu secara cerdas dan cepat (BFS)."""
    t0 = time.time()
    
    # 1. Normalisasi jalur awal
    target_path = str(drive or "C:\\").strip().strip("\"'")
    if len(target_path) == 2 and target_path[1] == ':':
        target_path += "\\"
    
    p = Path(target_path)
    
    # Resolusi cerdas jika nama folder ada perbedaan ejaan (mis. 'Project recording' vs 'projek recording')
    if not p.exists():
        parent = p.parent
        if parent.exists():
            target_name_clean = re.sub(r'[^a-zA-Z0-9]', '', p.name.lower().replace('project', 'projek'))
            for child in parent.iterdir():
                child_clean = re.sub(r'[^a-zA-Z0-9]', '', child.name.lower().replace('project', 'projek'))
                if child.is_dir() and child_clean == target_name_clean:
                    p = child
                    break
                    
    if not p.exists():
        return f"Drive atau folder '{drive}' tidak ditemukan di komputer."
        
    start_dir = str(p.resolve())
    
    # 2. Tokenisasi query & pembersihan filter kata kualifikasi
    q_raw = str(query or '').strip()
    if not q_raw:
        return 'Kata kunci pencarian tidak boleh kosong.'
    q_lower = q_raw.lower()
    
    qualifiers = {'project', 'projek', 'folder', 'file', 'berkas', 'dokumen', 'data', 'lagu'}
    raw_words = [w for w in re.split(r'[\s_\-]+', q_lower) if w]
    substantive_words = [w for w in raw_words if w not in qualifiers]
    if not substantive_words:
        substantive_words = raw_words
        
    skip_dirs = {
        '$recycle.bin', 'system volume information', 'recovery',
        'node_modules', '.git', '__pycache__', 'appdata',
        'ldplayer9', 'ldplayer', 'temp', 'tmp'
    }
    
    found_dirs = []
    found_files = []
    current_level = [start_dir]
    matched_dir_paths = set()
    
    for depth in range(max_depth):
        if time.time() - t0 > timeout:
            break
        if (len(found_dirs) + len(found_files)) >= max_results:
            break
            
        next_level = []
        for curr in current_level:
            if time.time() - t0 > timeout:
                break
            try:
                with os.scandir(curr) as it:
                    for entry in it:
                        name_lower = entry.name.lower()
                        
                        if entry.is_dir():
                            is_dir_match = (q_lower in name_lower) or all(w in name_lower for w in substantive_words)
                            if is_dir_match:
                                found_dirs.append(f"📁 [FOLDER/PROYEK] {entry.path}")
                                matched_dir_paths.add(entry.path.lower())
                                if (len(found_dirs) + len(found_files)) >= max_results:
                                    break
                            if entry.is_dir(follow_symlinks=False) and entry.name.lower() not in skip_dirs:
                                next_level.append(entry.path)
                        else:
                            is_file_match = (q_lower in name_lower) or all(w in name_lower for w in substantive_words)
                            is_child_proj = False
                            if not is_file_match and curr.lower() in matched_dir_paths:
                                ext = os.path.splitext(name_lower)[1]
                                if ext in ('.rpp', '.flp', '.cpr', '.als', '.wav', '.mp3'):
                                    is_child_proj = True
                                    
                            if is_file_match or is_child_proj:
                                found_files.append(f"📄 [FILE] {entry.path}")
                                if (len(found_dirs) + len(found_files)) >= max_results:
                                    break
            except (PermissionError, OSError):
                continue
                
        # Jika sudah menemukan folder proyek dan file di kedalaman awal, batasi
        if (found_dirs or found_files) and depth >= 2:
            break
            
        current_level = next_level
        if not current_level:
            break
            
    durasi = time.time() - t0
    total = len(found_dirs) + len(found_files)
    if total == 0:
        return f"Tidak menemukan file atau folder yang mengandung '{query}' di {drive} ({durasi:.2f} detik)."
        
    hasil_gabung = found_dirs + found_files
    header = f"Ditemukan {total} hasil untuk '{query}' di {drive} ({durasi:.2f} detik):"
    return header + '\n' + '\n'.join(hasil_gabung)

def baca_isi_folder_lokal(path_folder):
    """Membaca isi direktori"""
    if not os.path.exists(path_folder):
        return f"Folder tidak ditemukan: {path_folder}"
    if not os.path.isdir(path_folder):
        return f"Path tersebut bukan folder: {path_folder}"
        
    try:
        items = os.scandir(path_folder)
        folders = []
        files = []
        
        for item in items:
            if item.is_dir():
                folders.append(f"📁 {item.name}")
            else:
                size_mb = item.stat().st_size / (1024**2)
                files.append(f"📄 {item.name} ({size_mb:.2f} MB)")
                
        hasil = []
        if folders:
            hasil.extend(folders)
        if files:
            hasil.extend(files)
            
        if not hasil:
            return f"Folder {path_folder} kosong."
            
        return f"Isi folder {path_folder}:\n" + "\n".join(hasil)
    except PermissionError:
        return f"Akses ditolak (Permission Denied) saat membaca: {path_folder}"
    except Exception as e:
        return f"Gagal membaca folder: {str(e)}"

def kelola_file_lokal(action, path_sumber, path_tujuan=None):
    """Operasi copy, move, rename, delete"""
    if not os.path.exists(path_sumber):
        return f"Sumber tidak ditemukan: {path_sumber}"
        
    try:
        if action == "copy":
            if not path_tujuan: return "Path tujuan harus diisi untuk fungsi copy."
            copy_with_progress(path_sumber, path_tujuan, "Copy Lokal")
            msg = f"✅ Berhasil menyalin ke {path_tujuan}"
            kirim_notif(msg)
            return msg
            
        elif action == "move":
            if not path_tujuan: return "Path tujuan harus diisi untuk fungsi move."
            try:
                os.rename(path_sumber, path_tujuan)
            except OSError:
                # Beda drive, lakukan copy lalu delete
                copy_with_progress(path_sumber, path_tujuan, "Move Lokal (Lintas Drive)")
                if os.path.isdir(path_sumber): shutil.rmtree(path_sumber)
                else: os.remove(path_sumber)
            msg = f"✅ Berhasil memindahkan ke {path_tujuan}"
            kirim_notif(msg)
            return msg
            
        elif action == "rename":
            if not path_tujuan: return "Nama baru (path_tujuan) harus diisi."
            os.rename(path_sumber, path_tujuan)
            return f"Berhasil mengganti nama menjadi {os.path.basename(path_tujuan)}"
            
        elif action == "delete":
            if os.path.isdir(path_sumber):
                shutil.rmtree(path_sumber)
            else:
                os.remove(path_sumber)
            return f"Berhasil menghapus secara permanen: {path_sumber}"
            
        else:
            return "Action tidak dikenali. Gunakan: copy, move, rename, delete."
            
    except PermissionError:
        return f"Akses ditolak (Permission Denied). Anda mungkin sedang membuka file tersebut."
    except Exception as e:
        return f"Gagal melakukan kelola file: {str(e)}"

def cek_disk_lokal(drive="C:\\"):
    """Cek sisa storage"""
    if not drive.endswith("\\"):
        drive += "\\"
        
    if not os.path.exists(drive):
        return f"Drive {drive} tidak ditemukan."
        
    try:
        total, used, free = shutil.disk_usage(drive)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        return f"Drive {drive}\nTotal: {total_gb:.2f} GB\nTerpakai: {used_gb:.2f} GB\nKosong (Sisa): {free_gb:.2f} GB"
    except Exception as e:
        return f"Gagal mengecek drive: {str(e)}"


def putar_folder_musik(path_folder):
    """Mencari semua file audio di folder, buat M3U, dan putar"""
    if not os.path.exists(path_folder): return f"Folder tidak ditemukan: {path_folder}"
    
    exts = ('.mp3', '.wav', '.flac', '.ogg', '.m4a')
    audio_files = []
    for item in os.listdir(path_folder):
        if item.lower().endswith(exts):
            audio_files.append(os.path.join(path_folder, item))
            
    if not audio_files: return f"Tidak ada file musik (.mp3, .wav, dll) di {path_folder}"
    
    playlist_path = os.path.join(DATA_DIR, "playlist_sementara.m3u")
    try:
        with open(playlist_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for audio in audio_files:
                f.write(audio + "\n")
        
        os.startfile(playlist_path)
        return f"Berhasil! Memutar {len(audio_files)} lagu menggunakan aplikasi PC Player Anda."
    except Exception as e:
        return f"Gagal memutar folder: {str(e)}"

def buka_aplikasi_lokal(nama_aplikasi):
    """Membuka software/file secara cerdas tanpa memicu pop-up error Windows."""
    try:
        if not nama_aplikasi:
            return "Nama aplikasi tidak boleh kosong."
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from plugins.system_plugin import buka_aplikasi as system_buka_aplikasi
        return system_buka_aplikasi(nama_aplikasi)
    except Exception as e:
        return f"Gagal membuka aplikasi: {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["cari", "baca", "kelola", "cek_disk", "buka", "putar_folder"])
    parser.add_argument("--query", help="Pencarian / Nama Aplikasi")
    parser.add_argument("--drive", default="C:\\", help="Drive letter")
    parser.add_argument("--src", help="Path sumber (untuk baca/kelola)")
    parser.add_argument("--dst", help="Path tujuan (untuk kelola)")
    parser.add_argument("--mode", choices=["copy", "move", "rename", "delete"], help="Mode kelola file")
    
    args = parser.parse_args()
    
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        
        if args.action == "cari":
            print(cari_file_lokal(args.query, args.drive))
        elif args.action == "baca":
            print(baca_isi_folder_lokal(args.src))
        elif args.action == "kelola":
            print(kelola_file_lokal(args.mode, args.src, args.dst))
        elif args.action == "cek_disk":
            print(cek_disk_lokal(args.drive))
        elif args.action == "putar_folder":
            print(putar_folder_musik(args.src))
        elif args.action == "buka":
            print(buka_aplikasi_lokal(args.query))
            
    except Exception as e:
        print(f"ERROR_SISTEM_LOKAL: {str(e)}")
        sys.exit(1)
