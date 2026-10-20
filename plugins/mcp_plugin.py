"""
Harmoni Agent - Plugin Kelola MCP
Menyediakan perintah obrolan bagi pengguna untuk mengecek, mengaktifkan,
dan menonaktifkan server MCP langsung dari antarmuka obrolan.
"""

from typing import Dict, Any, List
from sari_core.mcp_manager import mcp_manager

MANIFEST = {
    "name": "Model Context Protocol (MCP) Bridge",
    "version": "1.0.0",
    "author": "Harmoni Agent",
    "description": "Jembatan koneksi ke server MCP (Spotify, YouTube, DB, dll) dengan sakelar on/off hemat token."
}

def cek_status_mcp():
    """Mengecek daftar seluruh server MCP eksternal yang terpasang di Harmoni dan status aktif/matinya."""
    daftar = mcp_manager.daftar_mcp()
    if not daftar:
        return "🔌 Belum ada server MCP yang terdaftar di Harmoni."

    aktif_count = sum(1 for d in daftar if d["enabled"])
    baris = [f"🔌 **DAFTAR SERVER MCP HARMONI ({aktif_count}/{len(daftar)} AKTIF):**\n"]

    for i, s in enumerate(daftar, 1):
        status_icon = "✅ [AKTIF]" if s["enabled"] else "❌ [NONAKTIF]"
        baris.append(f"{i}. **{s['name']}** ({s['id']})\n   Status: {status_icon}\n   Keterangan: {s['description']}\n   Perintah: `{s['command']} {' '.join(s['args'])}`\n")

    baris.append("\n💡 *Tips: Anda bisa mengaktifkan atau mematikan alat dengan berkata: 'Harmoni, aktifkan MCP spotify' atau 'Harmoni, matikan MCP youtube'.*")
    return "\n".join(baris)

def atur_sakelar_mcp(id_mcp: str, aksi: str):
    """Mengaktifkan atau mematikan satu server MCP tertentu.
    
    Args:
        id_mcp: ID server MCP (contoh: 'spotify', 'youtube')
        aksi: 'aktifkan' / 'on' untuk menyalakan, atau 'matikan' / 'off' untuk mematikan.
    """
    id_bersih = id_mcp.lower().strip()
    status_baru = aksi.lower().strip() in ["on", "aktif", "aktifkan", "true", "enable", "nyalakan"]
    
    sukses, pesan = mcp_manager.set_status_mcp(id_bersih, status_baru)
    if sukses:
        return f"✅ {pesan}"
    return f"❌ {pesan}"

FUNCTIONS = {
    "cek_status_mcp": cek_status_mcp,
    "atur_sakelar_mcp": atur_sakelar_mcp
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "cek_status_mcp",
            "description": "Menampilkan daftar seluruh koneksi alat MCP (Model Context Protocol) yang terpasang di Harmoni beserta status aktif/nonaktifnya.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atur_sakelar_mcp",
            "description": "Menyalakan (ON) atau mematikan (OFF) server MCP tertentu agar bisa menghemat token saat tidak digunakan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_mcp": {
                        "type": "string",
                        "description": "ID unik server MCP, misalnya 'spotify' atau 'youtube'"
                    },
                    "aksi": {
                        "type": "string",
                        "description": "Pilihan: 'aktifkan' / 'on' atau 'matikan' / 'off'"
                    }
                },
                "required": ["id_mcp", "aksi"]
            }
        }
    }
]
