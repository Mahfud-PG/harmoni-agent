"""
Harmoni Agent - Markdown Skills Manager
Sistem keahlian dan prosedur kerja on-demand (gaya Hermes Agent).
Menyimpan panduan teknis/SOP dalam berkas Markdown (SKILL.md) terpisah.
Hanya judul dan deskripsi 1 baris yang dimuat ke sistem prompt (sangat hemat token).
Isi lengkap prosedur hanya dimuat saat dibutuhkan.
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from sari_core.paths import PROJECT_ROOT

logger = logging.getLogger("HarmoniSkills")

SKILLS_DIR = PROJECT_ROOT / "skills"
os.makedirs(str(SKILLS_DIR), exist_ok=True)


def _parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Memisahkan frontmatter YAML dengan badan markdown."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body = match.group(2)
        try:
            meta = yaml.safe_load(yaml_text) or {}
            if isinstance(meta, dict):
                return meta, body.strip()
        except Exception:
            pass
    return {}, content.strip()


def list_available_skills() -> List[Dict[str, Any]]:
    """Mendaftar seluruh skill markdown yang tersedia di folder skills/."""
    skills = []
    if not SKILLS_DIR.exists():
        return skills

    # 1. Pindai folder anak yang berisi SKILL.md
    for entry in SKILLS_DIR.iterdir():
        skill_file = None
        if entry.is_dir():
            target = entry / "SKILL.md"
            if target.exists():
                skill_file = target
        elif entry.is_file() and entry.suffix.lower() == ".md":
            skill_file = entry

        if skill_file and skill_file.exists():
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    text = f.read()
                meta, body = _parse_frontmatter(text)
                name = meta.get("name") or entry.stem
                desc = meta.get("description") or ""
                if not desc and body:
                    # Ambil baris pertama sebagai deskripsi jika tidak ada di frontmatter
                    for line in body.split("\n"):
                        clean_line = line.strip().lstrip("#").strip()
                        if clean_line:
                            desc = clean_line[:120]
                            break
                tags = meta.get("tags") or []
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]

                skills.append({
                    "name": name.strip(),
                    "description": desc.strip(),
                    "tags": tags,
                    "file_path": str(skill_file)
                })
            except Exception as e:
                logger.warning(f"Gagal membaca skill {skill_file}: {e}")

    skills.sort(key=lambda s: s["name"])
    return skills


def get_skill_content(skill_name: str) -> Optional[str]:
    """Mengambil isi utuh prosedur dari sebuah skill."""
    clean_name = skill_name.strip().lower()
    
    # Cek format folder
    dir_target = SKILLS_DIR / clean_name / "SKILL.md"
    if dir_target.exists():
        with open(dir_target, "r", encoding="utf-8") as f:
            return f.read()

    # Cek format file langsung
    file_target = SKILLS_DIR / f"{clean_name}.md"
    if file_target.exists():
        with open(file_target, "r", encoding="utf-8") as f:
            return f.read()

    # Pencarian fleksibel
    for s in list_available_skills():
        if s["name"].lower() == clean_name:
            with open(s["file_path"], "r", encoding="utf-8") as f:
                return f.read()

    return None


def save_skill(name: str, description: str, markdown_content: str, tags: List[str] = None) -> bool:
    """Membuat atau memperbarui berkas skill SKILL.md."""
    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower()).strip("-")
    if not clean_name:
        return False

    folder = SKILLS_DIR / clean_name
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / "SKILL.md"

    frontmatter_dict = {
        "name": clean_name,
        "description": description.strip(),
        "tags": tags or []
    }
    frontmatter_yaml = yaml.dump(frontmatter_dict, allow_unicode=True, default_flow_style=False).strip()
    
    # Bersihkan markdown content jika sudah ada frontmatter
    _, body = _parse_frontmatter(markdown_content)

    full_text = f"---\n{frontmatter_yaml}\n---\n\n{body}\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    return True


def delete_skill(name: str) -> bool:
    """Menghapus skill tertentu."""
    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower()).strip("-")
    folder = SKILLS_DIR / clean_name
    if folder.exists() and folder.is_dir():
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        return True
    file_target = SKILLS_DIR / f"{clean_name}.md"
    if file_target.exists():
        file_target.unlink()
        return True
    return False


def get_skills_catalog_prompt() -> str:
    """Menghasilkan ringkasan ringkas katalog skill untuk dimasukkan ke prompt sistem."""
    skills = list_available_skills()
    if not skills:
        return ""

    lines = ["<available_skills>"]
    for s in skills:
        lines.append(f"  - {s['name']}: {s['description']}")
    lines.append("</available_skills>")
    lines.append("Gunakan alat 'baca_panduan_skill' jika membutuhkan SOP/prosedur kerja lengkap dari keahlian di atas.")
    return "\n".join(lines)


def match_skills_for_context(user_text: str) -> List[Dict[str, Any]]:
    """Mendeteksi apakah pesan pengguna menyebut kata kunci yang cocok dengan skill tertentu."""
    matched = []
    text_lower = user_text.lower()
    for s in list_available_skills():
        # Cocokkan nama
        name_clean = s["name"].replace("-", " ").lower()
        if name_clean in text_lower or s["name"].lower() in text_lower:
            matched.append(s)
            continue
        # Cocokkan tags
        for t in s.get("tags", []):
            if str(t).lower() in text_lower:
                matched.append(s)
                break
    return matched


# === HANDLER TOOL UNTUK AI REGISTRY ===

def baca_panduan_skill(nama_skill: str) -> str:
    """Membaca isi lengkap berkas SOP/keahlian markdown tertentu."""
    content = get_skill_content(nama_skill)
    if content:
        return f"=== Panduan Skill: {nama_skill} ===\n\n{content}"
    return f"Skill '{nama_skill}' tidak ditemukan di folder skills/. Gunakan 'daftar_panduan_skill' untuk melihat daftar yang ada."


def simpan_panduan_skill(nama_skill: str, deskripsi: str, prosedur_markdown: str) -> str:
    """Menyimpan atau memperbarui panduan keahlian / SOP baru ke folder skills/."""
    ok = save_skill(nama_skill, deskripsi, prosedur_markdown)
    if ok:
        return f"Berhasil menyimpan panduan skill '{nama_skill}' ke folder skills/."
    return f"Gagal menyimpan panduan skill '{nama_skill}'."


def daftar_panduan_skill() -> str:
    """Mendaftar semua keahlian dan SOP markdown yang tersedia."""
    skills = list_available_skills()
    if not skills:
        return "Belum ada skill yang terpasang di folder skills/."
    lines = ["Daftar Skill yang Tersedia:"]
    for s in skills:
        lines.append(f"- {s['name']}: {s['description']}")
    return "\n".join(lines)


SKILL_TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "baca_panduan_skill",
            "description": "Membaca SOP atau panduan kerja lengkap dari keahlian tertentu yang terdaftar di katalog skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_skill": {
                        "type": "string",
                        "description": "Nama skill yang ingin dibaca (misal: 'mixing-audio', 'layanan-studio')"
                    }
                },
                "required": ["nama_skill"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "simpan_panduan_skill",
            "description": "Menyimpan atau memperbarui SOP / prosedur kerja baru ke dalam berkas Markdown (SKILL.md).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama_skill": {
                        "type": "string",
                        "description": "Nama pengenal skill (huruf kecil, pisah tanda minus, misal: 'pembuat-lirik')"
                    },
                    "deskripsi": {
                        "type": "string",
                        "description": "Ringkasan 1 kalimat tentang apa tujuan keahlian ini."
                    },
                    "prosedur_markdown": {
                        "type": "string",
                        "description": "Isi lengkap langkah kerja, panduan, atau aturan dalam format Markdown."
                    }
                },
                "required": ["nama_skill", "deskripsi", "prosedur_markdown"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "daftar_panduan_skill",
            "description": "Melihat daftar seluruh panduan keahlian dan SOP yang tersimpan di sistem.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
