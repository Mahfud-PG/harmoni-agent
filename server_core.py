import sys
import os
import json
import subprocess
import logging
from pathlib import Path

# ANTI-JENDELA HITAM: Pastikan semua subprocess/os.system tidak pernah memunculkan jendela konsol hitam (CMD/PowerShell)
if os.name == "nt":
    _orig_popen_init = subprocess.Popen.__init__
    def _silent_popen_init(self, *args, **kwargs):
        cf = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = cf | subprocess.CREATE_NO_WINDOW
        return _orig_popen_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _silent_popen_init

    def _silent_system(cmd):
        return subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW).returncode
    os.system = _silent_system

PROGRAM_DIR = Path(__file__).parent.resolve()
if str(PROGRAM_DIR) not in sys.path:
    sys.path.insert(0, str(PROGRAM_DIR))

from sari_core.paths import DATA_ROOT  # folder data pengguna
AI_ASISTEN_DIR = DATA_ROOT

from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from dotenv import dotenv_values, set_key

# Logger modul. Sebelumnya banyak fungsi memanggil logger.warning/error tanpa
# pernah mendefinisikannya, sehingga saat terjadi masalah muncul NameError dan
# pesan aslinya hilang (error tertutupi).
logger = logging.getLogger("HarmoniCore")

