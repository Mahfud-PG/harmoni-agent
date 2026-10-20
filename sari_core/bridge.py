import asyncio
import logging
from sari_core.memory_broker import memory_broker
from sari_core.brain import ReasoningLayer, QualityGate, PersonaLayer
from sari_core.observability import Observability

logger = logging.getLogger(__name__)


def sesi_masih_ada(session_id) -> bool:
    """Cek apakah sesi obrolan masih terdaftar di tabel conversation_sessions.

    Penting: kalau sesi sudah dihapus dari UI Desktop, pointer sesi yang tersimpan
    (mis. di telegram_session.json) menjadi basi. Menyimpan pesan ke session_messages
    memakai kunci asing (foreign key), sehingga tanpa pemeriksaan ini akan muncul
    error 'FOREIGN KEY constraint failed' pada setiap pesan.
    """
    if not session_id:
        return False
    sid = str(session_id)
    if sid == "temporary_chat" or sid.startswith("temp"):
        return False
    try:
        from sari_core.db_manager import db
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM conversation_sessions WHERE session_id = ?", (sid,))
            return c.fetchone() is not None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Gagal memeriksa keberadaan sesi {sid}: {e}")
        return False


async def process_wa_message_async(pengirim_wa: str, nama: str, isi_pesan: str, profile_id: str = None) -> str:
    """
    Asynchronous bridge for WhatsApp to interact with the new Sari AI OS.
    profile_id: ID profil nomor WA yang menerima pesan (agar identitas usaha tidak tertukar).
    """
    trace_id = Observability.generate_trace_id()
    Observability.log_trace(trace_id, "WA_INCOMING", phone=pengirim_wa, message=isi_pesan, profile=profile_id)
    
    # 1. Resolve Identity - diisolasi per profil nomor WA agar riwayat antar nomor usaha tidak saling mencemari
    channel_key = f"{profile_id}:{pengirim_wa}" if profile_id else pengirim_wa
    person_id = await memory_broker.get_or_create_person(channel_key, "WHATSAPP")
    
    # 2. Append User Message
    pesan_dengan_nama = f"[{nama}]: {isi_pesan}"
    await memory_broker.append_event(person_id, "MESSAGE_RECEIVED", {"content": pesan_dengan_nama})
    
    # 3. Build Full Context State
    state = await memory_broker.build_state(person_id)
    state.platform = "WHATSAPP"
    state.wa_profile_id = profile_id
    
    # 4. LLM Reasoning
    response_data = await ReasoningLayer.process_state(state)
    balasan = response_data["content"]
    
    # 6. Append Assistant Response
    await memory_broker.append_event(person_id, "LLM_RESPONSE_SENT", {"content": balasan})
    
    Observability.log_trace(trace_id, "WA_OUTGOING", phone=pengirim_wa, message=balasan)
    
    return balasan

def process_wa_message_sync(pengirim_wa: str, nama: str, isi_pesan: str, profile_id: str = None) -> str:
    """
    Synchronous bridge for WhatsApp to interact with the new Sari AI OS.
    """
    return asyncio.run(process_wa_message_async(pengirim_wa, nama, isi_pesan, profile_id))

