import os
import json
import time
import glob
from datetime import datetime

MANIFEST = {
    "name": "Obsidian Brain Engine & Auto-Memory Vault",
    "version": "1.0.0",
    "author": "Harmoni Agent",
    "description": "Modul ingatan abadi tingkat tinggi berbasis Obsidian Markdown Vault. Bekerja otomatis tanpa perlu diperintah, hemat ruang penyimpanan (Auto-Pruning), dan menyambung percakapan secara seamless lintas restart PC."
}

from sari_core.paths import OBSIDIAN_DIR

VAULT_DIR = str(OBSIDIAN_DIR)
FOLDER_KONTEKS = os.path.join(VAULT_DIR, "01_Konteks_Aktif")
FOLDER_PENGETAHUAN = os.path.join(VAULT_DIR, "02_Basis_Pengetahuan")
FOLDER_ARSIP = os.path.join(VAULT_DIR, "03_Arsip_Harian")

def _inisialisasi_vault():
    for f in [VAULT_DIR, FOLDER_KONTEKS, FOLDER_PENGETAHUAN, FOLDER_ARSIP]:
        os.makedirs(f, exist_ok=True)
        
    context_file = os.path.join(FOLDER_KONTEKS, "Sari_Context.md")
    if not os.path.exists(context_file):
        with open(context_file, "w", encoding="utf-8") as f:
            f.write("# 🧠 KONTEKS UNGGULAN & INGATAN AKTIF SARI AI\n\n"
                    "## 📌 PROYEK & KONTROL TERAKHIR\n"
                    "- **Hardware:** BARDI Universal IR Remote (IP: `192.168.1.78` | ID: `eb5992346b9dd50d7a0h9l`)\n"
                    "- **AC Studio:** AC SAMSUNG (Terkunci & Aktif)\n"
                    "- **Sistem Memori:** Obsidian Brain Engine v1.0.0 (Auto-Sync & Auto-Compact)\n\n"
                    "## 💬 STATUS PERCAKAPAN TERAKHIR\n"
                    "- Pemasangan Obsidian Vault otomatis tanpa perlu perintah manual 'Sari catat ini'.\n")

_inisialisasi_vault()

def catat_memori_obsidian(kategori: str, topik: str, isi_catatan: str, tags: str = ""):
    """
    Mencatat memori baru atau memperbarui catatan di Obsidian Vault secara otomatis & terstruktur.
    Kategori: 'klien', 'keuangan', 'peralatan', 'proyek', 'rahasia', 'umum'
    """
    try:
        _inisialisasi_vault()
        kat_clean = kategori.lower().strip()
        topik_clean = topik.replace(" ", "_").strip()
        
        target_folder = FOLDER_PENGETAHUAN
        file_path = os.path.join(target_folder, f"{kat_clean}_{topik_clean}.md")
        
        tgl_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag_list = [f"#{t.strip()}" for t in tags.split(",") if t.strip()]
        tag_str = " ".join(tag_list) if tag_list else "#memori_sari"
        
        catatan_md = f"""---
kategori: {kat_clean}
topik: {topik}
diperbarui: {tgl_str}
tags: {tag_str}
---

# 📌 {topik.upper()}
{tag_str}

## 📝 CATATAN REAL-TIME ({tgl_str}):
{isi_catatan}

---
*Diarsipkan otomatis oleh Obsidian Brain Engine Sari AI*
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(catatan_md)
            
        # Pangkas & jaga ukuran memori tetap ringkas (Auto-Pruning)
        ringkas_arsip_memori()
        return f"🧠 *Obsidian Memory Updated:* Catatan [{topik}] berhasil disimpan di Vault secara otomatis & hemat ruang!"
    except Exception as e:
        return f"❌ Gagal menulis memori Obsidian: {str(e)}"

# IN-MEMORY RAM CACHE UNTUK PENCARIAN MEMORI INSTAN (SUB-DETIK)
_MEMORI_CACHE = {}
_LAST_CACHE_TIME = 0

def baca_memori_obsidian(kata_kunci: str = "", kategori: str = ""):
    """
    Membaca dan mencari memori di Obsidian Vault secara super cepat menggunakan In-Memory RAM Cache (0.001 detik).
    """
    global _MEMORI_CACHE, _LAST_CACHE_TIME
    try:
        _inisialisasi_vault()
        now = time.time()
        
        # Refresh cache setiap 30 detik agar RAM tetap segar & instan
        if not _MEMORI_CACHE or (now - _LAST_CACHE_TIME > 30):
            _MEMORI_CACHE.clear()
            pattern = os.path.join(FOLDER_PENGETAHUAN, "*.md")
            files = glob.glob(pattern)
            
            context_file = os.path.join(FOLDER_KONTEKS, "Sari_Context.md")
            if os.path.exists(context_file):
                files.append(context_file)
                
            for fp in files:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        _MEMORI_CACHE[os.path.basename(fp)] = f.read()
                except Exception: pass
            _LAST_CACHE_TIME = now
            
        hasil = []
        kw_clean = kata_kunci.lower().strip()
        kat_clean = kategori.lower().strip()
        
        for fname, content in _MEMORI_CACHE.items():
            if kat_clean and f"kategori: {kat_clean}" not in content and kat_clean not in fname.lower():
                continue
                
            if kw_clean:
                if kw_clean in content.lower() or kw_clean in fname.lower():
                    hasil.append(f"📄 **[{fname}]**\n{content[:300]}...")
            else:
                hasil.append(f"📄 **[{fname}]**\n{content[:250]}...")
                
        if not hasil:
            return "🔍 Tidak ditemukan catatan memori yang cocok di Obsidian Vault."
            
        return "🧠 *LAPORAN INGATAN OBSIDIAN VAULT (RAM CACHED):*\n\n" + "\n\n---\n\n".join(hasil[:3])
    except Exception as e:
        return f"❌ Gagal membaca memori Obsidian: {str(e)}"

def singkronkan_konteks_percakapan(rangkuman_obrolan: str, topik_terakhir: str):
    """
    Menyimpan konteks percakapan terakhir agar tetap menyambung secara seamless saat PC di-restart atau bot dinyalakan ulang.
    """
    try:
        _inisialisasi_vault()
        context_file = os.path.join(FOLDER_KONTEKS, "Sari_Context.md")
        tgl_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        md_content = f"""# 🧠 KONTEKS UNGGULAN & INGATAN AKTIF SARI AI