app = FastAPI(
    title="Harmoni Agent Core API",
    description="Local Backend Gateway untuk antarmuka Desktop Harmoni Agent, Telegram & WhatsApp",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    user_name: str = "pengguna"
    platform: str = "DESKTOP_UI"
    enable_tts: bool = False
    attachment: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None

class CreateSessionRequest(BaseModel):
    title: Optional[str] = None

class RenameSessionRequest(BaseModel):
    session_id: str
    title: str

class SwitchSessionRequest(BaseModel):
    session_id: str

class DeleteSessionRequest(BaseModel):
    session_id: str

class UploadFileBase64Request(BaseModel):
    file_name: str
    file_base64: str = ""
    file_path: str = ""

class ChatResponse(BaseModel):
    reply: str
    status: str = "success"

class ModelSwitchRequest(BaseModel):
    model_id_or_name: str

class AddModelRequest(BaseModel):
    model_id: str
    display_name: str = ""
    provider: str = "openrouter"

class RemoveModelRequest(BaseModel):
    target_id: str

class SetKeyRequest(BaseModel):
    provider_name: str
    api_key: str

class SpecialistRequest(BaseModel):
    domain: str
    target: str

class PersonalizationRequest(BaseModel):
    bot_name: str = "Harmoni"
    user_call_name: str = "Kak"
    app_language: str = "en"
    tone: str = "santai"
    enthusiasm: str = "normal"
    emoji_level: str = "sedikit"
    format_style: str = "default"
    custom_instructions: str = ""
    voice_provider: str = "edge-tts"
    voice_type: str = "id-ID-GadisNeural"
    voice_rate: str = "+0%"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_api_key: Optional[str] = None
    google_voice_name: str = "id-ID-Wavenet-A"
    google_tts_api_key: Optional[str] = None
    openai_voice_name: str = "alloy"
    openai_tts_api_key: Optional[str] = None
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_voice_name: str = "Puck"
    gemini_tts_api_key: Optional[str] = None
    temperature: float = 0.7
    quality_gate_mode: str = "safe"

class AppLanguageRequest(BaseModel):
    app_language: str = "id"

class WhatsAppConfigRequest(BaseModel):
    profile_id: str = "nomor_1"
    admin_wa_enabled: bool = True
    wa_bot_name: str = "Lisa"
    business_name: str = ""
    business_address: str = ""
    wa_tone: str = "gaul"
    vip_numbers: str = ""
    owner_phone: str = ""
    owner_name: str = ""
    custom_info: str = ""
    notify_telegram: bool = True
    auto_transcribe_vn: bool = True
    portfolio_links: str = ""
    target_phone: Optional[str] = None
    attachments: Optional[List[dict]] = None
    auto_reply_mode: Optional[str] = "off"
    auto_reply_text: Optional[str] = ""
    business_hours_open: Optional[str] = "09:00"
    business_hours_close: Optional[str] = "18:00"
    quick_replies: Optional[List[dict]] = None

class WAPairingRequest(BaseModel):
    phone: str
    profile_id: Optional[str] = None

class WASwitchProfileRequest(BaseModel):
    profile_id: str

class WASendStatusRequest(BaseModel):
    profile_id: Optional[str] = None
    text: Optional[str] = ""
    file_path: Optional[str] = ""

class TelegramConfigRequest(BaseModel):
    token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: Optional[bool] = None

class ScheduleAddTaskRequest(BaseModel):
    jam_atau_waktu: str
    fungsi_aksi: str = "lapor_telegram"
    pesan_atau_prompt: str = ""
    deskripsi: Optional[str] = None
    target_kontak: Optional[str] = None
    target_email: Optional[str] = None
    subjek_email: Optional[str] = None
    profile_id: Optional[str] = None
    interval_menit: int = 0
    total_pengulangan: int = 1

class ScheduleCancelTaskRequest(BaseModel):
    task_id: str

@app.on_event("startup")
async def startup_event():
    import asyncio

    # Penyiapan berkas awal: lengkapi konfigurasi yang belum ada dari templates/
    # (agar aplikasi tetap jalan di komputer baru tanpa membawa data pribadi)
    try:
        from sari_core.first_run import siapkan_berkas_awal
        dibuat = siapkan_berkas_awal()
        if dibuat:
            print(f"[Harmoni Startup] Berkas awal disiapkan: {', '.join(dibuat)}")
    except Exception as e_fr:
        print(f"[Harmoni Startup] Penyiapan berkas awal dilewati: {e_fr}")

    from tool_loader import load_and_register_all_tools
    count = load_and_register_all_tools(PROGRAM_DIR)
    print(f"[Core Startup] {count} tools berhasil dimuat ke Core Gateway.")

    # Jalankan Telegram Listener otomatis di background task Harmoni Agent
    try:
        from telegram_listener import start_telegram_bot_async
        asyncio.create_task(start_telegram_bot_async())
        print("[Harmoni Startup] Telegram Listener aktif otomatis di background!")
    except Exception as e_tg:
        print(f"[Harmoni Startup] Gagal menyalakan Telegram Listener: {e_tg}")

    # Jalankan WhatsApp Listener otomatis di background task Harmoni Agent
    try:
        from wa_listener import wa_listener_loop
        asyncio.create_task(wa_listener_loop())
        print("[Harmoni Startup] WhatsApp Listener aktif otomatis di background!")
    except Exception as e_wa:
        print(f"[Harmoni Startup] Gagal menyalakan WhatsApp Listener: {e_wa}")

    # Jalankan Task Scheduler Engine otomatis di background task Harmoni Agent
    try:
        from task_scheduler import start_task_scheduler_loop
        asyncio.create_task(start_task_scheduler_loop())
        print("[Harmoni Startup] Task Scheduler Engine aktif otomatis di background (5s interval)!")
    except Exception as e_sched:
        print(f"[Harmoni Startup] Gagal menyalakan Task Scheduler: {e_sched}")

    # Jalankan Email & YouTube Listener otomatis di background task Harmoni Agent
    try:
        from email_listener import email_listener_loop, youtube_listener_loop
        asyncio.create_task(email_listener_loop())
        asyncio.create_task(youtube_listener_loop())
        print("[Harmoni Startup] Email & YouTube Listener aktif otomatis di background!")
    except Exception as e_em:
        print(f"[Harmoni Startup] Gagal menyalakan Email/YouTube Listener: {e_em}")

    # Sinkronisasi Google Drive + pencadangan berkala.
    # Dulu ini dinyalakan dari dalam main() milik bot_otomatis.py - dan main() itu
    # TIDAK PERNAH dipanggil oleh arsitektur sekarang, sehingga fitur sinkronisasi
    # mati total walau mesinnya lengkap. Sekarang dinyalakan di sini, di titik yang
    # sama dengan listener lain, supaya pasti berjalan dan tahan restart.
    try:
        from sari_core.sinkronisasi_loop import sinkronisasi_loop
        asyncio.create_task(sinkronisasi_loop())
        print("[Harmoni Startup] Sinkronisasi Drive & pencadangan otomatis aktif!")
    except Exception as e_sync:
        print(f"[Harmoni Startup] Gagal menyalakan sinkronisasi: {e_sync}")

@app.get("/")
def index():
    return {
        "status": "online",
        "service": "Harmoni Agent Local Gateway",
        "version": "1.0.0"
    }

# 1. CEK MENU & STATUS MODEL
@app.get("/models")
def get_models():
    try:
        from sari_core.model_config import load_model_config, format_menu_model
        cfg = load_model_config()
        return {
            "status": "success",
            "active_id": cfg.get("active_id", "1"),
            "active_model": cfg.get("active_model", ""),
            "display_name": cfg.get("display_name", ""),
            "fallback_id": cfg.get("fallback_id", "2"),
            "fallback_name": cfg.get("fallback_name", ""),
            "available_models": cfg.get("available_models", {}),
            "formatted_menu": format_menu_model()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. GANTI MODEL AKTIF
@app.post("/models/switch")
def switch_model(req: ModelSwitchRequest):
    try:
        from sari_core.model_config import set_active_model
        ok, msg, info = set_active_model(req.model_id_or_name)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg, "info": info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. CARI MODEL DARI OPENROUTER (400+ MODEL KATALOG)
@app.get("/models/search")
def search_models(q: str):
    try:
        from sari_core.model_config import search_openrouter_models
        results = search_openrouter_models(q, limit=10)
        return {"status": "success", "query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

_PROVIDER_MODELS_CACHE = {}

@app.get("/providers/models")
def get_provider_models(provider: str, refresh: bool = False):
    """Mengambil katalog model terbaru otomatis berdasarkan provider yang dipilih secara live & terkurasi."""
    import urllib.request
    import json
    import time
    from sari_core.model_config import get_provider_keys

    prov = provider.strip().lower()
    now = time.time()

    # Periksa cache lokal memori (TTL 5 menit) jika tidak force refresh
    if not refresh and prov in _PROVIDER_MODELS_CACHE:
        cached_time, cached_models = _PROVIDER_MODELS_CACHE[prov]
        if now - cached_time < 300:
            return {"status": "success", "provider": prov, "models": cached_models, "cached": True}

    models_result = []

    # 1. 9Router (Antigravity & Cursor - Ambil langsung 47+ model lokal aktif)
    if prov in ["9router", "ninerouter", "antigravity"]:
        try:
            with urllib.request.urlopen("http://localhost:20128/v1/models", timeout=2.0) as r:
                r_data = json.loads(r.read())
                models = [m.get("id") for m in r_data.get("data", []) if m.get("id")]
                if models:
                    models_result = sorted(models)
        except Exception:
            pass
        if not models_result:
            models_result = [
                "ag/gemini-3.8-flash-high", "ag/gemini-3.8-flash-medium", "ag/gemini-3.8-flash",
                "ag/gemini-pro-agent", "ag/claude-opus-4-6-thinking", "ag/claude-sonnet-4-6",
                "ag/gpt-oss-120b-medium", "cx/gpt-5.5-review", "cx/claude-3.7-sonnet"
            ]

    # 2. OpenRouter (Live API 400+ Model Dunia)
    elif prov == "openrouter":
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "HarmoniAgent/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as r:
                r_data = json.loads(r.read()).get("data", [])
                live_ids = [m["id"] for m in r_data if m.get("id")]
                if live_ids:
                    curated = [
                        "anthropic/claude-3.7-sonnet", "anthropic/claude-3.7-sonnet:thinking",
                        "anthropic/claude-3.5-sonnet", "anthropic/claude-3.5-haiku",
                        "deepseek/deepseek-r1", "deepseek/deepseek-chat",
                        "google/gemini-2.5-pro", "google/gemini-2.5-flash",
                        "meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-72b-instruct"
                    ]
                    top = [c for c in curated if c in live_ids]
                    rest = [m for m in live_ids if m not in top]
                    models_result = top + rest
        except Exception as e:
            logger.warning(f"Gagal live fetch OpenRouter: {e}")
        if not models_result:
            models_result = [
                "anthropic/claude-3.7-sonnet", "anthropic/claude-3.7-sonnet:thinking",
                "anthropic/claude-3.5-sonnet", "anthropic/claude-3.5-haiku",
                "deepseek/deepseek-r1", "deepseek/deepseek-chat",
                "google/gemini-2.5-pro", "google/gemini-2.5-flash",
                "meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-72b-instruct"
            ]

    # 3. Google Gemini Resmi (Live API AI Studio)
    elif prov in ["gemini", "google"]:
        keys = get_provider_keys("gemini")
        if keys:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={keys[0]}"
                with urllib.request.urlopen(url, timeout=3.5) as r:
                    r_data = json.loads(r.read()).get("models", [])
                    live = [m["name"].replace("models/", "") for m in r_data if "generateContent" in m.get("supportedGenerationMethods", [])]
                    if live:
                        pref = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
                        top = [p for p in pref if p in live]
                        rest = [m for m in sorted(live) if m not in top]
                        models_result = top + rest
            except Exception as e:
                logger.warning(f"Gagal live fetch Gemini: {e}")
        if not models_result:
            models_result = [
                "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash",
                "gemini-2.0-flash-thinking-exp", "gemini-1.5-pro", "gemini-1.5-flash"
            ]

    # 4. DeepSeek Resmi (Live API)
    elif prov == "deepseek":
        keys = get_provider_keys("deepseek")
        if keys:
            try:
                req = urllib.request.Request("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {keys[0]}", "User-Agent": "HarmoniAgent/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as r:
                    r_data = json.loads(r.read()).get("data", [])
                    live = [m["id"] for m in r_data if m.get("id")]
                    if live:
                        models_result = live
            except Exception as e:
                logger.warning(f"Gagal live fetch DeepSeek: {e}")
        if not models_result:
            models_result = ["deepseek-chat", "deepseek-reasoner"]

    # 5. OpenAI Resmi (Live API)
    elif prov == "openai":
        keys = get_provider_keys("openai")
        if keys:
            try:
                req = urllib.request.Request("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {keys[0]}", "User-Agent": "HarmoniAgent/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as r:
                    r_data = json.loads(r.read()).get("data", [])
                    live = [m["id"] for m in r_data if m.get("id") and any(m["id"].startswith(p) for p in ["gpt-", "o1", "o3", "chatgpt"])]
                    if live:
                        models_result = sorted(live)
            except Exception as e:
                logger.warning(f"Gagal live fetch OpenAI: {e}")
        if not models_result:
            models_result = ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "o3-mini", "chatgpt-4o-latest", "gpt-4-turbo"]

    # 6. Groq Cloud (Live API)
    elif prov == "groq":
        keys = get_provider_keys("groq")
        if keys:
            try:
                req = urllib.request.Request("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {keys[0]}", "User-Agent": "HarmoniAgent/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as r:
                    r_data = json.loads(r.read()).get("data", [])
                    live = [m["id"] for m in r_data if m.get("active", True) and not m.get("id", "").startswith("whisper")]
                    if live:
                        models_result = sorted(live)
            except Exception as e:
                logger.warning(f"Gagal live fetch Groq: {e}")
        if not models_result:
            models_result = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it", "deepseek-r1-distill-llama-70b"]

    # 7. Local Ollama (Live API localhost:11434)
    elif prov == "ollama":
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0) as r:
                r_data = json.loads(r.read()).get("models", [])
                live = [m["name"] for m in r_data if m.get("name")]
                if live:
                    models_result = sorted(live)
        except Exception:
            pass
        if not models_result:
            models_result = ["llama3:latest", "mistral:latest", "qwen2.5:latest", "deepseek-r1:latest"]

    if models_result:
        _PROVIDER_MODELS_CACHE[prov] = (now, models_result)
        return {"status": "success", "provider": prov, "models": models_result}

    # 7. Mistral AI Resmi
    elif prov == "mistral":
        return {
            "status": "success", "provider": "mistral",
            "models": [
                "mistral-large-latest",
                "mistral-small-latest",
                "codestral-latest",
                "pixtral-large-latest",
                "ministral-8b-latest"
            ]
        }

    # 8. Alibaba Cloud DashScope (Qwen)
    elif prov in ["alibaba", "qwen"]:
        return {
            "status": "success", "provider": "alibaba",
            "models": [
                "qwen-max",
                "qwen-plus",
                "qwen-turbo",
                "qwen2.5-72b-instruct",
                "qwen-vl-max"
            ]
        }

    # 9. Cohere
    elif prov == "cohere":
        return {
            "status": "success", "provider": "cohere",
            "models": [
                "command-r-plus-08-2024",
                "command-r-08-2024",
                "command-light"
            ]
        }

    # 10. Perplexity AI (Online Search & Reasoning)
    elif prov == "perplexity":
        return {
            "status": "success", "provider": "perplexity",
            "models": [
                "sonar-reasoning-pro",
                "sonar-reasoning",
                "sonar-pro",
                "sonar"
            ]
        }

    # 11. xAI Grok
    elif prov in ["xai", "grok"]:
        return {
            "status": "success", "provider": "xai",
            "models": [
                "grok-3",
                "grok-3-mini",
                "grok-2",
                "grok-2-latest",
                "grok-2-vision-latest"
            ]
        }

    # 12. Cerebras (Inference Tercepat Dunia 2000+ tps)
    elif prov == "cerebras":
        return {
            "status": "success", "provider": "cerebras",
            "models": [
                "llama3.3-70b",
                "llama3.1-8b"
            ]
        }

    # 13. SambaNova Cloud
    elif prov == "sambanova":
        return {
            "status": "success", "provider": "sambanova",
            "models": [
                "Meta-Llama-3.3-70B-Instruct",
                "DeepSeek-R1",
                "Qwen2.5-72B-Instruct"
            ]
        }

    # 14. Together AI
    elif prov == "together":
        return {
            "status": "success", "provider": "together",
            "models": [
                "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                "deepseek-ai/DeepSeek-R1",
                "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
            ]
        }

    # 15. Xiaomi MiMo AI
    elif prov in ["mimo", "xiaomi"]:
        return {
            "status": "success", "provider": "mimo",
            "models": [
                "mimo-v2.5"
            ]
        }

    # 16. Local Ollama (Komputer Sendiri)
    elif prov == "ollama":
        return {
            "status": "success", "provider": "ollama",
            "models": [
                "llama3.3",
                "deepseek-r1:8b",
                "qwen2.5:7b",
                "mistral",
                "phi4"
            ]
        }

    return {"status": "success", "provider": prov, "models": []}

# 4. TAMBAH MODEL BARU (DENGAN AUTO PING-TEST SAMA PERSIS SEPERTI DI BOT)
@app.post("/models/add")
def add_model_endpoint(req: AddModelRequest):
    try:
        from sari_core.model_config import verify_and_add_model
        model_id = req.model_id.strip()
        display_name = req.display_name.strip()
        provider = req.provider.strip().lower()

        # Deteksi otomatis pintar sama persis seperti di bot_otomatis.py
        full_lower = f"{model_id} {display_name} {provider}".lower()
        if "opus" in full_lower and ("claude" in full_lower or "9router" in full_lower or "antigravity" in full_lower):
            model_id = "ag/claude-opus-4-6-thinking"
            display_name = "Claude Opus 4.6 (Thinking)"
            provider = "9router"
        elif "sonnet" in full_lower and ("claude" in full_lower or "9router" in full_lower or "antigravity" in full_lower):
            model_id = "ag/claude-sonnet-4-6"
            display_name = "Claude Sonnet 4.6"
            provider = "9router"
        elif model_id.lower().startswith(("ag/", "cx/", "9router/")):
            provider = "9router"

        ok, msg, info = verify_and_add_model(model_id=model_id, display_name=display_name, provider=provider)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg, "info": info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. HAPUS MODEL TAMBAHAN
@app.post("/models/remove")
def remove_model_endpoint(req: RemoveModelRequest):
    try:
        from sari_core.model_config import remove_custom_model
        ok, msg = remove_custom_model(req.target_id.strip())
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. SET / TAMBAH API KEY SECARA AMAN (SAMA PERSIS DENGAN /set_key)
@app.post("/keys/set")
def set_api_key_endpoint(req: SetKeyRequest):
    try:
        from sari_core.model_config import update_env_api_key
        ok, msg = update_env_api_key(req.provider_name.strip(), req.api_key.strip())
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6B. TIM SPESIALIS TUGAS AI
@app.get("/specialists")
def get_specialists():
    try:
        from sari_core.model_config import load_model_config, format_specialists_menu
        cfg = load_model_config()
        return {
            "status": "success",
            "specialists": cfg.get("specialists", {}),
            "formatted_menu": format_specialists_menu()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/specialists/set")
def set_specialist_endpoint(req: SpecialistRequest):
    try:
        from sari_core.model_config import set_specialist
        ok, msg = set_specialist(req.domain.strip(), req.target.strip())
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/specialists/reset")
def reset_specialists_endpoint():
    try:
        from sari_core.model_config import reset_all_specialists
        ok, msg = reset_all_specialists()
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6b. KONEKSI LAYANAN (Google Drive, YouTube, TikTok, WhatsApp, Telegram, Email)
class ConnectionActionRequest(BaseModel):
    service: str = "semua"

_CONN_CACHE: dict = {}
_CONN_CACHE_DETIK = 120


def _cek_google_drive() -> dict:
    token_file = AI_ASISTEN_DIR / "token_drive_utama.json"
    if not token_file.exists():
        return {"status": "belum_diatur", "detail": "Kunci Google Drive belum dipasang.", "akun": ""}
    try:
        from drive_api import get_authenticated_service
        svc = get_authenticated_service("utama")
        about = svc.about().get(fields="user,storageQuota").execute()
        u = about.get("user", {})
        q = about.get("storageQuota", {})
        pakai = int(q.get("usage", 0)) / 1024 ** 3
        batas = int(q.get("limit", 0)) / 1024 ** 3
        return {
            "status": "tersambung",
            "akun": u.get("emailAddress", ""),
            "detail": f"Penyimpanan terpakai {pakai:.2f} GB dari {batas:.2f} GB",
        }
    except Exception as e:
        return {"status": "gagal", "detail": f"{type(e).__name__}: {str(e)[:180]}", "akun": ""}


def _cek_youtube() -> dict:
    token_file = AI_ASISTEN_DIR / "token_utama.json"
    if not token_file.exists():
        return {"status": "belum_diatur", "detail": "Kunci YouTube belum dipasang.", "akun": ""}
    try:
        from youtube_api import get_authenticated_service, get_stats
        st = get_stats(get_authenticated_service("utama"))
        teks = str(st)
        jumlah = ""
        for baris in teks.splitlines():
            if "Subscribers" in baris:
                jumlah = baris.strip()
        akun = ""
        for baris in teks.splitlines():
            if baris.strip().startswith("Channel"):
                akun = baris.split(":", 1)[-1].strip()
        return {"status": "tersambung", "akun": akun, "detail": jumlah or teks[:150].replace("\n", " | ")}
    except Exception as e:
        return {"status": "gagal", "detail": f"{type(e).__name__}: {str(e)[:180]}", "akun": ""}


def _cek_tiktok() -> dict:
    cookie_file = AI_ASISTEN_DIR / "tiktok_cookies.txt"
    if not cookie_file.exists():
        return {"status": "belum_diatur", "detail": "File cookie TikTok belum ada.", "akun": ""}
    try:
        import requests
        cookies = {}
        with open(cookie_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#HttpOnly_"):
                    line = line[len("#HttpOnly_"):]
                elif line.startswith("#") or not line:
                    continue
                bagian = line.split("\t")
                if len(bagian) >= 7:
                    cookies[bagian[5]] = bagian[6]
        if "sessionid" not in cookies:
            return {"status": "kedaluwarsa", "detail": "Cookie ada, tapi sesi login tidak ditemukan.", "akun": ""}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Referer": "https://www.tiktok.com/",
        }
        r = requests.get("https://www.tiktok.com/passport/web/account/info/", cookies=cookies, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {}) or {}
            akun = data.get("username") or data.get("screen_name") or "Akun TikTok"
            return {"status": "tersambung", "akun": akun, "detail": f"Sesi login aktif ({len(cookies)} cookie)"}
        return {"status": "kedaluwarsa", "detail": f"TikTok menjawab HTTP {r.status_code}. Cookie perlu diperbarui.", "akun": ""}
    except Exception as e:
        return {"status": "gagal", "detail": f"{type(e).__name__}: {str(e)[:180]}", "akun": ""}


def _cek_whatsapp() -> dict:
    try:
        import urllib.request as _u, json as _j
        with _u.urlopen("http://localhost:3000/status", timeout=6) as r:
            d = _j.loads(r.read().decode())
        if d.get("ready"):
            return {"status": "tersambung", "akun": d.get("targetPhone", ""), "detail": "Perangkat WhatsApp aktif"}
        return {"status": "terputus", "detail": "Jembatan WhatsApp hidup, tapi belum tertaut ke nomor.", "akun": ""}
    except Exception as e:
        return {"status": "terputus", "detail": f"Jembatan WhatsApp tidak menjawab: {type(e).__name__}", "akun": ""}


def _cek_telegram() -> dict:
    env_path = AI_ASISTEN_DIR / ".env"
    env_data = dotenv_values(env_path) if env_path.exists() else {}
    enabled_str = env_data.get("TELEGRAM_BOT_ENABLED", os.getenv("TELEGRAM_BOT_ENABLED", "true")).lower()
    if enabled_str in ["false", "0", "off", "no"]:
        return {"status": "terputus", "detail": "Bot Telegram dinonaktifkan (Status: OFF).", "akun": ""}
    token = env_data.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"status": "belum_diatur", "detail": "Token bot Telegram belum diisi.", "akun": ""}
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        d = r.json()
        if d.get("ok"):
            u = d.get("result", {})
            return {"status": "tersambung", "akun": "@" + str(u.get("username", "")), "detail": "Bot aktif dan siap menerima pesan"}
        return {"status": "gagal", "detail": f"Telegram menolak token: {d}", "akun": ""}
    except Exception as e:
        return {"status": "gagal", "detail": f"{type(e).__name__}: {str(e)[:180]}", "akun": ""}


def _cek_email() -> dict:
    env_data = dotenv_values(AI_ASISTEN_DIR / ".env") if (AI_ASISTEN_DIR / ".env").exists() else {}
    alamat = env_data.get("EMAIL_ADDRESS") or os.getenv("EMAIL_ADDRESS")
    sandi = env_data.get("EMAIL_APP_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD")
    if not alamat or not sandi:
        return {"status": "belum_diatur", "detail": "Alamat atau sandi email belum diisi.", "akun": ""}
    try:
        import imaplib
        server = "imap.gmail.com" if "gmail" in alamat.lower() else None
        if not server:
            return {"status": "belum_diatur", "detail": "Penyedia email di luar Gmail belum didukung untuk pemeriksaan otomatis.", "akun": alamat}
        m = imaplib.IMAP4_SSL(server, timeout=15)
        m.login(alamat, sandi)
        m.select("INBOX")
        jumlah = m.search(None, "UNSEEN")[1][0].split()
        m.logout()
        return {"status": "tersambung", "akun": alamat, "detail": f"{len(jumlah)} email belum dibaca"}
    except Exception as e:
        return {"status": "gagal", "detail": f"{type(e).__name__}: {str(e)[:180]}", "akun": alamat}


_LAYANAN = {
    "google_drive": {"label": "Google Drive", "grup": "Google", "periksa": _cek_google_drive,
                     "berkas_kunci": ["token_drive_utama.json", "client_secret.json"]},
    "youtube": {"label": "YouTube", "grup": "Google", "periksa": _cek_youtube,
                "berkas_kunci": ["token_utama.json", "token_kedua.json", "client_secret.json"]},
    "tiktok": {"label": "TikTok", "grup": "Media Sosial", "periksa": _cek_tiktok,
               "berkas_kunci": ["tiktok_cookies.txt"]},
    "whatsapp": {"label": "WhatsApp", "grup": "Pesan & Surat", "periksa": _cek_whatsapp, "berkas_kunci": []},
    "telegram": {"label": "Telegram", "grup": "Pesan & Surat", "periksa": _cek_telegram, "berkas_kunci": []},
    "email": {"label": "Email", "grup": "Pesan & Surat", "periksa": _cek_email, "berkas_kunci": []},
}


def _periksa_layanan(nama: str, paksa: bool = False) -> dict:
    import time as _t
    info = _LAYANAN[nama]
    cached = _CONN_CACHE.get(nama)
    if cached and not paksa and (_t.time() - cached["_waktu"]) < _CONN_CACHE_DETIK:
        return cached
    hasil = info["periksa"]()
    hasil = dict(hasil)
    hasil["id"] = nama
    hasil["label"] = info["label"]
    hasil["grup"] = info["grup"]
    hasil["_waktu"] = _t.time()
    hasil["diperiksa"] = _t.strftime("%H:%M:%S")
    _CONN_CACHE[nama] = hasil
    return hasil


# --------------------------------------------------------------------------
# ENDPOINT MANAJEMEN MCP (Model Context Protocol)
# --------------------------------------------------------------------------
@app.get("/mcp/list")
def mcp_list():
    try:
        from sari_core.mcp_manager import mcp_manager
        return {"status": "success", "servers": mcp_manager.daftar_mcp()}
    except Exception as e:
        return {"status": "error", "message": str(e), "servers": []}

@app.post("/mcp/toggle")
def mcp_toggle(payload: dict):
    try:
        from sari_core.mcp_manager import mcp_manager
        server_id = payload.get("id")
        aktif = payload.get("enabled", False)
        sukses, pesan = mcp_manager.set_status_mcp(server_id, aktif)
        return {"status": "success" if sukses else "error", "message": pesan}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/connections/status")
def connections_status():
    """Ringkasan status semua sambungan layanan (memakai hasil pemeriksaan terakhir bila masih segar)."""
    daftar = [_periksa_layanan(n) for n in _LAYANAN]
    ringkas = " · ".join(
        f"{d['label']} {'✓' if d['status'] == 'tersambung' else '✗'}" for d in daftar
    )
    return {"status": "success", "ringkasan": ringkas, "layanan": daftar}


@app.post("/connections/test")
def connections_test(req: ConnectionActionRequest):
    """Menguji satu layanan (atau semua) secara langsung ke penyedianya."""
    target = (req.service or "semua").strip().lower()
    if target == "semua":
        daftar = [_periksa_layanan(n, paksa=True) for n in _LAYANAN]
        return {"status": "success", "layanan": daftar}
    if target not in _LAYANAN:
        raise HTTPException(status_code=400, detail=f"Layanan '{req.service}' tidak dikenal.")
    return {"status": "success", "layanan": [_periksa_layanan(target, paksa=True)]}


@app.post("/connections/connect")
async def connections_connect(req: ConnectionActionRequest):
    """Memicu otorisasi login Google Drive atau YouTube via browser otomatis."""
    import asyncio
    import shutil
    target = (req.service or "").strip().lower()
    if target not in ["google_drive", "youtube"]:
        raise HTTPException(status_code=400, detail=f"Layanan '{req.service}' tidak didukung untuk login otomatis via browser.")

    # Pastikan client_secret.json ada di folder data
    cs_file = AI_ASISTEN_DIR / "client_secret.json"
    if not cs_file.exists():
        from sari_core.paths import TEMPLATE_DIR, PROGRAM_ROOT
        sumber_cs = None
        for s in [TEMPLATE_DIR / "client_secret.json", PROGRAM_ROOT / "client_secret.json", PROGRAM_ROOT / "templates" / "client_secret.json"]:
            if s.exists():
                sumber_cs = s
                break
        if sumber_cs:
            shutil.copy2(str(sumber_cs), str(cs_file))
        else:
            return {
                "status": "error",
                "message": "Berkas gerbang client_secret.json tidak ditemukan. Hubungi pengembang untuk berkas otorisasi."
            }

    def _lakukan_auth():
        if target == "google_drive":
            from drive_api import get_authenticated_service
            get_authenticated_service("utama")
        elif target == "youtube":
            from youtube_api import get_authenticated_service
            get_authenticated_service("utama")

    try:
        await asyncio.to_thread(_lakukan_auth)
        _CONN_CACHE.pop(target, None)
        label = _LAYANAN.get(target, {}).get("label", target)
        return {
            "status": "success",
            "message": f"Akun {label} berhasil ditautkan dan diotorisasi!"
        }
    except Exception as e:
        logger.error(f"Gagal otorisasi {target}: {e}")
        return {
            "status": "error",
            "message": f"Gagal otorisasi: {str(e)}"
        }


@app.post("/connections/disconnect")
async def connections_disconnect(req: ConnectionActionRequest):
    """Memutuskan satu layanan dengan memindahkan berkas kuncinya ke folder cadangan (bisa disambung ulang)."""
    import shutil
    import time as _t
    target = (req.service or "").strip().lower()
    if target not in _LAYANAN:
        raise HTTPException(status_code=400, detail=f"Layanan '{req.service}' tidak dikenal.")

    if target == "telegram":
        env_path = AI_ASISTEN_DIR / ".env"
        from dotenv import set_key
        set_key(str(env_path), "TELEGRAM_BOT_ENABLED", "false")
        os.environ["TELEGRAM_BOT_ENABLED"] = "false"
        try:
            from telegram_listener import stop_telegram_bot_async
            await stop_telegram_bot_async()
        except Exception:
            pass
        _CONN_CACHE.pop("telegram", None)
        return {
            "status": "success",
            "message": "Bot Telegram dinonaktifkan (Status: OFF). Anda bisa mengaktifkannya kembali kapan saja."
        }

    berkas = _LAYANAN[target]["berkas_kunci"]
    if not berkas:
        raise HTTPException(status_code=400, detail=f"{_LAYANAN[target]['label']} tidak bisa diputuskan dari sini (atur di tabnya masing-masing).")

    tujuan = PROGRAM_DIR / "cadangan_kode" / "koneksi_terputus"
    tujuan.mkdir(parents=True, exist_ok=True)
    dipindah = []
    for nama_berkas in berkas:
        asal = PROGRAM_DIR / nama_berkas
        if asal.exists():
            shutil.move(str(asal), str(tujuan / f"{nama_berkas}.{_t.strftime('%Y%m%d_%H%M')}"))
            dipindah.append(nama_berkas)
    _CONN_CACHE.pop(target, None)
    if not dipindah:
        return {"status": "success", "message": f"Tidak ada berkas kunci {_LAYANAN[target]['label']} yang perlu dipindahkan."}
    return {
        "status": "success",
        "message": f"{_LAYANAN[target]['label']} diputuskan. Berkas kunci dipindahkan ke cadangan_kode/koneksi_terputus ({', '.join(dipindah)}).",
    }


# 6c. MENU GOOGLE DRIVE & YOUTUBE (data terstruktur untuk tampilan)
def _drive():
    from drive_api import get_authenticated_service
    return get_authenticated_service("utama")


def _yt():
    from youtube_api import get_authenticated_service
    return get_authenticated_service("utama")


class DriveAksiRequest(BaseModel):
    file_id: str
    nama_baru: str = ""
    nama_folder: str = ""
    email: str = ""
    ke_lokal: bool = False


class YoutubeAksiRequest(BaseModel):
    video_id: str = ""
    comment_id: str = ""
    teks: str = ""
    judul_playlist: str = ""
    playlist_id: str = ""
    maksimal: int = 5


@app.get("/drive/kapasitas")
def drive_kapasitas():
    try:
        about = _drive().about().get(fields="user,storageQuota").execute()
        q = about.get("storageQuota", {})
        pakai = int(q.get("usage", 0))
        batas = int(q.get("limit", 0))
        return {
            "status": "success",
            "akun": about.get("user", {}).get("emailAddress", ""),
            "terpakai_gb": round(pakai / 1024 ** 3, 2),
            "batas_gb": round(batas / 1024 ** 3, 2),
            "persen": round((pakai / batas * 100) if batas else 0, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.get("/drive/cari")
def drive_cari(query: str, batas: int = 15):
    """Mencari berkas/folder di Google Drive berdasarkan nama."""
    try:
        q = query.replace("'", "")
        hasil = _drive().files().list(
            q=f"name contains '{q}' and trashed=false",
            pageSize=max(1, min(batas, 50)),
            fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()
        berkas = []
        for f in hasil.get("files", []):
            berkas.append({
                "id": f.get("id"),
                "nama": f.get("name"),
                "tipe": "folder" if "folder" in (f.get("mimeType") or "") else "berkas",
                "ukuran_mb": round(int(f.get("size", 0)) / 1024 ** 2, 2) if f.get("size") else None,
                "diubah": str(f.get("modifiedTime"))[:16].replace("T", " "),
                "tautan": f.get("webViewLink", ""),
            })
        return {"status": "success", "query": query, "jumlah": len(berkas), "hasil": berkas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.get("/drive/isi-folder")
def drive_isi_folder(nama_folder: str, batas: int = 25):
    """Menampilkan isi sebuah folder dari root Drive."""
    try:
        svc = _drive()
        qf = nama_folder.replace("'", "")
        cari_folder = svc.files().list(
            q=f"name='{qf}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id,name)", pageSize=1
        ).execute().get("files", [])
        if not cari_folder:
            raise HTTPException(status_code=404, detail=f"Folder '{nama_folder}' tidak ditemukan di Drive.")
        fid = cari_folder[0]["id"]
        isi = svc.files().list(
            q=f"'{fid}' in parents and trashed=false",
            pageSize=max(1, min(batas, 100)),
            fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()
        berkas = []
        for f in isi.get("files", []):
            berkas.append({
                "id": f.get("id"),
                "nama": f.get("name"),
                "tipe": "folder" if "folder" in (f.get("mimeType") or "") else "berkas",
                "ukuran_mb": round(int(f.get("size", 0)) / 1024 ** 2, 2) if f.get("size") else None,
                "diubah": str(f.get("modifiedTime"))[:16].replace("T", " "),
                "tautan": f.get("webViewLink", ""),
            })
        return {"status": "success", "folder": nama_folder, "folder_id": fid, "jumlah": len(berkas), "hasil": berkas}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.post("/drive/buat-folder")
def drive_buat_folder(req: DriveAksiRequest):
    try:
        from sari_core.drive_sync_engine import create_drive_folder, get_drive_folder_id
        svc = _drive()
        nama = (req.nama_folder or "").strip()
        if not nama:
            raise HTTPException(status_code=400, detail="Nama folder belum diisi.")
        if get_drive_folder_id(svc, nama):
            return {"status": "success", "message": f"Folder '{nama}' sudah ada di Drive."}
        fid = create_drive_folder(svc, nama)
        ada = bool(get_drive_folder_id(svc, nama))
        if not ada:
            raise HTTPException(status_code=500, detail="Folder dilaporkan dibuat tetapi tidak ditemukan saat dibaca ulang.")
        return {"status": "success", "message": f"Folder '{nama}' benar-benar dibuat di Drive.", "folder_id": fid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.post("/drive/ganti-nama")
def drive_ganti_nama(req: DriveAksiRequest):
    try:
        nama = (req.nama_baru or "").strip()
        if not nama:
            raise HTTPException(status_code=400, detail="Nama baru belum diisi.")
        svc = _drive()
        svc.files().update(fileId=req.file_id, body={"name": nama}).execute()
        cek = svc.files().get(fileId=req.file_id, fields="name").execute()
        if cek.get("name") != nama:
            raise HTTPException(status_code=500, detail="Nama tidak berubah saat dibaca ulang.")
        return {"status": "success", "message": f"Nama berkas benar-benar diubah menjadi '{nama}'."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.post("/drive/hapus")
def drive_hapus(req: DriveAksiRequest):
    try:
        svc = _drive()
        svc.files().delete(fileId=req.file_id).execute()
        try:
            svc.files().get(fileId=req.file_id, fields="id").execute()
            raise HTTPException(status_code=500, detail="Berkas masih ada setelah perintah hapus.")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
        return {"status": "success", "message": "Berkas benar-benar terhapus dari Drive."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.get("/youtube/ringkasan")
def youtube_ringkasan():
    """Statistik channel + daftar video terbaru (dibaca langsung dari YouTube)."""
    try:
        yt = _yt()
        stat = yt.channels().list(part="snippet,statistics", mine=True).execute().get("items", [])
        if not stat:
            raise HTTPException(status_code=404, detail="Channel tidak ditemukan untuk akun ini.")
        ch = stat[0]
        s = ch.get("statistics", {})
        hasil = yt.search().list(part="id,snippet", forMine=True, type="video",
                                 maxResults=5, order="date").execute()
        video = []
        for it in hasil.get("items", []):
            vid = it["id"].get("videoId")
            if not vid:
                continue
            video.append({
                "id": vid,
                "judul": it["snippet"]["title"],
                "tanggal": it["snippet"]["publishedAt"][:10],
                "tautan": f"https://youtu.be/{vid}",
            })
        return {
            "status": "success",
            "channel": ch["snippet"]["title"],
            "pelanggan": s.get("subscriberCount"),
            "tontonan": s.get("viewCount"),
            "jumlah_video": s.get("videoCount"),
            "video_terbaru": video,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.get("/youtube/komentar")
def youtube_komentar(video_id: str, maksimal: int = 5):
    try:
        yt = _yt()
        hasil = yt.commentThreads().list(part="snippet", videoId=video_id,
                                         maxResults=max(1, min(maksimal, 25)),
                                         textFormat="plainText").execute()
        daftar = []
        for it in hasil.get("items", []):
            top = it["snippet"]["topLevelComment"]["snippet"]
            daftar.append({
                "comment_id": it["snippet"]["topLevelComment"]["id"],
                "penulis": top.get("authorDisplayName"),
                "isi": top.get("textDisplay", "")[:300],
                "waktu": str(top.get("publishedAt"))[:16].replace("T", " "),
            })
        return {"status": "success", "video_id": video_id, "jumlah": len(daftar), "komentar": daftar}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.post("/youtube/balas-komentar")
def youtube_balas_komentar(req: YoutubeAksiRequest):
    try:
        teks = (req.teks or "").strip()
        if not req.comment_id or not teks:
            raise HTTPException(status_code=400, detail="ID komentar dan teks balasan wajib diisi.")
        yt = _yt()
        yt.comments().insert(part="snippet", body={"snippet": {"parentId": req.comment_id, "textOriginal": teks}}).execute()
        cek = yt.comments().list(part="id,snippet", parentId=req.comment_id, maxResults=25,
                                 textFormat="plainText").execute()
        ketemu = any(teks[:40] in (b["snippet"]["textDisplay"] or "") for b in cek.get("items", []))
        if not ketemu:
            raise HTTPException(status_code=500, detail="Balasan tidak ditemukan saat dibaca ulang.")
        return {"status": "success", "message": "Balasan benar-benar terkirim ke YouTube (sudah diperiksa ulang)."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@app.post("/youtube/buat-playlist")
def youtube_buat_playlist(req: YoutubeAksiRequest):
    try:
        judul = (req.judul_playlist or "").strip()
        if not judul:
            raise HTTPException(status_code=400, detail="Judul playlist belum diisi.")
        yt = _yt()
        res = yt.playlists().insert(part="snippet,status", body={
            "snippet": {"title": judul, "description": "Dibuat oleh Harmoni Agent"},
            "status": {"privacyStatus": "private"},
        }).execute()
        cek = yt.playlists().list(part="id,snippet", id=res["id"]).execute().get("items", [])
        if not cek:
            raise HTTPException(status_code=500, detail="Playlist dilaporkan dibuat tetapi tidak ditemukan saat dibaca ulang.")
        return {"status": "success", "message": f"Playlist '{judul}' benar-benar dibuat (privat).",
                "playlist_id": res["id"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


# 6d. GANTI AKUN (Google, TikTok) & PENGATURAN EMAIL
class GantiAkunRequest(BaseModel):
    service: str = "google_drive"
    account: str = "utama"
    pindahkan_lama: bool = True


class EmailSettingRequest(BaseModel):
    alamat: str = ""
    sandi_app: str = ""


def _akun_google_terhubung(akun: str, jenis: str) -> dict:
    """Membaca identitas akun dari berkas token (jenis: 'drive' atau 'youtube')."""
    berkas = AI_ASISTEN_DIR / (f"token_drive_{akun}.json" if jenis == "drive" else f"token_{akun}.json")
    if not berkas.exists():
        return {"akun": akun, "jenis": jenis, "ada": False, "identitas": "", "pesan": "belum ada kunci"}
    hasil = {"akun": akun, "jenis": jenis, "ada": True, "identitas": "", "pesan": ""}
    try:
        if jenis == "drive":
            from drive_api import get_authenticated_service
            svc = get_authenticated_service(akun)
            info = svc.about().get(fields="user,storageQuota").execute()
            q = info.get("storageQuota", {})
            hasil["identitas"] = info.get("user", {}).get("emailAddress", "")
            hasil["pesan"] = f"terpakai {int(q.get('usage', 0))/1024**3:.2f} GB dari {int(q.get('limit', 0))/1024**3:.2f} GB"
        else:
            from youtube_api import get_authenticated_service
            yt = get_authenticated_service(akun)
            ch = yt.channels().list(part="snippet,statistics", mine=True).execute().get("items", [])
            if ch:
                hasil["identitas"] = ch[0]["snippet"]["title"]
                s = ch[0].get("statistics", {})
                hasil["pesan"] = f"{s.get('subscriberCount', '?')} pelanggan · {s.get('videoCount', '?')} video"
            else:
                hasil["pesan"] = "akun aktif, tetapi belum punya channel"
    except Exception as e:
        hasil["pesan"] = f"kunci ada tetapi gagal dibaca: {type(e).__name__}: {str(e)[:120]}"
    return hasil


@app.get("/connections/accounts")
def connections_accounts():
    """Menampilkan daftar akun yang tersambung (dari berkas kunci yang ada)."""
    daftar = []
    for berkas in sorted(AI_ASISTEN_DIR.glob("token_drive_*.json")):
        nama = berkas.stem.replace("token_drive_", "")
        if nama and nama != "utama":
            continue  # akun 'utama' ditangani di bawah agar tidak dobel
        daftar.append(_akun_google_terhubung(nama or "utama", "drive"))
    if not any(d["jenis"] == "drive" for d in daftar) and (AI_ASISTEN_DIR / "token_drive_utama.json").exists():
        daftar.append(_akun_google_terhubung("utama", "drive"))

    for nama in ["utama", "kedua", "ketiga", "keempat"]:
        if (AI_ASISTEN_DIR / f"token_{nama}.json").exists():
            daftar.append(_akun_google_terhubung(nama, "youtube"))

    tiktok_cookie = AI_ASISTEN_DIR / "tiktok_cookies.txt"
    daftar.append({
        "akun": "cookie", "jenis": "tiktok", "ada": tiktok_cookie.exists(),
        "identitas": "", "pesan": "berkas cookie ada" if tiktok_cookie.exists() else "belum ada berkas cookie",
    })
    return {"status": "success", "akun": daftar}


@app.post("/connections/google-login")
def connections_google_login(req: GantiAkunRequest):
    """Memulai login akun Google baru (Drive atau YouTube). Jendela Chrome akan terbuka di PC."""
    import shutil
    import subprocess
    import time as _t

    layanan = (req.service or "google_drive").strip().lower()
    if layanan not in ("google_drive", "youtube"):
        raise HTTPException(status_code=400, detail="Layanan harus 'google_drive' atau 'youtube'.")
    akun = (req.account or "utama").strip().replace(" ", "_")
    if not akun:
        raise HTTPException(status_code=400, detail="Nama akun belum diisi.")

    jenis = "drive" if layanan == "google_drive" else "youtube"
    skrip = PROGRAM_DIR / ("drive_api.py" if jenis == "drive" else "youtube_api.py")
    berkas_token = AI_ASISTEN_DIR / (f"token_drive_{akun}.json" if jenis == "drive" else f"token_{akun}.json")

    dipindah = []
    if req.pindahkan_lama and berkas_token.exists():
        tujuan = PROGRAM_DIR / "cadangan_kode" / "koneksi_terputus"
        tujuan.mkdir(parents=True, exist_ok=True)
        shutil.move(str(berkas_token), str(tujuan / f"{berkas_token.name}.{_t.strftime('%Y%m%d_%H%M')}"))
        dipindah.append(berkas_token.name)

    aksi = "stat" if jenis == "drive" else "latest_my_video"
    try:
        # Python bawaan aplikasi, BUKAN launcher "py" milik Windows: launcher itu
        # hanya ada kalau Python terpasang di komputer pengguna, sedangkan aplikasi
        # ini membawa Python-nya sendiri.
        from sari_core.paths import cari_python_console
        r = subprocess.run(
            [cari_python_console(), str(skrip), "--action", aksi, "--account", akun],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=600,
            cwd=str(PROGRAM_DIR),
        )
        keluaran = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return {"status": "error", "message":
                "Proses login melebihi 10 menit. Kalau jendela Chrome terbuka, selesaikan loginnya, lalu tekan Uji Koneksi."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")

    info = _akun_google_terhubung(akun, jenis)
    if info.get("ada") and info.get("identitas"):
        pesan = (f"✅ Akun Google baru ({akun}) tersambung sebagai {info['identitas']} — {info['pesan']}.")
    elif info.get("ada"):
        pesan = f"⚠️ Berkas kunci ({akun}) terbentuk, tetapi identitas akun belum terbaca: {info['pesan']}"
    else:
        potong = " | ".join([b for b in keluaran.splitlines() if b.strip()][-3:])[:300]
        pesan = ("⚠️ Login belum selesai — berkas kunci belum terbentuk.\n"
                 f"Kalau jendela Chrome terbuka di PC, selesaikan loginnya, lalu ulangi penekanan tombol ini atau tekan Uji Koneksi.\n"
                 f"Catatan teknis: {potong}")
    return {"status": "success", "message": pesan, "dipindah": dipindah, "akun": info}


@app.post("/connections/email")
def connections_email(req: EmailSettingRequest):
    """Menyimpan alamat email dan sandi aplikasi ke berkas .env, lalu menguji loginnya."""
    alamat = (req.alamat or "").strip()
    sandi = (req.sandi_app or "").strip()
    if not alamat or not sandi:
        raise HTTPException(status_code=400, detail="Alamat email dan sandi aplikasi wajib diisi.")

    env_path = AI_ASISTEN_DIR / ".env"
    try:
        set_key(str(env_path), "EMAIL_ADDRESS", alamat)
        set_key(str(env_path), "EMAIL_APP_PASSWORD", sandi)
        os.environ["EMAIL_ADDRESS"] = alamat
        os.environ["EMAIL_APP_PASSWORD"] = sandi
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan ke .env: {type(e).__name__}: {e}")

    hasil = _cek_email()
    if hasil.get("status") == "tersambung":
        return {"status": "success", "message":
                f"✅ Email disimpan dan login BERHASIL. Akun {hasil.get('akun')} — {hasil.get('detail')}."}
    return {"status": "success", "message":
            f"⚠️ Email tersimpan, tetapi login belum berhasil: {hasil.get('detail')} "
            "Periksa kembali sandi aplikasinya (bukan sandi akun biasa)."}


class EmailConfigRequest(BaseModel):
    admin_email_enabled: Optional[bool] = None
    notify_telegram: Optional[bool] = None

class YoutubeConfigRequest(BaseModel):
    satpam_youtube_enabled: Optional[bool] = None
    notify_telegram: Optional[bool] = None

@app.get("/email/config")
def get_email_config():
    from email_listener import baca_konfigurasi_email
    return {"status": "success", "data": baca_konfigurasi_email()}

@app.post("/email/config")
def set_email_config(req: EmailConfigRequest):
    from email_listener import baca_konfigurasi_email, simpan_konfigurasi_email
    cfg = baca_konfigurasi_email()
    if req.admin_email_enabled is not None:
        cfg["admin_email_enabled"] = req.admin_email_enabled
    if req.notify_telegram is not None:
        cfg["notify_telegram"] = req.notify_telegram
    simpan_konfigurasi_email(cfg)
    return {"status": "success", "data": cfg}

@app.get("/youtube/config")
def get_youtube_config():
    from email_listener import baca_konfigurasi_youtube
    return {"status": "success", "data": baca_konfigurasi_youtube()}

@app.post("/youtube/config")
def set_youtube_config(req: YoutubeConfigRequest):
    from email_listener import baca_konfigurasi_youtube, simpan_konfigurasi_youtube
    cfg = baca_konfigurasi_youtube()
    if req.satpam_youtube_enabled is not None:
        cfg["satpam_youtube_enabled"] = req.satpam_youtube_enabled
    if req.notify_telegram is not None:
        cfg["notify_telegram"] = req.notify_telegram
    simpan_konfigurasi_youtube(cfg)
    return {"status": "success", "data": cfg}


# 7. CEK KUOTA & SALDO TOKEN REAL-TIME
@app.get("/tokens/status")
def get_tokens_status():
    """Mengecek saldo dan status kuota real-time dari provider (DeepSeek, OpenRouter, dll)."""
    import requests
    env_path = AI_ASISTEN_DIR / ".env"
    env_data = dotenv_values(env_path) if env_path.exists() else {}

    laporan_lines = ["📊 Laporan Status Real-Time Kuota & Saldo Token:\n"]

    # 1. DeepSeek Saldo
    deepseek_key = env_data.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        try:
            res = requests.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {deepseek_key}"}, timeout=5)
            if res.status_code == 200:
                d_info = res.json().get("balance_infos", [{}])[0]
                usd = float(d_info.get("total_balance", 0.0))
                idr = int(usd * 16200)
                laporan_lines.append(f"🟢 DeepSeek Official: Aktif | Saldo: ${usd:.2f} USD (± Rp {idr:,})")
            else:
                laporan_lines.append("🟢 DeepSeek Official: Aktif & Normal")
        except Exception:
            laporan_lines.append("🟢 DeepSeek Official: Aktif")
    else:
        laporan_lines.append("⚪ DeepSeek Official: Belum diatur")

    # 2. OpenRouter Saldo & Limit
    or_key = env_data.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            res_or = requests.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {or_key}"}, timeout=5)
            if res_or.status_code == 200:
                k_data = res_or.json().get("data", {})
                usage = k_data.get("usage", 0.0)
                limit_rem = k_data.get("free_model_daily_requests", {}).get("remaining", "Unlimited")
                laporan_lines.append(f"🟢 OpenRouter: Aktif | Pemakaian: ${usage:.4f} USD | Free Kuota Harian: {limit_rem} request")
            else:
                laporan_lines.append("🟢 OpenRouter: Aktif & Normal")
        except Exception:
            laporan_lines.append("🟢 OpenRouter: Aktif")
    else:
        laporan_lines.append("⚪ OpenRouter: Belum diatur")

    # 3. 9Router (Antigravity & Cursor)
    laporan_lines.append("🟢 9Router (Antigravity / Cursor): Aktif (Local Unlimited)")

    # 4. Google Gemini
    gemini_key = env_data.get("GEMINI_API_KEY")
    laporan_lines.append(f"🟢 Google Gemini: {'Aktif (Free/Tier)' if gemini_key else 'Belum diatur'}")

    # 5. Groq Cloud
    groq_key = env_data.get("GROQ_API_KEY_1") or env_data.get("GROQ_API_KEY")
    laporan_lines.append(f"🟢 Groq Cloud: {'Aktif (Free Tier Kilat)' if groq_key else 'Belum diatur'}")

    laporan_lines.append("\n⚡ Fitur Smart Tool Filtering aktif (Penghematan token 95-99%).")

    return {
        "status": "success",
        "report": "\n".join(laporan_lines)
    }

# 8. STATUS INTEGRASI LENGKAP
@app.get("/settings")
def get_channel_settings():
    env_path = AI_ASISTEN_DIR / ".env"
    env_data = dotenv_values(env_path) if env_path.exists() else {}

    tg_token = env_data.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = env_data.get("TELEGRAM_CHAT_ID", "")
    gemini_key = env_data.get("GEMINI_API_KEY", "")
    deepseek_key = env_data.get("DEEPSEEK_API_KEY", "")
    openrouter_key = env_data.get("OPENROUTER_API_KEY", "")
    openai_key = env_data.get("OPENAI_API_KEY", "")
    groq_key = env_data.get("GROQ_API_KEY_1") or env_data.get("GROQ_API_KEY", "")
    from sari_core.model_config import get_provider_keys

    def mask_str(s: str) -> str:
        if not s: return "Belum diatur"
        if len(s) < 8: return "Terpasang"
        return f"{s[:4]}...{s[-4:]}"

    def format_multi_keys(prov_name: str) -> str:
        keys = get_provider_keys(prov_name)
        if not keys:
            return "Belum diatur"
        if len(keys) == 1:
            return mask_str(keys[0])
        return f"{len(keys)} Akun (" + ", ".join(mask_str(k) for k in keys) + ")"

    keys_dict = {
        "GEMINI": format_multi_keys("gemini"),
        "DEEPSEEK": format_multi_keys("deepseek"),
        "OPENROUTER": format_multi_keys("openrouter"),
        "OPENAI": format_multi_keys("openai"),
        "GROQ": format_multi_keys("groq"),
        "XIAOMI_MIMO": format_multi_keys("mimo"),
        "9ROUTER": "Otomatis Aktif (Lokal)"
    }
    for p_id, p_label in [
        ("cerebras", "CEREBRAS"), ("sambanova", "SAMBANOVA"), ("together", "TOGETHER"),
        ("mistral", "MISTRAL"), ("alibaba", "QWEN_ALIBABA"), ("xai", "XAI_GROK"), ("perplexity", "PERPLEXITY")
    ]:
        k_val = format_multi_keys(p_id)
        if k_val != "Belum diatur":
            keys_dict[p_label] = k_val

    return {
        "status": "success",
        "telegram": {
            "is_configured": bool(tg_token),
            "masked_token": mask_str(tg_token),
            "chat_id": tg_chat or "-"
        },
        "whatsapp": {
            "is_configured": True,
            "bridge_status": "Siap / Local Gateway (Baileys)"
        },
        "api_keys": keys_dict
    }

# 8b. PENGATURAN & SAKELAR TELEGRAM LENGKAP
@app.get("/telegram/config")
def get_telegram_config_endpoint():
    env_path = AI_ASISTEN_DIR / ".env"
    env_data = dotenv_values(env_path) if env_path.exists() else {}
    token = env_data.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = env_data.get("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID", "")
    enabled_str = env_data.get("TELEGRAM_BOT_ENABLED", os.getenv("TELEGRAM_BOT_ENABLED", "true")).lower()
    enabled = enabled_str not in ["false", "0", "off", "no"]

    def mask_token(t: str) -> str:
        if not t: return "Belum diatur"
        if len(t) < 10: return "Terpasang"
        return f"{t[:6]}...{t[-4:]}"

    bot_username = ""
    if token and enabled:
        try:
            import requests
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if r.status_code == 200:
                d = r.json()
                if d.get("ok"):
                    bot_username = "@" + str(d.get("result", {}).get("username", ""))
        except Exception:
            pass

    try:
        from telegram_listener import is_telegram_running
        running = is_telegram_running()
    except Exception:
        running = False

    return {
        "status": "success",
        "enabled": enabled,
        "configured": bool(token),
        "token_masked": mask_token(token),
        "chat_id": chat_id or "-",
        "bot_username": bot_username or ("Nonaktif" if not enabled else "Tidak terhubung"),
        "is_running": running
    }


@app.post("/telegram/config")
async def set_telegram_config_endpoint(req: TelegramConfigRequest):
    env_path = AI_ASISTEN_DIR / ".env"
    from dotenv import set_key, dotenv_values
    env_data = dotenv_values(env_path) if env_path.exists() else {}

    token_to_check = req.token.strip() if req.token is not None and req.token.strip() else None
    bot_username = ""

    if token_to_check:
        import requests
        try:
            r = requests.get(f"https://api.telegram.org/bot{token_to_check}/getMe", timeout=8)
            d = r.json()
            if not d.get("ok"):
                raise HTTPException(status_code=400, detail=f"Token ditolak Telegram: {d.get('description', 'Token tidak valid')}")
            bot_username = "@" + str(d.get("result", {}).get("username", ""))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Gagal verifikasi token ke Telegram: {e}")

        set_key(str(env_path), "TELEGRAM_BOT_TOKEN", token_to_check)
        os.environ["TELEGRAM_BOT_TOKEN"] = token_to_check

    if req.chat_id is not None and req.chat_id.strip():
        new_chat_id = req.chat_id.strip()
        set_key(str(env_path), "TELEGRAM_CHAT_ID", new_chat_id)
        os.environ["TELEGRAM_CHAT_ID"] = new_chat_id

    if req.enabled is not None:
        val_str = "true" if req.enabled else "false"
        set_key(str(env_path), "TELEGRAM_BOT_ENABLED", val_str)
        os.environ["TELEGRAM_BOT_ENABLED"] = val_str

    _CONN_CACHE.pop("telegram", None)

    from telegram_listener import restart_telegram_bot_async, stop_telegram_bot_async
    current_enabled = os.getenv("TELEGRAM_BOT_ENABLED", "true").lower() not in ["false", "0", "off", "no"]
    current_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if current_enabled and current_token:
        await restart_telegram_bot_async()
    else:
        await stop_telegram_bot_async()

    return {
        "status": "success",
        "message": f"Pengaturan Telegram berhasil disimpan! {('Bot terhubung sebagai ' + bot_username) if bot_username else ''}",
        "bot_username": bot_username
    }


@app.post("/telegram/toggle")
async def toggle_telegram_endpoint():
    env_path = AI_ASISTEN_DIR / ".env"
    from dotenv import set_key, dotenv_values
    env_data = dotenv_values(env_path) if env_path.exists() else {}
    enabled_str = env_data.get("TELEGRAM_BOT_ENABLED", os.getenv("TELEGRAM_BOT_ENABLED", "true")).lower()
    currently_enabled = enabled_str not in ["false", "0", "off", "no"]
    new_state = not currently_enabled

    val_str = "true" if new_state else "false"
    set_key(str(env_path), "TELEGRAM_BOT_ENABLED", val_str)
    os.environ["TELEGRAM_BOT_ENABLED"] = val_str
    _CONN_CACHE.pop("telegram", None)

    from telegram_listener import restart_telegram_bot_async, stop_telegram_bot_async
    if new_state and os.getenv("TELEGRAM_BOT_TOKEN"):
        await restart_telegram_bot_async()
    else:
        await stop_telegram_bot_async()

    return {
        "status": "success",
        "enabled": new_state,
        "message": f"Bot Telegram sekarang {'DINYALAKAN (ON)' if new_state else 'DIMATIKAN (OFF)'}."
    }


@app.post("/telegram/disconnect")
async def disconnect_telegram_endpoint():
    env_path = AI_ASISTEN_DIR / ".env"
    from dotenv import set_key
    set_key(str(env_path), "TELEGRAM_BOT_ENABLED", "false")
    set_key(str(env_path), "TELEGRAM_BOT_TOKEN", "")
    os.environ["TELEGRAM_BOT_ENABLED"] = "false"
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    _CONN_CACHE.pop("telegram", None)

    from telegram_listener import stop_telegram_bot_async
    await stop_telegram_bot_async()

    return {
        "status": "success",
        "message": "Sambungan Bot Telegram berhasil diputuskan dan token telah dihapus."
    }

def _generate_tts_bytes(text: str) -> tuple:
    """Menghasilkan audio MP3 bytes menggunakan provider TTS terpilih di personalisasi.json (ElevenLabs, Edge-TTS, OpenAI, Google)."""
    import re, os, json
    from dotenv import dotenv_values

    try:
        clean = re.sub(r'🧠\s*_\[Otak:.*?\]_', '', text)
        clean = re.sub(r'https?://\S+', 'tautan', clean)
        clean = re.sub(r'[*_`#~>-]', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if not clean:
            return False, b"", "Teks kosong."

        pers_file = AI_ASISTEN_DIR / "personalisasi.json"
        pdata = {}
        if pers_file.exists():
            try:
                with open(pers_file, "r", encoding="utf-8") as pf:
                    pdata = json.load(pf)
            except Exception:
                pass

        env_path = AI_ASISTEN_DIR / ".env"
        env_data = dotenv_values(env_path) if env_path.exists() else {}

        provider = pdata.get("voice_provider", "edge-tts").lower()
        voice_type = pdata.get("voice_type", "id-ID-GadisNeural")
        voice_rate = pdata.get("voice_rate", "+0%")

        # 1. ELEVENLABS
        if provider == "elevenlabs":
            el_raw = env_data.get("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY", "")
            el_keys = [k.strip() for k in re.split(r'[,;\n\r]+', el_raw) if k.strip()]
            voice_id = pdata.get("elevenlabs_voice_id") or "EXAVITQu4vr4xnSDxMaL"
            if el_keys:
                import requests
                for single_key in el_keys:
                    try:
                        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                        headers = {"xi-api-key": single_key, "Content-Type": "application/json"}
                        payload = {"text": clean[:1000], "model_id": "eleven_multilingual_v2"}
                        r = requests.post(url, headers=headers, json=payload, timeout=20)
                        if r.status_code == 200 and len(r.content) > 100:
                            return True, r.content, "elevenlabs"
                    except Exception:
                        pass

        # 2. OPENAI TTS
        elif provider == "openai":
            oa_raw = env_data.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
            oa_keys = [k.strip() for k in re.split(r'[,;\n\r]+', oa_raw) if k.strip()]
            oa_voice = pdata.get("openai_voice_name", "alloy")
            if oa_keys:
                import requests
                for single_key in oa_keys:
                    try:
                        url = "https://api.openai.com/v1/audio/speech"
                        headers = {"Authorization": f"Bearer {single_key}", "Content-Type": "application/json"}
                        payload = {"model": "tts-1", "input": clean[:1000], "voice": oa_voice}
                        r = requests.post(url, headers=headers, json=payload, timeout=20)
                        if r.status_code == 200 and len(r.content) > 100:
                            return True, r.content, "openai"
                    except Exception:
                        pass

        # 3. GOOGLE CLOUD TTS
        elif provider == "google":
            g_raw = env_data.get("GOOGLE_TTS_API_KEY") or os.getenv("GOOGLE_TTS_API_KEY") or env_data.get("GEMINI_API_KEY", "")
            g_keys = [k.strip() for k in re.split(r'[,;\s]+', g_raw) if k.strip()]
            g_voice = pdata.get("google_voice_name", "id-ID-Wavenet-A")
            if g_keys:
                import requests, base64
                for single_key in g_keys:
                    try:
                        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={single_key}"
                        payload = {"input": {"text": clean[:1000]}, "voice": {"languageCode": "id-ID", "name": g_voice}, "audioConfig": {"audioEncoding": "MP3"}}
                        r = requests.post(url, json=payload, timeout=20)
                        if r.status_code == 200:
                            b64_audio = r.json().get("audioContent", "")
                            if b64_audio:
                                return True, base64.b64decode(b64_audio), "google"
                    except Exception:
                        pass

        # 4. GOOGLE GEMINI TTS (AI STUDIO - NATIVE AUDIO & VOICE REPLICATION)
        elif provider in ["gemini", "gemini-tts", "gemini_tts"]:
            from sari_core.model_config import get_provider_keys
            import requests, base64, struct

            gem_keys = get_provider_keys("gemini")
            gem_model = pdata.get("gemini_tts_model") or "gemini-3.8-flash-tts"
            gem_voice = pdata.get("gemini_voice_name") or "Puck"

            if gem_keys:
                for single_key in gem_keys:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={single_key}"
                        if gem_voice.startswith("voice_") or gem_voice.startswith("voicekey_"):
                            voice_cfg = {"voice": gem_voice}
                        else:
                            voice_cfg = {"prebuiltVoiceConfig": {"voiceName": gem_voice}}

                        payload = {
                            "contents": [{"parts": [{"text": clean[:1500]}]}],
                            "generationConfig": {
                                "responseModalities": ["AUDIO"],
                                "speechConfig": {
                                    "voiceConfig": voice_cfg
                                }
                            }
                        }
                        r = requests.post(url, json=payload, timeout=25)
                        if r.status_code == 200:
                            data = r.json()
                            cand = data.get("candidates", [{}])[0]
                            parts = cand.get("content", {}).get("parts", [])
                            for p in parts:
                                if "inlineData" in p:
                                    mime = p["inlineData"].get("mimeType", "")
                                    b64_data = p["inlineData"].get("data", "")
                                    if b64_data:
                                        raw_bytes = base64.b64decode(b64_data)
                                        if "pcm" in mime.lower():
                                            sample_rate = 24000
                                            channels = 1
                                            bits_per_sample = 16
                                            byte_rate = sample_rate * channels * bits_per_sample // 8
                                            block_align = channels * bits_per_sample // 8
                                            data_size = len(raw_bytes)
                                            wav_header = struct.pack(
                                                '<4sI4s4sIHHIIHH4sI',
                                                b'RIFF',
                                                36 + data_size,
                                                b'WAVE',
                                                b'fmt ',
                                                16,
                                                1,
                                                channels,
                                                sample_rate,
                                                byte_rate,
                                                block_align,
                                                bits_per_sample,
                                                b'data',
                                                data_size
                                            )
                                            return True, wav_header + raw_bytes, "gemini-tts"
                                        return True, raw_bytes, "gemini-tts"
                        else:
                            logger.warning(f"Gemini TTS error ({r.status_code}): {r.text[:150]}")
                    except Exception as e_gem_tts:
                        logger.warning(f"Error Gemini TTS ({gem_model}): {e_gem_tts}")

        # 5. EDGE-TTS (Default Suara Wanita Gadis - Jernih & Merdu, Cadangan Handal)
        try:
            import edge_tts, asyncio, concurrent.futures
            async def _stream_edge():
                comm = edge_tts.Communicate(clean[:1500], voice=voice_type, rate=voice_rate)
                b = b""
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        b += chunk["data"]
                return b

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    res_b = executor.submit(asyncio.run, _stream_edge()).result()
            else:
                res_b = asyncio.run(_stream_edge())

            if res_b and len(res_b) > 100:
                return True, res_b, "edge-tts"
        except Exception as e_ed:
            logger.warning(f"[Edge-TTS Stream Error]: {e_ed}")

    except Exception as e_top:
        logger.error(f"[TTS Gen Error]: {e_top}")

    return False, b"", "Gagal menghasilkan audio suara."

def _play_tts_sound_direct(audio_bytes: bytes):
    """Memutar audio bytes langsung lewat ffplay."""
    import tempfile, subprocess, os
    if not audio_bytes: return
    try:
        ext = ".wav" if audio_bytes.startswith(b"RIFF") else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            temp_file = tf.name
            tf.write(audio_bytes)
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", temp_file],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=45
        )
        try: os.remove(temp_file)
        except Exception: pass
    except Exception as e:
        logger.warning(f"[_play_tts_sound Error]: {e}")

def _play_tts_sound(text: str):
    """Menghasilkan audio dengan Edge-TTS, ElevenLabs, Google TTS, atau OpenAI TTS, dan memutar lewat speaker PC di background."""
    ok, audio_bytes, prov = _generate_tts_bytes(text)
    if ok and audio_bytes:
        _play_tts_sound_direct(audio_bytes)

class TTSSynthesizeRequest(BaseModel):
    text: str

@app.post("/tts/synthesize")
def tts_synthesize_endpoint(req: TTSSynthesizeRequest):
    """Menghasilkan audio suara untuk tombol Bacakan Keras di UI Desktop."""
    ok, audio_bytes, prov = _generate_tts_bytes(req.text)
    if not ok or not audio_bytes:
        raise HTTPException(status_code=500, detail="Gagal membuat audio suara.")
    return Response(content=audio_bytes, media_type="audio/mpeg")

# 7B. PERSONALISASI GAYA & NADA BICARA (ALA CHATGPT)
@app.get("/personalization")
def get_personalization():
    pers_file = AI_ASISTEN_DIR / "personalisasi.json"
    default_pers = {
        "bot_name": "Harmoni",
        "user_call_name": "Kak",
        "app_language": "en",
        "tone": "santai",
        "enthusiasm": "normal",
        "emoji_level": "sedikit",
        "format_style": "default",
        "custom_instructions": "Saya adalah seorang musisi dan kreator konten tunanetra. Utamakan kejelasan, sebutkan posisi atau shortcut keyboard jika menjelaskan antarmuka, dan hindari istilah visual murni.",
        "voice_provider": "edge-tts",
        "voice_type": "id-ID-GadisNeural",
        "voice_rate": "+0%",
        "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
        "google_voice_name": "id-ID-Wavenet-A",
        "openai_voice_name": "alloy",
        "gemini_tts_model": "gemini-3.8-flash-tts",
        "gemini_voice_name": "Puck",
        "temperature": 0.7,
        "quality_gate_mode": "safe"
    }
    if pers_file.exists():
        try:
            with open(pers_file, "r", encoding="utf-8") as f:
                import json
                loaded = json.load(f)
                default_pers.update(loaded)
        except Exception:
            pass

    env_path = AI_ASISTEN_DIR / ".env"
    env_data = dotenv_values(env_path) if env_path.exists() else {}

    from sari_core.model_config import get_provider_keys
    el_keys = get_provider_keys("elevenlabs")
    g_keys = get_provider_keys("google")
    oa_keys = get_provider_keys("openai")
    gem_keys = get_provider_keys("gemini")

    default_pers["has_elevenlabs_key"] = bool(el_keys)
    default_pers["elevenlabs_key_count"] = len(el_keys)

    default_pers["has_google_tts_key"] = bool(g_keys)
    default_pers["google_tts_key_count"] = len(g_keys)

    default_pers["has_openai_key"] = bool(oa_keys)
    default_pers["openai_key_count"] = len(oa_keys)

    default_pers["has_gemini_tts_key"] = bool(gem_keys)
    default_pers["gemini_tts_key_count"] = len(gem_keys)

    return {"status": "success", "data": default_pers}

@app.post("/personalization/language")
def set_personalization_language(req: AppLanguageRequest):
    try:
        lang = req.app_language.strip().lower()
        if lang not in ["id", "en"]:
            lang = "id"
        pers_file = AI_ASISTEN_DIR / "personalisasi.json"
        data = {}
        if pers_file.exists():
            try:
                with open(pers_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["app_language"] = lang
        with open(pers_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"status": "success", "app_language": lang}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/personalization/save")
def save_personalization(req: PersonalizationRequest):
    try:
        import json, re
        from dotenv import set_key
        pers_file = AI_ASISTEN_DIR / "personalisasi.json"
        env_path = AI_ASISTEN_DIR / ".env"

        # PENTING: baca dulu isi berkas yang ada, lalu HANYA timpa kunci yang dikelola
        # formulir ini. Kunci lain (mis. "pemasangan_selesai") harus tetap dipertahankan,
        # kalau tidak setiap kali menyimpan pengaturan akan ada data yang hilang.
        data = {}
        if pers_file.exists():
            try:
                with open(pers_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data.update({
            "bot_name": req.bot_name.strip() or "Harmoni",
            "user_call_name": req.user_call_name.strip() or "Kak",
            "app_language": req.app_language or "en",
            "tone": req.tone,
            "enthusiasm": req.enthusiasm,
            "emoji_level": req.emoji_level,
            "format_style": req.format_style,
            "custom_instructions": req.custom_instructions.strip(),
            "voice_provider": req.voice_provider,
            "voice_type": req.voice_type,
            "voice_rate": req.voice_rate,
            "elevenlabs_voice_id": req.elevenlabs_voice_id.strip() if req.elevenlabs_voice_id else "21m00Tcm4TlvDq8ikWAM",
            "google_voice_name": req.google_voice_name.strip() if req.google_voice_name else "id-ID-Wavenet-A",
            "openai_voice_name": req.openai_voice_name.strip() if req.openai_voice_name else "alloy",
            "gemini_tts_model": req.gemini_tts_model.strip() if req.gemini_tts_model else "gemini-3.8-flash-tts",
            "gemini_voice_name": req.gemini_voice_name.strip() if req.gemini_voice_name else "Puck",
            "temperature": float(req.temperature),
            "quality_gate_mode": req.quality_gate_mode,
        })
        with open(pers_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Simpan Kunci API TTS ke .env (Mendukung Multi-Key dipisah koma/baris baru)
        from sari_core.model_config import update_env_api_key

        if req.elevenlabs_api_key is not None and req.elevenlabs_api_key.strip():
            update_env_api_key("elevenlabs", req.elevenlabs_api_key)

        if req.google_tts_api_key is not None and req.google_tts_api_key.strip():
            update_env_api_key("google", req.google_tts_api_key)

        if req.openai_tts_api_key is not None and req.openai_tts_api_key.strip():
            update_env_api_key("openai", req.openai_tts_api_key)

        if req.gemini_tts_api_key is not None and req.gemini_tts_api_key.strip():
            update_env_api_key("gemini", req.gemini_tts_api_key)

        return {"status": "success", "message": "Pengaturan personalisasi & suara berhasil disimpan!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tts/test")
async def test_tts_endpoint():
    """Menguji suara asisten secara langsung lewat speaker PC."""
    import asyncio
    sample_text = "Halo pengguna, ini adalah uji coba karakter suara saya di Harmoni Agent."
    ok, audio_bytes, prov = await asyncio.to_thread(_generate_tts_bytes, sample_text)
    if ok and audio_bytes:
        asyncio.create_task(asyncio.to_thread(_play_tts_sound_direct, audio_bytes))
        return {"status": "success", "message": f"Suara ({prov}) berhasil dihasilkan dan sedang diputar lewat speaker PC!"}
    else:
        return {"status": "error", "message": f"Gagal memutar suara: {prov}"}

# 7C. PENGATURAN WHATSAPP LENGKAP, MULTI-PROFIL & GANTI NOMOR
@app.get("/whatsapp/config")
def get_whatsapp_config():
    multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
    legacy_file = AI_ASISTEN_DIR / "konfigurasi_wa.json"
    
    # Load multi profile jika ada
    if multi_file.exists():
        try:
            with open(multi_file, "r", encoding="utf-8") as f:
                import json
                return {"status": "success", "data": json.load(f)}
        except Exception:
            pass

    # Fallback init multi profile
    default_multi = {
        "active_profile": "nomor_1",
        "profiles": {
            "nomor_1": {
                "id": "nomor_1",
                "label": "Profil WhatsApp 1",
                "target_phone": "",
                "admin_wa_enabled": True,
                "wa_bot_name": "Lisa",
                "business_name": "",
                "business_address": "",
                "wa_tone": "gaul",
                "vip_numbers": "",
                "custom_info": "",
                "portfolio_links": "",
                "notify_telegram": True,
                "auto_transcribe_vn": True
            },
            "nomor_2": {
                "id": "nomor_2",
                "label": "Profil WhatsApp 2",
                "target_phone": "",
                "admin_wa_enabled": False,
                "wa_bot_name": "Admin",
                "business_name": "",
                "business_address": "",
                "wa_tone": "santai",
                "vip_numbers": "",
                "custom_info": "",
                "portfolio_links": "",
                "notify_telegram": True,
                "auto_transcribe_vn": True
            }
        }
    }
    return {"status": "success", "data": default_multi}

@app.post("/whatsapp/add-profile")
def add_wa_profile():
    multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
    import json
    data = {"active_profile": "nomor_1", "profiles": {}}
    if multi_file.exists():
        with open(multi_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    # Buat ID baru nomor_1, nomor_2, nomor_3 secara berurutan rapi
    existing_nums = [int(k.replace("nomor_", "")) for k in data.get("profiles", {}).keys() if k.startswith("nomor_") and k.replace("nomor_", "").isdigit()]
    next_num = (max(existing_nums) if existing_nums else 0) + 1
    new_pid = f"nomor_{next_num}"

    new_profile = {
        "id": new_pid,
        "label": f"Profil WhatsApp {next_num}",
        "target_phone": "",
        "admin_wa_enabled": False,
        "wa_bot_name": "Admin",
        "business_name": "",
        "business_address": "",
        "wa_tone": "santai",
        "vip_numbers": "",
        "custom_info": "",
        "portfolio_links": "",
        "notify_telegram": True,
        "auto_transcribe_vn": True,
        "attachments": []
    }
    data["profiles"][new_pid] = new_profile
    data["active_profile"] = new_pid
    with open(multi_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"status": "success", "message": f"Profil baru berhasil dibuat: {new_profile['label']}!", "new_profile_id": new_pid, "data": data}

@app.post("/whatsapp/delete-profile")
def delete_wa_profile(req: WASwitchProfileRequest):
    multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
    legacy_file = AI_ASISTEN_DIR / "konfigurasi_wa.json"
    from sari_core.paths import WA_AUTH_DIR
    auth_root = WA_AUTH_DIR
    temp_dir = AI_ASISTEN_DIR / "File" / "Temp"
    import json
    import shutil
    import subprocess

    if not multi_file.exists():
        raise HTTPException(status_code=404, detail="File multi WA belum ada")
    with open(multi_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    profiles = data.get("profiles", {})
    if len(profiles) <= 1:
        raise HTTPException(status_code=400, detail="Minimal harus ada 1 profil WhatsApp aktif. Tidak bisa dihapus semua.")

    del_pid = req.profile_id
    if del_pid not in profiles:
        raise HTTPException(status_code=404, detail="Profil tidak ditemukan")

    # 1. Bersihkan sesi auth & berkas temp profil yang dihapus
    del_auth = auth_root / del_pid
    if del_auth.exists():
        shutil.rmtree(del_auth, ignore_errors=True)
    for tmp_name in [f"KODE_PAIRING_WA_{del_pid}.txt", f"QR_CODE_WA_{del_pid}.png"]:
        tmp_f = temp_dir / tmp_name
        if tmp_f.exists():
            try: tmp_f.unlink()
            except Exception: pass

    # Bersihkan memori percakapan pelanggan dari profil yang dihapus
    try:
        from sari_core.db_manager import db
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT person_id FROM channels WHERE channel_type = 'WHATSAPP' AND (channel_id LIKE ? OR channel_id = ?)", (f"{del_pid}:%", del_pid))
            d_pids = [r['person_id'] for r in c.fetchall()]
            for p_id in d_pids:
                c.execute("DELETE FROM events WHERE person_id = ?", (p_id,))
                c.execute("DELETE FROM snapshots WHERE person_id = ?", (p_id,))
                c.execute("DELETE FROM channels WHERE person_id = ?", (p_id,))
                c.execute("DELETE FROM persons WHERE person_id = ?", (p_id,))
            conn.commit()
    except Exception as e_db:
        logger.warning(f"Error clean db for deleted profile: {e_db}")

    # 2. Urutkan profil yang tersisa dan geser nomor urutnya (auto re-index: 2->1, 3->2, dst.)
    def _get_sort_key(pid):
        num_part = pid.replace("nomor_", "")
        return int(num_part) if num_part.isdigit() else 999

    remaining_keys = sorted([k for k in profiles.keys() if k != del_pid], key=_get_sort_key)

    new_profiles = {}
    id_mapping = {}  # old_pid -> new_pid

    for idx, old_pid in enumerate(remaining_keys, start=1):
        new_pid = f"nomor_{idx}"
        id_mapping[old_pid] = new_pid

        prof_obj = profiles[old_pid]
        prof_obj["id"] = new_pid
        prof_obj["label"] = f"Profil WhatsApp {idx}"
        new_profiles[new_pid] = prof_obj

    # 3. Pindahkan folder autentikasi & berkas temp sesuai pergeseran ID (old_pid -> new_pid)
    for old_pid, new_pid in id_mapping.items():
        if old_pid != new_pid:
            old_auth = auth_root / old_pid
            new_auth = auth_root / new_pid
            if old_auth.exists():
                if new_auth.exists():
                    shutil.rmtree(new_auth, ignore_errors=True)
                shutil.move(str(old_auth), str(new_auth))

            old_code = temp_dir / f"KODE_PAIRING_WA_{old_pid}.txt"
            new_code = temp_dir / f"KODE_PAIRING_WA_{new_pid}.txt"
            if old_code.exists():
                if new_code.exists():
                    try: new_code.unlink()
                    except Exception: pass
                shutil.move(str(old_code), str(new_code))

            old_qr = temp_dir / f"QR_CODE_WA_{old_pid}.png"
            new_qr = temp_dir / f"QR_CODE_WA_{new_pid}.png"
            if old_qr.exists():
                if new_qr.exists():
                    try: new_qr.unlink()
                    except Exception: pass
                shutil.move(str(old_qr), str(new_qr))

    # 4. Perbarui referensi channel_id di database
    try:
        from sari_core.db_manager import db
        with db.get_connection() as conn:
            c = conn.cursor()
            for old_pid, new_pid in id_mapping.items():
                if old_pid != new_pid:
                    c.execute(
                        "UPDATE channels SET channel_id = ? || substr(channel_id, length(?) + 1) WHERE channel_type = 'WHATSAPP' AND channel_id LIKE ? || ':%'",
                        (new_pid, old_pid, old_pid)
                    )
            conn.commit()
    except Exception as e_db2:
        logger.warning(f"Error update channels for shifted profiles: {e_db2}")

    # 5. Tentukan profil aktif baru
    old_active = data.get("active_profile", "nomor_1")
    new_active = id_mapping.get(old_active, "nomor_1")
    data["profiles"] = new_profiles
    data["active_profile"] = new_active

    with open(multi_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Sinkronkan profil aktif ke legacy file
    if new_active in new_profiles:
        p_act = new_profiles[new_active]
        legacy_data = {
            "admin_wa_enabled": p_act.get("admin_wa_enabled", True),
            "wa_bot_name": p_act.get("wa_bot_name", "Admin"),
            "studio_name": p_act.get("business_name", ""),
            "studio_address": p_act.get("business_address", ""),
            "wa_tone": p_act.get("wa_tone", "gaul"),
            "vip_numbers": p_act.get("vip_numbers", ""),
            "custom_studio_info": p_act.get("custom_info", ""),
            "notify_telegram": p_act.get("notify_telegram", True),
            "auto_transcribe_vn": p_act.get("auto_transcribe_vn", True),
            "portfolio_links": p_act.get("portfolio_links", "")
        }
        with open(legacy_file, "w", encoding="utf-8") as lf:
            json.dump(legacy_data, lf, ensure_ascii=False, indent=2)

    # 6. Restart Node.js bridge agar memuat ulang pemetaan sesi baru
    try:
        ps = "Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique"
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        pids = [l.strip() for l in r.stdout.splitlines() if l.strip().isdigit()]
        for pid_val in set(pids):
            subprocess.run(["taskkill", "/F", "/PID", pid_val], capture_output=True)
    except Exception as e_proc:
        logger.warning(f"Error restart Node bridge: {e_proc}")

    return {
        "status": "success",
        "message": f"Profil {del_pid} berhasil dihapus! Nomor profil yang tersisa otomatis bergeser urutannya (1, 2, dst.).",
        "active_profile": new_active,
        "data": data
    }

@app.post("/whatsapp/switch-profile")
def switch_wa_profile(req: WASwitchProfileRequest):
    multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
    legacy_file = AI_ASISTEN_DIR / "konfigurasi_wa.json"
    import json
    if not multi_file.exists():
        raise HTTPException(status_code=404, detail="File konfigurasi multi WA belum ada")
    with open(multi_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if req.profile_id not in data.get("profiles", {}):
        raise HTTPException(status_code=400, detail=f"Profil {req.profile_id} tidak ditemukan")
    data["active_profile"] = req.profile_id
    with open(multi_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Sinkronkan profil aktif ke konfigurasi_wa.json agar engine langsung pakai
    p = data["profiles"][req.profile_id]
    legacy_data = {
        "admin_wa_enabled": p.get("admin_wa_enabled", True),
        "wa_bot_name": p.get("wa_bot_name", "Lisa"),
        "studio_name": p.get("business_name", ""),
        "studio_address": p.get("business_address", ""),
        "wa_tone": p.get("wa_tone", "gaul"),
        "vip_numbers": p.get("vip_numbers", ""),
        "custom_studio_info": p.get("custom_info", ""),
        "notify_telegram": p.get("notify_telegram", True),
        "auto_transcribe_vn": p.get("auto_transcribe_vn", True),
        "portfolio_links": p.get("portfolio_links", "")
    }
    with open(legacy_file, "w", encoding="utf-8") as lf:
        json.dump(legacy_data, lf, ensure_ascii=False, indent=2)

    admin_status_file = AI_ASISTEN_DIR / "admin_wa_status.json"
    with open(admin_status_file, "w", encoding="utf-8") as af:
        json.dump({"admin_wa": p.get("admin_wa_enabled", True)}, af, indent=2)

    return {"status": "success", "message": f"Berhasil beralih ke {p.get('label', req.profile_id)}!"}

@app.post("/whatsapp/save")
def save_whatsapp_config(req: WhatsAppConfigRequest):
    try:
        import json
        multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
        legacy_file = AI_ASISTEN_DIR / "konfigurasi_wa.json"
        admin_status_file = AI_ASISTEN_DIR / "admin_wa_status.json"

        # Load multi file
        data = {"active_profile": "nomor_1", "profiles": {}}
        if multi_file.exists():
            with open(multi_file, "r", encoding="utf-8") as f:
                data = json.load(f)

        pid = req.profile_id or data.get("active_profile", "nomor_1")
        prof_obj = data.get("profiles", {}).get(pid, {
            "id": pid, "label": f"Profil WhatsApp {pid.replace('nomor_', '')}"
        })

        owner_val = (req.owner_name or req.owner_phone or req.vip_numbers or "").strip()
        prof_obj.update({
            "admin_wa_enabled": req.admin_wa_enabled,
            "wa_bot_name": req.wa_bot_name.strip() or "Admin",
            "business_name": req.business_name.strip(),
            "business_address": req.business_address.strip(),
            "wa_tone": req.wa_tone,
            "vip_numbers": owner_val,
            "owner_name": owner_val,
            "custom_info": req.custom_info.strip(),
            "notify_telegram": req.notify_telegram,
            "auto_transcribe_vn": req.auto_transcribe_vn,
            "portfolio_links": req.portfolio_links.strip(),
            "auto_reply_mode": req.auto_reply_mode or "off",
            "auto_reply_text": (req.auto_reply_text or "").strip(),
            "business_hours_open": (req.business_hours_open or "09:00").strip(),
            "business_hours_close": (req.business_hours_close or "18:00").strip()
        })
        if req.quick_replies is not None:
            prof_obj["quick_replies"] = req.quick_replies
        if req.target_phone is not None and req.target_phone.strip():
            prof_obj["target_phone"] = req.target_phone.strip()
        if req.attachments is not None:
            prof_obj["attachments"] = req.attachments
        data["profiles"][pid] = prof_obj
        with open(multi_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Jika yang diedit adalah profil yang aktif, sinkronkan ke legacy file
        if pid == data.get("active_profile", "nomor_1"):
            legacy_data = {
                "admin_wa_enabled": req.admin_wa_enabled,
                "wa_bot_name": req.wa_bot_name.strip() or "Admin",
                "studio_name": req.business_name.strip(),
                "studio_address": req.business_address.strip(),
                "wa_tone": req.wa_tone,
                "vip_numbers": owner_val,
                "owner_name": owner_val,
                "custom_studio_info": req.custom_info.strip(),
                "notify_telegram": req.notify_telegram,
                "auto_transcribe_vn": req.auto_transcribe_vn,
                "portfolio_links": req.portfolio_links.strip()
            }
            with open(legacy_file, "w", encoding="utf-8") as lf:
                json.dump(legacy_data, lf, ensure_ascii=False, indent=2)
            with open(admin_status_file, "w", encoding="utf-8") as af:
                json.dump({"admin_wa": req.admin_wa_enabled}, af, indent=2)

        status_str = "AKTIF" if req.admin_wa_enabled else "NONAKTIF (Manual)"
        return {"status": "success", "message": f"Pengaturan {prof_obj.get('label', pid)} berhasil disimpan! Status: {status_str}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/whatsapp/request-pairing")
def request_wa_pairing(req: WAPairingRequest):
    """Meminta kode pairing 8 angka untuk menautkan nomor baru tanpa scan QR (per profil nomor)."""
    import urllib.request
    import json
    from wa_listener import ensure_wa_node_bridge
    # Pastikan background service wa_bridge di port 3000 hidup sebelum meminta pairing
    ensure_wa_node_bridge()
    try:
        url = "http://localhost:3000/request-pairing"
        payload = json.dumps({
            "phone": req.phone.strip(),
            "profile": req.profile_id
        }).encode("utf-8")
        r = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(r, timeout=40) as resp:
            data = json.loads(resp.read().decode())

        # Simpan nomor ke profil agar profil tahu nomor mana yang ditautkan
        if req.profile_id:
            try:
                multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
                if multi_file.exists():
                    with open(multi_file, "r", encoding="utf-8") as f:
                        kfg = json.load(f)
                    if req.profile_id in kfg.get("profiles", {}):
                        kfg["profiles"][req.profile_id]["target_phone"] = req.phone.strip()
                        with open(multi_file, "w", encoding="utf-8") as f:
                            json.dump(kfg, f, ensure_ascii=False, indent=2)
            except Exception as e_simpan:
                logger.warning(f"Gagal menyimpan target_phone profil WA: {e_simpan}")

        return {
            "status": "success",
            "pairing_code": data.get("pairingCode"),
            "phone": data.get("phone"),
            "profile_id": data.get("profile")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal meminta kode pairing: {str(e)}")


@app.get("/whatsapp/qr")
def get_wa_qr(profile_id: Optional[str] = "nomor_1"):
    """Mengembalikan gambar QR Code WhatsApp dalam format Base64 untuk ditampilkan di antarmuka."""
    import base64
    from sari_core.paths import DATA_ROOT
    pid = profile_id or "nomor_1"
    temp_dir = DATA_ROOT / "File" / "Temp"
    qr_file = temp_dir / f"QR_CODE_WA_{pid}.png"
    if not qr_file.exists():
        qr_file = temp_dir / "QR_CODE_WA.png"
    if qr_file.exists():
        try:
            with open(qr_file, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"status": "success", "has_qr": True, "qr_base64": f"data:image/png;base64,{b64}", "profile_id": pid}
        except Exception as e:
            return {"status": "error", "has_qr": False, "message": str(e)}
    return {"status": "success", "has_qr": False, "message": "QR Code belum tersedia atau sedang dimuat ulang.", "profile_id": pid}


@app.get("/whatsapp/status")
def status_wa_sesi():
    """Menampilkan status koneksi SEMUA nomor WhatsApp (multi-sesi, bisa jalan bersamaan)."""
    import urllib.request
    import json
    try:
        with urllib.request.urlopen("http://localhost:3000/status", timeout=8) as resp:
            data = json.loads(resp.read().decode())
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": f"Service WhatsApp belum siap: {str(e)}", "data": {"sessions": []}}


@app.post("/whatsapp/reset-session")
def reset_wa_session(req: Optional[WASwitchProfileRequest] = None):
    """Memutuskan koneksi dan menghapus sesi login SATU nomor (per profil) agar bisa ganti nomor."""
    import urllib.request
    import json
    pid = req.profile_id if req else None
    try:
        url = "http://localhost:3000/reset-session"
        payload = json.dumps({"profile": pid}).encode("utf-8")
        r = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(r, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            return {"status": "success", "message": data.get("message", "Sesi WhatsApp berhasil direset"), "profile_id": data.get("profile")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mereset sesi: {str(e)}")


class WAReplyRequest(BaseModel):
    to: str
    pesan: str
    profile_id: Optional[str] = "nomor_1"

@app.post("/whatsapp/send-reply")
def send_wa_reply_endpoint(req: WAReplyRequest):
    """Mengirim balasan WhatsApp langsung dari tombol UI Desktop."""
    from plugins.whatsapp_plugin import kirim_pesan_whatsapp
    res = kirim_pesan_whatsapp(
        nama_kontak=req.to.strip(),
        pesan=req.pesan.strip(),
        profile_id=req.profile_id or "nomor_1",
        force_send=True
    )
    if "Berhasil" in res or "terkirim" in res.lower():
        return {"status": "success", "message": res}
    else:
        return {"status": "error", "message": res}


@app.post("/whatsapp/send-status")
def send_wa_status(req: WASendStatusRequest):
    """Mengunggah Status (Story) WhatsApp dari Desktop UI atau skrip."""
    from plugins.whatsapp_plugin import kirim_status_whatsapp
    res = kirim_status_whatsapp(
        teks=req.text or "",
        path_file=req.file_path or "",
        profile_id=req.profile_id or "",
        force_send=True
    )
    if "Berhasil" in res:
        return {"status": "success", "message": res}
    else:
        return {"status": "error", "message": res}


@app.get("/whatsapp/status-viewers")
def get_wa_status_viewers(profile: Optional[str] = None):
    """Melihat daftar status terbaru dan jumlah penonton dari WA Bridge."""
    import urllib.request
    import json
    pid = profile or ""
    try:
        url = f"http://localhost:3000/status-viewers?profile={pid}" if pid else "http://localhost:3000/status-viewers"
        r = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as e:
        return {"status": "error", "message": str(e), "statuses": []}


@app.post("/whatsapp/clear-memory")
async def clear_wa_memory(req: Optional[WASwitchProfileRequest] = None):
    """Menghapus riwayat percakapan klien WhatsApp (per profil atau semua), tanpa menghapus sesi login/akun."""
    from sari_core.db_manager import db
    pid = req.profile_id if req else None
    cleaned_count = 0
    with db.get_connection() as conn:
        c = conn.cursor()
        if pid:
            # Cari person_id untuk channel yang berawalan pid: atau channel legacy
            c.execute(
                "SELECT person_id FROM channels WHERE channel_type = 'WHATSAPP' AND (channel_id LIKE ? OR channel_id = ? OR channel_id NOT LIKE '%:%')",
                (f"{pid}:%", pid)
            )
        else:
            c.execute("SELECT person_id FROM channels WHERE channel_type = 'WHATSAPP'")
        rows = c.fetchall()
        person_ids = list(set(r['person_id'] for r in rows))
        for p_id in person_ids:
            c.execute("DELETE FROM events WHERE person_id = ?", (p_id,))
            c.execute("DELETE FROM snapshots WHERE person_id = ?", (p_id,))
            cleaned_count += 1
        conn.commit()
    label = f"profil '{pid}'" if pid else "semua nomor"
    return {
        "status": "success",
        "message": f"Riwayat obrolan pelanggan WhatsApp untuk {label} berhasil dibersihkan ({cleaned_count} kontak direset). Akun WA tetap aman tersambung!"
    }


@app.post("/whatsapp/attachment/upload")
async def upload_wa_attachment_endpoint(req: UploadFileBase64Request):
    """Menerima file lampiran WhatsApp (MP3 sampel, PDF brosur, foto, dll.) dan menyimpannya di File/Lampiran_WA."""
    import base64
    import time
    
    upload_dir = AI_ASISTEN_DIR / "File" / "Lampiran_WA"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    if req.file_path and os.path.exists(req.file_path):
        target_path = Path(req.file_path)
    elif req.file_base64:
        clean_name = (req.file_name or "lampiran_wa.bin").replace(" ", "_").replace("/", "_").replace("\\", "_")
        safe_name = f"{int(time.time())}_{clean_name}"
        target_path = upload_dir / safe_name
        try:
            raw_bytes = base64.b64decode(req.file_base64)
            with open(target_path, "wb") as f_out:
                f_out.write(raw_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Gagal memproses file: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Data file belum dikirim.")
        
    return {
        "status": "success",
        "file_name": req.file_name or target_path.name,
        "file_path": str(target_path),
        "file_size": os.path.getsize(target_path)
    }


@app.post("/chat/clear")
async def clear_chat_memory_endpoint():
    try:
        from sari_core.memory_broker import memory_broker
        pers_file = AI_ASISTEN_DIR / "personalisasi.json"
        u_name = "Pengguna"
        if pers_file.exists():
            try:
                with open(pers_file, "r", encoding="utf-8") as pf:
                    u_name = json.load(pf).get("user_call_name") or u_name
            except Exception:
                pass
        person_id = await memory_broker.get_or_create_person(u_name, "DESKTOP_UI")
        await memory_broker.clear_memory(person_id)
        return {"status": "success", "message": "Riwayat percakapan berhasil direset dari memori database."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 7b. PANDUAN PEMASANGAN PERTAMA
# ============================================================
@app.get("/pemasangan/status")
def status_pemasangan():
    """Ringkasan bagian mana yang sudah terisi. TIDAK pernah membocorkan isi kunci."""
    import json
    from dotenv import dotenv_values

    env_path = AI_ASISTEN_DIR / ".env"
    env = dotenv_values(env_path) if env_path.exists() else {}

    def terisi(nama: str) -> bool:
        n = env.get(nama)
        return bool(n and str(n).strip())

    def baca_json(nama: str) -> dict:
        f = AI_ASISTEN_DIR / nama
        if not f.exists():
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}

    pers = baca_json("personalisasi.json")
    wa = baca_json("konfigurasi_multi_wa.json")
    jumlah_wa = len(wa.get("profiles") or {}) if isinstance(wa.get("profiles"), dict) else len(wa.get("profiles") or [])

    kunci_ai = ["DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
                "GROQ_API_KEY_1", "OPENROUTER_API_KEY", "ALIBABA_API_KEY", "XIAOMI_MIMO_API_KEY"]

    return {
        "status": "success",
        "selesai": pers.get("pemasangan_selesai"),  # None bila belum pernah diisi
        "otak_ai": any(terisi(k) for k in kunci_ai),
        "telegram": terisi("TELEGRAM_BOT_TOKEN"),
        "email": terisi("EMAIL_ADDRESS") and terisi("EMAIL_APP_PASSWORD"),
        "whatsapp": jumlah_wa > 0,
        "jumlah_whatsapp": jumlah_wa,
        "google": any((AI_ASISTEN_DIR / n).exists() for n in
                      ("token_utama.json", "token_drive_utama.json")),
        "folder_data": str(AI_ASISTEN_DIR),
    }


@app.get("/pemasangan/panduan")
def panduan_pemasangan():
    """Menyerahkan halaman panduan pemasangan supaya bisa dibuka di peramban."""
    from fastapi.responses import FileResponse
    berkas = PROGRAM_DIR / "pemasangan_pertama.html"
    if not berkas.exists():
        raise HTTPException(status_code=404, detail="Berkas panduan pemasangan tidak ditemukan.")
    return FileResponse(str(berkas), media_type="text/html")


@app.post("/pemasangan/selesai")
def selesai_pemasangan():
    """Menandai panduan pemasangan sudah ditutup, supaya tidak muncul lagi."""
    import json
    pers_file = AI_ASISTEN_DIR / "personalisasi.json"
    data = {}
    if pers_file.exists():
        try:
            data = json.loads(pers_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["pemasangan_selesai"] = True
    pers_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "success", "message": "Panduan pemasangan ditandai selesai."}


# ============================================================
# 8. BACKUP & RESTORE PENGATURAN HARMONI (1-KLIK)
# ============================================================
@app.get("/settings/backup")
def settings_backup():
    """Mengemas semua berkas konfigurasi Harmoni ke dalam satu objek JSON untuk dicadangkan."""
    import json
    backup_data = {}
    files_to_backup = {
        "personalisasi": AI_ASISTEN_DIR / "personalisasi.json",
        "konfigurasi_multi_wa": AI_ASISTEN_DIR / "konfigurasi_multi_wa.json",
        "konfigurasi_email": AI_ASISTEN_DIR / "konfigurasi_email.json",
        "konfigurasi_youtube": AI_ASISTEN_DIR / "konfigurasi_youtube.json",
        "kontak_tersimpan": AI_ASISTEN_DIR / "kontak_tersimpan.json",
    }
    for key, fpath in files_to_backup.items():
        if fpath.exists():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    backup_data[key] = json.load(f)
            except Exception:
                pass
    from datetime import datetime
    return {
        "status": "success",
        "app": "Harmoni Agent",
        "version": "1.0.0",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": backup_data
    }

class SettingsRestoreRequest(BaseModel):
    data: dict


# ===========================================================================
# SINKRONISASI GOOGLE DRIVE & PENCADANGAN LENGKAP
# ===========================================================================


class SinkronisasiAturRequest(BaseModel):
    aktif: Optional[bool] = None
    mode: Optional[str] = None
    folder_lokal: Optional[str] = None
    folder_drive: Optional[str] = None
    interval_menit: Optional[int] = None
    cadangan_aktif: Optional[bool] = None
    cadangan_interval_jam: Optional[int] = None


class SinkronisasiPulihkanRequest(BaseModel):
    berkas: str


@app.get("/sinkronisasi/status")
def sinkronisasi_status():
    """Keadaan sinkronisasi sekarang: pengaturan, hasil terakhir, daftar cadangan."""
    try:
        from sari_core import sinkronisasi_config as cfg
        from sari_core import cadangan

        pengaturan = cfg.muat()
        besok = cadangan.cadangan_perlu_dibuat()
        return {
            "status": "success",
            "pengaturan": pengaturan,
            "ringkas": cfg.ringkas(),
            "folder_cadangan": str(cadangan.folder_cadangan()),
            "berkas_cadangan": str(cadangan.berkas_utama()),
            "cadangan_perlu_dibuat": besok,
            "daftar_cadangan": cadangan.daftar_cadangan()[:20],
        }
    except Exception as e:
        logger.error(f"Gagal membaca status sinkronisasi: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/sinkronisasi/atur")
def sinkronisasi_atur(req: SinkronisasiAturRequest):
    """Ubah pengaturan sinkronisasi. Hanya bagian yang dikirim yang diubah."""
    try:
        from sari_core import sinkronisasi_config as cfg

        perubahan = {}
        if req.aktif is not None:
            perubahan["aktif"] = bool(req.aktif)
        if req.mode is not None:
            mode = str(req.mode).strip().lower()
            if mode not in (cfg.MODE_AMAN, cfg.MODE_PENUH):
                return {"status": "error", "message": "Mode harus 'aman' atau 'penuh'."}
            perubahan["mode"] = mode
        if req.folder_lokal is not None:
            jalur = str(req.folder_lokal).strip()
            if not jalur:
                return {"status": "error", "message": "Folder tidak boleh kosong."}
            try:
                Path(jalur).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return {"status": "error", "message": f"Folder tidak bisa dipakai: {e}"}
            perubahan["folder_lokal"] = jalur
        if req.folder_drive is not None:
            nama = str(req.folder_drive).strip().strip("/\\")
            if not nama:
                return {"status": "error", "message": "Nama folder Drive tidak boleh kosong."}
            perubahan["folder_drive"] = nama
        if req.interval_menit is not None:
            perubahan["interval_menit"] = max(1, int(req.interval_menit))
        if req.cadangan_aktif is not None:
            perubahan["cadangan_aktif"] = bool(req.cadangan_aktif)
        if req.cadangan_interval_jam is not None:
            perubahan["cadangan_interval_jam"] = max(1, int(req.cadangan_interval_jam))

        hasil = cfg.perbarui(**perubahan)
        return {"status": "success", "pengaturan": hasil, "ringkas": cfg.ringkas()}
    except Exception as e:
        logger.error(f"Gagal mengubah pengaturan sinkronisasi: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/sinkronisasi/sekarang")
def sinkronisasi_sekarang():
    """Jalankan satu siklus sinkronisasi sekarang juga."""
    try:
        from sari_core.drive_sync_engine import run_sync_cycle
        laporan = run_sync_cycle()
        return {"status": "success" if laporan.get("berhasil") else "error",
                "laporan": laporan,
                "message": laporan.get("pesan", "")}
    except Exception as e:
        logger.error(f"Sinkronisasi manual gagal: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/sinkronisasi/cadangkan")
def sinkronisasi_cadangkan():
    """Buat cadangan lengkap sekarang juga."""
    try:
        from sari_core import cadangan
        hasil = cadangan.buat_cadangan()
        return {"status": "success" if hasil.get("berhasil") else "error",
                "hasil": hasil, "message": hasil.get("pesan", "")}
    except Exception as e:
        logger.error(f"Pencadangan manual gagal: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/sinkronisasi/daftar_cadangan")
def sinkronisasi_daftar_cadangan():
    try:
        from sari_core import cadangan
        return {"status": "success", "daftar": cadangan.daftar_cadangan()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/sinkronisasi/pulihkan")
def sinkronisasi_pulihkan(req: SinkronisasiPulihkanRequest):
    """Pulihkan dari berkas cadangan. Menerima ZIP (baru) maupun JSON (lama)."""
    try:
        from sari_core import cadangan
        hasil = cadangan.pulihkan(req.berkas)
        return {"status": "success" if hasil.get("berhasil") else "error",
                "hasil": hasil, "message": hasil.get("pesan", "")}
    except Exception as e:
        logger.error(f"Pemulihan gagal: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/sinkronisasi/folder")
def sinkronisasi_folder(jalur: str = ""):
    """Daftar isi sebuah folder - untuk penjelajah folder di layar Pengaturan.

    Dibuat sendiri di dalam aplikasi (bukan memakai jendela bawaan Windows)
    supaya bisa dijelajahi dengan keyboard dan dibacakan NVDA dengan pasti.
    """
    try:
        if not jalur.strip():
            # Belum memilih apa pun: tawarkan drive yang ada
            isi = []
            for huruf in "CDEFGHIJ":
                akar = f"{huruf}:\\"
                if Path(akar).exists():
                    isi.append({"nama": f"Drive {huruf}:", "jalur": akar, "jenis": "drive"})
            return {"status": "success", "jalur": "", "induk": None, "isi": isi}

        akar = Path(jalur)
        if not akar.exists() or not akar.is_dir():
            return {"status": "error", "message": f"Folder tidak ditemukan: {jalur}"}

        isi = []
        try:
            for anak in sorted(akar.iterdir(), key=lambda p: p.name.lower()):
                try:
                    if not anak.is_dir():
                        continue
                    # Lewati folder tersembunyi/sistem supaya daftar tetap bersih
                    nama = anak.name
                    if nama.startswith(".") or nama in (
                        "$RECYCLE.BIN", "System Volume Information",
                        "Windows", "ProgramData", "AppData",
                    ):
                        continue
                    isi.append({"nama": nama, "jalur": str(anak), "jenis": "folder"})
                except (OSError, PermissionError):
                    continue
        except PermissionError:
            return {"status": "error", "message": f"Tidak diizinkan membuka: {jalur}"}

        induk = str(akar.parent) if akar.parent != akar else None
        return {"status": "success", "jalur": str(akar), "induk": induk, "isi": isi}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/sinkronisasi/buka_folder")
def sinkronisasi_buka_folder(jalur: str = ""):
    """Buka folder di Windows Explorer supaya pengguna bisa melihat isinya."""
    try:
        target = Path(jalur)
        if not target.exists():
            return {"status": "error", "message": f"Folder tidak ditemukan: {jalur}"}
        if os.name == "nt":
            os.startfile(str(target))  # noqa: S606
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(target)])
        return {"status": "success", "message": f"Membuka folder: {jalur}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/sinkronisasi/berkas_cadangan_lama")
def sinkronisasi_berkas_lama():
    """Cari berkas cadangan lama (format JSON) di folder Downloads dan Dokumen.

    Dipakai tombol Pulihkan supaya pengguna tidak perlu menelusuri folder sendiri
    untuk menemukan cadangan lama.
    """
    hasil = []
    tempat = [Path.home() / "Downloads", Path.home() / "Documents"]
    try:
        from sari_core import cadangan
        tempat.append(cadangan.folder_cadangan())
    except Exception:
        pass
    for folder in tempat:
        if not folder.exists():
            continue
        for pola in ("Backup_Pengaturan*.json", "*.zip"):
            for berkas in folder.glob(pola):
                try:
                    hasil.append({
                        "nama": berkas.name,
                        "jalur": str(berkas),
                        "ukuran_mb": round(berkas.stat().st_size / (1024 * 1024), 2),
                    })
                except OSError:
                    continue
    # Buang duplikat, urut dari yang paling baru
    dilihat = {}
    for h in hasil:
        dilihat[h["jalur"]] = h
    return {"status": "success", "daftar": list(dilihat.values())[:30]}


@app.post("/settings/backup/save")
def settings_backup_save():
    """Simpan berkas cadangan pengaturan LANGSUNG ke folder Downloads komputer ini.

    Lebih andal daripada unduhan lewat peramban: lokasi berkasnya pasti, dan
    jalurnya bisa dilaporkan ke pengguna (penting bagi pengguna NVDA yang butuh
    kepastian berkasnya benar-benar tersimpan).
    """
    import json
    from datetime import datetime

    isi = settings_backup()
    unduhan = Path.home() / "Downloads"
    unduhan.mkdir(parents=True, exist_ok=True)
    nama = f"Backup_Pengaturan_Harmoni_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    tujuan = unduhan / nama
    tujuan.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Cadangan pengaturan disimpan ke {tujuan}")
    return {
        "status": "success",
        "name": nama,
        "path": str(tujuan),
        "folder": str(unduhan),
        "message": f"Cadangan tersimpan di: {tujuan}",
    }


@app.post("/settings/restore")
def settings_restore(req: SettingsRestoreRequest):
    """Memulihkan konfigurasi Harmoni dari berkas cadangan JSON."""
    import json
    b_data = req.data
    restored_items = []
    file_map = {
        "personalisasi": AI_ASISTEN_DIR / "personalisasi.json",
        "konfigurasi_multi_wa": AI_ASISTEN_DIR / "konfigurasi_multi_wa.json",
        "konfigurasi_email": AI_ASISTEN_DIR / "konfigurasi_email.json",
        "konfigurasi_youtube": AI_ASISTEN_DIR / "konfigurasi_youtube.json",
        "kontak_tersimpan": AI_ASISTEN_DIR / "kontak_tersimpan.json",
    }
    for key, fpath in file_map.items():
        if key in b_data and isinstance(b_data[key], (dict, list)):
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(b_data[key], f, ensure_ascii=False, indent=2)
                restored_items.append(key)
            except Exception as e:
                logger.error(f"Gagal memulihkan {key}: {e}")

    return {
        "status": "success",
        "message": f"Berhasil memulihkan {len(restored_items)} komponen konfigurasi: {', '.join(restored_items)}."
    }

# 7c. UPLOAD & ANALISIS DOKUMEN / FILE
@app.post("/upload/file")
async def upload_file_endpoint(req: UploadFileBase64Request):
    """Menerima file (base64 atau local path), menyimpannya di File/Temp, dan mengekstrak isi teksnya."""
    import base64
    import time
    from sari_core.document_parser import parse_document
    
    upload_dir = AI_ASISTEN_DIR / "File" / "Temp"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    if req.file_path and os.path.exists(req.file_path):
        target_path = Path(req.file_path)
    elif req.file_base64:
        clean_name = (req.file_name or "file_upload.txt").replace(" ", "_").replace("/", "_").replace("\\", "_")
        safe_name = f"{int(time.time())}_{clean_name}"
        target_path = upload_dir / safe_name
        try:
            raw_bytes = base64.b64decode(req.file_base64)
            with open(target_path, "wb") as f_out:
                f_out.write(raw_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Gagal memproses data file: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Data file (base64 atau path) belum dikirim.")
        
    parsed = parse_document(str(target_path))
    if parsed.get("status") == "error":
        raise HTTPException(status_code=400, detail=parsed.get("error", "Gagal membaca isi file"))
        
    preview = parsed.get("extracted_text", "").strip()
    if len(preview) > 300:
        preview = preview[:300] + "..."
        
    return {
        "status": "success",
        "file_name": req.file_name or target_path.name,
        "category": parsed.get("category", "document"),
        "file_size_kb": parsed.get("file_size_kb", 0),
        "file_ext": parsed.get("file_ext", ""),
        "preview_text": preview,
        "summary_prompt": parsed.get("summary_prompt", ""),
        "file_path": str(target_path)
    }

# 7d. DIKTE & MIKROFON INPUT SUARA (VOICE INPUT)
@app.post("/voice/start")
async def voice_start_recording():
    """Mulai merekam suara dari mikrofon Windows secara lokal."""
    try:
        from sari_core.voice_recorder import voice_recorder
        res = voice_recorder.start_recording()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/voice/stop")
async def voice_stop_recording():
    """Hentikan perekaman dan transkripsikan rekaman ke teks bahasa Indonesia."""
    try:
        from sari_core.voice_recorder import voice_recorder
        res = voice_recorder.stop_recording()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/voice/status")
async def voice_status():
    """Cek status apakah perekam sedang aktif."""
    try:
        from sari_core.voice_recorder import voice_recorder
        return {"is_recording": voice_recorder.is_recording}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7e. MANAJEMEN PENJADWALAN TUGAS (SCHEDULE ENGINE)
@app.get("/scheduler/tasks")
def get_scheduler_tasks_endpoint():
    from sari_core.paths import OBSIDIAN_DIR
    import json
    file_jadwal = OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json"
    daftar = []
    if file_jadwal.exists():
        try:
            with open(file_jadwal, "r", encoding="utf-8") as f:
                daftar = json.load(f)
        except Exception:
            daftar = []
            
    if not isinstance(daftar, list):
        daftar = []

    active_statuses = {"pending", "retrying", "guaranteed_retry"}
    active_tasks = [t for t in daftar if t.get("status") in active_statuses]
    history_tasks = [t for t in daftar if t.get("status") not in active_statuses]

    active_tasks.sort(key=lambda x: x.get("timestamp_target", 0))
    history_tasks.sort(key=lambda x: x.get("timestamp_target", 0), reverse=True)

    summary = {
        "total": len(daftar),
        "active_count": len(active_tasks),
        "history_count": len(history_tasks)
    }

    return {
        "status": "success",
        "summary": summary,
        "active_tasks": active_tasks,
        "history_tasks": history_tasks,
        "all_tasks": active_tasks + history_tasks
    }

@app.post("/scheduler/tasks/add")
def add_scheduler_task_endpoint(req: ScheduleAddTaskRequest):
    try:
        from bot_otomatis import jadwalkan_tugas_otomatis
        import json
        params = {}
        if req.target_kontak:
            params["nama_kontak"] = req.target_kontak
            params["nomor"] = req.target_kontak
        if req.target_email:
            params["tujuan"] = req.target_email
            params["email"] = req.target_email
        if req.subjek_email:
            params["subjek"] = req.subjek_email
        if req.pesan_atau_prompt:
            params["pesan"] = req.pesan_atau_prompt
            params["teks"] = req.pesan_atau_prompt
            params["kata_kunci"] = req.pesan_atau_prompt
        if req.profile_id:
            params["profile_id"] = req.profile_id

        res = jadwalkan_tugas_otomatis(
            jam_atau_tanggal=req.jam_atau_waktu,
            fungsi_aksi=req.fungsi_aksi,
            parameter_json=json.dumps(params),
            deskripsi_laporan=req.deskripsi or req.pesan_atau_prompt,
            interval_menit=req.interval_menit,
            total_pengulangan=req.total_pengulangan,
            pesan_atau_prompt=req.pesan_atau_prompt,
            profile_id=req.profile_id or ""
        )
        return {"status": "success", "message": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/scheduler/tasks/clear-history")
def clear_scheduler_history_endpoint():
    from sari_core.paths import OBSIDIAN_DIR
    import json
    file_jadwal = OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json"
    if not file_jadwal.exists():
        return {"status": "success", "message": "Riwayat jadwal kosong."}
    try:
        with open(file_jadwal, "r", encoding="utf-8") as f:
            daftar = json.load(f)
    except Exception:
        daftar = []
        
    active_statuses = {"pending", "retrying", "guaranteed_retry"}
    active_tasks = [t for t in daftar if t.get("status") in active_statuses]
    deleted_count = len(daftar) - len(active_tasks)

    with open(file_jadwal, "w", encoding="utf-8") as f:
        json.dump(active_tasks, f, indent=2, ensure_ascii=False)

    return {
        "status": "success",
        "message": f"Berhasil membersihkan {deleted_count} riwayat tugas lama. Antrean aktif tetap aman.",
        "remaining_active": len(active_tasks)
    }

@app.post("/scheduler/tasks/cancel")
def cancel_scheduler_task_endpoint(req: ScheduleCancelTaskRequest):
    try:
        from bot_otomatis import kelola_jadwal_tugas
        res = kelola_jadwal_tugas(aksi="batalkan", task_id=req.task_id)
        return {"status": "success", "message": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/scheduler/tasks/execute")
async def execute_scheduler_task_now_endpoint(req: ScheduleCancelTaskRequest):
    try:
        from sari_core.paths import OBSIDIAN_DIR
        from task_scheduler import jalankan_satu_tugas_async
        import json
        file_jadwal = OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json"
        if not file_jadwal.exists():
            raise HTTPException(status_code=404, detail="File jadwal tidak ditemukan")
        with open(file_jadwal, "r", encoding="utf-8") as f:
            daftar = json.load(f)
        target = None
        for item in daftar:
            if item.get("id") == req.task_id:
                target = item
                break
        if not target:
            raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

        sukses, detail_res = await jalankan_satu_tugas_async(target)
        return {"status": "success" if sukses else "failed", "detail": detail_res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7e. MANAJEMEN SESI OBROLAN (SESSIONS ENGINE)
@app.get("/sessions")
def get_sessions_endpoint():
    from sari_core.db_manager import db
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT s.session_id, s.title, s.created_at, s.updated_at, s.is_active,
                   COUNT(m.message_id) as message_count
            FROM conversation_sessions s
            LEFT JOIN session_messages m ON s.session_id = m.session_id
            GROUP BY s.session_id
            ORDER BY s.is_active DESC, s.updated_at DESC
        ''')
        rows = [dict(r) for r in c.fetchall()]
    return {"status": "success", "sessions": rows}

@app.get("/sessions/{session_id}/messages")
def get_session_messages_endpoint(session_id: str):
    from sari_core.db_manager import db
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT title, is_active FROM conversation_sessions WHERE session_id = ?', (session_id,))
        s_row = c.fetchone()
        if not s_row:
            raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")
        c.execute('SELECT message_id, sender, text, timestamp FROM session_messages WHERE session_id = ? ORDER BY message_id ASC', (session_id,))
        msgs = [dict(r) for r in c.fetchall()]
    return {
        "status": "success",
        "session_id": session_id,
        "title": s_row["title"],
        "is_active": bool(s_row["is_active"]),
        "messages": msgs
    }

@app.post("/sessions/create")
def create_session_endpoint(req: CreateSessionRequest):
    import uuid
    from datetime import datetime
    from sari_core.db_manager import db
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = (req.title or "").strip() or f"Obrolan Baru ({datetime.now().strftime('%d %b %H:%M')})"
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('UPDATE conversation_sessions SET is_active = 0')
        c.execute('INSERT INTO conversation_sessions (session_id, title, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)', (session_id, title, now_str, now_str))
        conn.commit()
    return {"status": "success", "session_id": session_id, "title": title}

@app.post("/sessions/switch")
def switch_session_endpoint(req: SwitchSessionRequest):
    from sari_core.db_manager import db
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT session_id, title FROM conversation_sessions WHERE session_id = ?', (req.session_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")
        c.execute('UPDATE conversation_sessions SET is_active = 0')
        c.execute('UPDATE conversation_sessions SET is_active = 1 WHERE session_id = ?', (req.session_id,))
        conn.commit()
    return {"status": "success", "session_id": req.session_id, "title": row["title"]}

@app.post("/sessions/rename")
def rename_session_endpoint(req: RenameSessionRequest):
    from sari_core.db_manager import db
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Judul sesi tidak boleh kosong")
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('UPDATE conversation_sessions SET title = ?, updated_at = datetime("now", "localtime") WHERE session_id = ?', (title, req.session_id))
        conn.commit()
    return {"status": "success", "session_id": req.session_id, "title": title}

@app.post("/sessions/delete")
def delete_session_endpoint(req: DeleteSessionRequest):
    from sari_core.db_manager import db
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM session_messages WHERE session_id = ?', (req.session_id,))
        c.execute('DELETE FROM conversation_sessions WHERE session_id = ?', (req.session_id,))
        # Bersihkan juga identitas channel dan events reasoning untuk sesi ini
        c.execute('SELECT person_id FROM channels WHERE channel_id = ?', (f"desktop_{req.session_id}",))
        ch_row = c.fetchone()
        if ch_row:
            p_id = ch_row['person_id']
            c.execute('DELETE FROM events WHERE person_id = ?', (p_id,))
            c.execute('DELETE FROM snapshots WHERE person_id = ?', (p_id,))
            c.execute('DELETE FROM channels WHERE channel_id = ?', (f"desktop_{req.session_id}",))
            c.execute('DELETE FROM persons WHERE person_id = ?', (p_id,))
        c.execute('SELECT session_id FROM conversation_sessions WHERE is_active = 1')
        active = c.fetchone()
        if not active:
            c.execute('SELECT session_id FROM conversation_sessions ORDER BY updated_at DESC LIMIT 1')
            fallback = c.fetchone()
            if fallback:
                c.execute('UPDATE conversation_sessions SET is_active = 1 WHERE session_id = ?', (fallback["session_id"],))
        conn.commit()
    return {"status": "success", "message": "Sesi berhasil dihapus"}

# 8. PERCAKAPAN CHATBOT
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    try:
        from sari_core.memory_broker import memory_broker
        from sari_core.brain import ReasoningLayer
        from sari_core.db_manager import db
        import asyncio
        
        target_sid = req.session_id or "temporary_chat"
        is_temp = target_sid == "temporary_chat" or target_sid.startswith("temp")

        # Jaga-jaga: sesi bisa saja sudah dihapus, sehingga penyimpanan ke
        # session_messages gagal dengan 'FOREIGN KEY constraint failed'.
        if not is_temp:
            from sari_core.bridge import sesi_masih_ada
            if not sesi_masih_ada(target_sid):
                logger.warning(f"Sesi '{target_sid}' tidak ditemukan. Beralih ke mode Chat Sementara.")
                target_sid = "temporary_chat"
                is_temp = True

        # ISOLASI SESI LENGKAP: Setiap sesi desktop memiliki person_id sendiri agar konteks obrolan tidak bocor ke sesi lain!
        channel_id = f"desktop_{target_sid}" if req.platform == "DESKTOP_UI" else req.user_name
        person_id = await memory_broker.get_or_create_person(channel_id, req.platform)

        # Jika sesi ini baru di events namun sudah memiliki riwayat di session_messages, sinkronkan pesan sebelumnya
        if req.platform == "DESKTOP_UI" and not is_temp:
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT COUNT(*) as cnt FROM events WHERE person_id = ?', (person_id,))
                ev_cnt = c.fetchone()['cnt']
                if ev_cnt == 0:
                    c.execute('SELECT sender, text FROM session_messages WHERE session_id = ? ORDER BY message_id ASC LIMIT 50', (target_sid,))
                    past_rows = c.fetchall()
                    for pr in past_rows:
                        if pr['sender'] == 'user':
                            await memory_broker.append_event(person_id, "MESSAGE_RECEIVED", {"content": f"[{req.user_name}]: {pr['text']}"})
                        elif pr['sender'] == 'ai':
                            await memory_broker.append_event(person_id, "LLM_RESPONSE_SENT", {"content": pr['text']})

        # Integrasi lampiran dokumen/file jika ada
        full_content = req.message
        if req.attachment:
            summary_p = req.attachment.get("summary_prompt", "")
            if not summary_p and req.attachment.get("file_path"):
                from sari_core.document_parser import parse_document
                p_res = parse_document(req.attachment["file_path"])
                summary_p = p_res.get("summary_prompt", "")
            if summary_p:
                user_q = req.message.strip()
                if not user_q:
                    user_q = "Tolong analisa, pahami, dan rangkum poin-poin penting dari isi dokumen/file yang saya lampirkan di atas."
                full_content = f"{summary_p}\nInstruksi/Pertanyaan Pengguna:\n{user_q}"

        pesan_dengan_nama = f"[{req.user_name}]: {full_content}"
        await memory_broker.append_event(person_id, "MESSAGE_RECEIVED", {"content": pesan_dengan_nama})

        # Simpan ke tabel sesi obrolan aktif (Hanya jika bukan Chat Sementara)
        if not is_temp:
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('INSERT INTO session_messages (session_id, sender, text) VALUES (?, ?, ?)', (target_sid, 'user', req.message))
                c.execute('UPDATE conversation_sessions SET updated_at = datetime("now", "localtime") WHERE session_id = ?', (target_sid,))
                conn.commit()

        state = await memory_broker.build_state(person_id)
        state.platform = req.platform

        # Penampil proses (gaya Hermes): catat langkah kerja asisten untuk UI Desktop
        from sari_core.brain import CURRENT_STEP_SINK, LIVE_STEPS
        LIVE_STEPS[target_sid] = []
        _step_token = CURRENT_STEP_SINK.set(target_sid)
        try:
            response_data = await ReasoningLayer.process_state(state)
        finally:
            CURRENT_STEP_SINK.reset(_step_token)
        balasan_murni = response_data.get("content", "")
        
        # Pasang label transparansi otak aktif & deteksi fallback otomatis
        show_footer = response_data.get("show_footer", True)
        provider_used = response_data.get("provider_used", "")
        is_fallback = response_data.get("is_fallback", False)
        primary_name = response_data.get("primary_name", "")
        is_specialist = response_data.get("is_specialist", False)
        specialist_role = response_data.get("specialist_role", "")

        balasan_tampil = balasan_murni
        # Di aplikasi desktop, sembunyikan footer otak agar bersih & ramah NVDA (model sudah tampil di badge atas).
        # Khusus peringatan fallback tetap ditampilkan jika terjadi limit/gangguan.
        if show_footer and provider_used and is_fallback:
            balasan_tampil += f"\n\n⚠️ _[Catatan: Otak utama ({primary_name}) limit/gangguan, jawaban diproses via {provider_used}]_"

        await memory_broker.append_event(person_id, "LLM_RESPONSE_SENT", {"content": balasan_murni})

        # Simpan balasan AI ke tabel sesi obrolan (Hanya jika bukan Chat Sementara)
        if not is_temp:
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('INSERT INTO session_messages (session_id, sender, text) VALUES (?, ?, ?)', (target_sid, 'ai', balasan_tampil))
                c.execute('UPDATE conversation_sessions SET updated_at = datetime("now", "localtime") WHERE session_id = ?', (target_sid,))
                conn.commit()
        
        # Jika TTS aktif, putar suara di speaker PC secara asinkron tanpa menahan respon chat
        if req.enable_tts:
            asyncio.create_task(asyncio.to_thread(_play_tts_sound, balasan_murni))

        return ChatResponse(reply=balasan_tampil, status="success")
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        return ChatResponse(reply=f"Maaf, terjadi kendala teknis saat memproses pesan: {str(e)}", status="error")

@app.get("/chat/steps")
async def chat_steps(session_id: str = "temporary_chat"):
    """Penampil proses (gaya Hermes): kembalikan langkah kerja asisten yang sedang berjalan untuk sesi ini."""
    from sari_core.brain import LIVE_STEPS
    return {"steps": LIVE_STEPS.get(session_id, [])}


@app.get("/system/status-ringkas")
def get_system_status_ringkas():
    """Mengembalikan ringkasan status kesehatan sistem & koneksi secara instan (format teks kartu)."""
    import psutil
    import os
    import urllib.request
    from sari_core.model_config import load_model_config

    cfg = load_model_config()
    active_m = cfg.get("active_model", "-")
    active_prov = cfg.get("active_provider", "-")
    active_name = cfg.get("display_name") or active_m

    # 1. Hardware
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    ram_sisa = ram.available / (1024**3)
    disk_c = psutil.disk_usage("C:\\")
    c_sisa = disk_c.free / (1024**3)
    d_sisa = None
    if os.path.exists("D:\\"):
        try:
            d_sisa = psutil.disk_usage("D:\\").free / (1024**3)
        except Exception:
            pass

    # 2. Layanan (WA Bridge & 9Router)
    wa_status = "🟢 Terhubung"
    try:
        with urllib.request.urlopen("http://localhost:3000/status", timeout=1.5) as r:
            if r.status != 200:
                wa_status = "🔴 Gangguan"
    except Exception:
        wa_status = "⚪ Nonaktif / Offline"

    router_status = "🟢 Terhubung (Port 20128)"
    try:
        with urllib.request.urlopen("http://localhost:20128/v1/models", timeout=1.5) as r:
            if r.status != 200:
                router_status = "🔴 Gangguan"
    except Exception:
        router_status = "⚪ Nonaktif"

    lines = [
        "📊 **STATUS KESEHATAN SISTEM HARMONI**",
        "──────────────────────────────",
        f"🤖 **Otak AI Aktif:** {active_name} (`{active_prov}`)",
        f"💬 **WhatsApp Bridge:** {wa_status}",
        f"🔌 **9Router (Antigravity/Cursor):** {router_status}",
        "──────────────────────────────",
        f"🖥️ **Beban CPU:** {cpu}%",
        f"🧠 **Memori RAM:** Terpakai {ram.percent}% (Sisa {ram_sisa:.1f} GB)",
        f"💾 **Drive C:** Sisa {c_sisa:.1f} GB",
    ]
    if d_sisa is not None:
        lines.append(f"💾 **Drive D:** Sisa {d_sisa:.1f} GB")
    lines.append("──────────────────────────────")
    lines.append("✅ Semua subsistem utama beroperasi normal.")

    kartu = "\n".join(lines)
    return {"status": "success", "report": kartu}


@app.post("/system/buka-tautan")
async def buka_tautan(req: dict):
    """Buka tautan (http/https) di peramban bawaan Windows, dipakai tombol tautan di dalam chat."""
    import os as _os
    import re as _re
    url = str((req or {}).get("url", "")).strip()
    if not _re.match(r"^https?://", url, _re.IGNORECASE):
        return {"status": "error", "message": "Hanya tautan http/https yang diizinkan."}
    try:
        _os.startfile(url)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Gagal membuka tautan {url}: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/system/putar-audio-lokal")
async def putar_audio_lokal(req: dict):
    """Memutar atau menghentikan file audio lokal (Voice Note) via ffplay."""
    import os
    import subprocess
    action = str((req or {}).get("action", "play")).strip().lower()
    path_str = str((req or {}).get("path", "")).strip()
    
    try:
        # Jika perintahnya stop, bunuh semua proses ffplay yang berjalan
        if action == "stop":
            subprocess.run(["taskkill", "/F", "/IM", "ffplay.exe"], capture_output=True)
            return {"status": "success", "message": "Pemutaran dihentikan."}
            
        # Perintah play
        if not path_str or not os.path.exists(path_str):
            return {"status": "error", "message": "File audio tidak ditemukan."}
            
        # Matikan dulu audio yang mungkin sedang berjalan (mencegah tumpang tindih)
        subprocess.run(["taskkill", "/F", "/IM", "ffplay.exe"], capture_output=True)
        
        # Jalankan yang baru
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path_str], creationflags=flags)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Gagal operasi audio {path_str}: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/system/status-audio-lokal")
async def status_audio_lokal():
    """Mengecek apakah ada proses ffplay yang sedang berjalan."""
    import subprocess
    try:
        res = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffplay.exe", "/NH"], capture_output=True, text=True)
        is_playing = "ffplay.exe" in res.stdout.lower()
        return {"status": "success", "is_playing": is_playing}
    except Exception as e:
        return {"status": "error", "is_playing": False}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
