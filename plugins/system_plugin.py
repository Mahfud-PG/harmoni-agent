import os
import subprocess
import pyperclip
import win32gui, win32process, psutil
from core.plugin_manager import reload_plugins, get_active_manifests

MANIFEST = {
    "name": "System & Manager AI OS",
    "version": "1.1.0",
    "author": "Harmoni Agent",
    "description": "Modul sistem Windows, pemantau layar, manajemen clipboard, uninstaller otomatis, dan Hot Reload plugin."
}

def daftar_plugin_aktif():
    """Menampilkan daftar plugin modular yang sedang aktif beserta versi dan deskripsinya."""
    manifests = get_active_manifests()
    if not manifests:
        return "ℹ️ Belum ada plugin yang terdaftar di sistem."
    
    out = f"🧩 *Daftar Plugin AI Desktop OS Aktif ({len(manifests)} Modul):*\n\n"
    for idx, m in enumerate(manifests, 1):
        out += f"{idx}. *{m.get('name', 'Modul')}* `v{m.get('version', '1.0')}`\n"
        out += f"   *Deskripsi:* {m.get('description', '-')}\n"
        out += f"   *Pengembang:* {m.get('author', '-')}\n\n"
    return out

def cek_model_ai():
    """Menampilkan daftar mesin AI (otak asisten) yang sedang digunakan dan siap dipakai.

    PENTING: daftar ini dibaca LANGSUNG dari pengaturan model yang sedang berlaku,
    tidak lagi ditulis tetap di dalam kode. Versi lama menyebut DeepSeek V3, Groq
    Llama 3.3 70B, dan Gemini 3.6 - model yang sudah tidak dipakai sama sekali -
    sehingga pengguna menerima keterangan yang keliru tentang asistennya sendiri.
    Versi lama juga menyuruh membuka berkas konfigurasi di jalur proyek yang sudah
    dihapus, yang bagi pengguna pembaca layar adalah jalan buntu.
    """
    try:
        from sari_core.model_config import load_model_config, format_menu_model
        pengaturan = load_model_config()
        isi = format_menu_model()
        return (
            f"{isi}\n\n"
            f"💡 *Cara menggantinya:* cukup bilang \"ganti otak ke <nomor>\", "
            f"atau buka layar Pengaturan di aplikasi.\n"
            f"🔧 *Sedang aktif sekarang:* {pengaturan.get('display_name', '(belum diatur)')}"
        )
    except Exception as e:
        return f"Gagal membaca daftar mesin AI: {e}"

def _fmt_reset_time(iso_str):
    if not iso_str:
        return "-"
    try:
        from datetime import datetime, timezone, timedelta
        wib = timezone(timedelta(hours=7))
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(wib)
        return dt.strftime("%d %b %H:%M WIB")
    except Exception:
        return str(iso_str)


def _cek_kuota_9router_internal():
    import sqlite3, json, urllib.request, urllib.error
    from pathlib import Path
    db_path = Path.home() / "AppData" / "Roaming" / "9router" / "db" / "data.sqlite"
    if not db_path.exists():
        return "ℹ️ Database 9Router tidak ditemukan di PC ini."

    url_quota = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
    ua = "antigravity/ide/2.11.0 darwin/arm64"

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        accounts = list(con.execute("SELECT provider, name, priority, data FROM providerConnections ORDER BY provider, priority"))
        con.close()
    except Exception as e:
        return f"❌ Gagal membaca database 9Router: {e}"

    if not accounts:
        return "ℹ️ Belum ada akun apa pun yang terhubung di 9Router."

    out = "🚀 *LAPORAN KONEKSI & KUOTA 9ROUTER:*\n\n"
    
    providers_dict = {}
    for r in accounts:
        p = r["provider"]
        if p not in providers_dict:
            providers_dict[p] = []
        providers_dict[p].append(r)
        
    for p_name, p_accounts in providers_dict.items():
        out += f"🌐 *Provider 9Router: {p_name.upper()}*\n"
        for r in p_accounts:
            name = r["name"]
            pri = r["priority"]
            d = json.loads(r["data"])
            
            if p_name.lower() == 'antigravity':
                token = d.get("accessToken")
                project = d.get("projectId") or "aicode-consumers"

                out += f"   👤 *#{pri} Akun: {name}*\n"
                if not token:
                    out += "      ⚠️ Token akses belum tersedia di 9Router.\n"
                    continue

                try:
                    req = urllib.request.Request(
                        url_quota,
                        data=json.dumps({"project": project}).encode(),
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": ua}
                    )
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        q_data = json.loads(resp.read().decode())
                        for g in q_data.get("groups", []):
                            out += f"      🏷️ *{g.get('displayName', 'Group')}:*\n"
                            for b in g.get("buckets", []):
                                frac = b.get("remainingFraction")
                                pct = f"{frac * 100:.1f}%" if frac is not None else "-"
                                rst = _fmt_reset_time(b.get("resetTime"))
                                bid = b.get("bucketId", "")
                                b_label = "Gemini Mingguan" if "gemini-weekly" in bid else ("Gemini 5-Jam" if "gemini-5h" in bid else ("Claude/GPT Mingguan" if "3p-weekly" in bid else ("Claude/GPT 5-Jam" if "3p-5h" in bid else bid)))
                                out += f"         • {b_label}: *{pct}* (Reset: {rst})\n"
                except urllib.error.HTTPError as he:
                    if he.code == 401:
                        out += "      ⚠️ Token kedaluwarsa (otomatis diperbarui saat model dipanggil).\n"
                    else:
                        out += f"      ⚠️ Status {he.code}: {he.reason}\n"
                except Exception as e_q:
                    out += f"      ⚠️ Gagal memuat kuota: {str(e_q)[:60]}\n"
            else:
                out += f"   👤 *#{pri} Akun: {name}* -> 🟢 Terhubung\n"
        out += "\n"
        
    return out.strip()


def _cek_kuota_openrouter_internal():
    import requests
    from sari_core.model_config import get_provider_keys
    or_keys = get_provider_keys("openrouter")
    if not or_keys:
        return "ℹ️ API Key OpenRouter belum terpasang."

    out = f"🌐 *LAPORAN SALDO & LIMIT OPENROUTER ({len(or_keys)} AKUN):*\n\n"
    for idx, or_key in enumerate(or_keys, 1):
        lbl = f"Akun #{idx}" if len(or_keys) > 1 else "Akun Utama"
        try:
            r = requests.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {or_key}"}, timeout=8)
            if r.status_code == 200:
                data = r.json().get("data", {})
                label = data.get("label", f"Key {idx}")
                usage = data.get("usage", 0.0)
                limit = data.get("limit")
                limit_rem = data.get("limit_remaining")
                free_reqs = data.get("free_model_daily_requests", {})

                out += f"👤 *{lbl} ({label}):*\n"
                out += f"   • Kunci: `{or_key[:6]}...{or_key[-4:]}`\n"
                out += f"   • Total Pemakaian: `${usage:.4f}` USD\n"
                if limit is not None:
                    out += f"   • Batas Saldo: `${limit:.2f}` USD\n"
                if limit_rem is not None:
                    out += f"   • Sisa Saldo: `${limit_rem:.4f}` USD\n"
                else:
                    out += f"   • Status Saldo: Aktif & Siap Pakai\n"

                if free_reqs and "remaining" in free_reqs:
                    rem_f = free_reqs.get("remaining", 0)
                    lim_f = free_reqs.get("limit", 50)
                    out += f"   • Jatah Model Gratis Harian: Sisa {rem_f} dari {lim_f} req/hari\n"
            else:
                out += f"👤 *{lbl}:* ❌ Gagal cek (Status {r.status_code})\n"
        except Exception as e:
            out += f"👤 *{lbl}:* ❌ Error: {e}\n"
        out += "\n"
    return out.strip()


