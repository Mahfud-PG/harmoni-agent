"""
Harmoni Agent - Telegram Listener
Menangani pesan masuk Telegram, menu tombol model AI, sakelar admin WA, dan jembatan ke otak Harmoni.
"""

import os
import sys
import json
import time
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

PROGRAM_DIR = Path(__file__).parent.resolve()
if str(PROGRAM_DIR) not in sys.path:
    sys.path.insert(0, str(PROGRAM_DIR))

from sari_core.paths import DATA_ROOT  # folder data pengguna
AI_ASISTEN_DIR = DATA_ROOT

load_dotenv(AI_ASISTEN_DIR / ".env")

logger = logging.getLogger("HarmoniTelegram")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from sari_core.bridge import process_telegram_message_async
from sari_core.paths import OBSIDIAN_DIR, PROJECT_ROOT

# Batas waktu maksimal satu putaran jawaban (detik) agar bot tidak pernah diam membisu
BATAS_DETIK_JAWAB = 150.0

PROVIDERS = [
    ("9router", "9Router (Lokal Antigravity)"),
    ("openrouter", "OpenRouter (Katalog Global)"),
    ("gemini", "Google Gemini"),
    ("deepseek", "DeepSeek Official"),
    ("openai", "OpenAI"),
    ("groq", "Groq Cloud"),
    ("cerebras", "Cerebras (Inference 2000+ tps)"),
    ("sambanova", "SambaNova Cloud"),
    ("together", "Together AI"),
    ("mistral", "Mistral AI"),
    ("qwen", "Alibaba Qwen"),
    ("mimo", "Xiaomi MiMo (MiMo V2.5)"),
    ("perplexity", "Perplexity AI"),
    ("xai", "xAI Grok"),
    ("cohere", "Cohere"),
    ("ollama", "Local Ollama"),
]

PAGE_SIZE = 8

# Registry pesan yang sedang menunggu balasan cepat Telegram: chat_id -> target_dict
_TELEGRAM_PENDING_SESSION_REPLY = {}

