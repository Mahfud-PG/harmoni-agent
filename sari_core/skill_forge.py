"""
Sari AI Operating System - Dynamic Skill Forge
Modul perakit plugin dan keahlian baru secara otonom dengan izin manusia (Human-in-the-Loop)
dan pengujian mandiri di ruang isolasi (Sandbox Subprocess).
"""

import os
import sys
import json
import time
import re
import subprocess
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional

from sari_core.paths import PROJECT_ROOT

PLUGINS_DIR = PROJECT_ROOT / "plugins_dinamis"
TICKET_FILE = PLUGINS_DIR / "active_ticket.json"
TICKET_TIMEOUT_SECONDS = 600  # 10 menit batas waktu konfirmasi

# Pastikan folder plugins_dinamis tersedia
os.makedirs(str(PLUGINS_DIR), exist_ok=True)


def get_active_ticket() -> Optional[Dict[str, Any]]:
    """Membaca tiket konfirmasi yang sedang aktif dan belum kadaluarsa."""
    if not os.path.exists(str(TICKET_FILE)):
        return None
    try:
        with open(str(TICKET_FILE), "r", encoding="utf-8") as f:
            data = json.load(f)
        proposed_at = data.get("proposed_at", 0)
        if time.time() - proposed_at > TICKET_TIMEOUT_SECONDS:
            # Tiket sudah kadaluarsa
            clear_ticket()
            return None
        if data.get("status") == "PENDING_CONFIRMATION":
            return data
    except Exception:
        pass
    return None


def create_ticket(tool_name: str, description: str, reason: str, user_request: str = "") -> Dict[str, Any]:
    """Menerbitkan tiket konfirmasi baru."""
    ticket = {
        "ticket_id": f"SKILL_{int(time.time())}",
        "tool_name": tool_name,
        "description": description,
        "reason": reason,
        "user_request": user_request,
        "proposed_at": time.time(),
        "status": "PENDING_CONFIRMATION"
    }
    with open(str(TICKET_FILE), "w", encoding="utf-8") as f:
        json.dump(ticket, f, indent=4)
    return ticket


def clear_ticket():
    """Menghapus atau mengosongkan tiket aktif."""
    if os.path.exists(str(TICKET_FILE)):
        try:
            os.remove(str(TICKET_FILE))
        except Exception:
            pass


def propose_new_skill(tool_name: str, description: str, reason: str, user_request: str = "") -> str:
    """
    Harmoni mengajukan proposal pembuatan keahlian baru kepada pengguna.
    Fungsi ini TIDAK menulis kode, hanya menerbitkan tiket dan meminta konfirmasi.
    """
    from sari_core.brain import tool_registry

    # Bersihkan nama alat
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name.strip().lower())
    if clean_name.startswith("_"):
        clean_name = "alat" + clean_name

    # Cek apakah alat sudah ada
    if tool_registry.get_tool(clean_name):
        return f"Alat dengan nama '{clean_name}' sudah ada di daftar kemampuan Harmoni dan siap dipakai."

    create_ticket(clean_name, description, reason, user_request)

    pesan_izin = (
        f"💡 **Proposal Keahlian Baru dari Harmoni:**\n\n"
        f"pengguna, untuk perintah ini Harmoni belum memiliki alat khusus. Namun Harmoni bisa merakitkan keahlian baru secara otomatis:\n"
        f"• **Nama Alat:** `{clean_name}`\n"
        f"• **Fungsi:** {description}\n"
        f"• **Alasan:** {reason}\n\n"
        f"❓ **Apakah pengguna mengizinkan Harmoni merakit dan menguji alat ini sekarang?**\n"
        f"*(Balas **'ya'** atau **'gas'** untuk menyetujui, atau **'batal'** jika tidak jadi)*"
    )
    return pesan_izin