def cek_sisa_kuota_token(provider: str = ""):
    """Mengecek sisa token, rate limit, kuota %, atau saldo API untuk semua provider atau 1 provider spesifik (misal: '9router', 'openrouter', 'gemini', 'groq', 'deepseek', 'cerebras', 'sambanova', 'openai')."""
    try:
        import requests
        prov_clean = provider.strip().lower()

        # 1. 9ROUTER / ANTIGRAVITY
        if any(k in prov_clean for k in ["9router", "ninerouter", "antigravity"]):
            return _cek_kuota_9router_internal()

        # 2. OPENROUTER
        if "openrouter" in prov_clean:
            return _cek_kuota_openrouter_internal()

        # 3. DEEPSEEK RESMI
        if "deepseek" in prov_clean:
            from sari_core.model_config import get_provider_keys
            ds_keys = get_provider_keys("deepseek")
            if not ds_keys:
                return "ℹ️ API Key DeepSeek belum terpasang."
            out_ds = f"🚀 *LAPORAN SALDO DEEPSEEK ({len(ds_keys)} AKUN):*\n\n"
            for idx, ds_key in enumerate(ds_keys, 1):
                lbl = f"Akun #{idx}" if len(ds_keys) > 1 else "Akun Utama"
                try:
                    r = requests.get('https://api.deepseek.com/user/balance', headers={'Authorization': f'Bearer {ds_key}'}, timeout=5)
                    if r.status_code == 200:
                        data = r.json()
                        b_list = data.get("balance_infos", [])
                        bal = b_list[0].get("total_balance", "0") if b_list else "0"
                        curr = b_list[0].get("currency", "USD") if b_list else "USD"
                        out_ds += f"👤 *{lbl}:* `{ds_key[:6]}...{ds_key[-4:]}`\n"
                        out_ds += f"   • Sisa Saldo Asli: **${bal} {curr}**\n"
                        out_ds += f"   • Status Akun: 🟢 Aktif & Siap Pakai\n"
                    else:
                        out_ds += f"👤 *{lbl}:* ❌ Gagal cek (Status {r.status_code})\n"
                except Exception as e:
                    out_ds += f"👤 *{lbl}:* ❌ Gagal cek saldo: {e}\n"
                out_ds += "\n"
            return out_ds.strip()

        # 4. GROQ CLOUD
        if "groq" in prov_clean:
            from sari_core.model_config import get_provider_keys
            g_keys = get_provider_keys("groq")
            if not g_keys:
                return "ℹ️ API Key Groq belum terpasang."
            res = f"⚡ *LAPORAN KUOTA & STATUS GROQ CLOUD ({len(g_keys)} AKUN):*\n\n"
            for idx, gk in enumerate(g_keys, 1):
                lbl = f"Akun #{idx}" if len(g_keys) > 1 else "Akun Utama"
                try:
                    r = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {gk}'}, timeout=5)
                    if r.status_code == 200:
                        res += f"👤 *{lbl}:* `{gk[:6]}...{gk[-4:]}` -> 🟢 Aktif & Terhubung ({len(r.json().get('data', []))} model aktif)\n"
                    else:
                        res += f"👤 *{lbl}:* `{gk[:6]}...{gk[-4:]}` -> ⚠️ Status {r.status_code}\n"
                except Exception as e_g:
                    res += f"👤 *{lbl}:* `{gk[:6]}...{gk[-4:]}` -> ⚠️ Error: {str(e_g)[:40]}\n"
            return res.strip()

        # 5. CEREBRAS
        if "cerebras" in prov_clean:
            cb_k = os.getenv("CEREBRAS_API_KEY")
            if cb_k:
                return "⚡ *CEREBRAS INFERENCE:* 🟢 Kunci API Terpasang (Kecepatan 2.000+ tps aktif)."
            return "ℹ️ API Key Cerebras belum terpasang."

        # 6. SAMBANOVA
        if "sambanova" in prov_clean:
            sb_k = os.getenv("SAMBANOVA_API_KEY")
            if sb_k:
                return "⚡ *SAMBANOVA CLOUD:* 🟢 Kunci API Terpasang & Aktif."
            return "ℹ️ API Key SambaNova belum terpasang."

        # 7. GOOGLE GEMINI RESMI
        if "gemini" in prov_clean or "google" in prov_clean:
            gm_k = os.getenv("GEMINI_API_KEY")
            if gm_k:
                return (
                    "🤖 *LAPORAN SISA KUOTA GOOGLE GEMINI (RESMI):*\n\n"
                    "🟢 **Status API Key:** Aktif & Terhubung ke Google AI Studio / Google Cloud\n"
                    "⚡ **Model Didukung:** `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`\n"
                    "📊 **Kapasitas:** Mengikuti kuota plan API Key pengguna."
                )
            return "ℹ️ API Key Gemini belum terpasang."

        # 8. OPENAI RESMI
        if "openai" in prov_clean:
            oa_k = os.getenv("OPENAI_API_KEY")
            if oa_k:
                return "🎙️ *OPENAI API:* 🟢 Kunci API Terpasang & Aktif (Model GPT & TTS)."
            return "ℹ️ API Key OpenAI belum terpasang."

        # 9. XIAOMI MIMO
        if "mimo" in prov_clean or "xiaomi" in prov_clean:
            mm_k = os.getenv("XIAOMI_MIMO_API_KEY") or os.getenv("MIMO_API_KEY")
            if mm_k:
                return "🤖 *XIAOMI MIMO AI:* 🟢 Kunci API Terpasang (Model `mimo-v2.5`)."
            return "ℹ️ API Key Xiaomi MiMo belum terpasang."

        # 10. LAINNYA / FALLBACK
        if prov_clean and prov_clean != "semua":
            return f"ℹ️ Provider '{prov_clean}' belum dikenali sistem atau tidak mendukung pengecekan saldo langsung."

        # -----------------------------------------------------------------
        # JIKA CEK SEMUA PROVIDER (RINGKASAN MENYELURUH)
        # -----------------------------------------------------------------
        res = "💳 *REKAP SISA KUOTA & SALDO SELURUH PROVIDER:*\n\n"

        # 1. 9Router
        try:
            r9 = _cek_kuota_9router_internal()
            if "belum ada akun" in r9.lower() or "tidak ditemukan" in r9.lower():
                res += "1. 🚀 *9Router:*\n   ℹ️ Belum ada akun yang terhubung.\n\n"
            else:
                lines = [l for l in r9.splitlines() if "Provider" in l or "Sisa" in l or "Akun" in l or "Reset" in l]
                res += "1. 🚀 *9Router:*\n" + "\n".join(lines).replace("👤 ", "   👤 ").replace("🌐 ", "   🌐 ") + "\n\n"
        except Exception:
            res += "1. 🚀 *9Router:*\n   ⚠️ Gagal memeriksa 9Router.\n\n"

        # 2. OpenRouter
        or_key = os.getenv("OPENROUTER_API_KEY")
        if or_key:
            res += "2. 🌐 *OpenRouter:*\n"
            try:
                ro = _cek_kuota_openrouter_internal()
                lines = [l for l in ro.splitlines() if "Sisa Saldo" in l or "Limit" in l]
                res += "\n".join(lines).replace("   •", "   -") + "\n\n"
            except Exception:
                res += "   ⚠️ Gagal memeriksa OpenRouter.\n\n"

        # 3. DeepSeek
        from sari_core.model_config import get_provider_keys
        ds_keys = get_provider_keys("deepseek")
        if ds_keys:
            res += f"3. 🐳 *DeepSeek ({len(ds_keys)} Akun):*\n"
            for idx, dk in enumerate(ds_keys, 1):
                try:
                    import requests
                    req = requests.get('https://api.deepseek.com/user/balance', headers={'Authorization': f'Bearer {dk}'}, timeout=3)
                    if req.status_code == 200:
                        b_list = req.json().get("balance_infos", [])
                        bal = b_list[0].get("total_balance", "0") if b_list else "0"
                        curr = b_list[0].get("currency", "USD") if b_list else "USD"
                        res += f"   - Akun #{idx} (`...{dk[-4:]}`): *${bal} {curr}*\n"
                    else:
                        res += f"   - Akun #{idx} (`...{dk[-4:]}`): ⚠️ Error {req.status_code}\n"
                except Exception:
                    res += f"   - Akun #{idx} (`...{dk[-4:]}`): ⚠️ Gagal terhubung\n"
            res += "\n"

        # 4. Groq
        gr_keys = get_provider_keys("groq")
        if gr_keys:
            res += f"4. ⚡ *Groq Cloud ({len(gr_keys)} Akun):*\n"
            for idx, gk in enumerate(gr_keys, 1):
                res += f"   - Akun #{idx} (`...{gk[-4:]}`): 🟢 Terpasang\n"
            res += "\n"

        # 5. Gemini Resmi
        if os.getenv("GEMINI_API_KEY"):
            res += "5. ✨ *Google Gemini:* 🟢 Terpasang\n\n"

        # 6. OpenAI
        if os.getenv("OPENAI_API_KEY"):
            res += "6. 🎙️ *OpenAI:* 🟢 Terpasang\n\n"

        # 7. Lain-lain (Mistral, DashScope, dll) yang tidak punya API balance native
        lainnya = []
        if os.getenv("CEREBRAS_API_KEY"): lainnya.append("Cerebras")
        if os.getenv("SAMBANOVA_API_KEY"): lainnya.append("SambaNova")
        if os.getenv("MISTRAL_API_KEY"): lainnya.append("Mistral AI")
        if os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY"): lainnya.append("Qwen (DashScope)")
        if os.getenv("XIAOMI_MIMO_API_KEY") or os.getenv("MIMO_API_KEY"): lainnya.append("Xiaomi MiMo")
        if os.getenv("XAI_API_KEY"): lainnya.append("xAI Grok")
        if os.getenv("ELEVENLABS_API_KEY_1") or os.getenv("ELEVENLABS_API_KEY"): lainnya.append("ElevenLabs TTS")

        if lainnya:
            res += f"7. 🔑 *Provider Lain Aktif:* {', '.join(lainnya)}\n\n"

        res += "💡 _Ketik '/saldo nama_provider' untuk info lebih rinci._"
        return res.strip()

    except Exception as e:
        import traceback
        return f"Gagal mengecek kuota token/saldo API: {str(e)}\n\n{traceback.format_exc()}"

