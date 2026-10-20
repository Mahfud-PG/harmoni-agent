import os
import json
import re
from sari_core.paths import OUTPUT_DIR

MANIFEST = {
    "name": "Professional Prompt & PRD Architect",
    "version": "1.0.0",
    "author": "Harmoni Agent",
    "description": "Modul kecerdasan tinggi untuk membuat AI Prompt super keren dan dokumen Product Requirement Document (PRD.md) profesional."
}

def _minta_llm(prompt_sistem: str, prompt_user: str) -> str:
    """Helper untuk memanggil LLM (Groq Llama 3.3 70B / DeepSeek / Gemini) secara terisolasi."""
    try:
        from bot_otomatis import minta_jawaban_ai
        messages = [
            {"role": "system", "content": prompt_sistem},
            {"role": "user", "content": prompt_user}
        ]
        response, _ = minta_jawaban_ai(messages)
        if response and response.choices:
            return response.choices[0].message.content or ""
    except Exception as e:
        return f"Gagal memproses LLM: {str(e)}"
    return ""

def buat_prompt_pro(topik_atau_tujuan: str, kategori: str = "umum"):
    """
    Membuat Prompt AI kelas dunia (super keren, rinci, dan tidak asal-asalan)
    untuk berbagai keperluan: Gambar (Midjourney/FLUX/SD), Coding (LLM/Claude), Video (Sora/Runway), Musik (Suno), dll.
    """
    try:
        kat_clean = kategori.lower().strip()
        system_prompt = (
            "Anda adalah Senior Prompt Engineer kelas dunia. "
            "Tugas Anda adalah merancang Prompt AI yang SUPER KEREN, sangat detail, terstruktur, presisi, "
            "dan memberikan hasil yang menakjubkan (WOW factor). Jangan buat prompt yang generik atau sederhana.\n\n"
            "Format Output Wajib:\n"
            "1. 🎯 **Konsep & Tujuan Prompt**\n"
            "2. 🚀 **Master Prompt (Siap Copy-Paste)**\n"
            "3. ⚙️ **Negative Prompt / Batasan & Parameter**\n"
            "4. 💡 **Rekomendasi Setting & Model AI Terbaik**"
        )
        
        user_prompt = f"Tolong buatkan Prompt AI Super Keren untuk:\nTopik/Tujuan: {topik_atau_tujuan}\nKategori: {kat_clean}"
        
        hasil = _minta_llm(system_prompt, user_prompt)
        if not hasil:
            return "❌ Gagal menggenerate prompt pro."
            
        return f"🎨 *PROMPT ENGINEER PRO - SARI AI*\n\n{hasil}"
    except Exception as e:
        return f"❌ Gagal membuat prompt pro: {str(e)}"

def buat_prd_pro(nama_proyek: str, deskripsi_ide: str, jalur_simpan: str = ""):
    """
    Membuat dokumen Product Requirement Document (PRD) yang super komprehensif, profesional, dan berstandar industri.
    Selain mengirimkan ringkasan di Telegram, fungsi ini akan OTOMATIS MEMBUAT FILE DOKUMEN `.md` (misal: prd.md / PRD_[Nama_Proyek].md) di PC.
    """
    try:
        system_prompt = (
            "Anda adalah Lead Product Manager & Chief System Architect profesional dari Google / Silicon Valley. "
            "Tugas Anda adalah membuat Product Requirement Document (PRD) yang SUPER LENGKAP, terstruktur, "
            "presisi, berstandar enterprise, serta ramah aksesibilitas (termasuk aksesibilitas disabilitas netra/screen-reader).\n\n"
            "Struktur Dokumen PRD Wajib (Format Markdown Lengkap):\n"
            "# PRD: [Nama Proyek]\n\n"
            "## 1. Executive Summary & Overview\n"
            "## 2. Background & Problem Statement\n"
            "## 3. Goals & Success Metrics (KPIs)\n"
            "## 4. Target User Persona & User Stories\n"
            "## 5. Functional Requirements & Feature Breakdown (Detailed Input/Output & Edge Cases)\n"
            "## 6. Non-Functional Requirements (Performance, Security, Accessibility WCAG)\n"
            "## 7. Technical Architecture & Tech Stack\n"
            "## 8. Data Flow & System Logic\n"
            "## 9. UI/UX Design Guidelines\n"
            "## 10. Risk Analysis & Mitigation\n"
            "## 11. Implementation Roadmap & Milestones\n"
        )
        
        user_prompt = (
            f"Tolong buatkan dokumen PRD (Product Requirement Document) super keren dan komprehensif untuk:\n"
            f"Nama Proyek: {nama_proyek}\n"
            f"Deskripsi Ide & Fitur: {deskripsi_ide}"
        )
        
        isi_prd = _minta_llm(system_prompt, user_prompt)
        if not isi_prd:
            return "❌ Gagal menghasilkan dokumen PRD."
            
        nama_bersih = re.sub(r'[^\w\-]', '_', nama_proyek.strip()).strip('_')
        if not nama_bersih: nama_bersih = "Proyek"
        
        if not jalur_simpan:
            folder_output = str(OUTPUT_DIR)
            os.makedirs(folder_output, exist_ok=True)
            jalur_simpan = os.path.join(folder_output, f"PRD_{nama_bersih}.md")
        else:
            folder_dir = os.path.dirname(jalur_simpan)
            if folder_dir:
                os.makedirs(folder_dir, exist_ok=True)
                
        with open(jalur_simpan, "w", encoding="utf-8") as f:
            f.write(isi_prd)
            
        ringkasan_singkat = (
            f"📋 *PRD (Product Requirement Document) BERHASIL DIBUAT!*\n\n"
            f"📌 **Nama Proyek:** `{nama_proyek}`\n"
            f"📄 **Dokumen File:** `{jalur_simpan}`\n\n"
            f"--- *Ringkasan PRD* ---\n"
            f"{isi_prd[:1200]}...\n\n"
            f"💡 *Dokumen lengkap berformat Markdown telah tersimpan rapi di PC pengguna di:* `{jalur_simpan}`"
        )
        return ringkasan_singkat
    except Exception as e:
        return f"❌ Gagal membuat PRD: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buat_prompt_pro",
            "description": "Merancang Prompt AI kelas dunia (super keren, rinci, dan tidak asal-asalan) untuk gambar, coding, video, atau musik.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topik_atau_tujuan": {"type": "string", "description": "Topik, ide, atau tujuan utama prompt."},
                    "kategori": {"type": "string", "description": "Kategori prompt: 'image', 'code', 'suno', 'sora', 'gpt', atau 'umum'."}
                },
                "required": ["topik_atau_tujuan"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buat_prd_pro",
            "description": "Membuat dokumen Product Requirement Document (PRD) yang super komprehensif dan profesional, serta OTOMATIS MEMBUAT FILE DOKUMEN .md (misal: PRD_NamaProyek.md) di PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_proyek": {"type": "string", "description": "Nama proyek atau aplikasi."},
                    "deskripsi_ide": {"type": "string", "description": "Penjelasan detail ide, fitur, dan kebutuhan proyek."},
                    "jalur_simpan": {"type": "string", "description": "Optional: Path lokasi penyimpan file .md (misal: 'File/Output/prd.md'). Jika kosong, otomatis disimpan ke folder File/Output."}
                },
                "required": ["nama_proyek", "deskripsi_ide"]
            }
        }
    }
]

FUNCTIONS = {
    "buat_prompt_pro": buat_prompt_pro,
    "buat_prd_pro": buat_prd_pro
}