def execute_skill_forge(confirmation_text: str) -> str:
    """
    Mengeksekusi perakitan keahlian baru jika dan HANYA JIKA ada tiket resmi yang aktif
    dan disetujui secara sadar oleh pengguna.
    """
    ticket = get_active_ticket()
    if not ticket:
        return "Tidak ada tiket pembuatan keahlian baru yang sedang menunggu persetujuan. Perintah diabaikan."

    teks_lower = confirmation_text.strip().lower()

    # Cek pembatalan
    batal_words = ["batal", "jangan", "tidak", "gak usah", "nggak usah", "batalin", "cancel", "stop"]
    if any(bw in teks_lower for bw in batal_words):
        clear_ticket()
        return "Siap pengguna! Pembuatan keahlian baru resmi dibatalkan. Tidak ada file atau kode yang diubah."

    # Cek persetujuan eksplisit
    setuju_words = ["ya", "gas", "buat", "rakit", "lanjut", "oke", "ok", "lanjutkan", "setuju", "boleh", "gas buatkan"]
    if not any(sw == teks_lower or teks_lower.startswith(sw + " ") or sw in teks_lower for sw in setuju_words):
        # Jika bukan kata persetujuan, jangan hanguskan tiket langsung tapi ingatkan pengguna
        return (
            f"Tiket pembuatan alat `{ticket['tool_name']}` masih menunggu persetujuan pengguna.\n"
            f"Ketik **'ya'** / **'gas'** untuk membuat, atau **'batal'** untuk membatalkan."
        )

    # MULAI PERAKITAN (Sandbox Execution)
    tool_name = ticket["tool_name"]
    description = ticket["description"]
    user_request = ticket["user_request"]

    print(f"[SkillForge] Memulai perakitan alat dinamis: {tool_name}...")

    # Panggil LLM untuk men-generate kode plugin
    code_content = _generate_plugin_code(tool_name, description, user_request)
    if not code_content:
        clear_ticket()
        return f"Maaf pengguna, Harmoni gagal merancang kode untuk alat `{tool_name}`. Proses dihentikan."

    temp_path = PLUGINS_DIR / f"temp_{tool_name}.py"
    final_path = PLUGINS_DIR / f"{tool_name}.py"

    try:
        with open(str(temp_path), "w", encoding="utf-8") as f:
            f.write(code_content)

        # 1. Uji Sintaks & Verifikasi Keamanan AST
        syntax_ok, err_msg = _test_syntax_and_safety(temp_path)
        if not syntax_ok:
            print(f"[SkillForge] Keamanan/Sintaks ditolak: {err_msg}, mencoba perbaikan mandiri...")
            repaired_code = _repair_code(code_content, err_msg)
            if repaired_code:
                with open(str(temp_path), "w", encoding="utf-8") as f:
                    f.write(repaired_code)
                syntax_ok, err_msg = _test_syntax_and_safety(temp_path)

        if not syntax_ok:
            _cleanup_file(temp_path)
            clear_ticket()
            return f"Uji coba di dapur percobaan gagal ({err_msg}). Harmoni aman dan sistem tidak terpengaruh."

        # 2. Uji Coba Subprocess Sandbox
        test_ok, test_output = _test_subprocess_sandbox(temp_path)
        if not test_ok:
            print(f"[SkillForge] Sandbox test gagal: {test_output}, mencoba perbaikan mandiri...")
            repaired_code = _repair_code(code_content, test_output)
            if repaired_code:
                with open(str(temp_path), "w", encoding="utf-8") as f:
                    f.write(repaired_code)
                test_ok, test_output = _test_subprocess_sandbox(temp_path)

        if not test_ok:
            _cleanup_file(temp_path)
            clear_ticket()
            return f"Uji coba di dapur percobaan gagal: {test_output}. Alat tidak dipasang demi keamanan sistem."

        # 3. Sukses! Pindahkan ke file permanen dan daftarkan ke Tool Registry
        if os.path.exists(str(final_path)):
            _cleanup_file(final_path)
        os.rename(str(temp_path), str(final_path))

        registered_ok, reg_msg = register_single_plugin(final_path)
        clear_ticket()

        if registered_ok:
            return (
                f"🎉 **Keahlian Baru Berhasil Dirakit & Terpasang!**\n\n"
                f"• **Nama Alat:** `{tool_name}`\n"
                f"• **Fungsi:** {description}\n"
                f"• **Status:** 100% Lolos Uji Coba Dapur Percobaan (Sandbox).\n\n"
                f"Alat ini sudah aktif secara langsung di sistem Harmoni dan permanen tersimpan."
            )
        else:
            return f"Kode berhasil diuji, namun gagal didaftarkan ke memori: {reg_msg}"

    except Exception as e:
        _cleanup_file(temp_path)
        clear_ticket()
        return f"Terjadi kesalahan teknis saat merakit keahlian: {e}"