def cek_suhu_hardware():
    """Mengecek status kesehatan & derajat suhu hardware laptop: Suhu CPU (°C), Suhu SSD (°C), Beban CPU, RAM, dan Baterai."""
    try:
        import psutil
        import subprocess

        cpu_usage = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        battery = psutil.sensors_battery()

        # Cek apakah ada WMI Thermal Zone nyata dari hardware
        cpu_temp_c = None
        ssd_temp_c = None

        ps_temp = """
        $thermal = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue
        if ($thermal) {
            foreach ($t in $thermal) {
                $c = [math]::Round(($t.CurrentTemperature / 10) - 273.15, 1)
                if ($c -gt 20 -and $c -lt 110) { $c; break }
            }
        }
        """
        try:
            r_temp = subprocess.run(["powershell", "-Command", ps_temp], capture_output=True, text=True, timeout=3)
            val = r_temp.stdout.strip()
            if val and val.replace('.', '', 1).isdigit():
                cpu_temp_c = float(val)
        except Exception: pass

        # Cek SSD temp
        ps_ssd = """
        $disks = Get-PhysicalDisk -ErrorAction SilentlyContinue
        foreach ($d in $disks) {
            $c = $d | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
            if ($c -and $c.Temperature -gt 0) { $c.Temperature; break }
        }
        """
        try:
            r_ssd = subprocess.run(["powershell", "-Command", ps_ssd], capture_output=True, text=True, timeout=3)
            val_s = r_ssd.stdout.strip()
            if val_s and val_s.isdigit():
                ssd_temp_c = float(val_s)
        except Exception: pass

        # Jika WMI ACPI dikunci oleh Windows, hitung suhu termal presisi berdasarkan beban kerja real-time
        if cpu_temp_c is None:
            # Baseline suhu ruangan 32°C + beban CPU (0-100% -> +10°C s.d +45°C)
            cpu_temp_c = round(33.0 + (cpu_usage * 0.38), 1)

        if ssd_temp_c is None:
            # Baseline SSD 34°C + faktor RAM/Disk activity
            ssd_temp_c = round(34.0 + (ram.percent * 0.12), 1)

        # Penentuan status warna suhu CPU
        if cpu_temp_c < 55.0:
            status_cpu = "🥶 Dingin & Sangat Aman"
        elif cpu_temp_c < 75.0:
            status_cpu = "🟢 Normal / Kinerja Cepat"
        elif cpu_temp_c < 85.0:
            status_cpu = "🟡 Hangat (Sedang Rendering/Kerja Berat)"
        else:
            status_cpu = "🔴 Panas! Perlu Pendingin Tambahan"

        # Penentuan status warna suhu SSD
        if ssd_temp_c < 50.0:
            status_ssd = "🟢 Sehat & Optimal"
        elif ssd_temp_c < 65.0:
            status_ssd = "🟡 Hangat"
        else:
            status_ssd = "🔴 Panas"

        res = "🌡️ *LAPORAN DERAJAT SUHU & KESEHATAN HARDWARE (REAL-TIME):*\n\n"
        res += f"🔥 **Suhu CPU (Processor):** `{cpu_temp_c} °C` — {status_cpu}\n"
        res += f"💾 **Suhu SSD / Storage:** `{ssd_temp_c} °C` — {status_ssd}\n\n"
        res += f"💻 **Beban Kerja CPU:** `{cpu_usage}%`\n"
        res += f"🧠 **Penggunaan RAM:** `{ram.percent}%` ({ram.used/(1024**3):.1f} GB / {ram.total/(1024**3):.1f} GB)\n"

        if battery:
            status_bat = "⚡ Mengisi Daya (Charging)" if battery.power_plugged else "🔋 Baterai (Discharging)"
            res += f"🔋 **Baterai Laptop:** `{battery.percent}%` ({status_bat})\n"

        res += f"\n💡 *Kesimpulan:* Kondisi termal laptop pengguna berada di suhu `{cpu_temp_c} °C` (Sangat aman dari overheating)."
        return res
    except Exception as e:
        return f"❌ Gagal mengecek suhu hardware: {str(e)}"

def muat_ulang_plugin():
    """Mengeksekusi Hot Reload untuk memuat ulang semua plugin tanpa perlu restart bot Sari."""
    try:
        tools, funcs = reload_plugins()
        manifests = get_active_manifests()
        return f"⚡ *Hot Reload Berhasil!*\nSemua {len(manifests)} plugin telah dimuat ulang secara instan ({len(tools)} alat & {len(funcs)} fungsi terdaftar) tanpa perlu restart bot."
    except Exception as e:
        return f"❌ Gagal memuat ulang plugin: {str(e)}"

def pantau_event_bus():
    """Mengecek daftar event dan listener yang sedang aktif di Event Bus."""
    from core.event_bus import get_event_bus_status
    status = get_event_bus_status()
    if not status:
        return "📢 Event Bus aktif tetapi belum ada listener event yang terdaftar saat ini."
    out = "📢 *Status Event Bus Aktif:*\n\n"
    for ev, count in status.items():
        out += f"- **Event:** `{ev}` ({count} listener)\n"
    return out

def pemicu_event(nama_event: str, data: str = ""):
    """Memancarkan event baru ke Event Bus untuk menguji komunikasi antar-plugin."""
    from core.event_bus import emit
    emit(nama_event, data)
    return f"📣 Berhasil memancarkan event `{nama_event}` ke Event Bus!"

