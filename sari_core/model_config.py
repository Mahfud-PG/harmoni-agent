"""
Modul Manajemen Konfigurasi Otak & Model AI (Siti / Sari Core)
Mengelola pilihan model aktif, katalog model, dan penyimpanan persisten di disk.
"""

import os
import json
import logging
from dotenv import load_dotenv
from sari_core.paths import PROJECT_ROOT, ENV_FILE, OPENROUTER_CACHE_FILE

load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger(__name__)

CONFIG_PATH = str(PROJECT_ROOT / "konfigurasi_otak.json")

DEFAULT_CONFIG = {
    "active_id": "1",
    "active_model": "gemini-3.8-flash",
    "active_provider": "gemini",
    "display_name": "Google Gemini 3.8 Flash",
    "show_footer_tag": True,
    "fallback_model": "deepseek-flash",
    "fallback_name": "DeepSeek V4.1 Flash",
    "fallback_id": "2",
    "available_models": {
        "1": {
            "id": "gemini-3.8-flash",
            "provider": "gemini",
            "name": "Google Gemini 3.8 Flash",
            "desc": "Versi terbaru Google: Kecepatan tinggi, penalaran cerdas, dan tool calling sangat presisi"
        },
        "2": {
            "id": "deepseek-flash",
            "provider": "deepseek",
            "name": "DeepSeek V4.1 Flash",
            "desc": "Versi terbaru DeepSeek: Respons super kilat dengan penalaran cerdas dan bahasa luwes"
        },
        "3": {
            "id": "gemini-2.5-flash",
            "provider": "gemini",
            "name": "Google Gemini 2.5 Flash",
            "desc": "Versi stabil Google yang hemat kuota dan handal untuk tugas harian"
        },
        "4": {
            "id": "deepseek-chat",
            "provider": "deepseek",
            "name": "DeepSeek V3 Chat",
            "desc": "Model klasik DeepSeek V3: Bahasa santai, natural, dan seimbang"
        },
        "5": {
            "id": "gpt-4o-mini",
            "provider": "openai",
            "name": "OpenAI GPT-4o Mini",
            "desc": "Cepat, terstruktur, presisi tinggi dalam mengeksekusi alat"
        },
        "6": {
            "id": "gpt-4o",
            "provider": "openai",
            "name": "OpenAI GPT-4o (Flagship)",
            "desc": "Model multimodal andalan paling pintar dari OpenAI"
        }
    },
    "specialists": {
        "visual": "default",
        "system": "default",
        "messaging": "default",
        "scheduler": "default"
    }
}

def load_model_config() -> dict:
    """Membaca konfigurasi model dari file JSON. Jika file rusak/hilang, gunakan default."""
    if not os.path.exists(CONFIG_PATH):
        save_model_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            if "active_model" in data and "available_models" in data:
                if "specialists" not in data or not isinstance(data["specialists"], dict):
                    data["specialists"] = DEFAULT_CONFIG["specialists"].copy()
                else:
                    for k in ["visual", "system", "messaging", "scheduler"]:
                        if k not in data["specialists"]:
                            data["specialists"][k] = "default"
                if "fallback_model" not in data:
                    data["fallback_model"] = DEFAULT_CONFIG["fallback_model"]
                    data["fallback_name"] = DEFAULT_CONFIG["fallback_name"]
                    data["fallback_id"] = DEFAULT_CONFIG["fallback_id"]
                return data
            return DEFAULT_CONFIG
    except Exception as e:
        logger.error(f"Gagal membaca {CONFIG_PATH}: {e}. Memakai default.")
        return DEFAULT_CONFIG