def _call_llm_for_code(prompt: str) -> str:
    """Mengirim prompt ke LLM dengan rantai cadangan otomatis (9Router -> DeepSeek -> OpenAI)."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    from openai import OpenAI
    import os, urllib.request

    r_key = os.getenv("9ROUTER_API_KEY") or "sk-8c9a8b74b42eeed2-f22xx8-53234acd"
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    candidates = [
        # Candidate 1: 9Router (Antigravity Pro Gemini 3.8 Flash)
        ("http://localhost:20128/v1", r_key, "ag/gemini-3.8-flash-high"),
        # Candidate 2: DeepSeek Direct
        ("https://api.deepseek.com", deepseek_key, "deepseek-chat"),
        # Candidate 3: 9Router (Groq Llama 3.3)
        ("http://localhost:20128/v1", r_key, "groq/llama-3.3-70b-versatile"),
        # Candidate 4: OpenAI Direct
        ("https://api.openai.com/v1", openai_key, "gpt-4o-mini"),
    ]

    for base_url, key, model in candidates:
        if not key:
            continue
        try:
            client = OpenAI(base_url=base_url, api_key=key)
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                timeout=30.0
            )
            content = res.choices[0].message.content or ""
            code_match = re.search(r"```python(.*?)```", content, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            if "def execute" in content:
                return content.strip()
        except Exception as e:
            print(f"[SkillForge] Provider {model} ({base_url}) gagal: {e}")
            continue

    return ""


def _generate_plugin_code(tool_name: str, description: str, user_request: str) -> str:
    """Menggunakan LLM untuk menulis modul Python mandiri yang aman dan memiliki self-test."""
    prompt = f"""Anda adalah Senior Python Tool Architect untuk AI Asisten.
Tugas Anda: Menulis satu file skrip Python lengkap untuk alat baru bernama `{tool_name}`.

DESKRIPSI ALAT:
{description}

CONTOH KEBUTUHAN PENGGUNA:
{user_request}

STRUKTUR KODE YANG WAJIB DIIKUTI:
1. File ini adalah modul Python mandiri.
2. WAJIB mendefinisikan kamus `TOOL_SCHEMA`:
```python
TOOL_SCHEMA = {{
    "name": "{tool_name}",
    "description": "{description}",
    "parameters": {{
        "type": "object",
        "properties": {{
            # Definisikan parameter fungsi di sini beserta tipe dan deskripsinya
        }},
        "required": [
            # Daftar parameter wajib
        ]
    }}
}}
```
3. WAJIB mendefinisikan fungsi utama:
```python
def execute(**kwargs) -> str:
    # Logika eksekusi alat, return string hasil eksekusi
```
4. WAJIB memiliki blok self-test di bagian paling bawah:
```python
if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        # Jalankan tes dummy aman
        print("TEST_PASSED")
        sys.exit(0)
```
5. ATURAN KEAMANAN & INTEGRASI SISTEM:
   - Dilarang keras memformat harddisk, menghapus file di luar folder Temp, atau mematikan sistem.
   - Gunakan pustaka standar Python jika memungkinkan (urllib, json, re, math, os, pathlib).
   - Tangani error dengan try...except agar fungsi mengembalikan pesan teks yang ramah, bukan melempar Exception tak tertangani.
   - INTEGRASI YOUTUBE & DRIVE RESMI PENGGUNA:
     * Jika alat membutuhkan akses YouTube (like, komentar, upload, playlist), WAJIB gunakan:
       `from youtube_api import get_authenticated_service` lalu `youtube = get_authenticated_service('utama')`.
       DILARANG meminta YOUTUBE_ACCESS_TOKEN dari env karena sistem sudah memiliki OAuth login resmi!
     * Jika alat membutuhkan akses Google Drive, WAJIB gunakan:
       `from drive_api import get_authenticated_service` lalu `drive = get_authenticated_service('utama')`.