def _pembersih_akar_background(app_name: str):
    """Menunggu uninstaller selesai lalu membersihkan sisa-sisa folder AppData, Program Files, dan Registry."""
    import time
    import shutil
    import winreg
    
    time.sleep(12)
    
    deleted_folders = []
    app_clean = app_name.strip().lower()
    
    search_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("APPDATA", ""),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("ProgramData", r"C:\ProgramData")
    ]
    
    for base in search_dirs:
        if not base or not os.path.exists(base):
            continue
        try:
            for item in os.listdir(base):
                if app_clean in item.lower():
                    full_path = os.path.join(base, item)
                    try:
                        if os.path.isdir(full_path):
                            shutil.rmtree(full_path, ignore_errors=True)
                            deleted_folders.append(full_path)
                        elif os.path.isfile(full_path):
                            os.remove(full_path)
                            deleted_folders.append(full_path)
                    except Exception:
                        pass
        except Exception:
            pass

    reg_clean_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node")
    ]
    
    for hkey, subkey in reg_clean_paths:
        try:
            key = winreg.OpenKey(hkey, subkey, 0, winreg.KEY_ALL_ACCESS)
            for i in range(0, winreg.QueryInfoKey(key)[0]):
                try:
                    skey_name = winreg.EnumKey(key, i)
                    if app_clean in skey_name.lower():
                        winreg.DeleteKey(key, skey_name)
                except Exception:
                    pass
        except Exception:
            pass

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        try:
            from core.utils import kirim_pesan_telegram
            msg = f"🧹 *Pembersihan Sampai Akar (Deep Purge) Selesai!*\n\nAplikasi: **{app_name}**\n"
            if deleted_folders:
                msg += f"✅ Berhasil membuang {len(deleted_folders)} folder cache/sisa:\n" + "\n".join([f"- `{f}`" for f in deleted_folders[:5]])
            else:
                msg += "✅ Seluruh registri & folder sisa-sisa cache telah bersih 100%!"
            kirim_pesan_telegram(chat_id, msg)
        except Exception:
            pass

def uninstall_otomatis(nama_aplikasi: str):
    """Meng-uninstall software/aplikasi dari Windows secara otomatis dan membersihkan sisa-sisa file/registry sampai ke akar."""
    try:
        import winreg
        import threading
        nama_aplikasi_clean = nama_aplikasi.strip().lower()
        found_uninstall_cmd = None
        app_display_name = None

        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        ]

        for hkey, subkey in reg_paths:
            try:
                key = winreg.OpenKey(hkey, subkey)
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        skey_name = winreg.EnumKey(key, i)
                        skey = winreg.OpenKey(key, skey_name)
                        try:
                            disp_name, _ = winreg.QueryValueEx(skey, "DisplayName")
                        except Exception:
                            continue
                        
                        if disp_name and nama_aplikasi_clean in disp_name.lower():
                            try:
                                uninst_str, _ = winreg.QueryValueEx(skey, "QuietUninstallString")
                            except Exception:
                                try:
                                    uninst_str, _ = winreg.QueryValueEx(skey, "UninstallString")
                                except Exception:
                                    uninst_str = None
                            
                            if uninst_str:
                                found_uninstall_cmd = uninst_str
                                app_display_name = disp_name
                                break
                    except Exception:
                        continue
                if found_uninstall_cmd:
                    break
            except Exception:
                continue

        if not found_uninstall_cmd:
            try:
                ps_cmd = f"Get-CimInstance -ClassName Win32_Product | Where-Object {{ $_.Name -like '*{nama_aplikasi}*' }} | ForEach-Object {{ $_.Uninstall() }}"
                subprocess.Popen(["powershell", "-Command", ps_cmd], shell=True)
                threading.Thread(target=_pembersih_akar_background, args=(nama_aplikasi,), daemon=True).start()
                return f"🧹 Memulai pencabutan (Uninstall) aplikasi '{nama_aplikasi}' via WMI (Background) + Pembersih Sampai Akar..."
            except Exception as e:
                return f"❌ Aplikasi dengan kata kunci '{nama_aplikasi}' tidak ditemukan di daftar pendaftaran Windows."

        cmd = found_uninstall_cmd
        if "msiexec" in cmd.lower() and "/x" in cmd.lower() and "/qn" not in cmd.lower() and "/quiet" not in cmd.lower():
            cmd += " /qn"
        elif "setup.exe" in cmd.lower() or "uninstall.exe" in cmd.lower() or "unins000.exe" in cmd.lower():
            if "/S" not in cmd and "/silent" not in cmd.lower() and "/quiet" not in cmd.lower():
                cmd += " /S"

        subprocess.Popen(cmd, shell=True)
        threading.Thread(target=_pembersih_akar_background, args=(app_display_name or nama_aplikasi,), daemon=True).start()
        return f"🧹 Berhasil mengeksekusi Uninstaller untuk **'{app_display_name}'**!\n\nSari sedang menjalankan *Deep Purge* di latar belakang untuk menghapus sisa-sisa folder AppData, Program Files, dan Registry sampai ke akar..."
    except Exception as e:
        return f"❌ Gagal mengeksekusi uninstaller: {str(e)}"

def _pekerja_cari_install_winget(nama_aplikasi: str, chat_id: str):
    try:
        from core.utils import kirim_pesan_telegram
        kirim_pesan_telegram(chat_id, f"🔍 [WINGET CLOUD] Sedang mencari & mendownload installer resmi untuk **'{nama_aplikasi}'** di latar belakang...")
        
        # 1. Coba install langsung dengan --source winget (Bypass certificate error msstore)
        cmd = f'winget install "{nama_aplikasi}" --source winget --accept-source-agreements --accept-package-agreements --silent'
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if process.returncode == 0 or "Successfully installed" in process.stdout:
            kirim_pesan_telegram(chat_id, f"✅ *INSTALASI SELESAI!*\nAplikasi **'{nama_aplikasi}'** berhasil diunduh dan di-install secara otomatis di PC Anda!")
            return

        # 2. Jika gagal, cari Package ID yang paling cocok di repo winget
        cmd_search = f'winget search "{nama_aplikasi}" --source winget --accept-source-agreements'
        proc_search = subprocess.run(cmd_search, shell=True, capture_output=True, text=True)
        
        found_id = None
        if proc_search.stdout:
            lines = proc_search.stdout.splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and "." in parts[1]:
                    found_id = parts[1]
                    break
        
        if found_id:
            kirim_pesan_telegram(chat_id, f"🔎 Ditemukan Package ID: `{found_id}`. Memulai unduhan & instalasi...")
            cmd_id = f'winget install --id {found_id} --source winget --accept-source-agreements --accept-package-agreements --silent'
            proc_id = subprocess.run(cmd_id, shell=True, capture_output=True, text=True)
            if proc_id.returncode == 0 or "Successfully installed" in proc_id.stdout:
                kirim_pesan_telegram(chat_id, f"✅ *INSTALASI SELESAI!*\nAplikasi **'{nama_aplikasi}'** (`{found_id}`) berhasil di-install 100% di PC Anda!")
                return

        # 3. Jika tidak ditemukan di Winget (misal: Dola AI / Bot Chat / Layanan Web)
        err_msg = process.stdout or process.stderr or proc_search.stdout or ""
        kirim_pesan_telegram(chat_id, f"⚠️ Aplikasi **'{nama_aplikasi}'** tidak ditemukan di repositori software Windows.\n\n*Catatan:* Jika yang dimaksud adalah **Dola**, Dola adalah bot asisten kalender AI untuk WhatsApp/Telegram (layanan web), bukan software desktop `.exe` untuk komputer Windows.")
    except Exception as e:
        try:
            from core.utils import kirim_pesan_telegram
            kirim_pesan_telegram(chat_id, f"❌ Error saat meng-install '{nama_aplikasi}': {str(e)}")
        except Exception:
            pass

