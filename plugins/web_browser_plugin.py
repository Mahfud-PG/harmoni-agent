"""
Sari AI Operating System - Web Search & Browser Suite Plugin
Menyediakan pencarian berita real-time via DuckDuckGo serta ekstraksi artikel website & Google Docs.
"""

import os
import re
import json
import subprocess
import urllib.request
import urllib.parse
from html.parser import HTMLParser
import requests
from bs4 import BeautifulSoup

MANIFEST = {
    "name": "Web Search & Browser Suite",
    "version": "1.2.0",
    "author": "Harmoni Agent",
    "description": "Modul penjelajah internet cerdas untuk mencari berita, fakta aktual via DuckDuckGo (DoH Bypass) & Bing, serta mengekstrak isi artikel website dan dokumen Google Docs bebas sampah."
}

def cari_di_internet(kata_kunci: str):
    """Mencari informasi, berita, atau artikel di internet (DuckDuckGo DoH & Bing). Gunakan ini jika pengguna menanyakan berita atau informasi aktual."""
    hasil_list = []

    # 1. METODE UTAMA: DuckDuckGo HTML via DoH (Bypass Internet Positif / DNS Hijack di Indonesia)
    try:
        real_ip = "20.43.161.105"
        try:
            req_doh = urllib.request.Request("https://1.1.1.1/dns-query?name=html.duckduckgo.com&type=A", headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(req_doh, timeout=4) as r_doh:
                data_doh = json.loads(r_doh.read().decode())
                ips = [ans["data"] for ans in data_doh.get("Answer", []) if ans.get("type") == 1]
                if ips:
                    real_ip = ips[0]
        except Exception:
            pass

        cmd_ddg = [
            "curl", "-s", "-L", "--max-time", "12",
            "--resolve", f"html.duckduckgo.com:443:{real_ip}",
            "--data-urlencode", f"q={kata_kunci}",
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "https://html.duckduckgo.com/html/"
        ]
        res_ddg = subprocess.run(cmd_ddg, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res_ddg.stdout:
            soup = BeautifulSoup(res_ddg.stdout, "html.parser")
            for div in soup.find_all("div", class_="result"):
                classes = div.get("class", [])
                if any("ad" in c.lower() for c in classes):
                    continue
                a_snippet = div.find("a", class_="result__snippet")
                h2 = div.find("h2", class_="result__title")
                title = h2.get_text(strip=True) if h2 else ""
                snippet = a_snippet.get_text(strip=True) if a_snippet else ""
                a_url = div.find("a", class_="result__url") or a_snippet
                link = a_url.get("href", "") if a_url else ""
                m = re.search(r"uddg=([^&]+)", link)
                if m:
                    link = urllib.parse.unquote(m.group(1))
                if title and snippet:
                    hasil_list.append(f"• Judul: {title}\n  Tautan: {link}\n  Ringkasan: {snippet}")
    except Exception:
        pass

    # 2. METODE CADANGAN: Bing Search via Curl (hanya jika DuckDuckGo kosong)
    if not hasil_list:
        try:
            url_bing = f"https://www.bing.com/search?q={urllib.parse.quote(kata_kunci)}"
            cmd_bing = [
                "curl", "-s", "-L", "--max-time", "10",
                "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                url_bing
            ]
            res_bing = subprocess.run(cmd_bing, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            if res_bing.stdout:
                soup_b = BeautifulSoup(res_bing.stdout, "html.parser")
                for li in soup_b.find_all("li", class_="b_algo"):
                    h2 = li.find("h2")
                    if not h2: continue
                    title = h2.get_text(strip=True)
                    a = h2.find("a")
                    link = a["href"] if a and a.has_attr("href") else ""
                    p = li.find("p") or li.find("div", class_="b_caption")
                    desc = p.get_text(strip=True) if p else ""
                    if title and desc:
                        hasil_list.append(f"• Judul: {title}\n  Tautan: {link}\n  Ringkasan: {desc}")
        except Exception:
            pass

    if not hasil_list:
        return f"Sistem: Tidak ditemukan hasil pencarian aktual untuk '{kata_kunci}'. Beritahu pengguna dengan jujur bahwa informasinya belum tersedia di indeks pencarian."

    hasil_teks = "\n\n".join(hasil_list[:6])
    return (
        f"[HASIL PENCARIAN INTERNET UNTUK '{kata_kunci}']\n\n{hasil_teks}\n\n"
        f"[INSTRUKSI SISTEM UNTUK ASISTEN]:\n"
        f"Gunakan data di atas untuk menjawab pertanyaan pengguna secara lugas, faktual, dan ramah. "
        f"Sebutkan intisari jawaban dengan jelas dan sertakan sumber jika relevan."
    )

def baca_link_internet(url: str):
    """Membaca isi teks dari sebuah link/URL website secara bersih tanpa sampah navigasi/iklan."""
    try:
        if "docs.google.com/document" in url:
            try:
                from plugins.google_docs_plugin import baca_google_doc
                m = re.search(r'/document/d/([a-zA-Z0-9-_]+)', url)
                doc_id = m.group(1) if m else url
                return baca_google_doc(doc_id)
            except Exception:
                pass
        
        html = ""
        # 1. Coba via Requests dengan Browser Headers Lengkap
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'
            }
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code == 200:
                html = response.text
        except Exception:
            pass

        # 2. Fallback via curl jika diblokir (403/Cloudflare)
        if not html:
            try:
                cmd = [
                    'curl', '-s', '-L', '--max-time', '15',
                    '-A', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    url
                ]
                r_curl = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                if len(r_curl.stdout) > 200:
                    html = r_curl.stdout
            except Exception:
                pass

        if html:
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.title.string.strip() if soup.title and soup.title.string else "Tanpa Judul"
            
            for script in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                script.decompose()
                
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text)
            
            if len(text) > 4000:
                text = text[:4000] + "...(terpotong)"
                
            return (
                f"[ISI KONTEN WEB: {url}]\nJudul: {title}\nTeks: {text}\n\n"
                f"[INSTRUKSI SISTEM UNTUK ASISTEN]:\n"
                f"Pahami isinya, lalu buatkan RINGKASAN yang rapi, padat, dan faktual untuk pengguna."
            )
        else:
            return f"Sistem: Gagal membaca isi link ({url}). Halaman mungkin memerlukan otentikasi login atau memblokir akses otomatis."
    except Exception as e:
        return f"Sistem: Terjadi kesalahan koneksi saat membaca link ({str(e)})."

def unduh_dari_halaman_web(url: str, pilihan_kata_kunci: str = "x64"):
    """
    Menganalisis halaman web artikel/download, menemukan tautan berkas installer asli (.exe, .zip, .7z, .rar, dll),
    dan mengunduhnya secara otomatis ke folder Downloads pengguna (atau drive D jika ukuran besar).
    Mendukung bypass redirect SharePoint, Google Drive, Mediafire, dan tautan langsung.
    """
    import os
    import re
    import urllib.parse
    import subprocess
    import tempfile
    from pathlib import Path
    from bs4 import BeautifulSoup
    from sari_core.paths import DATA_ROOT

    target_dir = Path.home() / "Downloads"
    if not target_dir.exists():
        target_dir = DATA_ROOT / "File" / "Downloads"
        target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Unduh konten HTML halaman web
    headers_curl = [
        "-s", "-L", "--max-time", "20",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        url
    ]
    res_page = subprocess.run(["curl"] + headers_curl, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if not res_page.stdout or len(res_page.stdout) < 100:
        return f"❌ Gagal membuka halaman web: {url}. Server mungkin memblokir akses atau link tidak valid."

    soup = BeautifulSoup(res_page.stdout, "html.parser")

    # 2. Kumpulkan seluruh tautan <a> di halaman
    kandidat_links = []
    kw_target = pilihan_kata_kunci.strip().lower() if pilihan_kata_kunci else "x64"

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        teks = a.get_text(strip=True).lower()
        href_lower = href.lower()

        # Normalisasi link relatif
        full_href = urllib.parse.urljoin(url, href)

        # Cek apakah tautan mengarah ke berkas arsip/installer atau tombol download
        skor = 0
        if any(ext in href_lower for ext in [".exe", ".zip", ".7z", ".rar", ".msi", ".tar.gz", ".apk"]):
            skor += 10
        if "download" in href_lower or "download=1" in href_lower:
            skor += 6
        if "sharepoint.com" in href_lower or "mediafire.com" in href_lower or "drive.google.com" in href_lower:
            skor += 5

        # Skor kata kunci spesifik (misal x64, 64-bit, v7.80)
        if kw_target and (kw_target in teks or kw_target in href_lower):
            skor += 8
        elif "64" in teks or "x64" in teks:
            skor += 4

        if skor > 0 and full_href.startswith("http"):
            kandidat_links.append((skor, a.get_text(strip=True), full_href))

    if not kandidat_links:
        return f"⚠️ Halaman web berhasil dibaca, tetapi tidak ditemukan tautan berkas unduhan yang cocok di {url}."

    # Urutkan berdasarkan skor tertinggi
    kandidat_links.sort(key=lambda x: x[0], reverse=True)
    pilihan_terbaik = kandidat_links[0]
    label_tombol, direct_url = pilihan_terbaik[1], pilihan_terbaik[2]

    # 3. Lakukan inspeksi Header (curl -I) untuk memastikan nama berkas & tipe konten
    cookie_file = os.path.join(tempfile.gettempdir(), "harmoni_curl_cookie.txt")
    cmd_head = ["curl", "-s", "-I", "-L", "-c", cookie_file, "-b", cookie_file, "--max-time", "15", direct_url]
    res_head = subprocess.run(cmd_head, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    nama_berkas = ""
    # Deteksi filename dari Content-Disposition atau URL redirect
    for line in res_head.stdout.split("\n"):
        if "content-disposition:" in line.lower() and "filename=" in line.lower():
            m_fn = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', line, re.IGNORECASE)
            if m_fn:
                nama_berkas = urllib.parse.unquote(m_fn.group(1).strip())
                break
        elif "location:" in line.lower():
            loc = line.split(":", 1)[1].strip()
            loc_path = urllib.parse.urlparse(loc).path
            base_loc = os.path.basename(loc_path)
            if any(ext in base_loc.lower() for ext in [".exe", ".zip", ".7z", ".rar", ".msi"]):
                nama_berkas = urllib.parse.unquote(base_loc)

    if not nama_berkas:
        url_path = urllib.parse.urlparse(direct_url).path
        cand_name = os.path.basename(url_path)
        if "." in cand_name and len(cand_name) > 4:
            nama_berkas = urllib.parse.unquote(cand_name)
        else:
            clean_btn = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', label_tombol)[:30].strip('_')
            nama_berkas = f"unduhan_{clean_btn}.7z"

    # Jalur penyimpanan akhir
    filepath = target_dir / nama_berkas
    if os.path.exists("D:\\"):
        # Jika drive D ada dan sisa lega, simpan juga salinan mudah di D:\
        filepath = Path("D:\\") / nama_berkas

    # 4. Eksekusi pengunduhan berkas via curl (dengan resume -C -)
    cmd_dl = [
        "curl", "-L", "-C", "-",
        "--retry", "5", "--retry-delay", "3",
        "-c", cookie_file, "-b", cookie_file,
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-o", str(filepath),
        direct_url
    ]
    res_dl = subprocess.run(cmd_dl, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    if filepath.exists() and filepath.stat().st_size > 1024:
        size_mb = filepath.stat().st_size / (1024 * 1024)
        return (
            f"✅ **Pengunduhan Berhasil!**\n"
            f"📦 **Berkas:** `{nama_berkas}`\n"
            f"📊 **Ukuran:** {size_mb:.2f} MB\n"
            f"📁 **Lokasi Simpan:** `{filepath}`\n"
            f"🔗 **Sumber Halaman:** {url}\n"
            f"🎯 **Target Link Terdeteksi:** {label_tombol} ({direct_url[:80]}...)"
        )
    else:
        return f"❌ Gagal mengunduh berkas dari link '{direct_url}'. Berkas tidak terbentuk sempurna di disk."


def baca_artikel_website(url: str):
    """Membaca isi artikel dari website (alias penunjuk ke baca_link_internet untuk kompatibilitas penuh)."""
    return baca_link_internet(url)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "cari_di_internet",
            "description": "Mencari informasi, berita, atau artikel terkini di internet via DuckDuckGo. Gunakan ini jika pengguna menanyakan berita, informasi aktual, atau hal baru.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci pencarian di internet."}
                },
                "required": ["kata_kunci"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_link_internet",
            "description": "Membaca isi teks dari sebuah link/URL website berita, blog, artikel, ataupun link dokumen Google Docs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL lengkap website yang ingin dibaca (misal: https://news.detik.com/...)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "unduh_dari_halaman_web",
            "description": "Menganalisis halaman web download/software (seperti blindhelp.net, blog, forum), mencari link installer asli (.exe, .zip, .7z, .msi), dan mengunduhnya otomatis ke komputer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL halaman web yang memuat tombol atau informasi software."},
                    "pilihan_kata_kunci": {"type": "string", "description": "Kata kunci versi yang dicari (contoh: 'x64', '64-bit', 'portable', 'x86'). Bawaan: 'x64'."}
                },
                "required": ["url"]
            }
        }
    }
]

FUNCTIONS = {
    "cari_di_internet": cari_di_internet,
    "baca_link_internet": baca_link_internet,
    "baca_artikel_website": baca_artikel_website,
    "unduh_dari_halaman_web": unduh_dari_halaman_web
}