async def process_telegram_message_async(chat_id: str, nama: str, isi_pesan: str, session_id_override: str = None) -> str:
    """
    Asynchronous bridge for Telegram to interact with the new Sari AI OS.
    Mendukung isolasi multi-sesi dan sinkronisasi obrolan dua arah dengan Harmoni Desktop.
    """
    trace_id = Observability.generate_trace_id()
    Observability.log_trace(trace_id, "TG_INCOMING", chat_id=chat_id, message=isi_pesan)
    
    # 1. Tentukan Sesi Obrolan Aktif untuk Telegram
    import json
    from sari_core.paths import PROJECT_ROOT
    from sari_core.db_manager import db

    target_sid = session_id_override
    if not target_sid:
        tg_sess_file = PROJECT_ROOT / "telegram_session.json"
        if tg_sess_file.exists():
            try:
                with open(tg_sess_file, "r", encoding="utf-8") as f:
                    target_sid = json.load(f).get("active_session_id")
            except Exception:
                pass

        # Pointer sesi bisa BASI kalau sesinya sudah dihapus dari UI Desktop.
        # Kalau tidak diperiksa, penyimpanan pesan gagal dengan
        # 'FOREIGN KEY constraint failed' pada setiap pesan masuk.
        if target_sid and not sesi_masih_ada(target_sid):
            logger.warning(
                f"Sesi Telegram '{target_sid}' sudah tidak ada (kemungkinan dihapus dari Desktop). "
                "Beralih ke sesi aktif yang tersedia."
            )
            target_sid = None

    if not target_sid:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT session_id FROM conversation_sessions WHERE is_active = 1')
            act = c.fetchone()
            target_sid = act["session_id"] if act else "temporary_chat"

    is_temp = target_sid == "temporary_chat" or str(target_sid).startswith("temp")

    # 2. Resolve Identity: Gunakan channel yang SAMA persis dengan Desktop UI per sesi!
    channel_id = f"desktop_{target_sid}"
    person_id = await memory_broker.get_or_create_person(channel_id, "DESKTOP_UI")

    # Sinkronkan pesan dari session_messages jika events masih kosong
    if not is_temp:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) as cnt FROM events WHERE person_id = ?', (person_id,))
            if c.fetchone()['cnt'] == 0:
                c.execute('SELECT sender, text FROM session_messages WHERE session_id = ? ORDER BY message_id ASC LIMIT 50', (target_sid,))
                past_rows = c.fetchall()
                for pr in past_rows:
                    if pr['sender'] == 'user':
                        await memory_broker.append_event(person_id, "MESSAGE_RECEIVED", {"content": f"[{nama}]: {pr['text']}"})
                    elif pr['sender'] == 'ai':
                        await memory_broker.append_event(person_id, "LLM_RESPONSE_SENT", {"content": pr['text']})

    # 3. Append User Message
    pesan_dengan_nama = f"[{nama}]: {isi_pesan}"
    await memory_broker.append_event(person_id, "MESSAGE_RECEIVED", {"content": pesan_dengan_nama})

    # Simpan juga ke session_messages agar langsung muncul di layar Desktop UI jika sesi disimpan
    if not is_temp:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO session_messages (session_id, sender, text) VALUES (?, ?, ?)', (target_sid, 'user', isi_pesan))
            c.execute('UPDATE conversation_sessions SET updated_at = datetime("now", "localtime") WHERE session_id = ?', (target_sid,))
            conn.commit()

    # 4. Build Full Context State
    state = await memory_broker.build_state(person_id)
    state.platform = "TELEGRAM"

    # 5. LLM Reasoning
    response_data = await ReasoningLayer.process_state(state, chat_id_override=chat_id)
    balasan_murni = response_data["content"]

    # 6. Simpan respons murni ke memori broker
    await memory_broker.append_event(person_id, "LLM_RESPONSE_SENT", {"content": balasan_murni})

    # Simpan balasan AI ke session_messages agar tersinkronisasi di Desktop UI
    if not is_temp:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO session_messages (session_id, sender, text) VALUES (?, ?, ?)', (target_sid, 'ai', balasan_murni))
            c.execute('UPDATE conversation_sessions SET updated_at = datetime("now", "localtime") WHERE session_id = ?', (target_sid,))
            conn.commit()

    # 7. Pasang Label Transparan Bukti Nyata Otak Aktif khusus untuk tampilan Telegram pengguna
    show_footer = response_data.get("show_footer", True)
    provider_used = response_data.get("provider_used", "")
    is_fallback = response_data.get("is_fallback", False)
    primary_name = response_data.get("primary_name", "")
    
    balasan_tampil = balasan_murni

    # Catatan: footer "🧠 _[Otak: ...]_" sudah TIDAK dipakai lagi di Telegram,
    # karena penampil proses (gaya Hermes) sudah mengabarkan otak aktif & perpindahan
    # cadangan pada baris "🧠 Otak: ..." sebelum jawaban. Menghindari informasi dobel.

    Observability.log_trace(trace_id, "TG_OUTGOING", chat_id=chat_id, message=balasan_tampil)
    
    return balasan_tampil

def process_telegram_message_sync(chat_id: str, nama: str, isi_pesan: str) -> str:
    """
    Synchronous wrapper for Telegram bridge.
    """
    return asyncio.run(process_telegram_message_async(chat_id, nama, isi_pesan))


async def process_email_message_async(email_address: str, subjek: str, isi_pesan: str) -> str:
    """
    Asynchronous bridge for Email Auto-Reply.
    """
    trace_id = Observability.generate_trace_id()
    Observability.log_trace(trace_id, "EMAIL_INCOMING", email=email_address, subjek=subjek)
    
    person_id = await memory_broker.get_or_create_person(email_address, "EMAIL")
    
    pesan_masuk = f"Subjek Email: {subjek}\nIsi Email: {isi_pesan}"
    await memory_broker.append_event(person_id, "MESSAGE_RECEIVED", {"content": pesan_masuk})
    
    state = await memory_broker.build_state(person_id)
    state.platform = "EMAIL"
    
    response_data = await ReasoningLayer.process_state(state)
    balasan = response_data["content"]
    
    await memory_broker.append_event(person_id, "LLM_RESPONSE_SENT", {"content": balasan})
    Observability.log_trace(trace_id, "EMAIL_OUTGOING", email=email_address, message=balasan)
    
    return balasan

def process_email_message_sync(email_address: str, subjek: str, isi_pesan: str) -> str:
    return asyncio.run(process_email_message_async(email_address, subjek, isi_pesan))