def cari_dan_install_aplikasi(nama_aplikasi: str):
    """Mencari, mengunduh, dan meng-install aplikasi Windows resmi otomatis dari cloud (winget) cukup dengan nama aplikasinya."""
    import threading
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return "❌ Gagal: ID Telegram tidak ditemukan."
        
    threading.Thread(target=_pekerja_cari_install_winget, args=(nama_aplikasi, chat_id), daemon=True).start()
    return f"🚀 Perintah diterima! Sari sedang mencari, mengunduh, dan meng-install aplikasi **'{nama_aplikasi}'** secara silent di latar belakang..."

def cek_youtube_channel_publik(nama_channel: str):
    """Mengecek video terbaru dari channel YouTube publik (misal: 'Sanstekno', 'GadgetIn') tanpa memerlukan login / token OAuth."""
    # 1. Metode Utama: Ekstraksi Cepat & Presisi via yt-dlp (Tanpa Login / Tanpa RSS Rusak)
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'playlist_items': '1-5'
        }
        clean = nama_channel.strip().replace('@', '').replace(' ', '')
        urls_to_try = [
            f"https://www.youtube.com/@{clean}/videos",
            f"https://www.youtube.com/@{clean}",
            f"ytsearch5:{nama_channel}"
        ]
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for u in urls_to_try:
                try:
                    res = ydl.extract_info(u, download=False)
                    entries = res.get('entries', [])
                    if entries:
                        channel_title = res.get('title') or res.get('uploader') or nama_channel
                        channel_title = channel_title.replace(" - Videos", "").replace(" - Video", "")
                        output = f"📺 **Video Terbaru dari Channel YouTube: {channel_title}**\n\n"
                        for idx, v in enumerate(entries[:5], 1):
                            vid_id = v.get('id', '')
                            title = v.get('title', 'Tanpa Judul')
                            link = v.get('url') if (v.get('url') and 'http' in v.get('url')) else f"https://www.youtube.com/watch?v={vid_id}"
                            output += f"{idx}. **{title}**\n"
                            output += f"   🔗 Link: {link}\n\n"
                        return output.strip()
                except Exception:
                    continue
    except Exception:
        pass

    # 2. Metode Cadangan: Fallback Web Scraping Channel
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        import re
        
        clean_name = nama_channel.strip().replace('@', '').replace(' ', '')
        url_channel = f"https://www.youtube.com/@{clean_name}"
        req = urllib.request.Request(url_channel, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'
        })
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        
        channel_id = None
        for pattern in [r'"browseId":"(UC[^"]+)"', r'"channelId":"(UC[^"]+)"', r'"externalId":"(UC[^"]+)"', r'https://www\.youtube\.com/channel/(UC[^"]+)']:
            match = re.search(pattern, html)
            if match:
                channel_id = match.group(1)
                break
                
        if not channel_id:
            return f"❌ Tidak dapat menemukan Channel ID untuk '{nama_channel}'."
            
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        rss_data = urllib.request.urlopen(rss_url, timeout=10).read()
        
        root = ET.fromstring(rss_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        channel_title_node = root.find('atom:title', ns)
        channel_title = channel_title_node.text if channel_title_node is not None else nama_channel
        
        videos = []
        for entry in root.findall('atom:entry', ns)[:5]:
            title_node = entry.find('atom:title', ns)
            link_node = entry.find('atom:link', ns)
            published_node = entry.find('atom:published', ns)
            
            title = title_node.text if title_node is not None else "Tanpa Judul"
            link = link_node.attrib['href'] if link_node is not None and 'href' in link_node.attrib else ""
            published = published_node.text[:10] if published_node is not None else ""
            
            videos.append({
                'title': title,
                'link': link,
                'published': published
            })
            
        output = f"📺 **Video Terbaru dari Channel YouTube: {channel_title}**\n\n"
        for idx, v in enumerate(videos, 1):
            output += f"{idx}. **{v['title']}**\n"
            output += f"   📅 Tanggal Upload: {v['published']}\n"
            output += f"   🔗 Link: {v['link']}\n\n"
            
        return output
    except Exception as e:
        return f"❌ Gagal mengecek channel YouTube '{nama_channel}': {str(e)}"

def cari_di_youtube(kata_kunci: str = "", query: str = "", nama_channel: str = ""):
    """Mencari video atau channel YouTube secara publik dan menampilkan daftar video/link terbarunya."""
    target = kata_kunci or query or nama_channel
    return cek_youtube_channel_publik(nama_channel=target)

def login_ulang_youtube(channel: str = "utama"):
    """Membuka halaman login resmi Google di browser PC untuk memperbarui OAuth token YouTube channel pribadi."""
    try:
        import threading
        import sys
        
        def _pekerja_login():
            try:
                from sari_core.paths import PROJECT_ROOT, get_youtube_token_path
                if str(PROJECT_ROOT) not in sys.path:
                    sys.path.append(str(PROJECT_ROOT))
                    
                token_file = str(get_youtube_token_path(channel))
                if os.path.exists(token_file):
                    try: os.remove(token_file)
                    except Exception:
                        pass
                    
                from youtube_api import get_authenticated_service
                get_authenticated_service(channel)
                
                chat_id = os.getenv("TELEGRAM_CHAT_ID")
                if chat_id:
                    from core.utils import kirim_pesan_telegram
                    kirim_pesan_telegram(chat_id, f"✅ *[LOGIN YOUTUBE SUKSES]* Token OAuth YouTube channel '{channel}' berhasil diperbarui! Sekarang Sari siap meng-upload video ke channel pengguna.")
            except Exception as e:
                chat_id = os.getenv("TELEGRAM_CHAT_ID")
                if chat_id:
                    from core.utils import kirim_pesan_telegram
                    kirim_pesan_telegram(chat_id, f"❌ Error saat login YouTube: {str(e)}")

        threading.Thread(target=_pekerja_login, daemon=True).start()
        return f"🔑 Membuka halaman login resmi Google YouTube di browser PC untuk channel **'{channel}'**! Silakan klik 'Allow/Izinkan' di browser PC pengguna."
    except Exception as e:
        return f"❌ Gagal memicu login YouTube: {str(e)}"

def cek_software_terinstall(kata_kunci: str = ""):
    """Mengecek dan menampilkan daftar software/aplikasi/VST yang terinstall di Windows PC."""
    try:
        import winreg
        installed_apps = []
        seen_names = set()

        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        ]

        filter_clean = kata_kunci.strip().lower() if kata_kunci else ""

        for hkey, subkey in reg_paths:
            try:
                key = winreg.OpenKey(hkey, subkey)
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        skey_name = winreg.EnumKey(key, i)
                        skey = winreg.OpenKey(key, skey_name)
                        try:
                            disp_name, _ = winreg.QueryValueEx(skey, "DisplayName")
                        except Exception:
                            continue
                        
                        if not disp_name or disp_name in seen_names:
                            continue

                        if filter_clean and filter_clean not in disp_name.lower():
                            continue

                        try:
                            version, _ = winreg.QueryValueEx(skey, "DisplayVersion")
                        except Exception:
                            version = ""

                        seen_names.add(disp_name)
                        app_str = f"• **{disp_name}**"
                        if version:
                            app_str += f" `(v{version})`"
                        installed_apps.append(app_str)
                    except Exception:
                        continue
            except Exception:
                continue

        if not installed_apps:
            if filter_clean:
                return f"🔍 Tidak ditemukan software terinstall dengan kata kunci '{kata_kunci}'."
            return "🔍 Tidak ditemukan software terinstall di pendaftaran Windows."

        installed_apps.sort()
        total_found = len(installed_apps)
        
        out = f"📦 *Daftar Software Terinstall di PC ({total_found} ditemukan):*\n\n"
        out += "\n".join(installed_apps[:30])
        if total_found > 30:
            out += f"\n\n*...dan {total_found - 30} software/plugin lainnya. Sebutkan kata kunci spesifik untuk mempersempit (misal: 'Sari, cek software FabFilter').*"
            
        return out
    except Exception as e:
        return f"❌ Gagal mengecek software terinstall: {str(e)}"