def save_model_config(data: dict) -> bool:
    """Menyimpan konfigurasi model ke file JSON secara aman."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Gagal menyimpan konfigurasi model: {e}")
        return False

def get_active_model_info() -> dict:
    """Mengembalikan informasi model yang sedang aktif saat ini."""
    cfg = load_model_config()
    return {
        "id": cfg.get("active_id", "1"),
        "model": cfg.get("active_model", "gemini-3.8-flash"),
        "provider": cfg.get("active_provider", "gemini"),
        "name": cfg.get("display_name", "Google Gemini 3.8 Flash"),
        "show_footer": cfg.get("show_footer_tag", True)
    }

def set_active_model(target: str) -> tuple[bool, str, dict]:
    """
    Mengganti model aktif berdasarkan nomor ("1"-"6") atau kata kunci.
    Mengembalikan (sukses: bool, pesan: str, info_model: dict).
    """
    cfg = load_model_config()
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    
    target_clean = str(target).strip().lower()
    
    # 1. Cek jika input adalah nomor langsung "1", "2", dst
    if target_clean in models:
        chosen = models[target_clean]
        chosen_id = target_clean
    else:
        # 2. Cek kecocokan kata kunci fleksibel
        alias_map = {
            "gemini 3.8": "1", "gemini 3.8 flash": "1", "3.8": "1", "gemini": "1", "flash": "1",
            "deepseek flash": "2", "deepseek v4": "2", "deepseek 4": "2", "v4.1": "2", "v4": "2", "deepseek": "2",
            "gemini 2.5": "3", "gemini 2.5 flash": "3", "2.5": "3",
            "deepseek chat": "4", "deepseek v3": "4", "v3": "4",
            "gpt mini": "5", "gpt-4o-mini": "5", "4o mini": "5", "mini": "5",
            "gpt": "6", "gpt4": "6", "gpt-4o": "6", "4o": "6", "openai": "6"
        }
        
        matched_id = None
        for alias, mid in alias_map.items():
            if alias in target_clean or target_clean in alias:
                matched_id = mid
                break
                
        # Cek juga pencocokan dinamis ke nama atau ID semua model yang terdaftar
        if not matched_id:
            for mid, m in models.items():
                if target_clean in m.get("name", "").lower() or target_clean in m.get("id", "").lower():
                    matched_id = mid
                    break

        if matched_id and matched_id in models:
            chosen = models[matched_id]
            chosen_id = matched_id
        else:
            daftar = "\n".join([f"{k}. {v['name']}" for k, v in sorted(models.items(), key=lambda x: int(x[0]))])
            return False, f"Model '{target}' tidak dikenal. Silakan pilih nomor:\n{daftar}", {}

    # Update konfigurasi
    cfg["active_id"] = chosen_id
    cfg["active_model"] = chosen["id"]
    cfg["active_provider"] = chosen["provider"]
    cfg["display_name"] = chosen["name"]
    
    if save_model_config(cfg):
        return True, f"✅ Otak utama Siti berhasil dialihkan ke: **{chosen['name']}**!\n*(Cadangan otomatis tetap siaga jika terjadi limit/error)*", chosen
    else:
        return False, "❌ Gagal menyimpan konfigurasi ke file.", {}

def set_fallback_model(target: str) -> tuple[bool, str, dict]:
    """
    Mengatur model cadangan darurat (fallback priority 1) jika model utama limit/error.
    """
    cfg = load_model_config()
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    target_clean = str(target).strip().lower()
    
    chosen_id = None
    if target_clean in models:
        chosen_id = target_clean
    else:
        for mid, m in models.items():
            if target_clean in m.get("name", "").lower() or target_clean in m.get("id", "").lower():
                chosen_id = mid
                break
                
    if not chosen_id:
        return False, f"Model cadangan '{target}' tidak ditemukan di daftar menu.", {}
        
    chosen = models[chosen_id]
    cfg["fallback_model"] = chosen["id"]
    cfg["fallback_name"] = chosen["name"]
    cfg["fallback_id"] = chosen_id
    
    if save_model_config(cfg):
        return True, f"🛡️ Model cadangan darurat (Backup Utama) berhasil diatur ke: **{chosen['name']}**!\n*(Jika model utama limit atau gangguan, Siti otomatis merespons lewat model ini)*", chosen
    else:
        return False, "❌ Gagal menyimpan konfigurasi model cadangan.", {}

def _nama_asisten() -> str:
    """Nama asisten yang sedang dipakai pengguna (dari personalisasi.json).

    Dipakai supaya judul menu TIDAK memaku nama lama. Sebelumnya tertulis
    "OTAK SITI" di kode, sehingga pengguna yang sudah menamai asistennya sendiri
    tetap dibacakan nama lama oleh pembaca layar.
    """
    try:
        import json
        from sari_core.paths import DATA_ROOT
        berkas = DATA_ROOT / "personalisasi.json"
        if berkas.exists():
            with open(berkas, "r", encoding="utf-8") as f:
                nama = (json.load(f).get("bot_name") or "").strip()
            if nama:
                return nama
    except Exception:
        pass
    return "Harmoni"


def format_menu_model() -> str:
    """Menghasilkan teks daftar menu model yang rapi untuk dibaca screen reader NVDA di Telegram."""
    cfg = load_model_config()
    active_id = cfg.get("active_id", "1")
    fallback_name = cfg.get("fallback_name", "DeepSeek V4.1 Flash")
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    
    lines = [
        f"🧠 **PENGATURAN MODEL & OTAK {_nama_asisten().upper()}**",
        "Pilih otak utama yang ingin pengguna gunakan. Model pilihan Kakak selalu menjadi prioritas nomor 1.\n"
    ]
    
    for mid, m in sorted(models.items(), key=lambda x: int(x[0])):
        is_active = (mid == active_id)
        status_tag = "👉 [AKTIF] " if is_active else "   "
        lines.append(f"{status_tag}**{mid}. {m['name']}**")
        lines.append(f"   _{m['desc']}_")
        lines.append("")
        
    lines.append(f"🛡️ **Cadangan Utama (Backup Siaga):** {fallback_name}")
    lines.append("   _(Aktif otomatis secara mulus jika otak utama terkena limit atau gangguan)_\n")
    
    lines.append("📌 **Perintah Cepat:**")
    max_num = max([int(k) for k in models.keys() if k.isdigit()] or [6])
    lines.append(f"- Ganti model: `/model 1` sampai `/model {max_num}`")
    lines.append(f"- Ganti cadangan backup: `/cadangan <nomor>` (contoh: `/cadangan 2`)")
    lines.append("- Cari model online: `/cari_model <nama>` (contoh: `/cari_model claude` atau `/cari_model llama`)")
    lines.append("- Tambah model baru: `/tambah_model <id_model> [nama]`")
    lines.append("- Hapus model tambahan: `/hapus_model <nomor>`")
    lines.append("- Simpan API key baru: `/set_key <provider> <key>`")
    lines.append("- Atau chat santai: *'Siti ganti model ke DeepSeek Flash'* atau *'Siti jadikan DeepSeek Flash sebagai cadangan'*")
    
    return "\n".join(lines)

CACHE_OPENROUTER_PATH = str(OPENROUTER_CACHE_FILE)

def get_openrouter_models_cached() -> list[dict]:
    """Mengambil daftar model OpenRouter dengan sistem cache lokal (refresh otomatis setiap 24 jam)."""
    import time
    from openai import OpenAI
    
    # 1. Cek cache lokal di hard disk (kecepatan respon < 5 milidetik)
    if os.path.exists(CACHE_OPENROUTER_PATH):
        try:
            mtime = os.path.getmtime(CACHE_OPENROUTER_PATH)
            if time.time() - mtime < 86400:
                with open(CACHE_OPENROUTER_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and data:
                        return data
        except Exception: pass

    # 2. Ambil dari server jika cache belum ada atau sudah lebih dari 24 jam
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return []
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
        all_models = client.models.list()
        items = []
        for m in all_models.data:
            m_id = getattr(m, "id", "")
            m_name = getattr(m, "name", m_id)
            items.append({"id": m_id, "name": m_name})
        try:
            with open(CACHE_OPENROUTER_PATH, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=1, ensure_ascii=False)
        except Exception: pass
        return items
    except Exception as e:
        logger.error(f"Error fetching OpenRouter models: {e}")
        return []

def search_openrouter_models(keyword: str, limit: int = 5) -> list[dict]:
    """Mencari model AI online dari katalog OpenRouter secara instan (0.01 detik) menggunakan cache lokal."""
    all_models = get_openrouter_models_cached()
    if not all_models:
        return []
        
    kw = keyword.strip().lower()
    matches = []
    for m in all_models:
        m_id = m.get("id", "")
        m_name = m.get("name", m_id)
        if kw in m_id.lower() or kw in m_name.lower():
            matches.append({
                "id": m_id,
                "name": m_name,
                "desc": f"Model online via OpenRouter ({m_id})"
            })
            if len(matches) >= limit:
                break
    return matches

def search_all_provider_models(keyword: str, limit: int = 8) -> list[dict]:
    """Mencari model AI di semua provider aktif (9Router, Gemini, Groq, OpenRouter)."""
    kw = keyword.strip().lower()
    matches = []
    import urllib.request

    # 1. Cek 9Router lokal
    try:
        with urllib.request.urlopen("http://localhost:20128/v1/models", timeout=1.5) as r:
            r_data = json.loads(r.read()).get("data", [])
            for m in r_data:
                mid = m.get("id", "")
                if kw in mid.lower():
                    matches.append({
                        "id": mid,
                        "name": mid.split("/")[-1].replace("-", " ").title(),
                        "provider": "9router",
                        "desc": f"Model lokal 9Router / Antigravity ({mid})"
                    })
    except Exception:
        pass

    # 2. Cek Gemini Resmi
    gem_keys = get_provider_keys("gemini")
    if gem_keys:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gem_keys[0]}"
            with urllib.request.urlopen(url, timeout=2.0) as r:
                r_data = json.loads(r.read()).get("models", [])
                for m in r_data:
                    mid = m.get("name", "").replace("models/", "")
                    if kw in mid.lower() and "generateContent" in m.get("supportedGenerationMethods", []):
                        matches.append({
                            "id": mid,
                            "name": mid.replace("-", " ").title(),
                            "provider": "gemini",
                            "desc": f"Google Gemini Resmi ({mid})"
                        })
        except Exception:
            pass

    # 3. Cek Groq Cloud
    groq_keys = get_provider_keys("groq")
    if groq_keys:
        try:
            req = urllib.request.Request("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {groq_keys[0]}", "User-Agent": "HarmoniAgent/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as r:
                r_data = json.loads(r.read()).get("data", [])
                for m in r_data:
                    mid = m.get("id", "")
                    if kw in mid.lower() and not mid.startswith("whisper"):
                        matches.append({
                            "id": mid,
                            "name": mid.split("/")[-1].replace("-", " ").title(),
                            "provider": "groq",
                            "desc": f"Groq Cloud ({mid})"
                        })
        except Exception:
            pass

    # 4. Cek OpenRouter (Katalog global 400+ model)
    or_matches = search_openrouter_models(keyword, limit=limit)
    for om in or_matches:
        om["provider"] = "openrouter"
        matches.append(om)

    seen = set()
    unique = []
    for item in matches:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
            if len(unique) >= limit:
                break
    return unique

def verify_and_add_model(model_id: str, display_name: str = "", provider: str = "openrouter", desc: str = "") -> tuple[bool, str, dict]:
    """
    Melakukan health-check (tes ping) ke model baru sebelum mendaftarkannya secara permanen ke menu.
    Jika sukses, model otomatis mendapatkan nomor urut baru (misal 7, 8, dst).
    """
    from openai import OpenAI
    cfg = load_model_config()
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    
    # Cek apakah model_id sudah terdaftar
    for mid, m in models.items():
        if m.get("id") == model_id:
            return False, f"Model `{model_id}` sudah terdaftar di menu nomor **{mid}** ({m.get('name')}).", m
            
    # Tentukan base_url dan API Key berdasarkan provider
    provider_clean = provider.strip().lower()
    if model_id.lower().startswith(("ag/", "cx/", "9router/")) or "antigravity" in provider_clean:
        provider_clean = "9router"
    else:
        try:
            import urllib.request, json
            with urllib.request.urlopen("http://localhost:20128/v1/models", timeout=1.0) as r:
                r_data = json.loads(r.read())
                r_models = {m.get("id", "").lower() for m in r_data.get("data", [])}
                if model_id.lower() in r_models:
                    provider_clean = "9router"
        except Exception:
            pass
    
    base_url = "https://openrouter.ai/api/v1"
    api_key = os.getenv("OPENROUTER_API_KEY")
    
    if provider_clean in ["deepseek", "deepseek-api"]:
        base_url = "https://api.deepseek.com"
        api_key = os.getenv("DEEPSEEK_API_KEY")
        provider_clean = "deepseek"
    elif provider_clean in ["openai", "chatgpt"]:
        base_url = "https://api.openai.com/v1"
        api_key = os.getenv("OPENAI_API_KEY")
        provider_clean = "openai"
    elif provider_clean in ["groq"]:
        base_url = "https://api.groq.com/openai/v1"
        api_key = os.getenv("GROQ_API_KEY_1") or os.getenv("GROQ_API_KEY")
        provider_clean = "openai"
    elif provider_clean in ["9router", "ninerouter"]:
        base_url = "http://localhost:20128/v1"
        api_key = os.getenv("9ROUTER_API_KEY") or os.getenv("NINEROUTER_API_KEY") or "9router-local"
        provider_clean = "9router"
    else:
        provider_clean = "openrouter"
        
    if not api_key:
        return False, f"API key untuk provider `{provider_clean}` belum ditemukan di sistem. Silakan pasang terlebih dahulu dengan `/set_key {provider_clean.upper()} <API_KEY>`.", {}

    # === HEALTH CHECK (PING TEST) ===
    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=15.0)
        test_res = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Hai"}],
            max_tokens=15,
            timeout=15.0
        )
        if not test_res.choices:
            return False, f"Model `{model_id}` tidak mengembalikan respons teks saat diuji.", {}
    except Exception as e:
        err_msg = str(e)
        try:
            if hasattr(e, "response") and e.response:
                resp_json = e.response.json()
                if isinstance(resp_json, dict) and "error" in resp_json:
                    err_inner = resp_json["error"]
                    if isinstance(err_inner, dict) and "message" in err_inner:
                        err_msg = str(err_inner["message"])
        except Exception:
            pass
        return False, f"❌ Gagal menghubungkan ke model `{model_id}`:\n{err_msg}", {}

    # Hitung nomor ID urut berikutnya
    existing_nums = [int(k) for k in models.keys() if k.isdigit()]
    next_num = str(max(existing_nums) + 1) if existing_nums else "7"
    
    if not display_name:
        # Format nama ramah dari model_id (misal anthropic/claude-3.5-haiku -> Claude 3.5 Haiku)
        parts = model_id.split("/")
        raw_name = parts[-1] if len(parts) > 1 else parts[0]
        display_name = raw_name.replace("-", " ").replace(":", " ").title()

    if provider_clean == "openrouter" and "openrouter" not in display_name.lower():
        display_name += " (OpenRouter)"
    elif provider_clean == "9router" and "antigravity" not in display_name.lower() and "9router" not in display_name.lower():
        display_name += " (Antigravity 9Router)"
            
    if not desc:
        if provider_clean == "9router":
            desc = f"Model {display_name} via 9Router (Akun Antigravity Lokal)"
        else:
            desc = f"Model {display_name} ({model_id}) via {provider_clean.title()}"

    new_entry = {
        "id": model_id,
        "provider": provider_clean,
        "name": display_name,
        "desc": desc,
        "base_url": base_url,
        "custom": True
    }
    
    models[next_num] = new_entry
    cfg["available_models"] = models
    
    if save_model_config(cfg):
        return True, f"✅ Berhasil mendaftarkan model baru!\n\n**{next_num}. {display_name}**\n_{desc}_\n\n📌 Ketik `/model {next_num}` untuk mengaktifkan model ini kapan saja.", new_entry
    else:
        return False, "Gagal menyimpan konfigurasi model ke file JSON.", {}

def remove_custom_model(target_id: str) -> tuple[bool, str]:
    """Menghapus model tambahan dari daftar menu. Model inti 1-6 diproteksi permanen."""
    target_clean = str(target_id).strip()
    
    # Proteksi model inti
    if target_clean in ["1", "2", "3", "4", "5", "6"]:
        return False, f"❌ Model nomor {target_clean} adalah model inti bawaan sistem dan diproteksi agar tidak bisa dihapus."
        
    cfg = load_model_config()
    models = cfg.get("available_models", {})
    
    if target_clean not in models:
        return False, f"❌ Model nomor {target_clean} tidak ditemukan di daftar menu."
        
    deleted_name = models[target_clean].get("name", target_clean)
    del models[target_clean]

    # Re-indeks nomor model kustom (nomor 7 ke atas) agar urut dan tidak bolong
    core_models = {k: v for k, v in models.items() if int(k) <= 6}
    custom_models = [v for k, v in sorted(models.items(), key=lambda x: int(x[0])) if int(k) > 6]

    new_available = dict(core_models)
    curr_active_id = str(cfg.get("active_id", "1"))
    new_active_id = curr_active_id
    active_obj = models.get(curr_active_id)

    for idx, cm in enumerate(custom_models, start=7):
        new_key = str(idx)
        new_available[new_key] = cm
        if cm == active_obj:
            new_active_id = new_key

    # Jika model yang dihapus sedang aktif, kembalikan ke model 1 (Gemini 3.8 Flash)
    if curr_active_id == target_clean:
        new_active_id = "1"
        cfg["active_model"] = new_available.get("1", {}).get("id", "gemini-3.8-flash")
        cfg["active_provider"] = new_available.get("1", {}).get("provider", "gemini")
        cfg["display_name"] = new_available.get("1", {}).get("name", "Google Gemini 3.8 Flash")

    cfg["active_id"] = new_active_id
    cfg["available_models"] = new_available
    if save_model_config(cfg):
        return True, f"✅ Model nomor {target_clean} (**{deleted_name}**) berhasil dihapus. Nomor model kustom otomatis diurutkan rapi."
    else:
        return False, "❌ Gagal menyimpan perubahan ke file JSON."

PROVIDER_KEY_VARS = {
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "groq": ["GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4", "GROQ_API_KEY_5", "GROQ_API_KEY"],
    "mimo": ["XIAOMI_MIMO_API_KEY", "MIMO_API_KEY"],
    "xiaomi": ["XIAOMI_MIMO_API_KEY", "MIMO_API_KEY"],
    "cerebras": ["CEREBRAS_API_KEY"],
    "sambanova": ["SAMBANOVA_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "alibaba": ["DASHSCOPE_API_KEY", "ALIBABA_API_KEY", "QWEN_API_KEY"],
    "qwen": ["DASHSCOPE_API_KEY", "ALIBABA_API_KEY", "QWEN_API_KEY"],
    "xai": ["XAI_API_KEY", "GROK_API_KEY"],
    "grok": ["XAI_API_KEY", "GROK_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "9router": ["9ROUTER_API_KEY", "NINEROUTER_API_KEY"],
    "ninerouter": ["9ROUTER_API_KEY", "NINEROUTER_API_KEY"],
    "antigravity": ["9ROUTER_API_KEY", "NINEROUTER_API_KEY"],
}

def get_provider_keys(provider_name: str) -> list[str]:
    """Mengambil daftar seluruh kunci API untuk suatu provider.
    Mendukung format multi-kunci:
    - Koma di dalam satu nilai: 'key1, key2, key3'
    - Baris baru: 'key1\\nkey2'
    - Variabel berindeks: PROVIDER_API_KEY_1, PROVIDER_API_KEY_2, dst.
    """
    prov = (provider_name or "").lower().strip()
    var_names = PROVIDER_KEY_VARS.get(prov, [f"{prov.upper()}_API_KEY"])
    keys = []
    
    for vname in var_names:
        val = os.getenv(vname, "").strip()
        if val:
            for part in val.replace("\n", ",").split(","):
                part_clean = part.strip()
                if part_clean and part_clean not in keys:
                    keys.append(part_clean)
        base_v = vname.rstrip("_0123456789")
        for i in range(1, 10):
            sub_val = os.getenv(f"{base_v}_{i}", "").strip()
            if sub_val:
                for part in sub_val.replace("\n", ",").split(","):
                    p_c = part.strip()
                    if p_c and p_c not in keys:
                        keys.append(p_c)

    return keys

def update_env_api_key(provider_name: str, key_value: str = "") -> tuple[bool, str]:
    """Menyimpan atau memperbarui API key ke file .env dan mengaktifkannya di lingkungan proses saat ini.
    Mendukung format multi-kunci dengan pemisah koma: 'kunci1, kunci2, kunci3'."""
    raw_p = provider_name.strip()
    raw_k = key_value.strip() if key_value else ""
    
    # Jika pengguna memasukkan satu baris lengkap: "OPENROUTER_API_KEY=sk-or-..."
    if "=" in raw_p and not raw_k:
        parts = raw_p.split("=", 1)
        raw_p = parts[0].strip()
        raw_k = parts[1].strip()
        
    p_clean = raw_p.lower().replace("_api_key", "").replace("_key", "").replace("api_", "").strip()
    key_clean = raw_k.lstrip("=").strip()
    
    if not key_clean:
        return False, "❌ Nilai API Key tidak boleh kosong. Format: `/set_key <PROVIDER> <KUNCI1, KUNCI2>`"
        
    # Bersihkan multi-kunci koma/newline
    key_parts = [k.strip() for k in key_clean.replace("\n", ",").split(",") if k.strip()]
    if not key_parts:
        return False, "❌ Format kunci API tidak valid."
    key_clean = ",".join(key_parts)
        
    var_map = {
        "openrouter": "OPENROUTER_API_KEY",
        "groq": "GROQ_API_KEY_1",
        "deepseek": "DEEPSEEK_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "google": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "mimo": "XIAOMI_MIMO_API_KEY",
        "alibaba": "DASHSCOPE_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "cerebras": "CEREBRAS_API_KEY",
        "sambanova": "SAMBANOVA_API_KEY",
        "together": "TOGETHER_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "xai": "XAI_API_KEY",
        "grok": "XAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "cohere": "COHERE_API_KEY",
        "9router": "9ROUTER_API_KEY",
        "ninerouter": "9ROUTER_API_KEY"
    }
    
    env_var = var_map.get(p_clean, f"{p_clean.upper()}_API_KEY")
    os.environ[env_var] = key_clean
    
    env_path = str(ENV_FILE)
    try:
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(f"{env_var}="):
                        lines.append(f"{env_var}={key_clean}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"\n{env_var}={key_clean}\n")
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
        extra_info = ""
        if env_var == "OPENROUTER_API_KEY":
            try:
                import requests
                r = requests.get('https://openrouter.ai/api/v1/auth/key', headers={'Authorization': f'Bearer {key_clean}'}, timeout=6)
                if r.status_code == 200:
                    data = r.json().get('data', {})
                    extra_info = "\n\n🔍 **Verifikasi Otomatis:**\n- Status: ✅ **VALID & AKTIF**\n- Terhubung ke: **440+ Model AI Dunia**"
                elif r.status_code == 401:
                    extra_info = "\n\n⚠️ _[Catatan: OpenRouter mengembalikan error 401 Unauthorized. Pastikan kunci tidak salah ketik.]_"
            except Exception: pass
            
        info_jml = f" ({len(key_parts)} kunci tersimpan, rotasi otomatis aktif)" if len(key_parts) > 1 else ""
        return True, f"✅ API Key untuk **{p_clean.upper()}** (`{env_var}`) berhasil disimpan{info_jml} dan aktif saat ini juga!{extra_info}"
    except Exception as e:
        logger.error(f"Gagal memperbarui file .env: {e}")
        return False, f"❌ Gagal menyimpan API key ke .env: {e}"

# =====================================================================
# SISTEM TIM SPESIALIS TUGAS (CUSTOM DOMAIN DISPATCHER)
# =====================================================================

DOMAIN_NAMES = {
    "visual": "Visual & Layar (Mata AI)",
    "system": "Kontrol PC & Sistem",
    "messaging": "WhatsApp & Komunikasi",
    "scheduler": "Jadwal & Pengingat Otomatis"
}

DOMAIN_ALIASES = {
    "visual": "visual", "mata": "visual", "layar": "visual", "foto": "visual", "gambar": "visual", "kamera": "visual", "screenshot": "visual", "vision": "visual",
    "system": "system", "sistem": "system", "pc": "system", "komputer": "system", "windows": "system", "hardware": "system",
    "messaging": "messaging", "wa": "messaging", "whatsapp": "messaging", "pesan": "messaging", "email": "messaging", "komunikasi": "messaging", "chat": "messaging",
    "scheduler": "scheduler", "jadwal": "scheduler", "pengingat": "scheduler", "alarm": "scheduler", "tugas": "scheduler", "jadwalkan": "scheduler"
}

def get_specialists_config() -> dict:
    """Mengambil konfigurasi penugasan spesialis saat ini."""
    cfg = load_model_config()
    specialists = cfg.get("specialists", {})
    for k in ["visual", "system", "messaging", "scheduler"]:
        if k not in specialists:
            specialists[k] = "default"
    return specialists

def set_specialist(domain_input: str, target_model: str) -> tuple[bool, str]:
    """
    Menugaskan model tertentu untuk memegang divisi tugas tertentu.
    Jika target_model adalah 0 / 'default' / 'reset', divisi dikembalikan ke model utama.
    """
    domain_clean = str(domain_input).strip().lower()
    target_clean = str(target_model).strip().lower()
    
    domain_key = DOMAIN_ALIASES.get(domain_clean)
    if not domain_key:
        return False, f"❌ Divisi '{domain_input}' tidak dikenal.\nPilih salah satu: `visual`, `pc`, `wa`, atau `jadwal`."
        
    cfg = load_model_config()
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    specialists = cfg.get("specialists", DEFAULT_CONFIG["specialists"].copy())
    
    domain_name = DOMAIN_NAMES[domain_key]
    
    # 1. Reset ke default jika input 0 atau kata kunci default
    if target_clean in ["0", "default", "normal", "reset", "otomatis", "auto"]:
        specialists[domain_key] = "default"
        cfg["specialists"] = specialists
        save_model_config(cfg)
        active_name = cfg.get("display_name", "Google Gemini 3.8 Flash")
        return True, f"✅ Divisi **{domain_name}** berhasil dikembalikan ke **Default** (mengikuti Model Utama: {active_name})."
        
    # 2. Cari model yang cocok (nomor atau alias)
    if target_clean in models:
        chosen_id = target_clean
        chosen_model = models[target_clean]
    else:
        matched_id = None
        for mid, m in models.items():
            if target_clean in m.get("name", "").lower() or target_clean in m.get("id", "").lower():
                matched_id = mid
                break
        if not matched_id:
            alias_map = {
                "gemini 3.8": "1", "gemini": "1", "3.8": "1",
                "deepseek flash": "2", "deepseek": "2", "v4.1": "2", "v4": "2",
                "gemini 2.5": "3", "2.5": "3",
                "deepseek v3": "4", "v3": "4",
                "gpt mini": "5", "mini": "5",
                "gpt": "6", "gpt4": "6", "4o": "6"
            }
            for al, mid in alias_map.items():
                if al in target_clean:
                    matched_id = mid
                    break
        if matched_id and matched_id in models:
            chosen_id = matched_id
            chosen_model = models[matched_id]
        else:
            return False, f"❌ Model '{target_model}' tidak ditemukan di menu /model."

    specialists[domain_key] = chosen_id
    cfg["specialists"] = specialists
    if save_model_config(cfg):
        return True, f"✅ Berhasil menugaskan **{chosen_model['name']}** sebagai spesialis **{domain_name}**!"
    else:
        return False, "❌ Gagal menyimpan konfigurasi ke file."

def reset_all_specialists() -> tuple[bool, str]:
    """Mengembalikan seluruh divisi spesialis seragam ke Model Utama (Default)."""
    cfg = load_model_config()
    cfg["specialists"] = {
        "visual": "default",
        "system": "default",
        "messaging": "default",
        "scheduler": "default"
    }
    active_name = cfg.get("display_name", "Google Gemini 3.8 Flash")
    if save_model_config(cfg):
        return True, f"✅ Seluruh pembagian spesialis berhasil di-reset!\nSekarang semua tugas (Visual, PC, WhatsApp, Jadwal, Obrolan) kembali dikerjakan seragam oleh model utama: **{active_name}**."
    return False, "❌ Gagal menyimpan konfigurasi ke file."

def format_specialists_menu() -> str:
    """Menghasilkan teks susunan tim spesialis yang rapi untuk screen reader NVDA di Telegram."""
    cfg = load_model_config()
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    specialists = cfg.get("specialists", {})
    active_name = cfg.get("display_name", "Google Gemini 3.8 Flash")
    
    lines = [
        "🏛️ **SUSUNAN TIM SPESIALIS TUGAS SITI**",
        "Setiap divisi dapat ditangani oleh model ahli pilihan pengguna, atau dibiarkan mengikuti Model Utama (Default).\n"
    ]
    
    icons = {
        "visual": "👁️",
        "system": "🖥️",
        "messaging": "💬",
        "scheduler": "⏰"
    }
    
    for d_key, d_name in DOMAIN_NAMES.items():
        assigned_id = specialists.get(d_key, "default")
        icon = icons.get(d_key, "👉")
        if assigned_id == "default" or assigned_id not in models:
            status_str = f"👉 [Default (Ikut Model Utama: {active_name})]"
        else:
            m_obj = models[assigned_id]
            status_str = f"👉 **{assigned_id}. {m_obj.get('name')}**"
        lines.append(f"{icon} **{d_name}:**")
        lines.append(f"   {status_str}\n")
        
    lines.append(f"🌟 **Model Utama Aktif Saat Ini:** **{active_name}**\n")
    lines.append("📌 **Cara Mengatur Spesialis:**")
    lines.append("- Ketik: `/atur_spesialis <divisi> <nomor_model>`")
    lines.append("  Contoh: `/atur_spesialis visual 1` atau `/atur_spesialis pc 2` atau `/atur_spesialis wa 2`")
    lines.append("- Reset 1 divisi ke default: `/atur_spesialis <divisi> 0`")
    lines.append("- Reset semua tim kembali ke normal: `/reset_spesialis`")
    lines.append("- Atau chat santai: *'Siti, urusan visual pakai Gemini'* atau *'Siti, reset spesialis'*")
    
    return "\n".join(lines)

def resolve_model_for_task(domain: str = None, text: str = "", has_media: bool = False, platform: str = "TELEGRAM") -> dict:
    """
    Menentukan model yang harus menangani tugas berdasarkan divisi spesialis yang ditugaskan.
    Jika tidak ada spesialis yang ditugaskan (atau default), menggunakan model utama aktif.
    """
    cfg = load_model_config()
    models = cfg.get("available_models", DEFAULT_CONFIG["available_models"])
    specialists = cfg.get("specialists", {})
    
    detected_domain = domain
    if not detected_domain:
        p_clean = str(platform).strip().upper()
        if p_clean in ["WHATSAPP", "EMAIL"]:
            detected_domain = "messaging"
        elif has_media:
            detected_domain = "visual"
        else:
            t_low = text.lower()
            if any(k in t_low for k in ["baca layar", "lihat layar", "screenshot", "kamera", "foto", "gambar", "pantau layar", "lihat kamera"]):
                detected_domain = "visual"
            elif any(k in t_low for k in ["restart pc", "matikan pc", "shutdown", "reboot", "volume", "kesehatan pc", "cek suhu", "cek ram", "cek cpu", "install", "uninstall", "bersihkan sampah", "kunci pc"]):
                detected_domain = "system"
            elif any(k in t_low for k in ["kirim wa", "chat wa", "pesan wa", "voice note", "balas wa", "kirim email", "baca email", "balas email", "komentar youtube"]):
                detected_domain = "messaging"
            elif any(k in t_low for k in ["jadwalkan", "ingatkan", "jadwal tugas", "setiap jam", "pasang pengingat"]):
                detected_domain = "scheduler"
                
    if detected_domain and detected_domain in specialists:
        assigned_id = specialists[detected_domain]
        if assigned_id != "default" and assigned_id in models:
            spec_model = models[assigned_id]
            d_title = DOMAIN_NAMES.get(detected_domain, detected_domain)
            return {
                "id": assigned_id,
                "model": spec_model.get("id"),
                "provider": spec_model.get("provider"),
                "name": spec_model.get("name"),
                "show_footer": cfg.get("show_footer_tag", True),
                "is_specialist": True,
                "specialist_domain": detected_domain,
                "specialist_role": f"Spesialis {d_title}"
            }
            
    # Default: gunakan model utama aktif
    active_info = get_active_model_info()
    active_info["is_specialist"] = False
    active_info["specialist_role"] = ""
    return active_info


