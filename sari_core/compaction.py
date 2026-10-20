"""
Harmoni Agent - Auto-Compaction Engine
Mengompres dan merangkum riwayat percakapan lama secara otomatis agar:
1. Konteks percakapan lampau tidak hilang saat obrolan panjang.
2. Konsumsi token hemat 70-80% per putaran pesan.
3. Respons AI lebih cepat dan tajam.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional

logger = logging.getLogger("HarmoniCompaction")

# Konfigurasi Threshold
COMPACTION_THRESHOLD_MESSAGES = 18  # Memicu pemadatan jika pesan melebihi ini
KEEP_RECENT_COUNT = 8              # Jumlah pesan aktif terbaru yang tetap dibiarkan utuh
MIN_NEW_MESSAGES_FOR_RECOMPACT = 8 # Jeda pesan baru sebelum memadatkan ulang


def need_compaction(recent_messages: List[Dict[str, Any]], context_pointers: Dict[str, Any]) -> bool:
    """Mengecek apakah percakapan sudah waktunya dipadatkan."""
    if len(recent_messages) < COMPACTION_THRESHOLD_MESSAGES:
        return False
    
    last_compacted_count = context_pointers.get("compacted_message_count", 0)
    current_count = len(recent_messages)
    
    # Jika belum pernah dipadatkan, atau pesan baru sudah bertambah melebihi jeda
    if current_count - last_compacted_count >= MIN_NEW_MESSAGES_FOR_RECOMPACT:
        return True
        
    return False


async def generate_summary(to_compact: List[Dict[str, Any]], existing_summary: str = "") -> Optional[str]:
    """Menghasilkan ringkasan ringkas dari pesan-pesan lampau."""
    from sari_core.model_config import get_provider_keys
    from openai import OpenAI
    import os

    # Format pesan-pesan yang akan diringkas
    lines = []
    if existing_summary:
        lines.append(f"[Ringkasan Sebelumnya]: {existing_summary}")
        
    for m in to_compact:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            lines.append(f"Pengguna: {content}")
        elif role == "assistant":
            # Lewati jika hanya tool calls
            if content:
                lines.append(f"Asisten: {content[:300]}")
        elif role == "tool":
            lines.append(f"[Alat {m.get('name', '')}]: {str(content)[:150]}")
            
    dialog_text = "\n".join(lines)
    if not dialog_text.strip():
        return None

    prompt = (
        "Anda adalah sistem perangkum memori percakapan asisten AI.\n"
        "Tugas Anda: Padatkan percakapan lampau berikut ke dalam 3-5 poin ringkas padat:\n"
        "1. Topik utama atau proyek yang dibahas\n"
        "2. Keputusan, instruksi permanen, atau preferensi yang diminta pengguna\n"
        "3. Aksi teknis yang sudah selesai dan hal yang masih perlu dilanjutkan\n"
        "Aturan: Tulis lugas, faktual, tanpa basa-basi, dalam bahasa Indonesia.\n\n"
        f"Percakapan:\n{dialog_text}"
    )

    # 1. Coba DeepSeek (Super cepat & hemat)
    deepseek_keys = get_provider_keys("deepseek")
    if deepseek_keys:
        try:
            client = OpenAI(base_url="https://api.deepseek.com", api_key=deepseek_keys[0])
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=350,
                temperature=0.3,
                timeout=12.0
            )
            summary = resp.choices[0].message.content.strip()
            if summary:
                return summary
        except Exception as e:
            logger.warning(f"[Compaction] DeepSeek gagal: {e}")

    # 2. Coba Gemini via direct endpoint jika ada key
    gemini_keys = get_provider_keys("gemini")
    if gemini_keys:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_keys[0])
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp = await asyncio.to_thread(model.generate_content, prompt)
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            logger.warning(f"[Compaction] Gemini gagal: {e}")

    # 3. Coba OpenAI / OpenRouter jika ada
    openai_keys = get_provider_keys("openai")
    if openai_keys:
        try:
            client = OpenAI(api_key=openai_keys[0])
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=350,
                temperature=0.3,
                timeout=12.0
            )
            summary = resp.choices[0].message.content.strip()
            if summary:
                return summary
        except Exception as e:
            logger.warning(f"[Compaction] OpenAI gagal: {e}")

    # Fallback lokal ekstraksi poin kata kunci tanpa LLM bila offline
    summary_lines = []
    user_pts = [m.get("content", "") for m in to_compact if m.get("role") == "user" and len(str(m.get("content", "")).split()) > 2]
    if user_pts:
        summary_lines.append("Topik lampau yang dibahas: " + "; ".join(user_pts[-4:]))
    return "\n".join(summary_lines) if summary_lines else None


async def run_auto_compaction_if_needed(state, memory_broker) -> Dict[str, Any]:
    """
    Menjalankan proses pemadatan jika syarat terpenuhi.
    Mengembalikan dict context pointers terbaru.
    """
    recent = state.recent_messages or []
    pointers = state.context_pointers or {}
    
    if not need_compaction(recent, pointers):
        return pointers
        
    logger.info(f"[AutoCompaction] Memicu pemadatan untuk person {state.person_id} ({len(recent)} pesan aktif)")
    
    # Bagi pesan: yang lama diringkas, yang baru dipertahankan
    to_compact = recent[:-KEEP_RECENT_COUNT]
    existing_summary = pointers.get("compacted_summary", "")
    
    summary = await generate_summary(to_compact, existing_summary)
    if summary:
        pointers["compacted_summary"] = summary
        pointers["compacted_message_count"] = len(recent)
        
        # Simpan pembaruan ke event store memory_broker
        try:
            await memory_broker.append_event(
                state.person_id,
                "CONTEXT_POINTER_SET",
                {"key": "compacted_summary", "value": summary}
            )
            await memory_broker.append_event(
                state.person_id,
                "CONTEXT_POINTER_SET",
                {"key": "compacted_message_count", "value": len(recent)}
            )
            logger.info(f"[AutoCompaction] Ringkasan berhasil diperbarui dan disimpan.")
        except Exception as e:
            logger.error(f"[AutoCompaction] Gagal menyimpan pointer ringkasan: {e}")
            
    return pointers
