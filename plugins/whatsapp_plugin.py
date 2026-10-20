import os
import re
import time
import json
from pathlib import Path
import requests
from sari_core.paths import TEMP_DIR, ADMIN_WA_STATUS_FILE, PROJECT_ROOT

MANIFEST = {
    "name": "WhatsApp Bridge Integrator",
    "version": "1.3.0",
    "author": "Harmoni Agent",
    "description": "Modul integrasi WhatsApp untuk mengirim pesan teks, Voice Note (VN), dan file media (PDF, Gambar, Video)."
}

WA_API_URL = "http://localhost:3000"


def _plugin_wa_aktif():
    """MEMERIKSA SAKELAR PLUGIN WHATSAPP (JANGAN DIHAPUS).

    Kalau plugin 'WhatsApp Bridge Integrator' sedang dimatikan di Pengaturan,
    semua pengiriman yang berangkat dari PERMINTAAN (AI, tombol Telegram, tugas
    terjadwal) wajib ditolak. Ini supaya sakelar benar-benar mengikat, bukan
    sekadar menyembunyikan alat dari daftar AI.

    CATATAN PENTING: balasan otomatis ke pelanggan TIDAK lewat fungsi ini
    (wa_listener mengirim sendiri lewat jembatan WA), jadi auto-reply tetap
    jalan walau plugin ini dimatikan.
    """
    try:
        from core.plugin_manager import get_disabled_plugins
        if "whatsapp_plugin" in get_disabled_plugins():
            return False, ("🔒 Plugin WhatsApp sedang DIMATIKAN di Pengaturan. "
                           "Nyalakan dulu 'WhatsApp Bridge Integrator' kalau memang mau mengirim.")
    except Exception:
        pass
    return True, ""


def _selaraskan_profile_id(profile_input: str) -> str:
    """Menyelaraskan input profil pengguna (misal: '1', 'profil 1', 'studio', 'pijat', 'nomor_2') ke ID profil resmi."""
    if not profile_input:
        return ""
    s = str(profile_input).strip().lower()
    
    # Format langsung angka atau nama profil
    peta_langsung = {
        "1": "nomor_1", "profil 1": "nomor_1", "nomor 1": "nomor_1", "profile 1": "nomor_1", "nomor_1": "nomor_1", "profile_1": "nomor_1",
        "2": "nomor_2", "profil 2": "nomor_2", "nomor 2": "nomor_2", "profile 2": "nomor_2", "nomor_2": "nomor_2", "profile_2": "nomor_2",
        "3": "nomor_3", "profil 3": "nomor_3", "nomor 3": "nomor_3", "profile 3": "nomor_3", "nomor_3": "nomor_3", "profile_3": "nomor_3",
        "4": "nomor_4", "profil 4": "nomor_4", "nomor 4": "nomor_4", "profile 4": "nomor_4", "nomor_4": "nomor_4", "profile_4": "nomor_4",
    }
    if s in peta_langsung:
        return peta_langsung[s]
        
    # Cek berdasarkan nama usaha atau label dari konfigurasi_multi_wa.json
    try:
        from pathlib import Path
        import json
        cfg_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
        if cfg_file.exists():
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles = data.get("profiles", {})
            for pid, pdata in profiles.items():
                bname = str(pdata.get("business_name", "")).lower()
                lbl = str(pdata.get("label", "")).lower()
                bot_n = str(pdata.get("wa_bot_name", "")).lower()
                if (bname and (s in bname or bname in s)) or (lbl and (s in lbl or lbl in s)) or (bot_n and s == bot_n):
                    return pid
    except Exception:
        pass
    return profile_input

KONTAK_FILE = PROJECT_ROOT / "kontak_tersimpan.json"

