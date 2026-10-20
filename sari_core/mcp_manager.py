"""
Harmoni Agent - MCP Client & Registry Bridge (JSON-RPC 2.0 via Stdio / SSE)
Modul mandiri untuk menghubungkan Harmoni Agent dengan Model Context Protocol (MCP).
Mendukung:
1. Pemuatan daftar server MCP dari `konfigurasi_mcp.json`.
2. Sakelar ON/OFF per server MCP (menghemat token saat nonaktif).
3. Pemanggilan alat (tools/call) via protokol standar JSON-RPC 2.0 stdio.
4. Pendaftaran dinamis ke `tool_registry` Harmoni Agent saat server berstatus AKTIF.
"""

import os
import sys
import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

try:
    from sari_core.paths import PROJECT_ROOT
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

KONFIGURASI_MCP_FILE = PROJECT_ROOT / "konfigurasi_mcp.json"

def _muat_konfigurasi() -> Dict[str, Any]:
    default_cfg = {
        "mcp_enabled": True,
        "servers": {
            "spotify": {
                "name": "Spotify Player",
                "description": "Kendali pemutar musik Spotify di latar belakang",
                "enabled": False,
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-spotify"],
                "env": {},
                "tools_cache": []
            },
            "youtube": {
                "name": "YouTube Audio & Transcript",
                "description": "Pencari audio dan transkrip video YouTube",
                "enabled": False,
                "command": "npx",
                "args": ["-y", "youtube-transcript-mcp"],
                "env": {},
                "tools_cache": []
            }
        }
    }
    if not KONFIGURASI_MCP_FILE.exists():
        try:
            with open(KONFIGURASI_MCP_FILE, "w", encoding="utf-8") as f:
                json.dump(default_cfg, f, indent=2)
        except Exception as e:
            logger.warning(f"[MCP] Gagal membuat file default konfigurasi_mcp.json: {e}")
        return default_cfg

    try:
        with open(KONFIGURASI_MCP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[MCP] Gagal membaca konfigurasi_mcp.json: {e}")
        return default_cfg

def _simpan_konfigurasi(cfg: Dict[str, Any]) -> bool:
    try:
        with open(KONFIGURASI_MCP_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"[MCP] Gagal menyimpan konfigurasi_mcp.json: {e}")
        return False

class MCPClientManager:
    """Manajer Server MCP untuk Harmoni Agent."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPClientManager, cls).__new__(cls)
            cls._instance._registered_tools = {}
        return cls._instance

    def daftar_mcp(self) -> List[Dict[str, Any]]:
        """Mengembalikan daftar seluruh server MCP beserta status aktifnya."""
        cfg = _muat_konfigurasi()
        hasil = []
        for server_id, data in cfg.get("servers", {}).items():
            hasil.append({
                "id": server_id,
                "name": data.get("name", server_id),
                "description": data.get("description", ""),
                "enabled": bool(data.get("enabled", False)),
                "command": data.get("command", ""),
                "args": data.get("args", []),
                "tools_count": len(data.get("tools_cache", []))
            })
        return hasil

    def set_status_mcp(self, server_id: str, aktif: bool) -> tuple:
        """Mengubah status aktif/nonaktif server MCP tertentu."""
        cfg = _muat_konfigurasi()
        servers = cfg.get("servers", {})
        if server_id not in servers:
            return False, f"Server MCP '{server_id}' tidak ditemukan."

        servers[server_id]["enabled"] = aktif
        _simpan_konfigurasi(cfg)

        # Refresh sinkronisasi ke ToolRegistry
        self.sinkronkan_ke_tool_registry()

        status_teks = "diaktifkan" if aktif else "dinonaktifkan"
        return True, f"Server MCP '{servers[server_id].get('name', server_id)}' berhasil {status_teks}."

    def tambah_server_mcp(self, server_id: str, name: str, command: str, args: List[str], description: str = "") -> tuple:
        """Menambahkan server MCP baru ke konfigurasi."""
        cfg = _muat_konfigurasi()
        servers = cfg.setdefault("servers", {})
        servers[server_id] = {
            "name": name or server_id,
            "description": description or f"Eksternal MCP Server {server_id}",
            "enabled": True,
            "command": command,
            "args": args,
            "env": {},
            "tools_cache": []
        }
        _simpan_konfigurasi(cfg)
        self.sinkronkan_ke_tool_registry()
        return True, f"Server MCP '{name}' berhasil didaftarkan dan diaktifkan."

    def hapus_server_mcp(self, server_id: str) -> tuple:
        """Menghapus server MCP dari konfigurasi."""
        cfg = _muat_konfigurasi()
        servers = cfg.get("servers", {})
        if server_id in servers:
            nama = servers[server_id].get("name", server_id)
            del servers[server_id]
            _simpan_konfigurasi(cfg)
            self.sinkronkan_ke_tool_registry()
            return True, f"Server MCP '{nama}' berhasil dihapus."
        return False, f"Server MCP '{server_id}' tidak ditemukan."

    def jalankan_tool_mcp(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Memanggil alat spesifik pada server MCP via JSON-RPC stdio."""
        cfg = _muat_konfigurasi()
        srv = cfg.get("servers", {}).get(server_id)
        if not srv or not srv.get("enabled"):
            return f"Gagal: Server MCP '{server_id}' sedang dinonaktifkan."

        cmd = [srv.get("command")] + srv.get("args", [])
        # Di Windows, npx adalah file batch (.cmd) sehingga membutuhkan shell=True atau resolusi path
        import shutil
        if sys.platform == "win32":
            resolved_cmd = shutil.which(cmd[0])
            if resolved_cmd:
                cmd[0] = resolved_cmd

        rpc_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {}
            }
        }

        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=(sys.platform == "win32"),
                env=os.environ.copy()
            )
            stdout, stderr = p.communicate(input=json.dumps(rpc_request) + "\n", timeout=30)
            if not stdout:
                return f"Gagal: Server MCP tidak memberikan balasan stdout. Error: {stderr}"

            for line in stdout.strip().splitlines():
                try:
                    data = json.loads(line)
                    if data.get("id") == 1:
                        if "error" in data:
                            return f"Error dari MCP ({server_id}): {data['error']}"
                        result = data.get("result", {})
                        content = result.get("content", [])
                        if isinstance(content, list) and len(content) > 0:
                            teks = content[0].get("text", "")
                            if teks:
                                return teks
                        return json.dumps(result, ensure_ascii=False)
                except Exception:
                    continue

            return f"Respons mentah MCP: {stdout[:300]}"
        except Exception as e:
            logger.error(f"[MCP] Error saat menjalankan {server_id}:{tool_name}: {e}")
            return f"Gagal mengeksekusi alat MCP '{tool_name}': {str(e)}"

    def sinkronkan_ke_tool_registry(self):
        """Mendaftarkan atau mencabut alat MCP ke ToolRegistry Harmoni."""
        try:
            from sari_core.brain import tool_registry
        except Exception:
            return

        cfg = _muat_konfigurasi()
        servers = cfg.get("servers", {})

        # 1. Cabut alat MCP yang sebelumnya pernah didaftarkan
        for tool_name in list(self._registered_tools.keys()):
            tool_registry.unregister_tool(tool_name)
        self._registered_tools.clear()

        if not cfg.get("mcp_enabled", True):
            logger.info("[MCP] Seluruh MCP dinonaktifkan secara global.")
            return

        # 2. Daftarkan fungsi pemanggil dinamis untuk tiap server yang aktif
        for srv_id, srv in servers.items():
            if not srv.get("enabled"):
                continue

            # Buat handler fungsi dinamis
            def _buat_handler(s_id):
                def _handler(perintah: str, parameter: dict = None):
                    return mcp_manager.jalankan_tool_mcp(s_id, perintah, parameter or {})
                return _handler

            tool_name = f"mcp_{srv_id}"
            deskripsi = f"[Eksternal MCP] {srv.get('name')}: {srv.get('description')}. Gunakan untuk menjalankan perintah khusus pada server ini."
            schema = {
                "name": tool_name,
                "description": deskripsi,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "perintah": {
                            "type": "string",
                            "description": "Nama aksi atau tool yang ingin dijalankan di server MCP ini"
                        },
                        "parameter": {
                            "type": "object",
                            "description": "Objek argumen parameter untuk perintah tersebut (opsional)"
                        }
                    },
                    "required": ["perintah"]
                }
            }

            tool_registry.register_tool(
                name=tool_name,
                risk_level="MEDIUM",
                handler=_buat_handler(srv_id),
                description=deskripsi,
                schema=schema
            )
            self._registered_tools[tool_name] = srv_id
            logger.info(f"[MCP] Berhasil mendaftarkan alat '{tool_name}' ke ToolRegistry.")

# Objek Global
mcp_manager = MCPClientManager()