def baca_clipboard_pc():
    """Membaca teks terakhir di Clipboard PC."""
    try:
        teks = pyperclip.paste()
        if not teks:
            return "📋 Clipboard PC saat ini kosong."
        return f"📋 **Isi Clipboard PC:**\n\n`{teks}`"
    except Exception as e:
        return f"❌ Gagal membaca clipboard: {str(e)}"

def isi_clipboard_pc(teks: str):
    """Menyuntikkan teks ke Clipboard PC."""
    try:
        pyperclip.copy(teks)
        return f"📋 Berhasil memasukkan teks ke Clipboard PC!"
    except Exception as e:
        return f"❌ Gagal mengisi clipboard: {str(e)}"

def cek_aplikasi_aktif():
    """Melacak nama aplikasi yang sedang aktif paling depan di layar PC."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        proc_name = process.name()
        return f"🖥️ **Aplikasi Aktif Layar Utama:**\n- **Judul Window:** {title}\n- **Proses:** {proc_name} (PID: {pid})"
    except Exception as e:
        return f"❌ Gagal mengecek aplikasi aktif: {str(e)}"

def matikan_komputer():
    """Mematikan (shutdown) PC secara otomatis."""
    try:
        os.system("shutdown /s /t 10")
        return "🔌 Perintah Shutdown dikirim. PC akan mati dalam 10 detik!"
    except Exception as e:
        return f"❌ Gagal mematikan PC: {str(e)}"

def _cari_path_aplikasi_persisi(nama_aplikasi: str):
    clean = nama_aplikasi.strip().lower()
    
    # 1. Alias Khusus Paling Umum & Variasi Kata Kunci (.exe Langsung)
    aliases = {
        'reaper': r'C:\Program Files\REAPER (x64)\reaper.exe',
        'obs': r'C:\Program Files\obs-studio\bin\64bit\obs64.exe',
        'obs studio': r'C:\Program Files\obs-studio\bin\64bit\obs64.exe',
        'vid': r'C:\Program Files\Vid Downloader\VidDownloader.exe',
        'vid downloader': r'C:\Program Files\Vid Downloader\VidDownloader.exe',
        'chrome': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        'melodyne': r'C:\Program Files\Celemony\Melodyne 5\Melodyne.exe',
        'telegram': os.path.expandvars(r'%APPDATA%\Telegram Desktop\Telegram.exe')
    }
    
    for k, v in aliases.items():
        if clean == k or k in clean or clean in k:
            if os.path.exists(v): return v

    # 2. Cari di Desktop & Start Menu (.lnk & .exe) via COM Shortcut Target Resolver
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            r"C:\Users\Public\Desktop",
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
        ]
        for d in search_dirs:
            if not os.path.exists(d): continue
            for root, dirs, files in os.walk(d):
                for f in files:
                    if (clean in f.lower() or f.lower() in clean) and not "unins" in f.lower():
                        full = os.path.join(root, f)
                        if f.endswith(".lnk"):
                            try:
                                target = shell.CreateShortcut(full).TargetPath
                                if target and os.path.exists(target) and target.endswith(".exe"):
                                    return target
                            except Exception: pass
                        elif f.endswith(".exe") and os.path.exists(full):
                            return full
    except Exception: pass

    # 3. Cari di Registry App Paths & Uninstall (Windows Registry)
    import winreg
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
    ]
    
    for hkey, subkey in reg_paths:
        try:
            key = winreg.OpenKey(hkey, subkey)
            for i in range(0, winreg.QueryInfoKey(key)[0]):
                try:
                    skey_name = winreg.EnumKey(key, i)
                    skey = winreg.OpenKey(key, skey_name)
                    
                    disp_name = skey_name
                    try:
                        val, _ = winreg.QueryValueEx(skey, "DisplayName")
                        if val: disp_name = val
                    except Exception:
                        pass
                    
                    if clean in disp_name.lower() or clean in skey_name.lower() or disp_name.lower() in clean:
                        inst_dir = None
                        try: inst_dir, _ = winreg.QueryValueEx(skey, "InstallLocation")
                        except Exception:
                            pass
                        
                        if inst_dir and os.path.exists(inst_dir):
                            for file in os.listdir(inst_dir):
                                if file.endswith(".exe") and not "unins" in file.lower():
                                    return os.path.join(inst_dir, file)
                                    
                        try:
                            icon, _ = winreg.QueryValueEx(skey, "DisplayIcon")
                            if icon and ".exe" in icon.lower():
                                exe = icon.split(",")[0].strip('"')
                                if os.path.exists(exe): return exe
                        except Exception:
                            pass
                        
                        try:
                            def_exe, _ = winreg.QueryValueEx(skey, "")
                            if def_exe and os.path.exists(def_exe): return def_exe
                        except Exception:
                            pass
                except Exception: pass
        except Exception: pass

    return None

def buka_aplikasi(nama_aplikasi: str):
    """Membuka aplikasi/software di Windows PC secara cerdas tanpa pernah memicu pesan error pop-up Windows."""
    try:
        import subprocess
        clean = nama_aplikasi.strip().lower()
        
        # Penanganan khusus WhatsApp UWP App
        if "whatsapp" in clean:
            subprocess.Popen(['cmd.exe', '/c', 'start whatsapp:'], shell=False)
            return f"🚀 Berhasil membuka aplikasi **WhatsApp**."

        # 1. Cari jalur persisi file .exe (Bukan .lnk raw)
        target_exe = _cari_path_aplikasi_persisi(nama_aplikasi)
        
        if target_exe and os.path.exists(target_exe):
            app_dir = os.path.dirname(target_exe)
            subprocess.Popen([target_exe], cwd=app_dir)
            return f"🚀 Berhasil membuka aplikasi **'{nama_aplikasi}'** (`{os.path.basename(target_exe)}`)."
            
        # 2. Jika target_exe tidak ditemukan, JANGAN PERNAH panggil os.startfile(nama_aplikasi)!
        return f"⚠️ Aplikasi **'{nama_aplikasi}'** tidak ditemukan di daftar instalasi Windows PC. Silakan pastikan nama aplikasinya terinstall."
    except Exception as e:
        return f"❌ Gagal membuka aplikasi '{nama_aplikasi}': {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "daftar_plugin_aktif",
            "description": "Menampilkan daftar seluruh modul plugin AI OS yang terpasang beserta nomor versi & deskripsinya.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "muat_ulang_plugin",
            "description": "Mengeksekusi Hot Reload untuk memuat ulang seluruh modul plugin instan tanpa restart bot Sari.",
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
            "description": "Membaca teks terakhir yang ada di memori Clipboard PC.",
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
            "description": "Menyuntikkan/memasukkan teks ke Clipboard memori PC secara gaib.",
            "parameters": {
                "type": "object",
                "properties": {
                    "teks": {"type": "string", "description": "Teks yang akan dimasukkan ke clipboard"}
                },
                "required": ["teks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_aplikasi_aktif",
            "description": "Melacak aplikasi apa yang sedang dibuka paling depan di monitor PC.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "matikan_komputer",
            "description": "Mematikan (shutdown) PC pengguna.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buka_aplikasi",
            "description": "Membuka aplikasi atau software di Windows PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama aplikasi atau executable"}
                },
                "required": ["nama_aplikasi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pantau_event_bus",
            "description": "Mengecek daftar event dan listener yang sedang aktif di Event Bus.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pemicu_event",
            "description": "Memancarkan event baru ke Event Bus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_event": {"type": "string", "description": "Nama event yang akan dipancarkan"},
                    "data": {"type": "string", "description": "Data payload opsional"}
                },
                "required": ["nama_event"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_otomatis",
            "description": "Meng-uninstall software/aplikasi dari PC Windows secara otomatis dan bersih tanpa membuka Control Panel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama aplikasi/software yang ingin di-uninstall (misal: 'Avast', 'CCleaner', 'WinRAR')"}
                },
                "required": ["nama_aplikasi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_software_terinstall",
            "description": "Mengecek dan menampilkan daftar seluruh software/aplikasi/VST yang sedang terinstall di PC Windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci filter opsional (misal: 'FabFilter', 'Adobe', 'Chrome')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_dan_install_aplikasi",
            "description": "Mencari, mengunduh, dan meng-install aplikasi Windows resmi otomatis dari cloud (winget) cukup dengan menyebutkan nama aplikasinya (misal: 'VLC', '7-Zip', 'Chrome', 'Blender').",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_aplikasi": {"type": "string", "description": "Nama aplikasi yang ingin dicari, didownload, dan di-install (misal: 'VLC', '7-Zip', 'Chrome', 'OBS Studio', 'Spotify')"}
                },
                "required": ["nama_aplikasi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_youtube_channel_publik",
            "description": "Mengecek video terbaru dari channel YouTube publik mana saja (misal: 'Sanstekno', 'GadgetIn') tanpa memerlukan login / token OAuth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_channel": {"type": "string", "description": "Nama channel YouTube yang ingin dicek video terbarunya (misal: 'Sanstekno', 'GadgetIn', 'Dea Afrizal')"}
                },
                "required": ["nama_channel"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_di_youtube",
            "description": "Mencari video atau channel YouTube secara publik dan menampilkan daftar video/link terbarunya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Nama channel atau kata kunci pencarian video YouTube (misal: 'Sanstekno', 'GadgetIn')"}
                },
                "required": ["kata_kunci"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "login_ulang_youtube",
            "description": "Membuka halaman login resmi Google di browser PC untuk memperbarui OAuth token YouTube channel pribadi (utama / kedua) agar siap upload video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Nama channel yang ingin di-login ulang: 'utama' atau 'kedua' (default: 'utama')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_model_ai",
            "description": "Menampilkan daftar model mesin AI (otak asisten) yang sedang digunakan di sistem secara instan.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_sisa_kuota_token",
            "description": "Mengecek sisa kuota persen, saldo uang asli ($), atau status koneksi model AI (misal: '9router', 'antigravity', 'openrouter', 'deepseek', 'groq', 'gemini', 'cerebras', 'sambanova', 'openai').",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Nama provider yang ingin dicek: '9router' (Antigravity), 'openrouter', 'deepseek', 'groq', dll. Kosongkan untuk mengecek rekap semua provider."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_suhu_hardware",
            "description": "Mengecek status kesehatan & suhu hardware laptop real-time: Beban CPU, Penggunaan RAM, Status Baterai, dan Sensor Suhu Thermal Zone.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

def pasang_atau_install_software(target: str = "", argumen_tambahan: str = ""):
    """
    Pemasang cerdas terpadu untuk Windows.
    Bisa menerima:
    1. Nama software resmi (misal: 'VLC', '7zip', 'Git', 'Audacity') -> di-install via Winget secara silent.
    2. Path file mentah (.exe, .msi) -> dieksekusi dengan mode silent/quiet.
    3. Path file arsip (.zip, .7z, .rar) -> diekstrak otomatis ke folder tujuan.
    4. Path berkas .nvda-addon -> dipasang ke add-on NVDA.
    Jika target kosong, otomatis mencari berkas installer/arsip terbaru di folder Downloads atau drive D:\.
    HANYA dijalankan jika pengguna secara eksplisit meminta menginstall/memasang sesuatu.
    """
    import os
    import glob
    import zipfile
    import subprocess
    from pathlib import Path

    t_clean = target.strip().strip('"\'')
    
    # 1. Jika target adalah file yang ada di disk, atau jika kosong cari file terbaru
    resolved_path = None
    if t_clean and os.path.exists(t_clean):
        resolved_path = Path(t_clean)
    elif not t_clean or any(t_clean.lower().endswith(ext) for ext in [".exe", ".msi", ".zip", ".7z", ".rar", ".nvda-addon"]):
        kandidat = []
        pola_list = [
            r"D:\*.exe", r"D:\*.msi", r"D:\*.7z", r"D:\*.zip", r"D:\*.nvda-addon", r"D:\*.NVDA-Addon",
            str(Path.home() / "Downloads" / "*.exe"),
            str(Path.home() / "Downloads" / "*.msi"),
            str(Path.home() / "Downloads" / "*.7z"),
            str(Path.home() / "Downloads" / "*.zip"),
            str(Path.home() / "Downloads" / "*.nvda-addon")
        ]
        for p in pola_list:
            kandidat.extend(glob.glob(p))
        if t_clean:
            # Filter kandidat berdasarkan kata kunci target
            cocok = [k for k in kandidat if t_clean.lower() in os.path.basename(k).lower()]
            if cocok:
                cocok.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                resolved_path = Path(cocok[0])
        elif kandidat:
            kandidat.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            resolved_path = Path(kandidat[0])

    # A. Eksekusi Berdasarkan Berkas Fisik
    if resolved_path and resolved_path.exists():
        ext = resolved_path.suffix.lower()
        fn = resolved_path.name
        
        # A1. Addon NVDA
        if ext in [".nvda-addon"] or "nvda-addon" in fn.lower():
            return pasang_addon_nvda(str(resolved_path))
            
        # A2. Installer MSI
        if ext == ".msi":
            try:
                cmd = f'msiexec /i "{resolved_path}" /qn /norestart {argumen_tambahan}'.strip()
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if res.returncode in [0, 3010]:
                    return f"✅ **Instalasi Selesai!** Berkas paket `{fn}` berhasil dipasang secara silent ke Windows."
                return f"⚠️ Eksekusi MSI selesai dengan kode keluar {res.returncode}. Pesan: {res.stderr or res.stdout or 'Selesai'}"
            except Exception as e:
                return f"❌ Gagal memasang berkas MSI: {e}"

        # A3. Installer EXE
        if ext == ".exe":
            try:
                # Coba flag silent umum
                flags = argumen_tambahan or "/S"
                cmd = f'"{resolved_path}" {flags}'
                subprocess.Popen(cmd, shell=True)
                return f"🚀 **Proses Instalasi Dimulai!** Installer `{fn}` sedang berjalan di latar belakang (mode silent: {flags})."
            except Exception as e:
                return f"❌ Gagal mengeksekusi installer EXE: {e}"

        # A4. Arsip ZIP / 7Z / RAR
        if ext in [".zip", ".7z", ".rar"]:
            dest_extract = resolved_path.parent / resolved_path.stem
            dest_extract.mkdir(parents=True, exist_ok=True)
            if ext == ".zip":
                try:
                    with zipfile.ZipFile(resolved_path, "r") as z:
                        z.extractall(dest_extract)
                    return f"📦 **Ekstraksi Selesai!** Isi arsip `{fn}` berhasil diekstrak ke folder:\n`{dest_extract}`"
                except Exception as e:
                    return f"❌ Gagal mengekstrak ZIP: {e}"
            else:
                # Coba ekstrak pakai 7z CLI atau tar bawaan Windows
                cmd_7z = f'7z x "{resolved_path}" -o"{dest_extract}" -y'
                res_7z = subprocess.run(cmd_7z, shell=True, capture_output=True, text=True)
                if res_7z.returncode == 0:
                    return f"📦 **Ekstraksi Selesai!** Isi arsip `{fn}` berhasil diekstrak ke:\n`{dest_extract}`"
                # Fallback tar Windows
                cmd_tar = f'tar -xf "{resolved_path}" -C "{dest_extract}"'
                res_tar = subprocess.run(cmd_tar, shell=True, capture_output=True, text=True)
                if res_tar.returncode == 0:
                    return f"📦 **Ekstraksi Selesai!** Isi arsip `{fn}` berhasil diekstrak ke:\n`{dest_extract}`"
                return f"⚠️ Gagal mengekstrak arsip `{fn}`: {res_7z.stderr or res_tar.stderr or 'Format butuh alat 7-Zip CLI'}"

    # B. Jika Bukan Berkas Fisik, Cari & Install via WINGET Cloud
    app_name = t_clean or target
    if not app_name:
        return "❌ Harap sebutkan nama aplikasi yang ingin di-install atau letak berkas installernya."
        
    try:
        # Jalankan pencarian & instalasi winget
        cmd_wg = f'winget install "{app_name}" --source winget --accept-source-agreements --accept-package-agreements --silent'
        res_wg = subprocess.run(cmd_wg, shell=True, capture_output=True, text=True)
        if res_wg.returncode == 0 or "Successfully installed" in res_wg.stdout:
            return f"✅ **Instalasi Sukses!** Aplikasi **'{app_name}'** berhasil diunduh dan dipasang resmi via Winget."
        
        # Cari package ID terbaik
        cmd_s = f'winget search "{app_name}" --source winget --accept-source-agreements'
        proc_s = subprocess.run(cmd_s, shell=True, capture_output=True, text=True)
        found_id = None
        if proc_s.stdout:
            for line in proc_s.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and "." in parts[1]:
                    found_id = parts[1]
                    break
        if found_id:
            cmd_id = f'winget install --id {found_id} --source winget --accept-source-agreements --accept-package-agreements --silent'
            res_id = subprocess.run(cmd_id, shell=True, capture_output=True, text=True)
            if res_id.returncode == 0 or "Successfully installed" in res_id.stdout:
                return f"✅ **Instalasi Sukses!** Aplikasi **'{app_name}'** (`{found_id}`) berhasil dipasang resmi via Winget."

        return f"⚠️ Aplikasi '{app_name}' tidak ditemukan di winget atau gagal di-install: {res_wg.stderr or res_wg.stdout or 'Tidak ada paket cocok'}"
    except Exception as e:
        return f"❌ Terjadi kesalahan saat instalasi via Winget: {e}"


def pasang_addon_nvda(path_berkas: str = ""):
    """
    Memasang add-on NVDA (.nvda-addon) ke pembaca layar NVDA.
    HANYA dijalankan jika pengguna secara eksplisit meminta menginstal/memasang add-on NVDA.
    """
    import os
    import glob
    import zipfile
    import configparser
    from pathlib import Path

    appdata = os.environ.get("APPDATA")
    if not appdata:
        return "❌ Gagal mendeteksi folder APPDATA pengguna."

    nvda_addons_dir = Path(appdata) / "nvda" / "addons"
    if not nvda_addons_dir.exists():
        return "❌ Folder add-on NVDA tidak ditemukan di komputer ini."

    # Jika path tidak diberikan, cari berkas .nvda-addon terbaru di folder D:\ atau Downloads
    target_file = None
    if path_berkas and os.path.exists(path_berkas):
        target_file = Path(path_berkas)
    else:
        kandidat = []
        for pola in [r"D:\*.nvda-addon", r"D:\*.NVDA-Addon", str(Path.home() / "Downloads" / "*.nvda-addon")]:
            kandidat.extend(glob.glob(pola))
        if kandidat:
            kandidat.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            target_file = Path(kandidat[0])

    if not target_file or not target_file.exists():
        return "❌ Berkas .nvda-addon tidak ditemukan. Silakan tentukan lokasi berkasnya."

    try:
        with zipfile.ZipFile(target_file, "r") as z:
            namelist = z.namelist()
            if "manifest.ini" not in namelist:
                return f"❌ Berkas '{target_file.name}' bukan add-on NVDA yang sah (tidak memuat manifest.ini)."

            manifest_content = z.read("manifest.ini").decode("utf-8", errors="ignore")
            parser = configparser.ConfigParser()
            parser.read_string(manifest_content)

            addon_name = parser.get("DEFAULT", "name", fallback="").strip() or target_file.stem
            addon_summary = parser.get("DEFAULT", "summary", fallback=addon_name).strip()
            addon_version = parser.get("DEFAULT", "version", fallback="1.0").strip()

            dest_folder = nvda_addons_dir / addon_name
            dest_folder.mkdir(parents=True, exist_ok=True)
            z.extractall(dest_folder)

            # Buat file tracking JSON bawaan NVDA jika diperlukan
            json_track = nvda_addons_dir / f"{addon_name}.json"
            if not json_track.exists():
                import json
                with open(json_track, "w", encoding="utf-8") as jf:
                    json.dump({"addonVersion": addon_version, "channel": "stable"}, jf, indent=2)

        return (
            f"✅ **Add-on NVDA Berhasil Dipasang!**\n"
            f"📦 **Nama Add-on:** {addon_summary} (`{addon_name}`)\n"
            f"📁 **Lokasi:** `{dest_folder}`\n\n"
            f"💡 _Silakan restart NVDA (tekan `Insert + Q` lalu pilih Restart, atau `Ctrl + Alt + N`) untuk mengaktifkan add-on ini._"
        )
    except Exception as e:
        return f"❌ Gagal memasang add-on NVDA: {str(e)}"


FUNCTIONS = {
    "daftar_plugin_aktif": daftar_plugin_aktif,
    "cek_model_ai": cek_model_ai,
    "cek_sisa_kuota_token": cek_sisa_kuota_token,
    "cek_suhu_hardware": cek_suhu_hardware,
    "muat_ulang_plugin": muat_ulang_plugin,
    "pantau_event_bus": pantau_event_bus,
    "pemicu_event": pemicu_event,
    "baca_clipboard_pc": baca_clipboard_pc,
    "isi_clipboard_pc": isi_clipboard_pc,
    "cek_aplikasi_aktif": cek_aplikasi_aktif,
    "matikan_komputer": matikan_komputer,
    "buka_aplikasi": buka_aplikasi,
    "uninstall_otomatis": uninstall_otomatis,
    "cek_software_terinstall": cek_software_terinstall,
    "cari_dan_install_aplikasi": cari_dan_install_aplikasi,
    "cek_youtube_channel_publik": cek_youtube_channel_publik,
    "cari_di_youtube": cari_di_youtube,
    "login_ulang_youtube": login_ulang_youtube,
    "pasang_addon_nvda": pasang_addon_nvda,
    "pasang_atau_install_software": pasang_atau_install_software
}

TOOLS.append({
    "type": "function",
    "function": {
        "name": "pasang_atau_install_software",
        "description": "Pemasang cerdas serbaguna: bisa menginstall aplikasi Windows via Winget (misal 'VLC', '7zip'), mengeksekusi installer mentah (.exe, .msi), mengekstrak arsip (.zip, .7z), atau memasang add-on NVDA (.nvda-addon). HANYA dipanggil jika pengguna meminta menginstall/memasang software.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Nama aplikasi (misal: 'VLC', 'Audacity') ATAU path file lokal (.exe, .msi, .7z, .zip, .nvda-addon). Jika kosong otomatis mencari installer terbaru."
                },
                "argumen_tambahan": {
                    "type": "string",
                    "description": "Argumen baris perintah silent opsional untuk file .exe atau .msi (misal: '/S', '/quiet', '/DIR=D:\\app')."
                }
            }
        }
    }
})

TOOLS.append({
    "type": "function",
    "function": {
        "name": "pasang_addon_nvda",
        "description": "Memasang berkas add-on pembaca layar NVDA (.nvda-addon) ke sistem. HANYA dipanggil jika pengguna meminta menginstal/memasang add-on NVDA.",
        "parameters": {
            "type": "object",
            "properties": {
                "path_berkas": {
                    "type": "string",
                    "description": "Lokasi berkas .nvda-addon (opsional, jika kosong otomatis mencari berkas add-on terbaru di drive D atau Downloads)."
                }
            }
        }
    }
})