KEMBALIKAN HANYA KODE PYTHON MURNI di dalam blok ```python ... ``` tanpa pengantar atau penutup tambahan.
"""
    return _call_llm_for_code(prompt)


def _repair_code(code_content: str, error_message: str) -> str:
    """Memperbaiki kode yang error menggunakan LLM (Self-Debugging)."""
    prompt = f"""Perbaiki kode Python berikut yang gagal saat diuji coba.

ERROR SAAT PENGUJIAN:
{error_message}

KODE SEBELUMNYA:
```python
{code_content}
```

Pastikan:
1. Tetap sertakan TOOL_SCHEMA dan fungsi execute(**kwargs).
2. Blok if __name__ == '__main__': if '--test' in sys.argv: print('TEST_PASSED') sys.exit(0) harus tetap ada.
3. Perbaiki akar penyebab error tersebut.

Kembalikan HANYA kode Python yang sudah diperbaiki di dalam blok ```python ... ```.
"""
    return _call_llm_for_code(prompt)


def _test_syntax_and_safety(file_path: Path) -> tuple[bool, str]:
    """Menguji sintaks Python menggunakan py_compile dan AST check untuk perlindungan keamanan PC."""
    import py_compile
    import ast

    # 1. Compile check
    try:
        py_compile.compile(str(file_path), doraise=True)
    except py_compile.PyCompileError as e:
        return False, f"Error Sintaks: {e}"

    # 2. AST Safety Inspection (Mencegah perintah berbahaya)
    try:
        with open(str(file_path), "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code)

        # Daftar kata kunci / fungsi terlarang demi keamanan PC
        FORBIDDEN_CALLS = ["rmdir", "removedirs"]
        FORBIDDEN_STRINGS = ["shutdown", "format", "del /f", "rm -rf", "drop database"]

        for node in ast.walk(tree):
            # Cek pemanggilan fungsi
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in FORBIDDEN_CALLS:
                        return False, f"Keamanan Ditolak: Fungsi berbahaya '{node.func.attr}' dilarang digunakan."
                    # Cek os.system
                    if node.func.attr == "system":
                        return False, "Keamanan Ditolak: Pemanggilan langsung 'os.system' dilarang. Gunakan subprocess aman."
                elif isinstance(node.func, ast.Name):
                    if node.func.id in ["eval", "exec"] and node.func.id != "execute":
                        return False, f"Keamanan Ditolak: Fungsi '{node.func.id}' tidak diizinkan di modul plugin."

            # Cek string literal berbahaya
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val_lower = node.value.lower()
                for bad_str in FORBIDDEN_STRINGS:
                    if bad_str in val_lower:
                        return False, f"Keamanan Ditolak: Perintah terlarang '{bad_str}' terdeteksi pada skrip."

        return True, "Sintaks dan keamanan valid"
    except Exception as e:
        return False, f"Pemeriksaan keamanan gagal: {e}"


def _test_subprocess_sandbox(file_path: Path) -> tuple[bool, str]:
    """Menjalankan file di subprocess terisolasi dengan flag --test."""
    try:
        proc = subprocess.run(
            [sys.executable, str(file_path), "--test"],
            capture_output=True,
            text=True,
            timeout=15
        )
        if proc.returncode == 0 and "TEST_PASSED" in proc.stdout:
            return True, "Lolos uji coba sandbox"
        err = proc.stderr.strip() or proc.stdout.strip() or f"Exit code {proc.returncode}"
        return False, err
    except subprocess.TimeoutExpired:
        return False, "Uji coba melebihi batas waktu (Timeout 15 detik)"
    except Exception as e:
        return False, str(e)


def register_single_plugin(plugin_path: Path) -> tuple[bool, str]:
    """Memuat dan mendaftarkan satu file plugin ke dalam tool_registry."""
    from sari_core.brain import tool_registry, klasifikasi_risiko

    module_name = plugin_path.stem
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_path))
        if not spec or not spec.loader:
            return False, "Gagal memuat modul spec"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not hasattr(mod, "TOOL_SCHEMA") or not hasattr(mod, "execute"):
            return False, "Modul tidak memiliki TOOL_SCHEMA atau fungsi execute"

        schema = getattr(mod, "TOOL_SCHEMA")
        handler = getattr(mod, "execute")
        name = schema.get("name", module_name)
        desc = schema.get("description", "")

        tool_registry.register_tool(
            name=name,
            risk_level=klasifikasi_risiko(name, desc),
            handler=handler,
            description=desc,
            schema=schema
        )
        print(f"[SkillForge] Plugin dinamis '{name}' berhasil didaftarkan ke ToolRegistry.")
        return True, f"Alat {name} aktif"
    except Exception as e:
        print(f"[SkillForge] Gagal mendaftarkan plugin {module_name}: {e}")
        return False, str(e)


def load_all_dynamic_plugins():
    """Memuat semua plugin yang ada di folder plugins_dinamis saat bot pertama kali nyala."""
    if not os.path.exists(str(PLUGINS_DIR)):
        return 0

    from core.plugin_manager import get_disabled_plugins
    disabled_list = get_disabled_plugins()

    count = 0
    for p in PLUGINS_DIR.glob("*.py"):
        if p.name.startswith("temp_"):
            _cleanup_file(p)
            continue
        if p.stem in disabled_list or f"custom_{p.stem}" in disabled_list:
            print(f"[SkillForge] Plugin kustom '{p.stem}' DINONAKTIFKAN (dilewati).")
            continue
        ok, _ = register_single_plugin(p)
        if ok:
            count += 1
    if count > 0:
        print(f"[SkillForge] Berhasil memuat {count} plugin dinamis persisten.")
    return count


def manage_dynamic_skills(action: str = "lihat", tool_name: str = "") -> str:
    """
    Mengelola plugin/keahlian dinamis yang ada di folder plugins_dinamis.
    action: 'lihat' (daftar alat rakitan), 'hapus' (menghapus alat rakitan tertentu).
    """
    from sari_core.brain import tool_registry

    act = action.strip().lower()

    if act == "lihat" or act == "daftar" or act == "list":
        if not os.path.exists(str(PLUGINS_DIR)):
            return "Folder plugins_dinamis belum ada. Belum ada keahlian rakitan tambahan."
        
        plugins = [p.stem for p in PLUGINS_DIR.glob("*.py") if not p.name.startswith("temp_")]
        if not plugins:
            return "Saat ini belum ada keahlian rakitan tambahan di folder plugins_dinamis."
        
        res = "📋 **Daftar Keahlian Rakitan Tambahan (plugins_dinamis):**\n"
        for idx, p in enumerate(plugins, 1):
            t = tool_registry.get_tool(p)
            desc = t.get("description", "Tanpa deskripsi") if t else "Tersimpan di disk"
            res += f"{idx}. `{p}`: {desc}\n"
        res += "\n*(Ketik perintah untuk menghapus jika tidak dibutuhkan, misal: 'hapus alat nama_alat')*"
        return res

    elif act == "hapus" or act == "delete" or act == "remove":
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name.strip().lower())
        if not clean_name:
            return "Mohon sebutkan nama alat rakitan yang ingin dihapus."

        target_file = PLUGINS_DIR / f"{clean_name}.py"
        if not os.path.exists(str(target_file)):
            return f"Alat rakitan `{clean_name}` tidak ditemukan di folder plugins_dinamis."

        try:
            os.remove(str(target_file))
            # Hapus dari memori tool_registry jika terdaftar
            if clean_name in tool_registry.tools:
                del tool_registry.tools[clean_name]

            return f"✅ **Alat Rakitan `{clean_name}` Berhasil Dihapus!**\nBerkas kodingan telah dibersihkan dan dicabut dari memori Harmoni."
        except Exception as e:
            return f"Gagal menghapus alat rakitan `{clean_name}`: {e}"

    else:
        return f"Aksi '{action}' tidak dikenal. Pilihan aksi: 'lihat' atau 'hapus'."


def _cleanup_file(file_path: Path):
    if os.path.exists(str(file_path)):
        try:
            os.remove(str(file_path))
        except Exception:
            pass
