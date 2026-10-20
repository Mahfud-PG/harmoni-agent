import sys
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger("ToolLoader")

def load_and_register_all_tools(ai_asisten_dir: Path):
    """
    Memuat registry tools dari sistem AI Asisten tanpa mengeksekusi bot Telegram.
    Mengisolasi fungsi-fungsi lokal (PC control, YouTube, media, sistem)
    agar bisa dipanggil secara netral oleh Server Core Desktop.
    """
    if str(ai_asisten_dir) not in sys.path:
        sys.path.insert(0, str(ai_asisten_dir))

    from sari_core.brain import tool_registry, klasifikasi_risiko

    # Impor modul bot_otomatis secara terisolasi untuk mengambil definitions
    # atau langsung ambil implementasi fungsi sistem inti
    import bot_otomatis as bot_mod

    tools_definitions = getattr(bot_mod, "tools", [])
    available_funcs = getattr(bot_mod, "available_functions", {})

    count = 0
    jumlah_berisiko = 0
    for t_schema in tools_definitions:
        func_spec = t_schema.get("function", {})
        func_name = func_spec.get("name")
        handler = available_funcs.get(func_name)

        if func_name and handler:
            deskripsi = func_spec.get("description", "")
            # Tingkat risiko DITENTUKAN dari nama & deskripsi alat, bukan lagi
            # selalu "LOW". Sebelumnya semua alat bertingkat LOW sehingga
            # pengaturan Mode Aman tidak pernah berpengaruh apa pun.
            tingkat = klasifikasi_risiko(func_name, deskripsi)
            if tingkat != "LOW":
                jumlah_berisiko += 1
            tool_registry.register_tool(
                name=func_name,
                risk_level=tingkat,
                handler=handler,
                description=deskripsi,
                schema=func_spec
            )
            count += 1

    # Registrasi Sistem Skill Markdown (Hermes-Style SOP Tools)
    try:
        from sari_core.skills_manager import (
            baca_panduan_skill,
            simpan_panduan_skill,
            daftar_panduan_skill,
            SKILL_TOOLS_SCHEMAS
        )
        handlers_map = {
            "baca_panduan_skill": baca_panduan_skill,
            "simpan_panduan_skill": simpan_panduan_skill,
            "daftar_panduan_skill": daftar_panduan_skill
        }
        for s_spec in SKILL_TOOLS_SCHEMAS:
            fn = s_spec["function"]
            fn_name = fn["name"]
            h = handlers_map.get(fn_name)
            if h:
                tool_registry.register_tool(
                    name=fn_name,
                    risk_level="LOW",
                    handler=h,
                    description=fn["description"],
                    schema=fn
                )
                count += 1
    except Exception as e_sk_tool:
        logger.warning(f"Gagal meregistrasi skill tools: {e_sk_tool}")

    # Registrasi tool hapus model tambahan untuk AI Agent
    try:
        from sari_core.model_config import remove_custom_model
        def tool_hapus_model(nomor_model: str) -> str:
            ok, msg = remove_custom_model(nomor_model)
            return msg

        schema_hapus = {
            "name": "hapus_model_tambahan",
            "description": "Menghapus model AI tambahan dari menu model sistem (nomor 7 ke atas). Model 1-6 dilindungi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nomor_model": {
                        "type": "string",
                        "description": "Nomor urut model tambahan yang ingin dihapus (contoh: '7', '8', '18')"
                    }
                },
                "required": ["nomor_model"]
            }
        }
        tool_registry.register_tool(
            name="hapus_model_tambahan",
            risk_level="MEDIUM",
            handler=tool_hapus_model,
            description=schema_hapus["description"],
            schema=schema_hapus
        )
        count += 1
    except Exception as e_mtool:
        logger.warning(f"Gagal meregistrasi tool hapus model: {e_mtool}")

    logger.info(
        f"Berhasil meregistrasi {count} tools ke dalam Local Core Registry "
        f"({jumlah_berisiko} di antaranya bertingkat berisiko / butuh izin)."
    )
    return count
