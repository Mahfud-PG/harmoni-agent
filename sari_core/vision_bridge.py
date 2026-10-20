"""
Harmoni Agent - Vision Bridge via 9Router / OpenAI Compatible
Memungkinkan Harmoni melihat webcam dan membaca layar PC menggunakan model Vision
tanpa bergantung pada saldo API Key Google Cloud resmi (memanfaatkan 9Router lokal).
"""

import os
import base64
import json
import urllib.request
import logging

logger = logging.getLogger(__name__)

def _ambil_kunci_9router() -> str:
    # Coba baca dari config hermes jika ada
    config_hermes = os.path.expanduser(r'~\AppData\Local\hermes\config.yaml')
    if os.path.exists(config_hermes):
        try:
            with open(config_hermes, 'r', encoding='utf-8') as f:
                for line in f:
                    if 'api_key:' in line and 'sk-' in line:
                        return line.split('api_key:')[1].strip()
        except Exception:
            pass
    # Default key lokal 9Router
    return "sk-8c9a8b74b42eeed2-f22xx8-53234acd"

def kirim_gambar_ke_vision(file_path: str, prompt: str, timeout: int = 45) -> str:
    """
    Mengirim berkas gambar lokal ke 9Router Vision (ag/gemini-3.8-flash-medium).
    Mendukung format JPEG / PNG.
    """
    if not os.path.exists(file_path):
        return f"Gagal: Berkas gambar tidak ditemukan: {file_path}"

    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
    mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"

    try:
        with open(file_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": "ag/gemini-3.8-flash-medium",
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                    ]
                }
            ]
        }

        api_key = _ambil_kunci_9router()
        req = urllib.request.Request(
            "http://127.0.0.1:20128/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices and len(choices) > 0:
                konten = choices[0].get("message", {}).get("content", "").strip()
                if konten:
                    return konten
            return "Maaf, Vision AI tidak memberikan teks balasan."
    except Exception as e:
        logger.error(f"[Vision 9Router] Gagal menganalisis gambar: {e}")
        return f"Gagal menganalisis gambar via 9Router: {str(e)}"