def baca_buku_kontak_tersimpan() -> dict:
    if KONTAK_FILE.exists():
        try:
            with open(KONTAK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def simpan_buku_kontak_tersimpan(data: dict):
    try:
        with open(KONTAK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WA Plugin] Gagal simpan kontak_tersimpan.json: {e}")

def nomor_wa_sah(nomor: str) -> tuple:
    """Periksa apakah sebuah nomor masuk akal sebagai nomor seluler WhatsApp.

    PENTING: nomor sampah yang lolos ke daftar kontak bisa membuat server WhatsApp
    MENGGANTUNG saat pengiriman massal (misal status), dan soketnya ikut tersandera
    sehingga SEMUA pengiriman berikutnya gagal. Karena itu penyaringan ini wajib.

    Mengembalikan (benar, alasan) - alasan berisi penjelasan bila tidak sah.
    """
    angka = "".join(c for c in str(nomor) if c.isdigit())
    if angka.startswith("0"):
        angka = "62" + angka[1:]
    if not angka:
        return False, "tidak memuat angka"
    # Seluler Indonesia: 628 diikuti 8-11 angka (total 11-13)
    if re.fullmatch(r"628[0-9]{8,11}", angka):
        return True, ""
    if angka.startswith("628"):
        return False, (f"panjangnya tidak wajar untuk nomor seluler ({angka}, {len(angka)} angka) - "
                       f"nomor seluler Indonesia umumnya 11 sampai 13 angka")
    if angka.startswith("62"):
        return False, (f"bukan nomor seluler Indonesia ({angka}) - seharusnya diawali 628. "
                       f"Nomor telepon rumah/kantor/kode layanan tidak bisa dipakai status WhatsApp")
    if re.fullmatch(r"[1-9][0-9]{10,14}", angka):
        return True, ""
    return False, f"panjang atau bentuknya tidak wajar ({angka}, {len(angka)} angka)"


def simpan_kontak_wa(nama: str, nomor: str) -> str:
    """Menyimpan kontak baru ke Buku Kontak Harmoni agar AI bisa langsung mengenali nama tersebut (misal: 'istri', 'Bang Ceper')."""
    if not nama or not nomor:
        return "❌ Nama dan nomor telepon wajib diisi."
    clean_num = "".join([c for c in str(nomor) if c.isdigit()])
    if clean_num.startswith("0"):
        clean_num = "62" + clean_num[1:]
    benar, alasan = nomor_wa_sah(clean_num)
    if not benar:
        return (
            f"❌ Nomor '{nomor}' tidak disimpan karena {alasan}.\n\n"
            f"Contoh nomor yang benar: 08123456789 atau 628123456789."
        )

    data = baca_buku_kontak_tersimpan()
    k_key = str(nama).strip().lower()
    data[k_key] = clean_num
    simpan_buku_kontak_tersimpan(data)
    return (
        f"📇 *Berhasil Menyimpan Kontak!*\n\n"
        f"👤 **Nama:** {nama.title()}\n"
        f"📱 **Nomor:** {clean_num}\n\n"
        f"Sekarang Kakak bisa langsung perintahkan: 'kirim pesan ke {nama}' atau 'kirim VN ke {nama}' tanpa perlu ketik nomor lagi."
    )

def hapus_kontak_wa(nama: str) -> str:
    """Menghapus kontak dari Buku Kontak Harmoni berdasarkan nama."""
    data = baca_buku_kontak_tersimpan()
    k_key = str(nama).strip().lower()
    if k_key in data:
        num = data.pop(k_key)
        simpan_buku_kontak_tersimpan(data)
        return f"🗑️ Kontak **{nama.title()}** ({num}) telah dihapus dari buku kontak."
    return f"⚠️ Kontak dengan nama '{nama}' tidak ditemukan di buku kontak."

def daftar_buku_kontak() -> str:
    """Melihat daftar seluruh kontak yang tersimpan di Buku Kontak Harmoni."""
    data = baca_buku_kontak_tersimpan()
    if not data:
        return "📇 Buku kontak Harmoni masih kosong. Simpan dengan perintah: 'simpan kontak <nama> <nomor_hp>'."
    output = f"📇 **Buku Kontak Harmoni ({len(data)} Kontak Tersimpan):**\n\n"
    for idx, (k, v) in enumerate(data.items(), 1):
        output += f"{idx}. **{k.title()}**: `{v}`\n"
    return output

def resolve_contact_auto(query: str, profile_id: str = "") -> dict:
    """Mencari dan mencocokkan nama kontak atau nomor telepon ke nomor WhatsApp valid secara cerdas."""
    if not query:
        return {"status": "not_found", "query": ""}
    raw = str(query).strip()

    # 1. Cek apakah input sudah berupa angka nomor HP
    digits = "".join([c for c in raw if c.isdigit()])
    if len(digits) >= 8 and (raw.startswith("+") or raw.startswith("0") or raw.startswith("62") or raw.isdigit()):
        phone = digits
        if phone.startswith("0"):
            phone = "62" + phone[1:]
        return {"status": "found", "number": phone, "name": phone, "display": f"{phone}"}

    q_lower = raw.lower()

    # 2. Cek Buku Kontak Harmoni (kontak_tersimpan.json)
    buku = baca_buku_kontak_tersimpan()
    if q_lower in buku:
        num = buku[q_lower]
        return {"status": "found", "number": num, "name": raw.title(), "display": f"{raw.title()} ({num})"}

    # Cari kecocokan kata utuh (word boundary) terlebih dahulu
    word_matches_buku = []
    for k, v in buku.items():
        words = [w.strip() for w in k.split()]
        if any(w == q_lower for w in words):
            word_matches_buku.append((k.title(), v))

    if len(word_matches_buku) == 1:
        return {"status": "found", "number": word_matches_buku[0][1], "name": word_matches_buku[0][0], "display": f"{word_matches_buku[0][0]} ({word_matches_buku[0][1]})"}
    elif len(word_matches_buku) > 1:
        return {"status": "ambiguous", "matches": word_matches_buku, "query": raw}

    # Jika tidak ada kecocokan kata utuh, baru cari kecocokan substring
    sub_matches_buku = []
    for k, v in buku.items():
        if q_lower in k or k in q_lower:
            sub_matches_buku.append((k.title(), v))
    if len(sub_matches_buku) == 1:
        return {"status": "found", "number": sub_matches_buku[0][1], "name": sub_matches_buku[0][0], "display": f"{sub_matches_buku[0][0]} ({sub_matches_buku[0][1]})"}
    elif len(sub_matches_buku) > 1:
        return {"status": "ambiguous", "matches": sub_matches_buku, "query": raw}

    # 3. Cek Sinkronisasi Kontak WhatsApp dari wa_bridge
    try:
        url = f"{WA_API_URL}/contacts?profile={profile_id}" if profile_id else f"{WA_API_URL}/contacts"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            c_data = res.json()
            contacts = c_data.get("contacts", [])
            matches = []
            for c in contacts:
                c_name = str(c.get("name") or "").strip()
                c_num = str(c.get("number") or "").strip()
                if not c_name or not c_num:
                    continue
                if q_lower == c_name.lower():
                    return {"status": "found", "number": c_num, "name": c_name, "display": f"{c_name} ({c_num})"}
                if q_lower in c_name.lower() or c_name.lower() in q_lower:
                    matches.append((c_name, c_num))

            if len(matches) == 1:
                return {"status": "found", "number": matches[0][1], "name": matches[0][0], "display": f"{matches[0][0]} ({matches[0][1]})"}
            elif len(matches) > 1:
                exact_word = [m for m in matches if any(w == q_lower for w in m[0].lower().split())]
                if len(exact_word) == 1:
                    return {"status": "found", "number": exact_word[0][1], "name": exact_word[0][0], "display": f"{exact_word[0][0]} ({exact_word[0][1]})"}
                return {"status": "ambiguous", "matches": matches, "query": raw}
    except Exception as e_c:
        print(f"[WA Plugin] Gagal cek contacts dari wa_bridge: {e_c}")

    return {"status": "not_found", "query": raw}

def _cek_butuh_konfirmasi_profil(profile_id: str, force_send: bool = False) -> tuple:
    """Memeriksa apakah pengiriman membutuhkan tombol konfirmasi profil (jika profil > 1 dan belum ditentukan)."""
    if force_send:
        return False, {}
    resolved_pid = _selaraskan_profile_id(profile_id)
    if resolved_pid:
        return False, {}
    try:
        from pathlib import Path
        import json
        cfg_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
        if cfg_file.exists():
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles = data.get("profiles", {})
            if len(profiles) > 1:
                return True, profiles
    except Exception:
        pass
    return False, {}

def _tampilkan_tombol_konfirmasi_wa(jenis: str, data_pending: dict, profiles: dict) -> str:
    """Menyimpan pengiriman tertunda dan memunculkan tombol konfirmasi nomor pengirim di Telegram."""
    import time, random, json, os
    from pathlib import Path
    import requests

    send_id = f"wa_{int(time.time()*1000)}_{random.randint(100, 999)}"
    pending_file = PROJECT_ROOT / "pending_wa_sends.json"
    pending_data = {}
    if pending_file.exists():
        try:
            with open(pending_file, "r", encoding="utf-8") as pf:
                pending_data = json.load(pf)
        except Exception:
            pass

    data_pending["jenis"] = jenis
    data_pending["waktu"] = time.strftime("%Y-%m-%d %H:%M:%S")
    pending_data[send_id] = data_pending

    try:
        with open(pending_file, "w", encoding="utf-8") as pf:
            json.dump(pending_data, pf, indent=2)
    except Exception as e_w:
        print(f"[WA Plugin] Gagal tulis pending_wa_sends: {e_w}")

    try:
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        tg_chat = os.getenv("TELEGRAM_CHAT_ID")
        if tg_token and tg_chat:
            keyboard_rows = []
            for pid, pdata in profiles.items():
                num_s = pid.replace("nomor_", "")
                bname = pdata.get("business_name") or pdata.get("label") or pid
                p_phone = pdata.get("target_phone", "")
                tail = f" (..{p_phone[-4:]})" if p_phone and len(p_phone) >= 4 else ""
                btn_txt = f"{num_s}️⃣ Kirim via Profil {num_s}: {bname}{tail}"
                keyboard_rows.append([{"text": btn_txt, "callback_data": f"send_wa:{send_id}:{pid}"}])

            keyboard_rows.append([{"text": "❌ Batalkan Pengiriman", "callback_data": f"send_wa_cancel:{send_id}"}])

            kontak_disp = data_pending.get("display_penerima") or data_pending.get("nama_kontak") or data_pending.get("kontak") or ""
            konten_disp = data_pending.get("pesan") or data_pending.get("pesan_teks") or data_pending.get("path_file") or data_pending.get("teks") or ""
            if jenis == "status":
                prompt_tg = (
                    f"📱 **Konfirmasi Nomor Pengirim WhatsApp:**\n\n"
                    f"Asisten siap mengunggah **Status (Story) WhatsApp**\n"
                    f"💬 Isi: _{konten_disp}_\n\n"
                    f"Mau diunggah menggunakan nomor WhatsApp yang mana, pengguna?"
                )
            else:
                jenis_label = "Voice Note (VN)" if jenis == "vn" else ("Dokumen/File" if jenis == "file" else "Pesan Teks")
                prompt_tg = (
                    f"📱 **Konfirmasi Nomor Pengirim WhatsApp:**\n\n"
                    f"Asisten siap mengirim **{jenis_label}** ke: **{kontak_disp}**\n"
                    f"💬 Isi: _{konten_disp}_\n\n"
                    f"Mau dikirim menggunakan nomor WhatsApp yang mana, pengguna?"
                )
            payload = {
                "chat_id": tg_chat,
                "text": prompt_tg,
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": keyboard_rows}
            }
            requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage", json=payload, timeout=5)
    except Exception as e_tg:
        print(f"[WA Plugin] Gagal kirim tombol TG: {e_tg}")

    return (
        "⏸️ Ada lebih dari 1 nomor WhatsApp yang aktif di sistem dan nomor pengirim belum ditentukan. "
        "Tombol pilihan nomor pengirim telah dimunculkan di Telegram pengguna. "
        "Pesan BELUM dikirimkan sampai salah satu tombol nomor pengirim diklik."
    )

def eksekusi_pending_send_wa(send_id: str, target_pid: str) -> tuple:
    """Mengeksekusi pengiriman pesan/VN WhatsApp yang tertunda setelah profil dipilih dari tombol Telegram."""
    from pathlib import Path
    import json, os

    pending_file = PROJECT_ROOT / "pending_wa_sends.json"
    if not pending_file.exists():
        return False, "⚠️ Berkas antrean pengiriman pesan tidak ditemukan."

    try:
        with open(pending_file, "r", encoding="utf-8") as pf:
            pending_data = json.load(pf)
    except Exception as e:
        return False, f"⚠️ Gagal membaca antrean pengiriman: {e}"

    if send_id not in pending_data:
        return False, "⚠️ Pesan ini sudah pernah dikirim atau dibatalkan sebelumnya."

    task = pending_data.pop(send_id)
    try:
        with open(pending_file, "w", encoding="utf-8") as pf:
            json.dump(pending_data, pf, indent=2)
    except Exception:
        pass

    b_name = target_pid
    try:
        cfg_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
        if cfg_file.exists():
            with open(cfg_file, "r", encoding="utf-8") as cf:
                c_obj = json.load(cf)
                p_obj = c_obj.get("profiles", {}).get(target_pid, {})
                b_name = p_obj.get("business_name") or p_obj.get("label") or f"Profil {target_pid}"
    except Exception:
        pass

    num_s = target_pid.replace("nomor_", "")
    jenis = task.get("jenis")
    kontak = task.get("nama_kontak") or ""
    kontak_disp = task.get("display_penerima") or kontak

    if jenis == "text":
        pesan = task.get("pesan", "")
        res_str = kirim_pesan_whatsapp(kontak, pesan, profile_id=target_pid, force_send=True)
        if "Berhasil" in res_str:
            return True, (
                f"✅ **Pesan Teks WhatsApp Berhasil Dikirim!**\n\n"
                f"📱 **Pengirim:** Profil {num_s} — **{b_name}** (`{target_pid}`)\n"
                f"🎯 **Penerima:** {kontak_disp}\n"
                f"💬 **Isi Pesan:** {pesan}"
            )
        else:
            return False, f"❌ Gagal mengirim: {res_str}"
    elif jenis == "vn":
        pesan_teks = task.get("pesan_teks", "")
        res_str = kirim_vn_whatsapp(kontak, pesan_teks, profile_id=target_pid, force_send=True)
        if "Berhasil" in res_str:
            return True, (
                f"🎙️ **Voice Note WhatsApp Berhasil Dikirim!**\n\n"
                f"📱 **Pengirim:** Profil {num_s} — **{b_name}** (`{target_pid}`)\n"
                f"🎯 **Penerima:** {kontak_disp}\n"
                f"💬 **Isi VN:** \"{pesan_teks}\""
            )
        else:
            return False, f"❌ Gagal mengirim VN: {res_str}"
    elif jenis == "file":
        path_file = task.get("path_file", "")
        caption = task.get("caption", "")
        as_doc = task.get("sebagai_dokumen", True)
        res_str = kirim_file_whatsapp(kontak, path_file, caption, sebagai_dokumen=as_doc, profile_id=target_pid, force_send=True)
        if "Berhasil" in res_str:
            return True, (
                f"📁 **Dokumen WhatsApp Berhasil Dikirim!**\n\n"
                f"📱 **Pengirim:** Profil {num_s} — **{b_name}** (`{target_pid}`)\n"
                f"🎯 **Penerima:** {kontak_disp}\n"
                f"📄 **File:** `{os.path.basename(path_file)}`"
            )
        else:
            return False, f"❌ Gagal mengirim file: {res_str}"
    elif jenis == "status":
        teks = task.get("teks", "")
        p_file = task.get("path_file", "")
        res_str = kirim_status_whatsapp(teks=teks, path_file=p_file, profile_id=target_pid, force_send=True)
        if "Berhasil" in res_str:
            isi_ringkas = teks or (os.path.basename(p_file) if p_file else "Status baru")
            return True, (
                f"📱 **Status WhatsApp Berhasil Diunggah!**\n\n"
                f"👤 **Pengunggah:** Profil {num_s} — **{b_name}** (`{target_pid}`)\n"
                f"💬 **Isi:** {isi_ringkas}"
            )
        else:
            return False, f"❌ Gagal mengunggah status: {res_str}"

    return False, f"⚠️ Jenis pengiriman tidak dikenal: {jenis}"

def kirim_pesan_whatsapp(nama_kontak: str, pesan: str, profile_id: str = "", force_send: bool = False):
    """Mengirim pesan WhatsApp ke nama kontak atau nomor telepon tertentu via WA Bridge."""
    boleh, pesan_tolak = _plugin_wa_aktif()
    if not boleh:
        return pesan_tolak
    info_kontak = resolve_contact_auto(nama_kontak, profile_id)
    if info_kontak.get("status") == "not_found":
        return f"❌ Kontak WhatsApp '{nama_kontak}' tidak ditemukan di buku kontak maupun riwayat obrolan. Silakan sebutkan nomor teleponnya (contoh: 'kirim WA ke 08123xxx pesan: ...') atau simpan ke buku kontak dengan perintah: 'simpan kontak {nama_kontak} <nomor_hp>'."
    if info_kontak.get("status") == "ambiguous":
        daftar_m = "\n".join([f"- **{m[0]}** ({m[1]})" for m in info_kontak.get("matches", [])[:4]])
        return f"🔍 Ditemukan beberapa kontak dengan nama '{nama_kontak}':\n{daftar_m}\n\nSilakan sebutkan nama lebih lengkap atau gunakan nomor teleponnya."

    nomor_tujuan = info_kontak.get("number", nama_kontak)
    label_penerima = info_kontak.get("display", nama_kontak)

    butuh_konfirmasi, profiles = _cek_butuh_konfirmasi_profil(profile_id, force_send)
    if butuh_konfirmasi:
        return _tampilkan_tombol_konfirmasi_wa("text", {"nama_kontak": nomor_tujuan, "display_penerima": label_penerima, "pesan": pesan}, profiles)

    try:
        url = f"{WA_API_URL}/send"
        resolved_pid = _selaraskan_profile_id(profile_id)
        payload = {"number": nomor_tujuan, "message": pesan}
        if resolved_pid:
            payload["profile"] = resolved_pid
        res = requests.post(url, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            if data.get("success") or data.get("status") == "success":
                label_p = f" (via {resolved_pid})" if resolved_pid else ""
                return f"✅ Berhasil mengirim WhatsApp ke {label_penerima}{label_p}: '{pesan}'"
            else:
                return f"❌ Gagal: {data.get('error') or data.get('message')}"
        else:
            return f"❌ Error Server WA Bridge (Status {res.status_code})"
    except Exception as e:
        return f"❌ Terjadi kesalahan saat menghubungi WA Bridge: {str(e)}"

def kirim_vn_whatsapp(nama_kontak: str, pesan_teks: str, profile_id: str = "", force_send: bool = False):
    """Mengonversi teks ucapan menjadi suara AI Manusiawi (ElevenLabs / OpenAI TTS) lalu mengirimkannya sebagai Voice Note WA."""
    boleh, pesan_tolak = _plugin_wa_aktif()
    if not boleh:
        return pesan_tolak
    info_kontak = resolve_contact_auto(nama_kontak, profile_id)
    if info_kontak.get("status") == "not_found":
        return f"❌ Kontak WhatsApp '{nama_kontak}' tidak ditemukan di buku kontak maupun riwayat obrolan. Silakan sebutkan nomor teleponnya atau simpan dengan perintah: 'simpan kontak {nama_kontak} <nomor_hp>'."
    if info_kontak.get("status") == "ambiguous":
        daftar_m = "\n".join([f"- **{m[0]}** ({m[1]})" for m in info_kontak.get("matches", [])[:4]])
        return f"🔍 Ditemukan beberapa kontak dengan nama '{nama_kontak}':\n{daftar_m}\n\nSilakan sebutkan nama lebih lengkap atau gunakan nomor teleponnya."

    nomor_tujuan = info_kontak.get("number", nama_kontak)
    label_penerima = info_kontak.get("display", nama_kontak)

    butuh_konfirmasi, profiles = _cek_butuh_konfirmasi_profil(profile_id, force_send)
    if butuh_konfirmasi:
        return _tampilkan_tombol_konfirmasi_wa("vn", {"nama_kontak": nomor_tujuan, "display_penerima": label_penerima, "pesan_teks": pesan_teks}, profiles)
    timestamp = int(time.time())
    temp_dir = str(TEMP_DIR)
    os.makedirs(temp_dir, exist_ok=True)
    mp3_path = os.path.join(temp_dir, f"temp_vn_{timestamp}.mp3")
    ogg_path = os.path.join(temp_dir, f"temp_vn_{timestamp}.ogg")
    try:
        import subprocess
        berhasil_audio = False
        
        # 0. Coba generate audio menggunakan engine TTS aktif di Harmoni (Gemini-TTS / ElevenLabs / OpenAI / Edge-TTS)
        try:
            from server_core import _generate_tts_bytes
            ok_tts, audio_bytes, prov_name = _generate_tts_bytes(pesan_teks)
            if ok_tts and audio_bytes and len(audio_bytes) > 100:
                with open(mp3_path, 'wb') as f:
                    f.write(audio_bytes)
                berhasil_audio = True
        except Exception:
            pass

        # 1. Coba ElevenLabs jika engine belum menghasilkan audio
        if not berhasil_audio:
            from dotenv import dotenv_values
            app_dir = Path(__file__).parent.parent.resolve()
            env_vals = dotenv_values(app_dir / ".env") if (app_dir / ".env").exists() else {}

            # Baca pilihan suara dari personalisasi.json
            voice_id = "EXAVITQu4vr4xnSDxMaL"  # Default Bella (Support Akun Gratis)
            pers_path = app_dir / "personalisasi.json"
            if pers_path.exists():
                try:
                    with open(pers_path, "r", encoding="utf-8") as pf:
                        pcfg = json.load(pf)
                        voice_id = pcfg.get("elevenlabs_voice_id") or voice_id
                except Exception:
                    pass

            el_raw = (env_vals.get("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY", "")).replace(chr(10), ",").replace(chr(13), ",")
            api_keys_eleven = [k.strip() for k in el_raw.split(",") if k.strip()]
            for extra in [env_vals.get("ELEVENLABS_API_KEY_1"), env_vals.get("ELEVENLABS_API_KEY_2"), os.getenv("ELEVENLABS_API_KEY_1"), os.getenv("ELEVENLABS_API_KEY_2")]:
                if extra and extra not in api_keys_eleven:
                    api_keys_eleven.append(extra)

            for key in api_keys_eleven:
                try:
                    headers = {'xi-api-key': key}
                    data_el = {
                        "text": pesan_teks,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                    }
                    res = requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}', headers=headers, json=data_el, timeout=30)
                    if res.status_code == 200:
                        with open(mp3_path, 'wb') as f:
                            f.write(res.content)
                        berhasil_audio = True
                        break
                except Exception:
                    pass

        # 2. Cadangan Utama: Edge-TTS Suara Gadis (id-ID-GadisNeural) - 100% Gratis & Jernih
        if not berhasil_audio:
            try:
                import asyncio
                import concurrent.futures
                import edge_tts
                
                async def _buat_edge():
                    communicate = edge_tts.Communicate(pesan_teks, "id-ID-GadisNeural")
                    await communicate.save(mp3_path)
                
                # Eksekusi dengan aman baik di dalam maupun di luar event loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        executor.submit(asyncio.run, _buat_edge()).result()
                else:
                    asyncio.run(_buat_edge())

                if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                    berhasil_audio = True
            except Exception as e_edge:
                print(f"[WA VN] Gagal Edge-TTS Python: {e_edge}")

        # 3. Cadangan Kedua: Edge-TTS CLI (Suara Gadis)
        if not berhasil_audio:
            try:
                teks_aman = pesan_teks.replace('"', "'")
                cmd = f'edge-tts --voice id-ID-GadisNeural --text "{teks_aman}" --write-media "{mp3_path}"'
                subprocess.run(cmd, shell=True, capture_output=True, timeout=20)
                if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                    berhasil_audio = True
            except Exception as e_cli:
                print(f"[WA VN] Gagal Edge-TTS CLI: {e_cli}")
        
        # Konversi ke OGG Opus (Format Asli VN WhatsApp) via FFmpeg kilat
        source_audio = mp3_path if os.path.exists(mp3_path) else None
        if source_audio:
            cmd = f'ffmpeg -y -i "{source_audio}" -c:a libopus -b:a 32k "{ogg_path}"'
            subprocess.run(cmd, shell=True, capture_output=True)
            
        send_path = ogg_path if os.path.exists(ogg_path) else source_audio

        if not send_path or not os.path.exists(send_path):
            return "❌ Gagal menghasilkan file audio Voice Note."

        url = f"{WA_API_URL}/send-media"
        resolved_pid = _selaraskan_profile_id(profile_id)
        payload = {
            "number": nomor_tujuan,
            "filePath": send_path,
            "isVoiceNote": True
        }
        if resolved_pid:
            payload["profile"] = resolved_pid
        res = requests.post(url, json=payload, timeout=60)
        
        for p in [mp3_path, ogg_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception:
                    pass

        if res.status_code == 200:
            label_p = f" (via {resolved_pid})" if resolved_pid else ""
            return f"🎙️ Berhasil mengirim Voice Note (Suara AI Studio) ke {label_penerima}{label_p}: '{pesan_teks}'"
        else:
            return f"❌ Gagal mengirim VN: {res.text}"
    except Exception as e:
        for p in [mp3_path, ogg_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception:
                    pass
        return f"❌ Error saat membuat/mengirim Voice Note: {str(e)}"

def kirim_file_whatsapp(nama_kontak: str, path_file: str, caption: str = "", sebagai_dokumen: bool = True, profile_id: str = "", force_send: bool = False):
    """Mengirim file media (Lagu, Audio, Gambar, PDF, Video, Dokumen, Proyek DAW) dari laptop ke WhatsApp penerima sebagai dokumen utuh."""
    boleh, pesan_tolak = _plugin_wa_aktif()
    if not boleh:
        return pesan_tolak
    if not os.path.exists(path_file):
        return f"❌ Gagal: File `{path_file}` tidak ditemukan di PC."

    info_kontak = resolve_contact_auto(nama_kontak, profile_id)
    if info_kontak.get("status") == "not_found":
        return f"❌ Kontak WhatsApp '{nama_kontak}' tidak ditemukan di buku kontak maupun riwayat obrolan. Silakan sebutkan nomor teleponnya."
    if info_kontak.get("status") == "ambiguous":
        daftar_m = "\n".join([f"- **{m[0]}** ({m[1]})" for m in info_kontak.get("matches", [])[:4]])
        return f"🔍 Ditemukan beberapa kontak dengan nama '{nama_kontak}':\n{daftar_m}\n\nSilakan sebutkan nama lebih lengkap atau gunakan nomor teleponnya."

    nomor_tujuan = info_kontak.get("number", nama_kontak)
    label_penerima = info_kontak.get("display", nama_kontak)

    butuh_konfirmasi, profiles = _cek_butuh_konfirmasi_profil(profile_id, force_send)
    if butuh_konfirmasi:
        return _tampilkan_tombol_konfirmasi_wa("file", {"nama_kontak": nomor_tujuan, "display_penerima": label_penerima, "path_file": path_file, "caption": caption, "sebagai_dokumen": sebagai_dokumen}, profiles)
    try:
        url = f"{WA_API_URL}/send-media"
        resolved_pid = _selaraskan_profile_id(profile_id)
        payload = {
            "number": nomor_tujuan,
            "filePath": path_file,
            "caption": caption,
            "isVoiceNote": False,
            "asDocument": sebagai_dokumen
        }
        if resolved_pid:
            payload["profile"] = resolved_pid
        res = requests.post(url, json=payload, timeout=60)
        if res.status_code == 200:
            label_p = f" (via {resolved_pid})" if resolved_pid else ""
            return f"📁 Berhasil mengirim file `{os.path.basename(path_file)}` ke WhatsApp {label_penerima}{label_p} sebagai dokumen!"
        else:
            return f"❌ Gagal mengirim file: {res.text}"
    except Exception as e:
        return f"❌ Error saat mengirim file ke WhatsApp: {str(e)}"

def _format_waktu_wib(iso_str: str) -> str:
    """Mengubah timestamp ISO UTC menjadi format waktu WIB ramah pembaca layar."""
    if not iso_str:
        return ""
    try:
        from datetime import datetime, timezone, timedelta
        if iso_str.endswith("Z"):
            dt_utc = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt_utc = datetime.fromisoformat(iso_str)
        wib_tz = timezone(timedelta(hours=7))
        dt_wib = dt_utc.astimezone(wib_tz)
        now_wib = datetime.now(wib_tz)
        diff_sec = int((now_wib - dt_wib).total_seconds())

        jam_menit = dt_wib.strftime("%H:%M WIB")
        if diff_sec < 60:
            return f"baru saja ({jam_menit})"
        elif diff_sec < 3600:
            return f"{diff_sec // 60} menit lalu ({jam_menit})"
        elif diff_sec < 86400 and dt_wib.date() == now_wib.date():
            return f"hari ini jam {jam_menit}"
        else:
            return dt_wib.strftime("%d %b jam %H:%M WIB")
    except Exception:
        return str(iso_str)[:16].replace("T", " ")


def baca_pesan_whatsapp_unread(profile_id: str = "", jumlah: int = 5, hanya_pribadi: bool = True):
    """Membaca daftar pesan WhatsApp terbaru via WA Bridge dengan format rapi, filter profil, dan waktu WIB."""
    try:
        resolved_pid = _selaraskan_profile_id(profile_id)
        limit_val = int(jumlah) if jumlah and int(jumlah) > 0 else 5
        url = f"{WA_API_URL}/unread?limit={limit_val}&private_only={'true' if hanya_pribadi else 'false'}"
        if resolved_pid:
            url += f"&profile={requests.utils.quote(resolved_pid)}"

        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                if not data:
                    label_p = f" pada profil {resolved_pid}" if resolved_pid else ""
                    return f"📩 Tidak ada pesan WhatsApp baru yang belum dibaca{label_p}."

                header_p = f" (Profil {resolved_pid})" if resolved_pid else " (Semua Nomor)"
                output = f"📩 *Pesan WhatsApp Masuk Terbaru{header_p}:*\n\n"
                for idx, m in enumerate(data, 1):
                    sender_num = m.get('senderNumber') or m.get('from', '').split('@')[0]
                    name_raw = m.get('name') or sender_num
                    waktu_str = _format_waktu_wib(m.get('timestamp', ''))
                    isi = m.get('body') or "[Media/Pesan Kosong]"
                    p_id = m.get('profile') or 'nomor_1'
                    num_lbl = p_id.replace('nomor_', '')

                    output += f"{idx}. 👤 *{name_raw}* (`{sender_num}`)\n"
                    output += f"   📱 Profil {num_lbl} | ⏰ {waktu_str}\n"
                    output += f"   💬 *Pesan:* \"{isi}\"\n"
                    
                    is_vn = m.get('isVoiceNote', False) or "[Voice Note]" in isi
                    v_path = m.get('voicePath')
                    if is_vn and v_path:
                        output += f"[AKSI_PUTAR_VN: {v_path}]\n"
                        
                    output += f"[AKSI_BALAS_WA: {name_raw}|{sender_num}|{p_id}]\n\n"

                output += "💡 _Klik tombol balas di atas, atau ketik langsung balasan Anda._"
                return output.strip()
            else:
                return "❌ Gagal membaca pesan unread dari WA Bridge."
        else:
            return f"❌ Error Server WA Bridge (Status {res.status_code})"
    except Exception as e:
        return f"❌ Terjadi kesalahan saat membaca WhatsApp: {str(e)}"

def daftar_kontak_whatsapp(kata_kunci: str = ""):
    """Mengambil atau mencari kontak WhatsApp dari Buku Kontak Harmoni dan WhatsApp HP berdasarkan nama/kata kunci."""
    buku = baca_buku_kontak_tersimpan()
    q = kata_kunci.strip().lower() if kata_kunci else ""

    hasil_list = []
    seen = set()

    # 1. Cari di Buku Kontak Harmoni (kontak_tersimpan.json)
    for name, num in buku.items():
        if not q or (q in name.lower() or any(w == q for w in name.lower().split())):
            k = f"{name}_{num}"
            if k not in seen:
                seen.add(k)
                hasil_list.append((name.title(), num))

    # 2. Cari di wa_bridge contacts
    try:
        url = f"{WA_API_URL}/contacts"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success":
                for c in data.get("contacts", []):
                    c_name = c.get("name") or ""
                    c_num = c.get("number") or ""
                    if not c_name or not c_num: continue
                    if not q or (q in c_name.lower() or any(w == q for w in c_name.lower().split())):
                        k = f"{c_name}_{c_num}"
                        if k not in seen:
                            seen.add(k)
                            hasil_list.append((c_name, c_num))
    except Exception:
        pass

    if not hasil_list:
        if q:
            return f"📇 Tidak ditemukan kontak WhatsApp dengan kata kunci '{kata_kunci}'."
        return "📇 Tidak ada kontak WhatsApp ditemukan."

    if q:
        output = f"📇 *Hasil Pencarian Kontak '{kata_kunci}' ({len(hasil_list)} Ditemukan):*\n\n"
        for idx, (nm, no) in enumerate(hasil_list[:15], 1):
            output += f"{idx}. *{nm}* (`{no}`)\n"
        return output
    else:
        output = f"📇 *Daftar Kontak WhatsApp ({len(hasil_list)} Kontak Tersedia, Menampilkan Top 25):*\n\n"
        for idx, (nm, no) in enumerate(hasil_list[:25], 1):
            output += f"{idx}. *{nm}* (`{no}`)\n"
        return output

def _pekerja_pantau_panggilan_wa(nama_kontak: str, chat_id: str):
    """Memantau status panggilan WhatsApp (diangkat, tidak diangkat, selesai) dan melaporkannya ke Telegram."""
    import time
    import uiautomation as auto
    
    start_time = time.time()
    reported_connected = False
    
    for _ in range(40):
        time.sleep(3)
        try:
            from core.utils import kirim_pesan_telegram
            wa_call_win = auto.WindowControl(searchDepth=2, Name='WhatsApp Call')
            if not wa_call_win.Exists(maxSearchSeconds=0.5):
                wa_call_win = auto.WindowControl(searchDepth=1, ClassName='WinUIDesktopWin32App')
            
            if wa_call_win.Exists(maxSearchSeconds=0.5):
                text_controls = wa_call_win.GetChildren()
                full_text = " ".join([c.Name for c in text_controls if c.Name])
                
                if any(kw in full_text.lower() for kw in ["00:", "01:", "02:", "terhubung", "connected"]):
                    if not reported_connected:
                        reported_connected = True
                        kirim_pesan_telegram(chat_id, f"📞 *[PANGGILAN DIANGKAT]* Panggilan ke **'{nama_kontak}'** telah diangkat! Panggilan sedang berlangsung...")
                
                elif any(kw in full_text.lower() for kw in ["tidak menjawab", "ditolak", "busy", "declined", "unanswered"]):
                    kirim_pesan_telegram(chat_id, f"⚠️ *[PANGGILAN TIDAK DIANGKAT]* Panggilan ke **'{nama_kontak}'** tidak diangkat, ditolak, atau tidak ada jawaban.")
                    return
            else:
                if reported_connected:
                    durasi = int(time.time() - start_time)
                    kirim_pesan_telegram(chat_id, f"⏱️ *[PANGGILAN SELESAI]* Panggilan dengan **'{nama_kontak}'** telah berakhir. Durasi: {durasi} detik.")
                    return
                elif time.time() - start_time > 20:
                    kirim_pesan_telegram(chat_id, f"⚠️ *[PANGGILAN TIDAK DIANGKAT]* Panggilan ke **'{nama_kontak}'** berakhir atau tidak diangkat.")
                    return
        except Exception:
            pass

    try:
        from core.utils import kirim_pesan_telegram
        if reported_connected:
            durasi = int(time.time() - start_time)
            kirim_pesan_telegram(chat_id, f"⏱️ *[PANGGILAN SELESAI]* Panggilan dengan **'{nama_kontak}'** telah berakhir. Total durasi: {durasi} detik.")
        else:
            kirim_pesan_telegram(chat_id, f"⚠️ *[STATUS PANGGILAN]* Pemantauan panggilan ke **'{nama_kontak}'** selesai.")
    except Exception:
        pass

def telepon_whatsapp(nama_kontak: str):
    """Melakukan panggilan suara (Voice Call) WhatsApp ke kontak target di PC Windows serta memantau & melaporkan status panggilan ke Telegram."""
    try:
        import subprocess
        import time
        import threading
        import uiautomation as auto
        
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        subprocess.Popen(["cmd", "/c", "start whatsapp:"], shell=True)
        time.sleep(2)
        
        wa_window = auto.WindowControl(searchDepth=1, ClassName='WinUIDesktopWin32App')
        if not wa_window.Exists(maxSearchSeconds=3):
            wa_window = auto.WindowControl(searchDepth=1, Name='WhatsApp')
            
        if wa_window.Exists(maxSearchSeconds=2):
            wa_window.SetFocus()
            time.sleep(0.5)
            
            # 1. Buka bilah pencarian WhatsApp Desktop (Ctrl + F)
            auto.SendKeys('^f')
            time.sleep(0.5)
            
            # 2. Ketik nama kontak target
            auto.SendKeys(nama_kontak)
            time.sleep(1)
            
            # 3. Pilih kontak (Enter)
            auto.SendKeys('{ENTER}')
            time.sleep(1)
            
            # 4. Lepaskan fokus dari kolom teks agar tidak mengetik '^+' di chat
            auto.SendKeys('{ESC}')
            time.sleep(0.5)
            
            # 5. Cari tombol Panggilan Suara atau eksekusi shortcut
            call_btn = wa_window.ButtonControl(Name='Voice call')
            if not call_btn.Exists(maxSearchSeconds=1):
                call_btn = wa_window.ButtonControl(Name='Panggilan suara')
                
            if call_btn.Exists(maxSearchSeconds=1):
                call_btn.Click()
            else:
                auto.SendKeys('^+c')
            time.sleep(1)
            
            try:
                wa_window.Minimize()
            except Exception:
                pass
                
        if chat_id:
            threading.Thread(target=_pekerja_pantau_panggilan_wa, args=(nama_kontak, chat_id), daemon=True).start()
            
        return f"📞 Memulai Panggilan Suara WhatsApp ke **'{nama_kontak}'**! Sari telah mencari nama kontak di WA Desktop, mendial panggilan suara, meminimalkan jendela ke background, dan memantau status secara real-time ke Telegram."
    except Exception as e:
        return f"❌ Gagal melakukan panggilan WhatsApp: {str(e)}"

def kirim_status_whatsapp(teks: str = "", path_file: str = "", profile_id: str = "", force_send: bool = False):
    """Mengunggah pesan teks atau file gambar/video/audio menjadi Status (Story) WhatsApp."""
    boleh, pesan_tolak = _plugin_wa_aktif()
    if not boleh:
        return pesan_tolak
    resolved_pid = _selaraskan_profile_id(profile_id)
    butuh_konfirmasi, profiles = _cek_butuh_konfirmasi_profil(resolved_pid, force_send)
    if butuh_konfirmasi:
        return _tampilkan_tombol_konfirmasi_wa("status", {"teks": teks, "path_file": path_file}, profiles)

    try:
        url = f"{WA_API_URL}/post-status"
        payload = {}
        if teks: payload["text"] = teks
        if path_file: payload["filePath"] = path_file
        if resolved_pid: payload["profile"] = resolved_pid

        res = requests.post(url, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            p_label = f" via {resolved_pid}" if resolved_pid else ""
            jml = data.get("recipientsCount", 0)
            return f"📱 *Berhasil mengunggah Status (Story) baru ke WhatsApp{p_label}!* (Ditujukan ke {jml} kontak)"
        else:
            return f"❌ Gagal update status: {res.text}"
    except Exception as e:
        return f"❌ Error saat update status WA: {str(e)}"

def cek_penonton_status_whatsapp(profile_id: str = ""):
    """Mengecek daftar penonton (viewers) dan interaksi pada Status (Story) WhatsApp yang baru diunggah."""
    try:
        resolved_pid = _selaraskan_profile_id(profile_id)
        url = f"{WA_API_URL}/status-viewers?profile={resolved_pid}" if resolved_pid else f"{WA_API_URL}/status-viewers"
        res = requests.get(url, timeout=30)
        if res.status_code == 200:
            data = res.json()
            statuses = data.get("statuses", [])
            if not statuses:
                return "👁️ Belum ada Status WhatsApp yang diunggah baru-baru ini."

            output = f"📊 *Laporan Penonton Status WhatsApp Anda ({data.get('totalStatuses')} Status):*\n\n"
            for idx, st in enumerate(statuses, 1):
                output += f"{idx}. **Caption:** `{st.get('caption')}`\n"
                output += f"   👁️ **Total Viewer:** {st.get('viewerCount')} orang\n"
                if st.get('viewers'):
                    viewers_str = ", ".join(st.get('viewers')[:10])
                    output += f"   👥 **Daftar Penonton:** {viewers_str}\n"
                output += "\n"
            return output
        else:
            return f"❌ Gagal mengambil penonton status: {res.text}"
    except Exception as e:
        return f"❌ Error saat cek penonton status: {str(e)}"

def angkat_telepon_whatsapp():
    """Mengangkat panggilan telepon/video WhatsApp masuk secara otomatis di PC Windows."""
    try:
        import uiautomation as auto
        import time
        
        wa_call_win = auto.WindowControl(searchDepth=2, Name='WhatsApp Call')
        if not wa_call_win.Exists(maxSearchSeconds=1):
            wa_call_win = auto.WindowControl(searchDepth=1, ClassName='WinUIDesktopWin32App')
            
        if wa_call_win.Exists(maxSearchSeconds=2):
            wa_call_win.SetFocus()
            time.sleep(0.3)
            
            accept_btn = wa_call_win.ButtonControl(Name='Accept')
            if not accept_btn.Exists(maxSearchSeconds=0.5):
                accept_btn = wa_call_win.ButtonControl(Name='Jawab')
            if not accept_btn.Exists(maxSearchSeconds=0.5):
                accept_btn = wa_call_win.ButtonControl(Name='Angkat')
                
            if accept_btn.Exists(maxSearchSeconds=1):
                accept_btn.Click()
                return "📞 *Berhasil mengangkat panggilan WhatsApp!* Panggilan sedang tersambung..."
            else:
                auto.SendKeys('^+a')
                return "📞 *Mengirim sinyal angkat panggilan WhatsApp (Ctrl+Shift+A).* Panggilan sedang tersambung..."
        else:
            return "⚠️ Tidak ditemukan jendela panggilan WhatsApp yang sedang berdering saat ini."
    except Exception as e:
        return f"❌ Gagal mengangkat panggilan WhatsApp: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "kirim_pesan_whatsapp",
            "description": "Mengirimkan pesan teks WhatsApp ke seseorang berdasarkan nama kontak atau nomor telepon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_kontak": {"type": "string", "description": "Nama kontak sesuai buku telepon atau nomor telepon WA"},
                    "pesan": {"type": "string", "description": "Isi pesan teks WhatsApp yang akan dikirim"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp pengirim opsional (misal: 'nomor_1', 'nomor_2', '1', '2', atau 'studio', 'pijat'). Kosongkan untuk memakai nomor default."}
                },
                "required": ["nama_kontak", "pesan"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kirim_vn_whatsapp",
            "description": "Mengonversi teks ucapan menjadi suara TTS AI lalu mengirimkannya sebagai Voice Note khas WA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_kontak": {"type": "string", "description": "Nama kontak penerima VN"},
                    "pesan_teks": {"type": "string", "description": "Teks ucapan yang akan diubah jadi suara VN"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp pengirim opsional ('nomor_1', 'nomor_2', dll)."}
                },
                "required": ["nama_kontak", "pesan_teks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kirim_file_whatsapp",
            "description": "Mengirimkan file (gambar, video, PDF, audio, dokumen) dari PC ke kontak WhatsApp penerima.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_kontak": {"type": "string", "description": "Nama kontak penerima"},
                    "path_file": {"type": "string", "description": "Path lokasi file di PC"},
                    "caption": {"type": "string", "description": "Caption opsional"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp pengirim opsional ('nomor_1', 'nomor_2', dll)."}
                },
                "required": ["nama_kontak", "path_file"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_pesan_terakhir_wa",
            "description": "Membaca daftar pesan WhatsApp yang baru masuk di latar belakang, bisa difilter per nomor profil ('nomor_1', 'nomor_2', dll).",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "string", "description": "Profil nomor WhatsApp opsional ('nomor_1', 'nomor_2', 'studio', 'pijat'). Kosongkan untuk melihat semua nomor."},
                    "jumlah": {"type": "integer", "description": "Jumlah pesan terbaru yang ingin dibaca (default: 5)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ambil_kontak_whatsapp",
            "description": "Mengambil atau mencari kontak WhatsApp dari Buku Kontak Harmoni dan WhatsApp berdasarkan nama atau kata kunci.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Nama atau kata kunci pencarian kontak opsional (misal: 'Ega', 'Kikin', 'Dani')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "telepon_whatsapp",
            "description": "Melakukan panggilan suara (Voice Call) WhatsApp ke kontak target di PC Windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_kontak": {"type": "string", "description": "Nama kontak target yang ingin ditelepon via WA"}
                },
                "required": ["nama_kontak"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "angkat_telepon_whatsapp",
            "description": "Mengangkat panggilan suara/video WhatsApp masuk secara otomatis.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kirim_status_whatsapp",
            "description": "Mengunggah pesan teks atau file media (gambar/video/audio) menjadi Status (Story) WhatsApp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "teks": {"type": "string", "description": "Pesan teks status opsional"},
                    "path_file": {"type": "string", "description": "Path mutlak ke file gambar/video/audio status opsional"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp pengirim opsional ('nomor_1', 'nomor_2', 'studio', 'pijat', dll)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cek_penonton_status_whatsapp",
            "description": "Mengecek daftar penonton (viewers/likes) pada Status (Story) WhatsApp yang baru diunggah.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "string", "description": "Profil WhatsApp opsional ('nomor_1', 'nomor_2', dll)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mode_admin_wa",
            "description": "Menyalakan (aktif=true) atau mematikan (aktif=false) mode Admin WA agar asisten Gea membalas chat WhatsApp masuk secara otomatis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aktif": {"type": "boolean", "description": "True untuk mengaktifkan Admin WA (Gea balas otomatis), False untuk mematikan"}
                },
                "required": ["aktif"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "simpan_kontak_wa",
            "description": "Menyimpan nama dan nomor telepon WhatsApp ke Buku Kontak Harmoni agar bisa dipanggil langsung dengan nama (misal: 'istri', 'Bang Ceper').",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama": {"type": "string", "description": "Nama panggilan atau nama kontak (misal: 'Bang Ceper', 'Istri')"},
                    "nomor": {"type": "string", "description": "Nomor WhatsApp (misal: '08123456789')"}
                },
                "required": ["nama", "nomor"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hapus_kontak_wa",
            "description": "Menghapus kontak tersimpan dari Buku Kontak Harmoni berdasarkan nama.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama": {"type": "string", "description": "Nama kontak yang ingin dihapus"}
                },
                "required": ["nama"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "daftar_buku_kontak",
            "description": "Melihat daftar seluruh kontak yang tersimpan di Buku Kontak Harmoni.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atur_mode_sibuk_wa",
            "description": "Mengatur mode balasan otomatis WhatsApp saat sibuk/istirahat atau di luar jam kerja.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "description": "Pilihan mode: 'always' (selalu aktif/sibuk), 'outside_hours' (di luar jam kerja), atau 'off' (matikan mode sibuk)"},
                    "pesan": {"type": "string", "description": "Teks pesan balasan otomatis yang dikirim ke klien"},
                    "jam_buka": {"type": "string", "description": "Jam mulai kerja format HH:MM (misal '09:00') jika mode='outside_hours'"},
                    "jam_tutup": {"type": "string", "description": "Jam selesai kerja format HH:MM (misal '18:00') jika mode='outside_hours'"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp opsional ('nomor_1', 'nomor_2', dll)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tambah_jawaban_kilat_wa",
            "description": "Menambahkan jawaban cepat instan (FAQ/pricelist/rekening) yang otomatis dibalas saat kata kunci terdeteksi tanpa memotong kuota AI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci pemicu dipisah koma (misal: 'pricelist, harga, tarif' atau 'rekening, bca, transfer')"},
                    "teks_jawaban": {"type": "string", "description": "Teks jawaban instan yang langsung dikirim ke klien"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp opsional ('nomor_1', 'nomor_2', dll)."}
                },
                "required": ["kata_kunci", "teks_jawaban"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "daftar_jawaban_kilat_wa",
            "description": "Melihat daftar seluruh jawaban cepat instan (FAQ/kata kunci) yang terdaftar pada profil WhatsApp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "string", "description": "Profil WhatsApp opsional ('nomor_1', 'nomor_2', dll)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hapus_jawaban_kilat_wa",
            "description": "Menghapus jawaban cepat instan WhatsApp berdasarkan kata kunci atau ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci atau ID jawaban cepat yang ingin dihapus"},
                    "profile_id": {"type": "string", "description": "Profil WhatsApp opsional ('nomor_1', 'nomor_2', dll)."}
                },
                "required": ["kata_kunci"]
            }
        }
    }
]

def mode_admin_wa(aktif: bool):
    """Menyalakan (aktif=True) atau mematikan (aktif=False) mode Admin WA (Gea) untuk membalas chat WhatsApp otomatis."""
    import json
    try:
        with open(str(ADMIN_WA_STATUS_FILE), "w", encoding="utf-8") as f:
            json.dump({"admin_wa": bool(aktif)}, f)
        status_teks = "DIAKTIFKAN (Gea memantau dan membalas WhatsApp otomatis)" if aktif else "DINONAKTIFKAN (Gea istirahat/tidak membalas otomatis)"
        return f"🟢 Mode Admin WA berhasil {status_teks}."
    except Exception as e:
        return f"❌ Gagal mengatur mode Admin WA: {str(e)}"

def atur_mode_sibuk_wa(profile_id: str = "", mode: str = "always", pesan: str = "", jam_buka: str = "", jam_tutup: str = ""):
    """Mengatur mode sibuk / jam operasional untuk auto-reply WhatsApp."""
    import json
    resolved_pid = _selaraskan_profile_id(profile_id) or "nomor_1"
    multi_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
    if not multi_file.exists():
        return "❌ File konfigurasi_multi_wa.json tidak ditemukan."
    try:
        with open(multi_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        prof = data.get("profiles", {}).get(resolved_pid)
        if not prof:
            return f"❌ Profil WhatsApp '{resolved_pid}' tidak ditemukan."

        mode_val = mode.lower().strip()
        if mode_val in ("off", "mati", "nonaktif", "false"):
            prof["auto_reply_mode"] = "off"
            msg_res = f"🔴 Mode sibuk / auto-reply untuk **{resolved_pid}** telah DINONAKTIFKAN."
        elif mode_val in ("outside_hours", "jam_kerja", "jadwal"):
            prof["auto_reply_mode"] = "outside_hours"
            if jam_buka: prof["business_hours_open"] = jam_buka.strip()
            if jam_tutup: prof["business_hours_close"] = jam_tutup.strip()
            if pesan: prof["auto_reply_text"] = pesan.strip()
            msg_res = f"⏰ Mode Jam Kerja untuk **{resolved_pid}** DIAKTIFKAN ({prof.get('business_hours_open', '09:00')} - {prof.get('business_hours_close', '18:00')}). Di luar jam ini pesan dibalas otomatis."
        else:
            prof["auto_reply_mode"] = "always"
            if pesan: prof["auto_reply_text"] = pesan.strip()
            msg_res = f"🟢 Mode Sibuk / Libur untuk **{resolved_pid}** DIAKTIFKAN. Pesan masuk otomatis dibalas: \"{prof.get('auto_reply_text', '')}\""

        with open(multi_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return msg_res
    except Exception as e:
        return f"❌ Gagal mengatur mode sibuk WA: {str(e)}"

def tambah_jawaban_kilat_wa(kata_kunci: str, teks_jawaban: str, profile_id: str = ""):
    """Menambahkan atau memperbarui jawaban kilat instan (FAQ) berdasarkan kata kunci."""
    import json, time
    resolved_pid = _selaraskan_profile_id(profile_id) or "nomor_1"
    multi_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
    if not multi_file.exists():
        return "❌ File konfigurasi_multi_wa.json tidak ditemukan."
    try:
        with open(multi_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        prof = data.get("profiles", {}).get(resolved_pid)
        if not prof:
            return f"❌ Profil WhatsApp '{resolved_pid}' tidak ditemukan."

        qrs = prof.get("quick_replies", []) or []
        qr_id = f"qr_{int(time.time()*1000)}"
        qrs.append({
            "id": qr_id,
            "keywords": kata_kunci.strip(),
            "reply": teks_jawaban.strip()
        })
        prof["quick_replies"] = qrs
        with open(multi_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return f"⚡ Berhasil menambah Jawaban Kilat untuk **{resolved_pid}**!\n🎯 Kata Kunci: `{kata_kunci}`\n💬 Jawaban: \"{teks_jawaban}\""
    except Exception as e:
        return f"❌ Gagal menambah jawaban kilat: {str(e)}"

def daftar_jawaban_kilat_wa(profile_id: str = ""):
    """Melihat daftar seluruh jawaban kilat (kata kunci instan) untuk profil WhatsApp."""
    import json
    resolved_pid = _selaraskan_profile_id(profile_id) or "nomor_1"
    multi_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
    if not multi_file.exists():
        return "❌ File konfigurasi_multi_wa.json tidak ditemukan."
    try:
        with open(multi_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        prof = data.get("profiles", {}).get(resolved_pid, {})
        qrs = prof.get("quick_replies", []) or []
        if not qrs:
            return f"⚡ Belum ada Jawaban Kilat yang tersimpan untuk profil {resolved_pid}."
        out = f"⚡ **Daftar Jawaban Kilat WhatsApp ({resolved_pid}):**\n\n"
        for idx, item in enumerate(qrs, 1):
            out += f"{idx}. 🎯 **Kata Kunci:** `{item.get('keywords')}`\n   💬 **Jawaban:** {item.get('reply')}\n\n"
        return out
    except Exception as e:
        return f"❌ Gagal membaca jawaban kilat: {str(e)}"

def hapus_jawaban_kilat_wa(kata_kunci: str, profile_id: str = ""):
    """Menghapus jawaban kilat berdasarkan kata kunci atau ID."""
    import json
    resolved_pid = _selaraskan_profile_id(profile_id) or "nomor_1"
    multi_file = PROJECT_ROOT / "konfigurasi_multi_wa.json"
    if not multi_file.exists():
        return "❌ File konfigurasi_multi_wa.json tidak ditemukan."
    try:
        with open(multi_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        prof = data.get("profiles", {}).get(resolved_pid, {})
        qrs = prof.get("quick_replies", []) or []
        target = kata_kunci.strip().lower()
        awal = len(qrs)
        qrs = [q for q in qrs if q.get("id") != kata_kunci and target not in q.get("keywords", "").lower()]
        if len(qrs) == awal:
            return f"⚠️ Tidak ditemukan jawaban kilat dengan kata kunci/ID '{kata_kunci}'."
        prof["quick_replies"] = qrs
        with open(multi_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return f"🗑️ Berhasil menghapus jawaban kilat '{kata_kunci}' dari profil {resolved_pid}."
    except Exception as e:
        return f"❌ Gagal menghapus jawaban kilat: {str(e)}"

FUNCTIONS = {
    "kirim_pesan_whatsapp": kirim_pesan_whatsapp,
    "kirim_vn_whatsapp": kirim_vn_whatsapp,
    "kirim_file_whatsapp": kirim_file_whatsapp,
    "baca_pesan_terakhir_wa": baca_pesan_whatsapp_unread,
    "ambil_kontak_whatsapp": daftar_kontak_whatsapp,
    "telepon_whatsapp": telepon_whatsapp,
    "angkat_telepon_whatsapp": angkat_telepon_whatsapp,
    "kirim_status_whatsapp": kirim_status_whatsapp,
    "cek_penonton_status_whatsapp": cek_penonton_status_whatsapp,
    "mode_admin_wa": mode_admin_wa,
    "simpan_kontak_wa": simpan_kontak_wa,
    "hapus_kontak_wa": hapus_kontak_wa,
    "daftar_buku_kontak": daftar_buku_kontak,
    "atur_mode_sibuk_wa": atur_mode_sibuk_wa,
    "tambah_jawaban_kilat_wa": tambah_jawaban_kilat_wa,
    "daftar_jawaban_kilat_wa": daftar_jawaban_kilat_wa,
    "hapus_jawaban_kilat_wa": hapus_jawaban_kilat_wa,
}
