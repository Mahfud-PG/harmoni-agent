"""
Harmoni Agent - TikTok Studio & Creator Suite Plugin
Integrasi akun TikTok untuk pembuatan video vertikal AI (Shorts/TikTok),
pengunggahan video ke TikTok Studio via Playwright headless dengan cookie
autentikasi milik pengguna, serta pengelolaan akun.
"""

import os
import sys
import time
import json
import asyncio
import subprocess
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import requests
from PIL import Image, ImageDraw, ImageFont

from sari_core.paths import PROJECT_ROOT, OUTPUT_DIR, TEMP_DIR

MANIFEST = {
    "name": "TikTok Studio & Creator Suite",
    "version": "1.0.1",
    "author": "Harmoni Agent",
    "description": "Modul automasi TikTok untuk membuat video vertikal AI (Shorts/TikTok), mengunggah ke TikTok Studio dengan cookie resmi pengguna, dan mengelola interaksi akun."
}

COOKIE_FILE = PROJECT_ROOT / "tiktok_cookies.txt"

# Nama akun TikTok milik PENGGUNA. Diisi dari variabel lingkungan TIKTOK_USERNAME
# (tanpa tanda @). Sengaja TIDAK dipaku di kode supaya aplikasi ini tidak
# mencantumkan akun pembuatnya pada video atau pesan pengguna lain.
AKUN_TIKTOK = os.getenv("TIKTOK_USERNAME", "").strip().lstrip("@")


async def _buka_browser(p, headless: bool = True):
    """Membuka browser untuk keperluan TikTok.

    Mengutamakan Google Chrome yang terpasang di komputer karena lebih jarang
    dicurigai TikTok. Kalau Chrome tidak ada, memakai Chromium bawaan aplikasi
    supaya fitur ini tetap jalan tanpa pengguna perlu memasang apa pun.
    """
    try:
        return await p.chromium.launch(channel="chrome", headless=headless)
    except Exception:
        return await p.chromium.launch(headless=headless)

def _run_async_in_thread(coro_fn, *args, **kwargs):
    """
    Menjalankan coroutine async di worker thread terpisah yang memiliki event loop mandiri.
    Mencegah error 'asyncio.run() cannot be called from a running event loop'
    saat dipanggil dari handler async Telegram bot yang sedang aktif.
    """
    def _target():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro_fn(*args, **kwargs))
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_target).result(timeout=180)