def get_user_call_name() -> str:
    """Mengambil nama panggilan pengguna secara dinamis dari personalisasi.json."""
    try:
        p_file = AI_ASISTEN_DIR / "personalisasi.json"
        if p_file.exists():
            with open(p_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d.get("user_call_name") or "Pengguna"
    except Exception:
        pass
    return "Pengguna"


def get_provider_keyboard(active_prov: str = ""):
    keyboard = []
    for pid, pname in PROVIDERS:
        prefix = "✓ " if pid == active_prov.lower() else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{pname}", callback_data=f"prov:{pid}")])
    keyboard.append([InlineKeyboardButton("❌ Tutup Menu", callback_data="model:close")])
    return InlineKeyboardMarkup(keyboard)


def get_models_keyboard(provider: str, page: int = 0):
    from server_core import get_provider_models
    from sari_core.model_config import load_model_config

    cfg = load_model_config()
    current_active_model = cfg.get("active_model", "")

    res = get_provider_models(provider)
    models = res.get("models", [])

    total_pages = max(1, (len(models) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * PAGE_SIZE
    page_models = models[start_idx:start_idx + PAGE_SIZE]

    keyboard = []
    for offset, m in enumerate(page_models):
        m_id = m if isinstance(m, str) else m.get("id", "")
        m_name = m_id.split("/")[-1] if "/" in m_id else m_id
        if len(m_name) > 34:
            m_name = m_name[:31] + "..."
        prefix = "✓ " if m_id == current_active_model else ""
        idx = start_idx + offset
        keyboard.append([InlineKeyboardButton(f"{prefix}{m_name}", callback_data=f"selm:{provider}:{page}:{idx}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Mundur", callback_data=f"mpage:{provider}:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"Hal {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Maju ▶", callback_data=f"mpage:{provider}:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton("◀ Pilih Provider Lain", callback_data="prov:list"),
        InlineKeyboardButton("❌ Tutup", callback_data="model:close"),
    ])
    return InlineKeyboardMarkup(keyboard), len(models), page + 1, total_pages


TG_SESSION_FILE = AI_ASISTEN_DIR / "telegram_session.json"

def get_telegram_active_session() -> tuple[str, str]:
    """Mengambil session_id dan judul yang sedang aktif untuk Telegram."""
    from sari_core.db_manager import db
    sid = "temporary_chat"
    if TG_SESSION_FILE.exists():
        try:
            with open(TG_SESSION_FILE, "r", encoding="utf-8") as f:
                sid = json.load(f).get("active_session_id", "temporary_chat")
        except Exception:
            pass

    if sid == "temporary_chat" or str(sid).startswith("temp"):
        return "temporary_chat", "Chat Sementara (Lepas / Bebas)"

    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT session_id, title FROM conversation_sessions WHERE session_id = ?', (sid,))
            row = c.fetchone()
            if row:
                return row['session_id'], row['title']
            c.execute('SELECT session_id, title FROM conversation_sessions WHERE is_active = 1')
            row2 = c.fetchone()
            if row2:
                return row2['session_id'], row2['title']
    except Exception:
        pass
    return "temporary_chat", "Chat Sementara (Lepas / Bebas)"

def set_telegram_active_session(session_id: str) -> None:
    """Menyimpan session_id aktif untuk Telegram."""
    try:
        with open(TG_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"active_session_id": session_id}, f, indent=2)
    except Exception as e:
        logger.error(f"Gagal simpan telegram active session: {e}")

def get_sessions_keyboard(active_session_id: str) -> tuple[InlineKeyboardMarkup, list]:
    """Menyusun tombol interaktif inline keyboard untuk daftar obrolan yang tersinkronisasi."""
    from sari_core.db_manager import db
    sessions = []
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT session_id, title, updated_at FROM conversation_sessions ORDER BY updated_at DESC')
            sessions = [dict(r) for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Gagal baca daftar sesi untuk Telegram: {e}")

    keyboard = []
    keyboard.append([InlineKeyboardButton("➕ Buat Obrolan Baru", callback_data="sess:new")])

    for s in sessions:
        sid = s["session_id"]
        title = s.get("title", "Obrolan")
        if len(title) > 28:
            title = title[:25] + "..."
        is_active = (sid == active_session_id)
        prefix = "✓ " if is_active else "💬 "
        keyboard.append([InlineKeyboardButton(f"{prefix}{title}", callback_data=f"sess:open:{sid}")])

    is_temp = (active_session_id == "temporary_chat" or str(active_session_id).startswith("temp"))
    pref_temp = "✓ " if is_temp else "⚡ "
    keyboard.append([InlineKeyboardButton(f"{pref_temp}Chat Sementara", callback_data="sess:temp")])
    keyboard.append([InlineKeyboardButton("❌ Tutup", callback_data="sess:close")])

    return InlineKeyboardMarkup(keyboard), sessions


def _cari_nomor_model(model_id: str) -> str:
    """Cari nomor urut di menu untuk sebuah model id (agar set_active_model bekerja)."""
    try:
        from sari_core.model_config import load_model_config
        models = load_model_config().get("available_models", {})
        for mid, m in models.items():
            if m.get("id") == model_id:
                return str(mid)
    except Exception as e:
        logger.error(f"Gagal mencari nomor model: {e}")
    return ""


async def handle_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani semua tombol menu model dan sesi obrolan (inline keyboard)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "noop":
        return

    # ==== HANDLER PILIH PROFIL JADWAL WHATSAPP ====
    if data.startswith("sched_wa:"):
        parts = data.split(":")
        if len(parts) >= 3:
            task_id = parts[1]
            target_pid = parts[2]
            file_jadwal = OBSIDIAN_DIR / "01_Konteks_Aktif" / "Jadwal_Tugas_Eksekusi.json"
            b_name = target_pid
            waktu_str_item = "Sesuai Jadwal"
            pesan_item = ""
            try:
                if file_jadwal.exists():
                    with open(file_jadwal, "r", encoding="utf-8") as f_j:
                        daftar = json.load(f_j)
                    for item in daftar:
                        if item.get("id") == task_id:
                            if not isinstance(item.get("params"), dict):
                                item["params"] = {}
                            item["params"]["profile_id"] = target_pid
                            waktu_str_item = item.get("waktu_str", waktu_str_item)
                            pesan_item = item.get("laporan") or item.get("pesan_atau_prompt", "")
                            break
                    with open(file_jadwal, "w", encoding="utf-8") as f_j:
                        json.dump(daftar, f_j, indent=2)

                multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
                if multi_file.exists():
                    with open(multi_file, "r", encoding="utf-8") as mf:
                        m_cfg = json.load(mf)
                        p_info = m_cfg.get("profiles", {}).get(target_pid, {})
                        b_name = p_info.get("business_name") or p_info.get("label") or f"Profil {target_pid}"

                num_s = target_pid.replace("nomor_", "")
                txt_res = (
                    f"✅ **Nomor Pengirim Terpasang!**\n\n"
                    f"📱 **Profil WhatsApp:** Profil {num_s} — **{b_name}**\n"
                    f"⏰ **Waktu:** {waktu_str_item}\n"
                    f"💬 **Tugas:** {pesan_item}\n\n"
                    f"Pesan akan otomatis dikirim menggunakan nomor usaha ini saat jadwal tiba."
                )
                await query.edit_message_text(txt_res, parse_mode="Markdown")
                return
            except Exception as e_wa_btn:
                logger.error(f"Gagal simpan profil tombol jadwal WA: {e_wa_btn}")
                await query.edit_message_text(f"⚠️ Gagal memperbarui jadwal: {e_wa_btn}")
                return

    # ==== HANDLER EKSEKUSI KIRIM LANGSUNG WHATSAPP DENGAN TOMBOL ====
    if data.startswith("send_wa:"):
        parts = data.split(":")
        if len(parts) >= 3:
            send_id = parts[1]
            target_pid = parts[2]
            try:
                from plugins.whatsapp_plugin import eksekusi_pending_send_wa
                ok, txt_resp = await asyncio.to_thread(eksekusi_pending_send_wa, send_id, target_pid)
                await query.edit_message_text(txt_resp, parse_mode="Markdown")
                return
            except Exception as e_send_btn:
                logger.error(f"Gagal eksekusi tombol send WA: {e_send_btn}")
                await query.edit_message_text(f"⚠️ Gagal mengirim: {e_send_btn}")
                return

    if data.startswith("send_wa_cancel:"):
        send_id = data.split("send_wa_cancel:", 1)[1]
        try:
            pending_file = PROJECT_ROOT / "pending_wa_sends.json"
            if pending_file.exists():
                with open(pending_file, "r", encoding="utf-8") as pf:
                    p_data = json.load(pf)
                if send_id in p_data:
                    p_data.pop(send_id)
                    with open(pending_file, "w", encoding="utf-8") as pf:
                        json.dump(p_data, pf, indent=2)
        except Exception:
            pass
        await query.edit_message_text("❌ **Pengiriman WhatsApp Dibatalkan.**", parse_mode="Markdown")
        return

    # ==== HANDLER BALAS CEPAT TELEGRAM (WA, EMAIL, DLL) ====
    if data.startswith("qr_act:"):
        reply_id = data.split("qr_act:", 1)[1]
        from sari_core.quick_reply_broker import get_reply_target
        target = get_reply_target(reply_id)
        if not target:
            await query.edit_message_text("⚠️ Data pesan ini sudah kadaluarsa atau sudah dibalas sebelumnya.")
            return

        chat_id = str(query.message.chat_id)
        _TELEGRAM_PENDING_SESSION_REPLY[chat_id] = target
        ch_name = "WhatsApp" if target.get("channel") == "whatsapp" else "Email"
        target_name = target.get("name") or target.get("to")
        txt = (
            f"✍️ **Ketik Balasan untuk {target_name} ({ch_name}):**\n\n"
            f"Ketik teks balasan Anda langsung di obrolan ini, pesan akan otomatis dikirimkan ke {ch_name} penerima.\n\n"
            f"💡 _Ketik /batal atau klik tombol di bawah untuk membatalkan._"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal Balas", callback_data="qr_cancel")]])
        await query.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    if data == "qr_cancel":
        chat_id = str(query.message.chat_id)
        _TELEGRAM_PENDING_SESSION_REPLY.pop(chat_id, None)
        await query.edit_message_text("❌ **Balasan Dibatalkan.**", parse_mode="Markdown")
        return

    # ==== HANDLER SESI OBROLAN TELEGRAM ====
    if data == "sess:close":
        await query.edit_message_text("Menu obrolan ditutup. Ketik /obrolan untuk membuka kembali.")
        return

    if data == "sess:new":
        txt = (
            "➕ **Buat Obrolan Baru**\n\n"
            "Silakan ketik perintah `/new` diikuti judul obrolan yang Anda inginkan.\n\n"
            "Contoh:\n"
            "`/new Aransemen Musik Akustik`\n\n"
            "Topik obrolan baru akan langsung dibuat dan aktif di Telegram serta Desktop."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Kembali ke Daftar Obrolan", callback_data="sess:list")]])
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    if data == "sess:list":
        cur_sid, cur_title = get_telegram_active_session()
        kb, sessions = get_sessions_keyboard(cur_sid)
        txt = (
            f"📑 **Daftar Obrolan Harmoni (Sinkron Desktop)**\n\n"
            f"📌 Obrolan Aktif di Telegram Saat Ini:\n**{cur_title}**\n\n"
            f"Silakan klik salah satu obrolan di bawah untuk beralih topik:"
        )
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    if data == "sess:temp":
        new_temp_sid = f"temp_tg_{int(time.time())}"
        set_telegram_active_session(new_temp_sid)
        u_call = get_user_call_name()
        txt = (
            "⚡ **Mode Chat Sementara Aktif**\n\n"
            f"Pesan yang {u_call} kirim via Telegram sekarang bersifat sementara (tidak disimpan ke topik obrolan manapun).\n\n"
            "💡 _Ketik /obrolan kapan saja untuk beralih ke obrolan tersimpan._"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📑 Buka Daftar Obrolan", callback_data="sess:list")]])
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("sess:open:"):
        target_sid = data.split("sess:open:", 1)[1]
        set_telegram_active_session(target_sid)
        from sari_core.db_manager import db
        title_found = "Obrolan"
        try:
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT title FROM conversation_sessions WHERE session_id = ?', (target_sid,))
                r = c.fetchone()
                if r:
                    title_found = r['title']
        except Exception:
            pass

        txt = (
            f"✅ **Telegram Terhubung ke Obrolan:**\n"
            f"💬 **{title_found}**\n\n"
            f"Semua pertanyaan dan percakapan berikutnya di Telegram sekarang tersinkronisasi langsung dengan topik ini di laptop.\n\n"
            f"💡 _Ketik /obrolan kapan saja untuk beralih topik._"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📑 Pilih Obrolan Lain", callback_data="sess:list")]])
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    # ==== HANDLER MODEL & PROVIDER ====

    if data == "model:close":
        await query.edit_message_text("Menu pemilihan model ditutup. Ketik /model untuk membuka kembali.")
        return

    if data == "prov:list":
        from sari_core.model_config import load_model_config
        cfg = load_model_config()
        curr_p = cfg.get("active_provider", "9router")
        curr_m = cfg.get("display_name", cfg.get("active_model", "-"))
        txt = (
            f"🧠 **Menu Otak & Model Harmoni Agent**\n\n"
            f"📌 Otak Aktif Saat Ini: **{curr_m}** ({curr_p})\n\n"
            f"Silakan pilih **Provider** di bawah ini untuk melihat daftar modelnya:"
        )
        await query.edit_message_text(txt, reply_markup=get_provider_keyboard(curr_p), parse_mode="Markdown")
        return

    if data.startswith("prov:"):
        prov = data.split(":", 1)[1]
        kb, total, cur_page, total_p = get_models_keyboard(prov, page=0)
        txt = (
            f"🌐 **Katalog Model Provider: {prov.upper()}**\n"
            f"Total tersedia: {total} model (Halaman {cur_page}/{total_p})\n\n"
            f"Pilih salah satu model di bawah untuk langsung mengaktifkannya:"
        )
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("mpage:"):
        parts = data.split(":")
        try:
            prov = parts[1]
            page = int(parts[2])
        except (IndexError, ValueError):
            await query.edit_message_text("❌ Data halaman tidak valid. Ketik /model untuk membuka ulang menu.")
            return
        kb, total, cur_page, total_p = get_models_keyboard(prov, page=page)
        txt = (
            f"🌐 **Katalog Model Provider: {prov.upper()}**\n"
            f"Total tersedia: {total} model (Halaman {cur_page}/{total_p})\n\n"
            f"Pilih salah satu model di bawah untuk langsung mengaktifkannya:"
        )
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("selm:"):
        parts = data.split(":")
        try:
            prov = parts[1]
            idx = int(parts[3])
        except (IndexError, ValueError):
            await query.edit_message_text("❌ Data model tidak valid. Ketik /model untuk membuka ulang menu.")
            return

        from server_core import get_provider_models
        from sari_core.model_config import verify_and_add_model, set_active_model

        models = get_provider_models(prov).get("models", [])
        if not (0 <= idx < len(models)):
            await query.edit_message_text("❌ Model tidak ditemukan atau menu sudah kadaluarsa. Ketik /model untuk membuka ulang.")
            return

        chosen_model = models[idx]
        disp_name = chosen_model.split("/")[-1]

        pesan_daftar = ""
        nomor = _cari_nomor_model(chosen_model)
        if not nomor:
            ok, msg, info = verify_and_add_model(model_id=chosen_model, display_name=disp_name, provider=prov)
            if ok:
                nomor = _cari_nomor_model(chosen_model)
                pesan_daftar = "\n📥 Model baru otomatis didaftarkan ke menu."
            else:
                logger.info(f"Model {chosen_model} sudah terdaftar atau gagal daftar: {msg}")

        aktif_ok = False
        pesan_aktif = ""
        if nomor:
            aktif_ok, pesan_aktif, _ = set_active_model(nomor)
        else:
            aktif_ok, pesan_aktif, _ = set_active_model(chosen_model)

        if aktif_ok:
            txt = (
                f"✅ **Otak AI Berhasil Diganti!**\n\n"
                f"🧠 **Model Aktif:** `{chosen_model}`\n"
                f"🌐 **Provider:** `{prov}`{pesan_daftar}\n\n"
                f"Harmoni Agent langsung siap memakai otak baru ini."
            )
        else:
            txt = f"⚠️ Model `{chosen_model}` belum bisa diaktifkan.\n\n{pesan_aktif}"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ Pilih Model Lain", callback_data=f"prov:{prov}")],
            [InlineKeyboardButton("🌐 Ganti Provider", callback_data="prov:list")],
            [InlineKeyboardButton("❌ Selesai", callback_data="model:close")],
        ])
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = str(update.effective_chat.id)
    u_call = get_user_call_name()
    user_name = update.effective_user.first_name or u_call
    text = update.message.text
    lower = text.strip().lower()

    logger.info(f"[TG Masuk] chat={chat_id} teks={text[:150]}")

    # 00. INTERCEPT BALASAN CEPAT TELEGRAM (WA, EMAIL, DLL)
    if chat_id in _TELEGRAM_PENDING_SESSION_REPLY:
        target = _TELEGRAM_PENDING_SESSION_REPLY.pop(chat_id)
        if lower in ("/batal", "batal", "cancel", "/cancel"):
            await update.message.reply_text("❌ **Balasan dibatalkan.**", parse_mode="Markdown")
            return

        ch = target.get("channel")
        to_addr = target.get("to")
        target_name = target.get("name") or to_addr

        if ch == "whatsapp":
            target_pid = target.get("profile_id") or "nomor_1"
            from plugins.whatsapp_plugin import kirim_pesan_whatsapp
            res_str = await asyncio.to_thread(kirim_pesan_whatsapp, to_addr, text, profile_id=target_pid, force_send=True)
            if "Berhasil" in str(res_str) or "✅" in str(res_str):
                await update.message.reply_text(
                    f"✅ **Balasan Terkirim ke WhatsApp!**\n\n"
                    f"👤 **Penerima:** {target_name} (`{to_addr}`)\n"
                    f"📱 **Profil Pengirim:** `{target_pid}`\n"
                    f"💬 **Pesan:** \"{text}\"",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ Gagal mengirim balasan WhatsApp:\n{res_str}")
            return

        elif ch == "email":
            subj = target.get("subject") or "Pesan"
            reply_subj = f"Re: {subj}" if not subj.lower().startswith("re:") else subj
            from bot_otomatis import kirim_email
            res_str = await asyncio.to_thread(kirim_email, to_addr, reply_subj, text)
            if "Berhasil" in str(res_str) or "terkirim" in str(res_str).lower():
                await update.message.reply_text(
                    f"✅ **Balasan Terkirim via Email!**\n\n"
                    f"👤 **Penerima:** {target_name} (`{to_addr}`)\n"
                    f"📑 **Subjek:** {reply_subj}\n"
                    f"💬 **Pesan:** \"{text}\"",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ Gagal mengirim balasan email:\n{res_str}")
            return

    # Sinyal typing ke pengguna
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception as e:
        logger.warning(f"Gagal kirim sinyal typing: {e}")

    # 0A. SAKELAR ADMIN & NOTIF EMAIL
    if any(k in lower for k in ["admin email", "notif email", "status email", "menu email", "/email"]):
        from email_listener import baca_konfigurasi_email, simpan_konfigurasi_email
        cfg_em = baca_konfigurasi_email()
        is_turn_on = any(k in lower for k in ["on", "nyala", "nyalakan", "aktif", "aktifkan", "hidup", "hidupkan", "start"])
        is_turn_off = any(k in lower for k in ["off", "mati", "matikan", "nonaktif", "nonaktifkan", "stop"])

        if "admin email" in lower:
            if is_turn_on:
                cfg_em["admin_email_enabled"] = True
                simpan_konfigurasi_email(cfg_em)
                await update.message.reply_text("🟢 **Admin Email DIAKTIFKAN!**\nHarmoni sekarang memantau dan membalas email masuk secara otomatis dengan AI.", parse_mode="Markdown")
                return
            elif is_turn_off:
                cfg_em["admin_email_enabled"] = False
                simpan_konfigurasi_email(cfg_em)
                await update.message.reply_text("🔴 **Admin Email DINONAKTIFKAN!**\nHarmoni berhenti membalas email otomatis.", parse_mode="Markdown")
                return

        if "notif email" in lower:
            if is_turn_on:
                cfg_em["notify_telegram"] = True
                simpan_konfigurasi_email(cfg_em)
                await update.message.reply_text("🔔 **Notifikasi Email Telegram DIAKTIFKAN!**\nSetiap ada email baru masuk, Harmoni akan melapor ke Telegram.", parse_mode="Markdown")
                return
            elif is_turn_off:
                cfg_em["notify_telegram"] = False
                simpan_konfigurasi_email(cfg_em)
                await update.message.reply_text("🔕 **Notifikasi Email Telegram DINONAKTIFKAN!**\nHarmoni tidak akan mengirim notifikasi email ke Telegram.", parse_mode="Markdown")
                return

        st_admin = "🟢 AKTIF (Balas Otomatis AI)" if cfg_em.get("admin_email_enabled") else "🔴 NONAKTIF"
        st_notif = "🔔 AKTIF (Lapor ke Telegram)" if cfg_em.get("notify_telegram") else "🔕 NONAKTIF"
        em_addr = os.getenv("EMAIL_ADDRESS") or "Belum disetel"
        txt = (
            f"📧 **Status Layanan Email Harmoni:**\n\n"
            f"📬 Akun: `{em_addr}`\n"
            f"🤖 Admin Balas Otomatis: {st_admin}\n"
            f"🔔 Notifikasi Telegram: {st_notif}\n\n"
            f"💡 *Perintah Cepat:*\n"
            f"- `admin email on` / `admin email off`\n"
            f"- `notif email on` / `notif email off`"
        )
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    # 0B. SAKELAR SATPAM & NOTIF YOUTUBE
    if any(k in lower for k in ["satpam youtube", "notif youtube", "status youtube", "admin youtube", "menu youtube", "/youtube"]):
        from email_listener import baca_konfigurasi_youtube, simpan_konfigurasi_youtube
        cfg_yt = baca_konfigurasi_youtube()
        is_turn_on = any(k in lower for k in ["on", "nyala", "nyalakan", "aktif", "aktifkan", "hidup", "hidupkan", "start"])
        is_turn_off = any(k in lower for k in ["off", "mati", "matikan", "nonaktif", "nonaktifkan", "stop"])

        if "satpam youtube" in lower or "admin youtube" in lower:
            if is_turn_on:
                cfg_yt["satpam_youtube_enabled"] = True
                simpan_konfigurasi_youtube(cfg_yt)
                await update.message.reply_text("🟢 **Satpam Komentar YouTube DIAKTIFKAN!**\nHarmoni memantau komentar baru di channel YouTube Anda.", parse_mode="Markdown")
                return
            elif is_turn_off:
                cfg_yt["satpam_youtube_enabled"] = False
                simpan_konfigurasi_youtube(cfg_yt)
                await update.message.reply_text("🔴 **Satpam Komentar YouTube DINONAKTIFKAN!**", parse_mode="Markdown")
                return

        if "notif youtube" in lower:
            if is_turn_on:
                cfg_yt["notify_telegram"] = True
                simpan_konfigurasi_youtube(cfg_yt)
                await update.message.reply_text("🔔 **Notifikasi YouTube Telegram DIAKTIFKAN!**", parse_mode="Markdown")
                return
            elif is_turn_off:
                cfg_yt["notify_telegram"] = False
                simpan_konfigurasi_youtube(cfg_yt)
                await update.message.reply_text("🔕 **Notifikasi YouTube Telegram DINONAKTIFKAN!**", parse_mode="Markdown")
                return

        st_satpam = "🟢 AKTIF (Pantau Komentar)" if cfg_yt.get("satpam_youtube_enabled") else "🔴 NONAKTIF"
        st_notif = "🔔 AKTIF (Lapor ke Telegram)" if cfg_yt.get("notify_telegram") else "🔕 NONAKTIF"
        txt = (
            f"▶️ **Status Layanan YouTube Harmoni:**\n\n"
            f"👮 Satpam Komentar: {st_satpam}\n"
            f"🔔 Notifikasi Telegram: {st_notif}\n\n"
            f"💡 *Perintah Cepat:*\n"
            f"- `satpam youtube on` / `satpam youtube off`\n"
            f"- `notif youtube on` / `notif youtube off`"
        )
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    # 0C. SAKELAR SINKRONISASI GOOGLE DRIVE & PENCADANGAN
    #
    # Perintahnya dicocokkan dari FRASA INTINYA ("sinkronisasi drive"), BUKAN dari
    # nama asisten. Akibatnya nama asisten apa pun tetap bekerja:
    #     "lisa nyalakan sinkronisasi drive"    -> dikenali
    #     "harmoni nyalakan sinkronisasi drive" -> dikenali
    #     "nyalakan sinkronisasi drive"         -> dikenali juga (tanpa nama)
    # Tidak ada nama asisten yang dipaku di dalam kode, sehingga perintah tidak
    # pernah rusak walau pengguna mengganti nama asistennya kapan saja.
    _cari = lower.replace("_", " ")
    if "sinkronisasi drive" in _cari or "sync drive" in _cari or "sinkronisasi google drive" in _cari:
        import re as _re
        from sari_core import sinkronisasi_config as cfg_sync

        def _ada(kata: str) -> bool:
            """Cari kata utuh. Penting: 'on' TIDAK boleh cocok dengan 'sinkronisasi'."""
            return _re.search(rf"(?<![a-z]){_re.escape(kata)}(?![a-z])", _cari) is not None

        nama = cfg_sync.nama_asisten()
        bisa_on = any(_ada(k) for k in ["nyalakan", "nyala", "hidupkan", "aktifkan", "aktif", "on", "enable", "start"])
        bisa_off = any(_ada(k) for k in ["matikan", "mati", "nonaktifkan", "nonaktif", "off", "disable", "stop"])

        # Menentukan folder: "sinkronisasi drive folder D:\musik"
        cocok_folder = _re.search(r"folder\s+(.+)$", text.strip(), flags=_re.IGNORECASE)
        if cocok_folder:
            jalur_baru = cocok_folder.group(1).strip().strip('"')
            try:
                Path(jalur_baru).mkdir(parents=True, exist_ok=True)
                cfg_sync.perbarui(folder_lokal=str(Path(jalur_baru)))
                await update.message.reply_text(
                    f"📁 Folder sinkronisasi diubah ke:\n`{jalur_baru}`",
                    parse_mode="Markdown",
                )
            except Exception as e_folder:
                await update.message.reply_text(f"❌ Folder tidak bisa dipakai: {e_folder}")
            return

        # Menentukan nama folder Drive: "sinkronisasi drive nama_drive Hasil Studio"
        cocok_nama = _re.search(r"(?:nama_drive|nama folder|folder drive)\s+(.+)$", text.strip(), flags=_re.IGNORECASE)
        if cocok_nama:
            nama_baru = cocok_nama.group(1).strip().strip('"').strip("/\\")
            if nama_baru:
                cfg_sync.perbarui(folder_drive=nama_baru)
                await update.message.reply_text(
                    f"📁 Folder di Google Drive sekarang bernama:\n`{nama_baru}`",
                    parse_mode="Markdown",
                )
            return

        # Ganti mode: "sinkronisasi drive mode aman" / "mode penuh"
        cocok_mode = _re.search(r"mode\s+(aman|penuh|safe|full)", _cari)
        if cocok_mode:
            pilihan = cocok_mode.group(1)
            mode_baru = cfg_sync.MODE_AMAN if pilihan in ("aman", "safe") else cfg_sync.MODE_PENUH
            cfg_sync.perbarui(mode=mode_baru)
            if mode_baru == cfg_sync.MODE_AMAN:
                ket = "Berkas yang terhapus di satu sisi tetap aman di sisi lain."
            else:
                ket = "Peringatan: berkas yang dihapus di satu sisi IKUT TERHAPUS di sisi lain."
            await update.message.reply_text(
                f"✅ Mode sinkronisasi sekarang: *{pilihan.upper()}*\n{ket}",
                parse_mode="Markdown",
            )
            return

        # Sinkronkan sekarang juga
        if any(k in _cari for k in ["sekarang", "sekarang juga", "jalankan", "paksa"]):
            await update.message.reply_text(f"⏳ {nama} sedang menyinkronkan. Mohon tunggu...")
            try:
                from sari_core.drive_sync_engine import run_sync_cycle
                laporan = await asyncio.to_thread(run_sync_cycle)
                if laporan.get("berhasil"):
                    isi = (
                        f"✅ *Sinkronisasi selesai.*\n\n"
                        f"⬆️ Naik ke Drive: {laporan.get('diunggah', 0)}\n"
                        f"⬇️ Turun dari Drive: {laporan.get('diunduh', 0)}\n"
                        f"🔄 Diperbarui: {laporan.get('diperbarui', 0)}"
                    )
                    if laporan.get("dilewati"):
                        isi += f"\n⏭️ Dilewati (mode aman): {laporan['dilewati']}"
                else:
                    isi = f"❌ Sinkronisasi gagal:\n{laporan.get('pesan')}"
                await update.message.reply_text(isi, parse_mode="Markdown")
            except Exception as e_sync_now:
                await update.message.reply_text(f"❌ Gagal menyinkronkan: {e_sync_now}")
            return

        # Membuat cadangan sekarang juga
        if any(k in _cari for k in ["cadangkan", "cadangan sekarang", "backup sekarang"]):
            await update.message.reply_text(f"⏳ {nama} sedang membuat cadangan lengkap. Mohon tunggu...")
            try:
                from sari_core import cadangan as cad
                hasil = await asyncio.to_thread(cad.buat_cadangan)
                if hasil.get("berhasil"):
                    await update.message.reply_text(
                        f"✅ *Cadangan selesai.*\n\n"
                        f"📦 {hasil.get('pesan')}\n"
                        f"📁 Tersimpan di:\n`{hasil.get('jalur')}`\n\n"
                        f"_Simpan berkas itu di tempat aman. Isinya memuat kunci API dan sesi WhatsApp._",
                        parse_mode="Markdown",
                    )
                else:
                    await update.message.reply_text(f"❌ Cadangan gagal: {hasil.get('pesan')}")
            except Exception as e_cad:
                await update.message.reply_text(f"❌ Gagal mencadangkan: {e_cad}")
            return

        if bisa_on:
            hasil = cfg_sync.perbarui(aktif=True)
            await update.message.reply_text(
                f"🟢 *Sinkronisasi Google Drive NYALA.*\n\n"
                f"{cfg_sync.ringkas()}",
                parse_mode="Markdown",
            )
            return
        if bisa_off:
            cfg_sync.perbarui(aktif=False)
            await update.message.reply_text(
                f"🔴 *Sinkronisasi Google Drive MATI.*\n\n{cfg_sync.ringkas()}",
                parse_mode="Markdown",
            )
            return

        # Tanpa kata nyala/mati -> tampilkan statusnya
        await update.message.reply_text(
            f"☁️ *Status Sinkronisasi Drive*\n\n{cfg_sync.ringkas()}\n\n"
            f"_Perintah:_\n"
            f"- `sinkronisasi drive on` / `off`\n"
            f"- `sinkronisasi drive sekarang`\n"
            f"- `sinkronisasi drive cadangkan`\n"
            f"- `sinkronisasi drive mode aman` / `mode penuh`\n"
            f"- `sinkronisasi drive folder D:\\nama folder`",
            parse_mode="Markdown",
        )
        return

    # Perintah garis miring: /sinkronisasi_drive
    if lower.startswith("/sinkronisasi") or lower.startswith("/sync_drive"):
        from sari_core import sinkronisasi_config as cfg_sync
        argumen = lower.split()[-1] if " " in lower else ""
        if argumen in ("on", "nyalakan", "aktif"):
            cfg_sync.perbarui(aktif=True)
        elif argumen in ("off", "matikan", "nonaktif"):
            cfg_sync.perbarui(aktif=False)
        await update.message.reply_text(
            f"☁️ *Sinkronisasi Drive*\n\n{cfg_sync.ringkas()}\n\n"
            f"_Pakai:_ `/sinkronisasi_drive on` atau `/sinkronisasi_drive off`",
            parse_mode="Markdown",
        )
        return

    # 0. KONTROL SAKELAR ADMIN WA PER PROFIL / SEMUA
    if "admin wa" in lower:
        multi_file = AI_ASISTEN_DIR / "konfigurasi_multi_wa.json"
        legacy_file = AI_ASISTEN_DIR / "konfigurasi_wa.json"
        admin_status_file = AI_ASISTEN_DIR / "admin_wa_status.json"

        data_multi = {"active_profile": "nomor_1", "profiles": {}}
        if multi_file.exists():
            try:
                with open(multi_file, "r", encoding="utf-8") as mf:
                    data_multi = json.load(mf)
            except Exception as e:
                logger.error(f"Gagal baca konfigurasi multi WA: {e}")

        profiles = data_multi.get("profiles", {})

        is_turn_on = any(k in lower for k in ["on", "nyala", "nyalakan", "aktif", "aktifkan", "hidup", "hidupkan", "start"])
        is_turn_off = any(k in lower for k in ["off", "mati", "matikan", "nonaktif", "nonaktifkan", "stop"])

        # Kasus A: "semua" admin wa
        if "semua" in lower:
            if is_turn_on:
                for p in profiles.values():
                    p["admin_wa_enabled"] = True
                status_txt = "🟢 SEMUA Profil WhatsApp BERHASIL DINYALAKAN!"
            elif is_turn_off:
                for p in profiles.values():
                    p["admin_wa_enabled"] = False
                status_txt = "🔴 SEMUA Profil WhatsApp BERHASIL DIMATIKAN!"
            else:
                status_txt = "📌 Format: admin wa semua on  atau  admin wa semua off"

            try:
                with open(multi_file, "w", encoding="utf-8") as mf:
                    json.dump(data_multi, mf, ensure_ascii=False, indent=2)

                act_id = data_multi.get("active_profile", "nomor_1")
                if act_id in profiles:
                    p_act = profiles[act_id]
                    legacy_data = {
                        "admin_wa_enabled": p_act.get("admin_wa_enabled", True),
                        "wa_bot_name": p_act.get("wa_bot_name", "Lisa"),
                        "studio_name": p_act.get("business_name", ""),
                        "studio_address": p_act.get("business_address", ""),
                        "wa_tone": p_act.get("wa_tone", "gaul"),
                        "vip_numbers": p_act.get("vip_numbers", ""),
                        "custom_studio_info": p_act.get("custom_info", ""),
                        "notify_telegram": p_act.get("notify_telegram", True),
                        "auto_transcribe_vn": p_act.get("auto_transcribe_vn", True),
                        "portfolio_links": p_act.get("portfolio_links", ""),
                    }
                    with open(legacy_file, "w", encoding="utf-8") as lf:
                        json.dump(legacy_data, lf, ensure_ascii=False, indent=2)
                    with open(admin_status_file, "w", encoding="utf-8") as af:
                        json.dump({"admin_wa": p_act.get("admin_wa_enabled", True)}, af, indent=2)
            except Exception as e:
                logger.error(f"Gagal simpan status admin WA semua: {e}")
                status_txt += "\n⚠️ Namun gagal menyimpan ke file konfigurasi."

            await update.message.reply_text(status_txt)
            return

        # Kasus B: Sebut nomor spesifik (1, 2, dst) atau nama bot admin
        target_pid = None
        for pid, pdata in profiles.items():
            num_suffix = pid.replace("nomor_", "")
            bot_name_p = (pdata.get("wa_bot_name") or "").lower()
            label_p = (pdata.get("label") or "").lower()

            rujukan = [f"wa {num_suffix}", f"wa_{num_suffix}", f"nomor {num_suffix}"]
            if bot_name_p:
                rujukan.append(f"admin {bot_name_p}")
            if label_p:
                rujukan.append(f"wa {label_p}")

            if any(r in lower for r in rujukan):
                target_pid = pid
                break

        if target_pid:
            p_obj = profiles[target_pid]
            p_label = p_obj.get("label", target_pid)
            p_bot = p_obj.get("wa_bot_name", "Admin")

            if is_turn_on:
                p_obj["admin_wa_enabled"] = True
                msg_resp = f"🟢 Admin WA untuk **{p_label}** ({p_bot}) BERHASIL DIAKTIFKAN!"
            elif is_turn_off:
                p_obj["admin_wa_enabled"] = False
                msg_resp = f"🔴 Admin WA untuk **{p_label}** ({p_bot}) BERHASIL DIMATIKAN (Mode Manual/Libur)."
            else:
                curr_st = "AKTIF" if p_obj.get("admin_wa_enabled") else "NONAKTIF"
                nomor_saja = target_pid.replace("nomor_", "")
                msg_resp = (
                    f"ℹ️ Status {p_label} ({p_bot}) saat ini: **{curr_st}**.\n"
                    f"Untuk ubah ketik: `nyalakan admin wa {nomor_saja}` atau `matikan admin wa {nomor_saja}`."
                )

            try:
                with open(multi_file, "w", encoding="utf-8") as mf:
                    json.dump(data_multi, mf, ensure_ascii=False, indent=2)

                if target_pid == data_multi.get("active_profile", "nomor_1"):
                    legacy_data = {
                        "admin_wa_enabled": p_obj.get("admin_wa_enabled", True),
                        "wa_bot_name": p_obj.get("wa_bot_name", "Lisa"),
                        "studio_name": p_obj.get("business_name", ""),
                        "studio_address": p_obj.get("business_address", ""),
                        "wa_tone": p_obj.get("wa_tone", "gaul"),
                        "vip_numbers": p_obj.get("vip_numbers", ""),
                        "custom_studio_info": p_obj.get("custom_info", ""),
                        "notify_telegram": p_obj.get("notify_telegram", True),
                        "auto_transcribe_vn": p_obj.get("auto_transcribe_vn", True),
                        "portfolio_links": p_obj.get("portfolio_links", ""),
                    }
                    with open(legacy_file, "w", encoding="utf-8") as lf:
                        json.dump(legacy_data, lf, ensure_ascii=False, indent=2)
                    with open(admin_status_file, "w", encoding="utf-8") as af:
                        json.dump({"admin_wa": p_obj.get("admin_wa_enabled", True)}, af, indent=2)
            except Exception as e:
                logger.error(f"Gagal simpan status admin WA {target_pid}: {e}")
                msg_resp += "\n⚠️ Namun gagal menyimpan ke file konfigurasi."

            await update.message.reply_text(msg_resp, parse_mode="Markdown")
            return

        # Kasus C: Tanpa nomor -> beri konfirmasi pengaman
        if is_turn_on or is_turn_off:
            aksi_str = "menyalakan" if is_turn_on else "mematikan"
            aksi_cmd = "on" if is_turn_on else "off"

            list_pilihan = []
            for pid, pdata in profiles.items():
                num_s = pid.replace("nomor_", "")
                p_name = pdata.get("business_name") or pdata.get("label") or pid
                p_bot = pdata.get("wa_bot_name", "Admin")
                st = "🟢 Aktif" if pdata.get("admin_wa_enabled") else "⚪ Mati"
                list_pilihan.append(
                    f"- Nomor {num_s}: **{p_name}** (Admin {p_bot}) [{st}]\n  Ketik: `admin wa {num_s} {aksi_cmd}`"
                )

            u_call = get_user_call_name()
            prompt_konfirmasi = (
                f"🛡️ **Konfirmasi Pengaman Nomor WhatsApp:**\n"
                f"{u_call} ingin {aksi_str} admin WA untuk nomor yang mana?\n\n"
                + "\n".join(list_pilihan)
                + f"\n\n💡 _Atau ketik:_ `admin wa semua {aksi_cmd}` (untuk ubah semua sekaligus)."
            )
            await update.message.reply_text(prompt_konfirmasi, parse_mode="Markdown")
            return

        # Kasus D: Cek status admin wa
        if any(k in lower for k in ["status admin wa", "cek admin wa", "menu admin wa", "/admin_wa"]):
            list_status = []
            for pid, pdata in profiles.items():
                num_s = pid.replace("nomor_", "")
                p_name = pdata.get("business_name") or pdata.get("label") or pid
                p_bot = pdata.get("wa_bot_name", "Admin")
                st = "🟢 AKTIF" if pdata.get("admin_wa_enabled") else "🔴 NONAKTIF"
                list_status.append(f"{num_s}. **{p_name}** ({p_bot}): {st}")

            rekap_st = (
                "📱 **Status Sakelar Admin WhatsApp:**\n\n"
                + "\n".join(list_status)
                + "\n\n💡 Ketik `nyalakan admin wa 1` atau `matikan admin wa 1`."
            )
            await update.message.reply_text(rekap_st, parse_mode="Markdown")
            return

    # 0A2. CEK STATUS KESEHATAN SISTEM TERPADU (/status)
    if lower in ["/status", "/kesehatan", "cek status", "status sistem", "kesehatan pc"]:
        try:
            from server_core import get_system_status_ringkas
            res = get_system_status_ringkas()
            teks_stat = res.get("report", "Status sistem tidak dapat dibaca.")
            await update.message.reply_text(teks_stat, parse_mode="Markdown")
            return
        except Exception as e_stat:
            logger.error(f"Error command /status di Telegram: {e_stat}")
            await update.message.reply_text(f"❌ Gagal membaca status sistem: {e_stat}")
            return

    # 0B. MENU OBROLAN & SINKRONISASI SESI DUA ARAH DENGAN DESKTOP
    if lower in ["/obrolan", "/sessions", "/sesi", "/session", "daftar obrolan", "menu obrolan", "list obrolan"]:
        try:
            cur_sid, cur_title = get_telegram_active_session()
            kb, sessions = get_sessions_keyboard(cur_sid)
            txt = (
                f"📑 **Daftar Obrolan Harmoni (Sinkron Desktop)**\n\n"
                f"📌 Obrolan Aktif di Telegram Saat Ini:\n**{cur_title}**\n\n"
                f"Silakan klik salah satu tombol di bawah untuk beralih topik atau membuka sesi baru:"
            )
            await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception as e_s:
            logger.error(f"Error menu sessions Telegram: {e_s}")
            await update.message.reply_text(f"Gagal memuat daftar obrolan: {e_s}")
            return

    # 0C. CEK PESAN WHATSAPP MASUK CEPAT (DENGAN TOMBOL BALAS LANGSUNG)
    if lower in ["/wa", "/chatwa", "/pesanwa", "cek wa", "cek chat wa", "pesan wa baru", "chat wa baru", "baca chat wa", "baca wa"]:
        try:
            import urllib.request
            url = "http://localhost:3000/unread?limit=5&private_only=true"
            req_u = urllib.request.Request(url)
            with urllib.request.urlopen(req_u, timeout=5) as resp:
                msgs = json.loads(resp.read().decode('utf-8'))

            if not msgs or not isinstance(msgs, list):
                await update.message.reply_text("📩 **Tidak ada pesan WhatsApp baru yang masuk.**", parse_mode="Markdown")
                return

            from sari_core.quick_reply_broker import register_reply_target
            from plugins.whatsapp_plugin import _format_waktu_wib
            import os
            
            txt_res = "📩 **Pesan WhatsApp Masuk Terbaru:**\n\n"
            keyboard_btns = []
            audio_to_send = []
            
            for idx, m in enumerate(msgs[:5], 1):
                s_num = m.get('senderNumber') or m.get('from', '').split('@')[0]
                name_disp = m.get('name') or s_num
                time_disp = _format_waktu_wib(m.get('timestamp', ''))
                body_disp = m.get('body') or "[Media/Pesan Kosong]"
                p_id = m.get('profile') or 'nomor_1'
                num_lbl = p_id.replace('nomor_', '')
                
                rid = register_reply_target(channel="whatsapp", to=s_num, name=name_disp, profile_id=p_id)

                is_vn = m.get('isVoiceNote', False) or "[Voice Note]" in body_disp
                v_path = m.get('voicePath')

                if is_vn and v_path and os.path.exists(v_path):
                    caption = f"🎙️ Voice Note dari {name_disp} (Profil {num_lbl})"
                    audio_to_send.append((v_path, caption, rid))
                    # Tandai bahwa pesan ini adalah VN supaya tidak dobel dikirim tombolnya di daftar teks utama
                    body_disp = "[Voice Note 🎙️ Dikirim ke bawah]"
                else:
                    # Tambahkan tombol Balas hanya untuk pesan teks biasa di kumpulan awal
                    keyboard_btns.append([InlineKeyboardButton(f"💬 Balas {name_disp[:18]}", callback_data=f"qr_act:{rid}")])

                txt_res += f"{idx}. 👤 *{name_disp}* (`{s_num}`)\n"
                txt_res += f"   📱 Profil {num_lbl} | ⏰ {time_disp}\n"
                txt_res += f"   💬 \"{body_disp}\"\n\n"

            txt_res += "💡 _Klik tombol di bawah untuk langsung membalas:_"
            kb = InlineKeyboardMarkup(keyboard_btns) if keyboard_btns else None
            await update.message.reply_text(txt_res, reply_markup=kb, parse_mode="Markdown")
            
            # Kirim Voice Note sebagai pesan audio native di Telegram
            for vp, cap, rid in audio_to_send:
                try:
                    with open(vp, 'rb') as f_audio:
                        nama_pendek = cap.split('dari')[1].split('(')[0].strip()[:18]
                        kb_audio = InlineKeyboardMarkup([[InlineKeyboardButton(f"💬 Balas {nama_pendek}", callback_data=f"qr_act:{rid}")]])
                        await update.message.reply_voice(voice=f_audio, caption=cap, reply_markup=kb_audio)
                except Exception as e_a:
                    logger.error(f"Gagal mengirim VN ke Telegram: {e_a}")
            return
        except Exception as e_wa_chk:
            logger.error(f"Error cek WA cepat di Telegram: {e_wa_chk}")
            await update.message.reply_text(f"⚠️ Gagal memeriksa WhatsApp: {e_wa_chk}")
            return

    # 0D. CEK KUOTA / SALDO MODEL AI CEPAT
    if lower.startswith("/saldo ") or lower.startswith("/kuota ") or lower in ["/kuota", "/saldo", "/token", "cek kuota", "cek saldo", "sisa kuota", "kuota ai", "kuota 9router"]:
        try:
            from plugins.system_plugin import cek_sisa_kuota_token
            # Parsing argumen spesifik (misal /saldo deepseek)
            target_p = ""
            if lower.startswith("/saldo "):
                target_p = lower.replace("/saldo ", "").strip()
            elif lower.startswith("/kuota "):
                target_p = lower.replace("/kuota ", "").strip()
            elif "9router" in lower:
                target_p = "9router"

            res_k = await asyncio.to_thread(cek_sisa_kuota_token, target_p)
            try:
                # Coba kirim Markdown murni dulu
                await update.message.reply_text(res_k, parse_mode="Markdown")
            except Exception as e_md:
                # Jika gagal parse markdown dari Telegram, buang semua bintang dan underscore, lalu kirim ulang
                logger.warning(f"Telegram Markdown parse failed: {e_md}. Stripping markdown and sending plain text.")
                res_clean = res_k.replace("*", "").replace("`", "").replace("_", "")
                await update.message.reply_text(res_clean)
            return
        except Exception as e_k:
            logger.error(f"Error cek kuota cepat Telegram: {e_k}")
            await update.message.reply_text(f"⚠️ Gagal mengecek kuota: {e_k}")
            return

    # Buat topik obrolan baru via /new
    if lower.startswith("/new ") or lower == "/new":
        judul = text.split(" ", 1)[1].strip() if len(text.split(" ", 1)) > 1 else ""
        if not judul:
            await update.message.reply_text(
                "Silakan tulis judul obrolan setelah perintah `/new`.\n\nContoh: `/new Aransemen Musik Akustik`",
                parse_mode="Markdown"
            )
            return

        import uuid
        from datetime import datetime
        from sari_core.db_manager import db
        new_sid = f"sess_{uuid.uuid4().hex[:10]}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('UPDATE conversation_sessions SET is_active = 0')
                c.execute('INSERT INTO conversation_sessions (session_id, title, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)', (new_sid, judul, now_str, now_str))
                conn.commit()

            set_telegram_active_session(new_sid)
            await update.message.reply_text(
                f"🎉 **Obrolan Baru Berhasil Dibuat!**\n\n"
                f"💬 **Topik:** {judul}\n"
                f"✅ Langsung aktif dan tersinkronisasi di Telegram serta Harmoni Desktop.",
                parse_mode="Markdown"
            )
            return
        except Exception as e_c:
            logger.error(f"Gagal membuat obrolan via telegram: {e_c}")
            await update.message.reply_text(f"Gagal membuat obrolan: {e_c}")
            return

    # 1. Perintah langsung Cek Token / Cek Kuota
    if lower in ["cek token", "cek kuota", "/token", "/kuota", "status token"]:
        try:
            from server_core import get_tokens_status
            res = get_tokens_status()
            await update.message.reply_text(res.get("report", "Laporan kuota tidak dapat dimuat."))
            return
        except Exception as e_tok:
            logger.error(f"Error cek token: {e_tok}")
            await update.message.reply_text(f"Gagal memuat laporan kuota: {e_tok}")
            return

    # 1b. Simpan kunci API (multi-kunci koma didukung): /set_key <provider> <kunci1, kunci2>
    if lower.startswith("/set_key ") or lower.startswith("/key "):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("💡 *Format:* `/set_key <provider> <kunci1, kunci2>`\nContoh: `/set_key deepseek sk-111, sk-222`", parse_mode="Markdown")
            return
        prov_target = parts[1].strip()
        key_val = parts[2].strip()
        try:
            from sari_core.model_config import update_env_api_key
            ok_k, msg_k = update_env_api_key(prov_target, key_val)
            await update.message.reply_text(msg_k, parse_mode="Markdown")
            return
        except Exception as e_sk:
            logger.error(f"Error set_key Telegram: {e_sk}")
            await update.message.reply_text(f"⚠️ Gagal menyimpan kunci: {e_sk}")
            return

    # 2. Menu model berbentuk tombol interaktif
    if lower in ["/model", "/otak", "menu model", "status otak"]:
        try:
            from sari_core.model_config import load_model_config
            cfg = load_model_config()
            curr_p = cfg.get("active_provider", "9router")
            curr_m = cfg.get("display_name", cfg.get("active_model", "-"))
            txt = (
                f"🧠 **Menu Otak & Model Harmoni Agent**\n\n"
                f"📌 Otak Aktif Saat Ini: **{curr_m}** ({curr_p})\n\n"
                f"Silakan pilih **Provider** di bawah ini untuk melihat daftar modelnya:"
            )
            await update.message.reply_text(txt, reply_markup=get_provider_keyboard(curr_p), parse_mode="Markdown")
            return
        except Exception as e_m:
            logger.error(f"Error menu model: {e_m}")

    # 3. Ganti model langsung dengan nomor atau nama: /model 3
    if lower.startswith("/model ") or lower.startswith("/otak "):
        target = text.split(" ", 1)[1].strip()
        try:
            from sari_core.model_config import set_active_model
            ok, msg, info = set_active_model(target)
            await update.message.reply_text(msg, parse_mode="Markdown")
            return
        except Exception as e_ms:
            logger.error(f"Error switch model: {e_ms}")

    # 4. Obrolan biasa -> teruskan ke otak Harmoni Agent
    try:
        reply = await asyncio.wait_for(
            process_telegram_message_async(chat_id, user_name, text),
            timeout=BATAS_DETIK_JAWAB,
        )
        if not reply:
            reply = "Siap, tugas telah selesai diproses."
        await update.message.reply_text(reply[:4000])
        # Balon proses (satu pesan dinamis gaya Hermes) dihapus setelah jawaban terkirim.
        # Dengan begitu ruang obrolan cuma berisi: perintah Kakak -> jawaban asisten.
        try:
            from sari_core.brain import _tg_progress_bersihkan
            _tg_progress_bersihkan(chat_id, hapus=True)
        except Exception:
            pass
    except asyncio.TimeoutError:
        logger.error(f"[TG Timeout] Jawaban melebihi {BATAS_DETIK_JAWAB} detik untuk: {text[:80]}")
        u_call = get_user_call_name()
        await update.message.reply_text(
            f"⏱️ Maaf {u_call}, proses jawaban melebihi {int(BATAS_DETIK_JAWAB)} detik sehingga saya hentikan. "
            f"Silakan coba lagi atau ganti model lewat /model."
        )
    except Exception as e:
        logger.error(f"Telegram error: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi kendala teknis: {str(e)}")
        # Gagal: balon proses SENGAJA dibiarkan sebagai jejak bukti (gaya Hermes).


async def kirim_sapaan_startup_async():
    """Mengirim sapaan pembuka ke Telegram pemilik HANYA saat Windows benar-benar baru dinyalakan/direstart."""
    await asyncio.sleep(4)
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return

    # 1. Cek Windows Uptime: Jangan kirim jika ini cuma reload/restart service di background
    try:
        import time
        import psutil
        uptime_sec = time.time() - psutil.boot_time()
        if uptime_sec > 300:
            logger.info(f"Lewati sapaan startup: Windows uptime sudah {int(uptime_sec)}s (bukan booting baru).")
            return
    except Exception as e_boot:
        logger.warning(f"Gagal memeriksa uptime boot Windows: {e_boot}")

    from datetime import datetime
    now = datetime.now()
    jam = now.hour
    if 4 <= jam < 11:
        fase_waktu = "pagi"
    elif 11 <= jam < 15:
        fase_waktu = "siang"
    elif 15 <= jam < 18:
        fase_waktu = "sore"
    else:
        fase_waktu = "malam"
    waktu_str = now.strftime("%H:%M")

    # 2. Pesan sapaan terisolasi: JANGAN panggil process_telegram_message_async agar AI tidak membaca riwayat
    # lama lalu berhalusinasi menjadwalkan ulang tugas yang sudah selesai!
    try:
        from sari_core.model_config import load_model_config
        cfg = load_model_config()
        curr_m = cfg.get("display_name", cfg.get("active_model", "Gemini"))
        u_call = get_user_call_name()
        balasan = (
            f"Selamat {fase_waktu}, {u_call}! Komputer baru saja dinyalakan (pukul {waktu_str}). "
            f"Harmoni Agent dan bot Telegram sudah online dan siap membantu. ☀️✨\n\n"
            f"🧠 _[Otak: {curr_m}]_"
        )
        from core.utils import kirim_pesan_telegram
        kirim_pesan_telegram(balasan)
        logger.info("Sapaan startup Windows berhasil dikirim ke Telegram.")
    except Exception as e_send:
        logger.warning(f"Gagal mengirim sapaan startup ke Telegram: {e_send}")


_CURRENT_TG_APP = None
_TG_RUNNING = False
_TG_LOCK = None

def _get_tg_lock():
    global _TG_LOCK
    if _TG_LOCK is None:
        _TG_LOCK = asyncio.Lock()
    return _TG_LOCK

def is_telegram_running() -> bool:
    global _TG_RUNNING, _CURRENT_TG_APP
    return bool(_TG_RUNNING and _CURRENT_TG_APP is not None)

async def stop_telegram_bot_async():
    global _CURRENT_TG_APP, _TG_RUNNING
    lock = _get_tg_lock()
    async with lock:
        if _CURRENT_TG_APP is not None:
            try:
                logger.info("Menghentikan Telegram Listener...")
                if getattr(_CURRENT_TG_APP, "updater", None) and _CURRENT_TG_APP.updater.running:
                    await _CURRENT_TG_APP.updater.stop()
                if getattr(_CURRENT_TG_APP, "running", False):
                    await _CURRENT_TG_APP.stop()
                await _CURRENT_TG_APP.shutdown()
                logger.info("Telegram Listener berhasil dihentikan.")
            except Exception as e:
                logger.warning(f"Catatan saat menghentikan Telegram Bot: {e}")
            finally:
                _CURRENT_TG_APP = None
                _TG_RUNNING = False

async def start_telegram_bot_async(kirim_sapaan: bool = True):
    global _CURRENT_TG_APP, _TG_RUNNING
    lock = _get_tg_lock()
    async with lock:
        if _TG_RUNNING and _CURRENT_TG_APP is not None:
            logger.info("Telegram Bot sudah aktif, tidak perlu dinyalakan ulang.")
            return

        env_path = AI_ASISTEN_DIR / ".env"
        from dotenv import dotenv_values
        env_vals = dotenv_values(env_path) if env_path.exists() else {}
        enabled_val = env_vals.get("TELEGRAM_BOT_ENABLED", os.getenv("TELEGRAM_BOT_ENABLED", "true")).lower()
        if enabled_val in ["false", "0", "off", "no"]:
            logger.info("TELEGRAM_BOT_ENABLED bernilai false. Listener Telegram dilewati.")
            _TG_RUNNING = False
            return

        token = env_vals.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN tidak ditemukan. Listener Telegram dilewati.")
            _TG_RUNNING = False
            return

        try:
            app = ApplicationBuilder().token(token).concurrent_updates(True).connect_timeout(60.0).read_timeout(60.0).write_timeout(60.0).pool_timeout(60.0).build()
            app.add_handler(CallbackQueryHandler(handle_model_callback))
            app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
            app.add_handler(MessageHandler(filters.COMMAND, handle_message))

            logger.info("Harmoni Telegram Listener sedang menyala...")
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=False, timeout=60)
            _CURRENT_TG_APP = app
            _TG_RUNNING = True

            if kirim_sapaan:
                asyncio.create_task(kirim_sapaan_startup_async())
        except Exception as e:
            logger.error(f"Gagal mengaktifkan Telegram Bot: {e}")
            _CURRENT_TG_APP = None
            _TG_RUNNING = False

async def restart_telegram_bot_async():
    await stop_telegram_bot_async()
    await start_telegram_bot_async(kirim_sapaan=False)