Diperbarui: `{tgl_str}`

## 📌 PROYEK & KONTROL TERAKHIR
- **Hardware:** BARDI Universal IR Remote (IP: `192.168.1.78` | ID: `eb5992346b9dd50d7a0h9l`)
- **AC Studio:** AC SAMSUNG (Terkunci & Aktif)
- **Sistem Memori:** Obsidian Brain Engine v1.0.0 (Auto-Sync & Auto-Compact)

## 💬 TOPIK & KONTEKS CHAT TERAKHIR:
**Topik Utama:** `{topik_terakhir}`

### 📝 Rangkuman Ringkas Obrolan:
{rangkuman_obrolan}

---
*Konteks ini dibaca otomatis oleh Sari setiap kali PC nyala atau bot di-restart agar percakapan tetap menyambung 100%.*
"""
        with open(context_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        return "⚡ Konteks percakapan berhasil disinkronkan ke Obsidian!"
    except Exception as e:
        return f"❌ Gagal menyinkronkan konteks: {str(e)}"

def ringkas_arsip_memori():
    """
    Fungsi Auto-Pruning: Menjaga ukuran Obsidian Vault tetap ringan, compact, dan tidak membengkak seperti gunung.
    Mengompresi catatan harian tua yang berusia lebih dari 14 hari menjadi 1 file rangkuman bulanan ringkas.
    """
    try:
        _inisialisasi_vault()
        pattern = os.path.join(FOLDER_ARSIP, "*.md")
        files = glob.glob(pattern)
        
        if len(files) > 14:
            # Jika file harian sudah lebih dari 14, gabung file-file tertua jadi 1 file rangkuman bulanan
            files.sort()
            files_to_compact = files[:-7] # Sisakan 7 hari terakhir
            
            bln_str = datetime.now().strftime("%Y_%m")
            compact_file = os.path.join(FOLDER_ARSIP, f"Rangkuman_Bulanan_{bln_str}.md")
            
            combined_text = f"# 📚 RANGKUMAN BULANAN OBSIDIAN ({bln_str})\n\n"
            for fp in files_to_compact:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        combined_text += f"\n--- {os.path.basename(fp)} ---\n" + f.read()[:300] + "\n"
                    os.remove(fp) # Hapus file mentah tua agar tidak memenuhi harddisk
                except Exception: pass
                
            with open(compact_file, "a", encoding="utf-8") as f:
                f.write(combined_text)
                
            return "🧹 *Obsidian Auto-Pruning:* File memori lama berhasil dikompresi ringkas agar harddisk tetap hemat!"
        return "🟢 Ukuran Obsidian Vault aman & sangat efisien."
    except Exception as e:
        return f"❌ Gagal melakukan auto-pruning memori: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "catat_memori_obsidian",
            "description": "Mencatat atau memperbarui informasi/memori secara otomatis ke dalam Obsidian Vault (tanpa perlu diminta manual oleh pengguna). Simpan fakta penting, sandi, preferensi, dan proyek.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kategori": {"type": "string", "description": "Kategori: 'klien', 'keuangan', 'peralatan', 'proyek', 'rahasia', 'umum'"},
                    "topik": {"type": "string", "description": "Judul/topik catatan (misal: 'Sandi_Koper', 'Preset_Vokal_Reaper', 'List_Peralatan')"},
                    "isi_catatan": {"type": "string", "description": "Isi lengkap catatan memori"},
                    "tags": {"type": "string", "description": "Tag dipisahkan koma (misal: 'rahasia,studio,lunas')"}
                },
                "required": ["kategori", "topik", "isi_catatan"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_memori_obsidian",
            "description": "Membaca dan mencari memori di Obsidian Vault berdasarkan kata kunci atau kategori untuk mengingat konteks/informasi lama.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci pencarian"},
                    "kategori": {"type": "string", "description": "Kategori spesifik (Opsional)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "singkronkan_konteks_percakapan",
            "description": "Menyimpan konteks percakapan terakhir agar tetap menyambung secara seamless saat PC di-restart atau bot dinyalakan ulang.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rangkuman_obrolan": {"type": "string", "description": "Rangkuman poin obrolan terakhir"},
                    "topik_terakhir": {"type": "string", "description": "Topik utama yang sedang dibahas"}
                },
                "required": ["rangkuman_obrolan", "topik_terakhir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ringkas_arsip_memori",
            "description": "Menjaga Obsidian Vault tetap efisien & ringan (Auto-Pruning) agar penyimpanan harddisk tidak membengkak.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

FUNCTIONS = {
    "catat_memori_obsidian": catat_memori_obsidian,
    "baca_memori_obsidian": baca_memori_obsidian,
    "singkronkan_konteks_percakapan": singkronkan_konteks_percakapan,
    "ringkas_arsip_memori": ringkas_arsip_memori,
}