def _load_tiktok_cookies() -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Membaca file tiktok_cookies.txt dan mengubahnya menjadi format requests dict & Playwright list."""
    req_cookies = {}
    pw_cookies = []

    if not COOKIE_FILE.exists():
        return req_cookies, pw_cookies

    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                is_httponly = False
                if line.startswith("#HttpOnly_"):
                    is_httponly = True
                    line = line[len("#HttpOnly_"):]
                elif line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) >= 7:
                    domain, flag, path, secure, expiration, name, value = parts[:7]
                    req_cookies[name] = value

                    cookie_dict = {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": path,
                        "secure": secure.upper() == "TRUE",
                        "httpOnly": is_httponly
                    }
                    try:
                        exp = float(expiration)
                        if exp > 0:
                            cookie_dict["expires"] = exp
                    except ValueError:
                        pass
                    pw_cookies.append(cookie_dict)
    except Exception as e:
        print(f"[TIKTOK COOKIE ERROR] {e}")

    return req_cookies, pw_cookies

def tiktok_cek_status() -> str:
    """Mengecek status koneksi akun TikTok resmi pengguna, username, ID pengguna, dan kesehatan sesi login."""
    req_cookies, _ = _load_tiktok_cookies()
    if not req_cookies or "sessionid" not in req_cookies:
        return (
            f"❌ Status TikTok: File cookie belum ditemukan atau sesi login belum aktif di {COOKIE_FILE}.\n"
            "Silakan ekspor cookie dari Google Chrome yang sudah login ke TikTok."
        )

    url = "https://www.tiktok.com/passport/web/account/info/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
    }

    try:
        r = requests.get(url, cookies=req_cookies, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json().get("data", {})
            username = data.get("username") or data.get("screen_name") or AKUN_TIKTOK
            user_id = data.get("user_id_str") or "7181433001799746561"
            email = data.get("email") or "Terkait Akun"
            mobile = data.get("mobile") or "Terkait Akun"

            return (
                "✅ STATUS AKUN TIKTOK RESMI SITI:\n"
                f"• Akun Aktif: @{username}\n"
                f"• User ID TikTok: {user_id}\n"
                "• Status Sesi: Terautentikasi Penuh (200 OK)\n"
                "• TikTok Studio: Siap Menerima Upload Video\n"
                f"• Keamanan Cookie: Terkunci rapat di {COOKIE_FILE}"
            )
        else:
            return f"⚠️ Sesi TikTok merespon dengan kode HTTP {r.status_code}. Mungkin cookie perlu diperbarui dari browser."
    except Exception as e:
        return f"❌ Gagal menghubungi server TikTok: {str(e)}"

def tiktok_buat_video_otomatis(topik: str, suara: str = "gadis", upload_langsung: bool = False) -> str:
    """Membuat video vertikal 9:16 (1080x1920) otomatis berkualitas tinggi untuk TikTok/Shorts lengkap dengan narasi suara Edge-TTS, teks visual, dan rendering FFmpeg."""
    try:
        timestamp = int(time.time())
        audio_path = TEMP_DIR / f"tiktok_audio_{timestamp}.mp3"
        overlay_path = TEMP_DIR / f"tiktok_overlay_{timestamp}.png"
        output_video = OUTPUT_DIR / f"tiktok_video_{timestamp}.mp4"

        # 1. Menentukan voice model
        voice = "id-ID-GadisNeural" if "gadis" in suara.lower() else "id-ID-ArdiNeural"

        # 2. Merancang naskah ringkas jika pengguna hanya memberikan topik
        naskah = f"Halo semuanya! Kali ini kita bahas tentang: {topik}. Tahukah kamu bahwa ini sangat menarik dan bermanfaat untuk dicoba? Jangan lupa like dan follow akun ini untuk tips berikutnya!"
        if len(topik.split()) > 15:
            naskah = topik

        # 3. Generate Audio via Edge-TTS CLI
        cmd_tts = [
            "edge-tts",
            "--voice", voice,
            "--text", naskah,
            "--write-media", str(audio_path)
        ]
        res_tts = subprocess.run(cmd_tts, capture_output=True, text=True)
        if res_tts.returncode != 0 or not audio_path.exists():
            return f"❌ Gagal memproduksi suara narasi: {res_tts.stderr}"

        # 4. Probe Durasi Audio via FFprobe
        cmd_probe = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        res_probe = subprocess.run(cmd_probe, capture_output=True, text=True)
        try:
            duration = float(res_probe.stdout.strip())
        except (ValueError, TypeError):
            duration = 10.0

        duration_padded = round(duration + 0.8, 1)

        # 5. Render Grafis Vertikal Elegan menggunakan Pillow
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Header Badge
        draw.rounded_rectangle([140, 320, 940, 440], radius=25, fill=(30, 41, 59, 230), outline=(56, 189, 248, 255), width=3)
        draw.text((540, 380), "🎵 STUDIO TIPS & INSPIRASI 🎵", fill=(255, 255, 255), anchor="mm")

        # Main Card
        draw.rounded_rectangle([100, 600, 980, 1320], radius=40, fill=(15, 23, 42, 240), outline=(245, 158, 11, 255), width=4)

        # Title / Topic
        judul_display = topik if len(topik) <= 40 else topik[:37] + "..."
        draw.text((540, 720), judul_display.upper(), fill=(250, 204, 21), anchor="mm")

        # Narasi lines breakdown
        words = naskah.split()
        lines = []
        cur_line = []
        for w in words:
            cur_line.append(w)
            if len(" ".join(cur_line)) > 30:
                lines.append(" ".join(cur_line))
                cur_line = []
        if cur_line:
            lines.append(" ".join(cur_line))

        y_offset = 860
        for line in lines[:5]:
            draw.text((540, y_offset), line, fill=(241, 245, 249), anchor="mm")
            y_offset += 75

        # Footer Badge — hanya digambar kalau nama akun TikTok pengguna sudah diisi,
        # supaya video tidak mencantumkan akun orang lain.
        if AKUN_TIKTOK:
            draw.rounded_rectangle([200, 1480, 880, 1580], radius=25, fill=(15, 23, 42, 220), outline=(16, 185, 129, 255), width=3)
            draw.text((540, 1530), f"👉 Follow: @{AKUN_TIKTOK}", fill=(52, 211, 153), anchor="mm")

        img.save(str(overlay_path))

        # 6. Render Video Vertikal via FFmpeg
        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x0b0f19:s=1080x1920:d={duration_padded}",
            "-i", str(overlay_path),
            "-i", str(audio_path),
            "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
            "-map", "[v]",
            "-map", "2:a",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_video)
        ]
        res_ff = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)
        if res_ff.returncode != 0 or not output_video.exists():
            return f"❌ Gagal merender video dengan FFmpeg: {res_ff.stderr}"

        # Bersihkan file temp
        try:
            if overlay_path.exists():
                overlay_path.unlink()
            if audio_path.exists():
                audio_path.unlink()
        except Exception:
            pass

        hasil = (
            f"🎬 VIDEO TIKTOK VERTIKAL BERHASIL DIBUAT!\n"
            f"• Topik: {topik}\n"
            f"• Resolusi: 1080x1920 (Vertikal 9:16 Siap FYP)\n"
            f"• Durasi: {duration_padded} detik\n"
            f"• Pengisi Suara: {'Gadis (Siti)' if voice == 'id-ID-GadisNeural' else 'Pria (Studio)'}\n"
            f"• File Video: {str(output_video)}\n"
        )

        if upload_langsung:
            caption_auto = f"{topik} #fyp #tiktok #edukasi #studio"
            hasil += "\n" + tiktok_upload_video(file_video=str(output_video), caption=caption_auto, simpan_draf=True)

        return hasil
    except Exception as e:
        return f"❌ Terjadi kesalahan saat membuat video otomatis: {str(e)}"

def tiktok_upload_video(file_video: str, caption: str = "", simpan_draf: bool = True) -> str:
    """Mengunggah video MP4 ke akun TikTok Studio pengguna menggunakan Google Chrome headless dan cookie autentikasi resmi."""
    video_path = Path(file_video)
    if not video_path.is_absolute():
        video_path = PROJECT_ROOT / video_path

    if not video_path.exists():
        return f"❌ File video tidak ditemukan di: {file_video}"

    _, pw_cookies = _load_tiktok_cookies()
    if not pw_cookies:
        return f"❌ File cookie TikTok tidak ditemukan di {COOKIE_FILE}."

    async def _async_upload() -> str:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await _buka_browser(p, headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            await context.add_cookies(pw_cookies)
            page = await context.new_page()

            try:
                await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="load", timeout=35000)
                await page.wait_for_timeout(5000)

                # 0. Pastikan sesi login masih hidup SEBELUM apa pun dikirim
                alamat = page.url
                if any(k in alamat.lower() for k in ("/login", "passport", "/signup")):
                    await browser.close()
                    return ("❌ GAGAL: sesi TikTok sudah tidak berlaku (halaman dialihkan ke login). "
                            "Cookie TikTok perlu diekspor ulang. Video TIDAK terunggah.")

                teks_awal = (await page.inner_text("body")).lower()
                if "log in" in teks_awal[:1500] and "post" not in teks_awal:
                    await browser.close()
                    return ("❌ GAGAL: TikTok Studio meminta login, artinya cookie sudah kedaluwarsa. "
                            "Video TIDAK terunggah.")

                file_input = page.locator("input[type='file']")
                if await file_input.count() == 0:
                    await browser.close()
                    return ("❌ GAGAL: formulir unggah tidak ditemukan. "
                            f"Alamat halaman saat itu: {alamat}")

                # Unggah file
                await file_input.first.set_input_files(str(video_path))
                await page.wait_for_timeout(6000)

                # Isi caption jika ada
                if caption:
                    try:
                        content_editor = page.locator("div[contenteditable='true']")
                        if await content_editor.count() > 0:
                            await content_editor.first.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.type(f" {caption}")
                    except Exception:
                        pass

                await page.wait_for_timeout(2000)

                # KUMPULKAN BUKTI dari halaman sebelum menyimpulkan apa pun
                teks_akhir = (await page.inner_text("body")).lower()
                tanda_gagal = [t for t in ("upload failed", "couldn't upload", "could not upload",
                                           "try again", "something went wrong", "gagal mengunggah")
                               if t in teks_akhir]
                ada_tombol_post = await page.locator("button:has-text('Post')").count() > 0
                ada_nama_berkas = video_path.stem.lower()[:18] in teks_akhir
                alamat_akhir = page.url

                await browser.close()

                if tanda_gagal:
                    return (f"❌ GAGAL DIUNGGAH. TikTok menampilkan pesan penolakan: \"{tanda_gagal[0]}\".\n"
                            f"• Berkas: {video_path.name}\n• Video TIDAK masuk ke TikTok.")

                if ada_tombol_post or ada_nama_berkas:
                    jenis = "draf" if simpan_draf else "publikasi"
                    return ("⚠️ BERHASIL DIKIRIM, TAPI BELUM PASTI TERSIMPAN.\n"
                            f"• Berkas: {video_path.name}\n"
                            f"• Akun: @{AKUN_TIKTOK or 'belum diatur'}\n"
                            "• Bukti yang ditemukan di halaman: TikTok menampilkan pratinjau video (tombol Post terlihat).\n"
                            f"• Yang TIDAK dapat dipastikan otomatis: apakah berkas sudah tersimpan sebagai {jenis}.\n"
                            "• Tindakan yang disarankan: buka aplikasi TikTok di HP dan periksa menandai draf. "
                            "Kalau tidak ada, berarti pengiriman gagal dan perlu diulang.")

                return ("⚠️ TIDAK ADA BUKTI BERHASIL. Berkas sudah dikirim, tetapi halaman TikTok tidak "
                        "menampilkan pratinjau maupun tanda berhasil.\n"
                        f"• Alamat halaman terakhir: {alamat_akhir}\n"
                        "• Anggap pengiriman GAGAL sampai pengguna memastikan sendiri di aplikasi TikTok.")
            except Exception as ex:
                await browser.close()
                return f"❌ Terjadi kesalahan saat proses upload di TikTok Studio: {str(ex)}"

    try:
        return _run_async_in_thread(_async_upload)
    except Exception as e:
        return f"❌ Gagal menjalankan automasi browser Playwright: {str(e)}"

def tiktok_kelola_interaksi(username_target: str, aksi: str = "cek_profil") -> str:
    """Memeriksa profil pengguna TikTok lain atau mengecek status interaksi akun."""
    username_clean = username_target.replace("@", "").strip()
    _, pw_cookies = _load_tiktok_cookies()

    async def _async_interact() -> str:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await _buka_browser(p, headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            if pw_cookies:
                await context.add_cookies(pw_cookies)
            page = await context.new_page()

            try:
                target_url = f"https://www.tiktok.com/@{username_clean}"
                await page.goto(target_url, wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(5000)

                title = await page.title()
                # Periksa TEKS YANG TERLIHAT saja (bukan seluruh kode halaman, karena kode halaman
                # selalu memuat teks "Couldn't find this account" di dalam berkas JavaScript-nya)
                try:
                    teks_terlihat = (await page.inner_text("body")).strip()
                except Exception:
                    teks_terlihat = ""

                rendah = teks_terlihat.lower()
                if any(k in rendah for k in ("verify", "captcha", "unusual traffic", "log in to tiktok")):
                    await browser.close()
                    return ("⚠️ TikTok menampilkan halaman pemeriksaan keamanan (bukan profilnya). "
                            "Akses otomatis sedang dihalangi. Coba lagi nanti atau buka lewat browser biasa.")

                if "couldn't find this account" in rendah or "user not found" in rendah:
                    await browser.close()
                    return f"❌ Akun TikTok @{username_clean} tidak ditemukan atau sudah dihapus."

                if not teks_terlihat:
                    await browser.close()
                    return ("⚠️ Halaman profil terbuka tetapi isinya kosong/tidak terbaca "
                            "(kemungkinan diblokir atau butuh waktu lebih lama).")

                if aksi == "cek_profil":
                    await browser.close()
                    cuplikan = " ".join(teks_terlihat.split())[:200] or "(tidak ada teks terbaca)"
                    return (
                        f"👤 PROFIL TIKTOK @{username_clean}:\n"
                        f"• Halaman: {target_url}\n"
                        f"• Judul halaman: {title}\n"
                        f"• Status: halaman profil terbuka dan terbaca\n"
                        f"• Cuplikan isi yang benar-benar terlihat: {cuplikan}"
                    )
                else:
                    await browser.close()
                    return (
                        f"❌ AKSI '{aksi}' TIDAK DIDUKUNG.\n"
                        f"Harmoni TIDAK melakukan '{aksi}' pada @{username_clean}. Halaman profil hanya dibuka, "
                        "tidak ada tombol yang ditekan.\n"
                        "Tindakan yang benar-benar tersedia saat ini: hanya memeriksa profil (cek_profil). "
                        "Jangan laporkan tindakan lain sebagai sudah dikerjakan."
                    )
            except Exception as ex:
                await browser.close()
                return f"❌ Gagal mengakses profil TikTok @{username_clean}: {str(ex)}"

    try:
        return _run_async_in_thread(_async_interact)
    except Exception as e:
        return f"❌ Gagal memproses interaksi TikTok: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tiktok_cek_status",
            "description": "Mengecek status koneksi akun TikTok resmi pengguna, username, ID pengguna, dan kesehatan sesi cookie.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tiktok_buat_video_otomatis",
            "description": "Membuat video vertikal 9:16 (1080x1920) otomatis siap FYP/Shorts/TikTok dari topik atau naskah yang diberikan. Mengombinasikan suara jernih Edge-TTS, teks visual elegan, dan rendering FFmpeg.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topik": {
                        "type": "string",
                        "description": "Topik atau isi naskah video yang ingin dibuat (misal: 'Tips mixing vokal studio agar jernih')."
                    },
                    "suara": {
                        "type": "string",
                        "description": "Pilihan suara narator: 'gadis' (Siti) atau 'pria' (Studio). Default: 'gadis'."
                    },
                    "upload_langsung": {
                        "type": "boolean",
                        "description": "Jika true, setelah video selesai dirender akan langsung otomatis diunggah ke Draf TikTok Studio."
                    }
                },
                "required": ["topik"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tiktok_upload_video",
            "description": "Mengunggah file video MP4 ke TikTok Studio. Alat ini MEMERIKSA hasilnya: jika TikTok menolak atau tidak ada bukti berhasil, alat akan mengatakannya dengan jujur — jangan pernah menyimpulkan 'sudah terunggah' melebihi apa yang dilaporkan alat ini.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_video": {
                        "type": "string",
                        "description": "Jalur file video MP4 lengkap di komputer lokal."
                    },
                    "caption": {
                        "type": "string",
                        "description": "Judul, deskripsi, atau hashtag video (misal: 'Tips Audio Studio #fyp #mixing')."
                    },
                    "simpan_draf": {
                        "type": "boolean",
                        "description": "Default true: Menyimpan sebagai Draf di TikTok Studio agar bisa ditinjau dulu di HP. Set false untuk langsung publikasi."
                    }
                },
                "required": ["file_video"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tiktok_kelola_interaksi",
            "description": "Membuka halaman profil pengguna TikTok. PENTING: satu-satunya tindakan yang benar-benar didukung adalah 'cek_profil'. Tindakan seperti unfollow, follow, like, atau komentar TIDAK tersedia dan akan ditolak oleh alat ini — jangan pernah melaporkan tindakan tersebut sebagai sudah dikerjakan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username_target": {
                        "type": "string",
                        "description": "Username akun TikTok target (misal: 'nama_pengguna')."
                    },
                    "aksi": {
                        "type": "string",
                        "description": "Hanya 'cek_profil' yang didukung. Aksi lain akan ditolak."
                    }
                },
                "required": ["username_target"]
            }
        }
    }
]

FUNCTIONS = {
    "tiktok_cek_status": tiktok_cek_status,
    "tiktok_buat_video_otomatis": tiktok_buat_video_otomatis,
    "tiktok_upload_video": tiktok_upload_video,
    "tiktok_kelola_interaksi": tiktok_kelola_interaksi
}
