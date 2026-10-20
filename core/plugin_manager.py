"""
Catatan riwayat (jangan dihapus):

Pernah ada fitur "sakelar ON/OFF plugin" di menu Pengaturan yang memakai berkas
konfigurasi_plugin.json. Fitur itu DIHAPUS karena dua kali terbukti tidak
mengikat: alat yang sudah termuat di memori tetap bisa dipanggil AI, dan banyak
bagian Harmoni memanggil fungsi plugin secara langsung tanpa lewat daftar alat.

Sekarang SELURUH plugin selalu dimuat dan aktif. Fungsi get_disabled_plugins()
sengaja dipertahankan hanya sebagai pengaman: kalau berkas konfigurasi_plugin.json
ada dan memuat nama plugin, fungsi perekaman/pengiriman di plugin terkait akan
menolak jalan (lihat _izin_penyadapan dan _plugin_wa_aktif).
"""

import os
import sys
import json
import importlib.util
from pathlib import Path

# Penyimpanan State Plugin Global
LOADED_PLUGINS = {}
LOADED_TOOLS = []
LOADED_FUNCTIONS = {}
LOADED_MANIFESTS = []

def _get_plugin_config_file():
    try:
        from sari_core.paths import DATA_ROOT
        return DATA_ROOT / "konfigurasi_plugin.json"
    except Exception:
        base_dir = Path(__file__).resolve().parent.parent
        return base_dir / "konfigurasi_plugin.json"

def get_disabled_plugins() -> list:
    """Mengambil daftar module_name plugin yang dinonaktifkan pengguna."""
    p_file = _get_plugin_config_file()
    if p_file.exists():
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("disabled_plugins", [])
        except Exception:
            return []
    return []

def load_plugins(plugins_dir=None):
    """
    Memindai folder plugins/, mengimpor/mere-load setiap modul plugin,
    dan mengumpulkan TOOLS (JSON schema), FUNCTIONS (dict), serta MANIFEST (metadata).
    """
    global LOADED_PLUGINS, LOADED_TOOLS, LOADED_FUNCTIONS, LOADED_MANIFESTS
    
    if plugins_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        plugins_dir = os.path.join(base_dir, "plugins")
        
    LOADED_TOOLS = []
    LOADED_FUNCTIONS = {}
    LOADED_MANIFESTS = []
    
    if not os.path.exists(plugins_dir):
        print(f"[PluginManager] Warning: Folder {plugins_dir} tidak ditemukan.")
        return LOADED_TOOLS, LOADED_FUNCTIONS

    if plugins_dir not in sys.path:
        sys.path.insert(0, plugins_dir)

    for file_name in os.listdir(plugins_dir):
        if file_name.endswith(".py") and not file_name.startswith("_"):
            module_name = file_name[:-3]
            file_path = os.path.join(plugins_dir, file_name)

            try:
                # Fault Isolation: Jika modul sudah pernah di-load, gunakan reload
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                
                LOADED_PLUGINS[module_name] = module
                
                # Ambil MANIFEST (Metadata)
                manifest = getattr(module, "MANIFEST", {
                    "name": module_name,
                    "version": "1.0.0",
                    "description": "Plugin tanpa deskripsi manifest."
                })
                LOADED_MANIFESTS.append(manifest)
                
                # Ambil TOOLS
                tools = getattr(module, "TOOLS", [])
                if isinstance(tools, list):
                    LOADED_TOOLS.extend(tools)
                    
                # Ambil FUNCTIONS
                functions = getattr(module, "FUNCTIONS", {})
                if isinstance(functions, dict):
                    LOADED_FUNCTIONS.update(functions)
                    
                print(f"[PluginManager] Loaded plugin: {manifest.get('name', module_name)} v{manifest.get('version', '1.0')} ({len(tools)} tools)")
            except Exception as e:
                print(f"[PluginManager] [ERROR] Gagal memuat plugin {module_name}: {e}")

    print(f"[PluginManager] Hot Reload Selesai: Total {len(LOADED_TOOLS)} alat & {len(LOADED_FUNCTIONS)} fungsi terdaftar.")
    return LOADED_TOOLS, LOADED_FUNCTIONS

def reload_plugins():
    """Mengeksekusi Hot Reload memuat ulang semua plugin tanpa restart bot."""
    return load_plugins()

def get_active_manifests():
    """Mengembalikan daftar metadata plugin aktif."""
    return LOADED_MANIFESTS
