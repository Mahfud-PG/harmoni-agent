import os
import io
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

MANIFEST = {
    "name": "Google Docs Studio Suite",
    "version": "1.0.0",
    "author": "Harmoni Agent",
    "description": "Modul integrasi Google Docs untuk membuat naskah lirik lagu, membaca dokumen, menambah revisi, dan membagikan link ke penyanyi/klien secara otomatis."
}

from sari_core.paths import get_drive_token_path, CLIENT_SECRET_FILE

SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = str(get_drive_token_path("utama"))
CLIENT_SECRET_FILE = str(CLIENT_SECRET_FILE)

def _get_drive_service():
    """Mengambil koneksi resmi Google Drive dan Docs yang terotentikasi."""
    if not os.path.exists(TOKEN_FILE):
        raise Exception(f"File token otentikasi `{TOKEN_FILE}` tidak ditemukan.")
    
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        else:
            raise Exception("Kredensial Google Drive kadaluarsa dan membutuhkan login ulang.")
            
    return build('drive', 'v3', credentials=creds)

def _cari_id_dokumen(drive_service, judul_atau_id: str):
    """Mencari file ID Google Doc berdasarkan ID langsung atau pencarian judul."""
    judul_atau_id = judul_atau_id.strip()
    
    if len(judul_atau_id) > 25 and " " not in judul_atau_id and not judul_atau_id.endswith(".txt"):
        try:
            file_meta = drive_service.files().get(fileId=judul_atau_id, fields='id, name, mimeType, webViewLink').execute()
            if file_meta and file_meta.get('mimeType') == 'application/vnd.google-apps.document':
                return file_meta
        except Exception:
            pass

    query = f"name contains '{judul_atau_id}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
    res = drive_service.files().list(q=query, pageSize=5, fields='files(id, name, webViewLink, modifiedTime)').execute()
    files = res.get('files', [])
    
    if not files:
        query_all = "mimeType = 'application/vnd.google-apps.document' and trashed = false"
        res_all = drive_service.files().list(q=query_all, pageSize=20, fields='files(id, name, webViewLink, modifiedTime)').execute()
        for f in res_all.get('files', []):
            if judul_atau_id.lower() in f.get('name', '').lower():
                return f
        return None
        
    return files[0]

def buat_google_doc(judul: str, isi: str, publik: bool = True):
    """Membuat file Google Docs baru di Google Drive (misal lirik lagu, naskah aransemen, atau catatan kerja)."""
    try:
        drive_service = _get_drive_service()
        
        file_metadata = {
            'name': judul,
            'mimeType': 'application/vnd.google-apps.document'
        }
        media = MediaInMemoryUpload(isi.encode('utf-8'), mimetype='text/plain')
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        doc_id = file.get('id')
        web_link = file.get('webViewLink')
        
        if publik:
            try:
                drive_service.permissions().create(
                    fileId=doc_id,
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()
            except Exception:
                pass
                
        status_akses = "Siapapun dengan link (Publik Reader)" if publik else "Pribadi"
        return (
            f"📄 *Google Docs Berhasil Dibuat!*\n\n"
            f"- **Judul:** `{judul}`\n"
            f"- **ID Dokumen:** `{doc_id}`\n"
            f"- **Akses:** {status_akses}\n"
            f"- **Link Dokumen:** {web_link}\n\n"
            f"💡 *pengguna bisa langsung membagikan link di atas ke penyanyi atau klien via WhatsApp.*"
        )
    except Exception as e:
        return f"❌ Gagal membuat Google Doc `{judul}`: {str(e)}"

def baca_google_doc(judul_atau_id: str):
    """Membaca isi teks dari dokumen Google Docs berdasarkan judul atau Document ID."""
    try:
        drive_service = _get_drive_service()
        target = _cari_id_dokumen(drive_service, judul_atau_id)
        if not target:
            return f"❌ Dokumen Google Docs dengan judul atau ID `{judul_atau_id}` tidak ditemukan di Google Drive."
            
        doc_id = target.get('id')
        doc_name = target.get('name')
        web_link = target.get('webViewLink')
        
        export_bytes = drive_service.files().export(fileId=doc_id, mimeType='text/plain').execute()
        isi_teks = export_bytes.decode('utf-8', errors='replace').strip()
        
        if not isi_teks:
            return f"📄 Dokumen `{doc_name}` ditemukan, namun isinya masih kosong.\nLink: {web_link}"
            
        return (
            f"📖 *Isi Dokumen Google Docs: '{doc_name}'*\n"
            f"🔗 Link: {web_link}\n"
            f"----------------------------------------\n"
            f"{isi_teks}\n"
            f"----------------------------------------"
        )
    except Exception as e:
        return f"❌ Gagal membaca Google Doc `{judul_atau_id}`: {str(e)}"

def tulis_tambah_google_doc(judul_atau_id: str, teks_tambahan: str):
    """Menambahkan teks/bait lirik/catatan revisi baru ke bagian akhir dokumen Google Docs yang sudah ada."""
    try:
        drive_service = _get_drive_service()
        target = _cari_id_dokumen(drive_service, judul_atau_id)
        if not target:
            return f"❌ Dokumen Google Docs `{judul_atau_id}` tidak ditemukan untuk ditambahkan teks."
            
        doc_id = target.get('id')
        doc_name = target.get('name')
        web_link = target.get('webViewLink')
        
        export_bytes = drive_service.files().export(fileId=doc_id, mimeType='text/plain').execute()
        isi_lama = export_bytes.decode('utf-8', errors='replace').strip()
        
        isi_baru = (isi_lama + "\n\n" + teks_tambahan).strip() if isi_lama else teks_tambahan.strip()
        media = MediaInMemoryUpload(isi_baru.encode('utf-8'), mimetype='text/plain')
        
        drive_service.files().update(fileId=doc_id, media_body=media).execute()
        
        return (
            f"✍️ *Berhasil Menambahkan Teks ke Dokumen!*\n"
            f"- **Dokumen:** `{doc_name}`\n"
            f"- **Teks yang Ditambahkan:**\n> {teks_tambahan}\n"
            f"- **Link Dokumen:** {web_link}"
        )
    except Exception as e:
        return f"❌ Gagal menambahkan teks ke Google Doc `{judul_atau_id}`: {str(e)}"

def cari_google_doc(kata_kunci: str = ""):
    """Mencari dan menampilkan daftar file Google Docs yang tersimpan di Google Drive."""
    try:
        drive_service = _get_drive_service()
        
        if kata_kunci.strip():
            query = f"name contains '{kata_kunci}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        else:
            query = "mimeType = 'application/vnd.google-apps.document' and trashed = false"
            
        res = drive_service.files().list(
            q=query,
            pageSize=15,
            fields='files(id, name, webViewLink, modifiedTime)'
        ).execute()
        
        docs = res.get('files', [])
        if not docs:
            return f"ℹ️ Tidak ditemukan dokumen Google Docs yang cocok dengan pencarian '{kata_kunci}'." if kata_kunci else "ℹ️ Belum ada dokumen Google Docs yang tersimpan di Google Drive pengguna."
            
        laporan = f"📚 *Daftar Google Docs di Google Drive ({len(docs)} file):*\n\n"
        for idx, d in enumerate(docs, 1):
            waktu = d.get('modifiedTime', '')[:10]
            laporan += f"{idx}. **{d.get('name')}** (Update: {waktu})\n   - Link: {d.get('webViewLink')}\n   - ID: `{d.get('id')}`\n\n"
            
        return laporan.strip()
    except Exception as e:
        return f"❌ Gagal mencari Google Docs: {str(e)}"

def bagikan_google_doc(judul_atau_id: str, sebagai_editor: bool = False):
    """Membuka izin akses Google Docs dan menghasilkan tautan (link) publik untuk dibagikan ke penyanyi atau klien."""
    try:
        drive_service = _get_drive_service()
        target = _cari_id_dokumen(drive_service, judul_atau_id)
        if not target:
            return f"❌ Dokumen Google Docs `{judul_atau_id}` tidak ditemukan."
            
        doc_id = target.get('id')
        doc_name = target.get('name')
        
        peran = 'writer' if sebagai_editor else 'reader'
        drive_service.permissions().create(
            fileId=doc_id,
            body={'type': 'anyone', 'role': peran}
        ).execute()
        
        meta = drive_service.files().get(fileId=doc_id, fields='webViewLink').execute()
        link = meta.get('webViewLink')
        
        peran_teks = "Bisa Mengedit (Editor)" if sebagai_editor else "Hanya Membaca (Viewer / Pelihat)"
        return (
            f"🔗 *Tautan Berbagi Google Docs Siap!*\n\n"
            f"- **Dokumen:** `{doc_name}`\n"
            f"- **Hak Akses:** {peran_teks}\n"
            f"- **Link:** {link}\n\n"
            f"Silakan salin atau teruskan link ini ke WhatsApp penyanyi/klien."
        )
    except Exception as e:
        return f"❌ Gagal mengatur link berbagi Google Doc `{judul_atau_id}`: {str(e)}"

def hapus_google_doc(judul_atau_id: str):
    """Memindahkan file Google Docs ke tong sampah (trash) Google Drive."""
    try:
        drive_service = _get_drive_service()
        target = _cari_id_dokumen(drive_service, judul_atau_id)
        if not target:
            return f"❌ Dokumen Google Docs `{judul_atau_id}` tidak ditemukan."
            
        doc_id = target.get('id')
        doc_name = target.get('name')
        
        drive_service.files().update(fileId=doc_id, body={'trashed': True}).execute()
        return f"🗑️ Dokumen Google Docs `{doc_name}` berhasil dipindahkan ke Tong Sampah Google Drive."
    except Exception as e:
        return f"❌ Gagal menghapus Google Doc `{judul_atau_id}`: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buat_google_doc",
            "description": "Membuat dokumen Google Docs baru di Google Drive (misal: lirik lagu, nota aransemen, naskah podcast) dan langsung mendapatkan link web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "judul": {"type": "string", "description": "Judul dokumen Google Docs"},
                    "isi": {"type": "string", "description": "Isi teks dokumen yang akan ditulis"},
                    "publik": {"type": "boolean", "description": "Apakah link dokumen bisa langsung dibuka oleh siapa saja (default: true)"}
                },
                "required": ["judul", "isi"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "baca_google_doc",
            "description": "Membaca isi teks dokumen Google Docs yang ada di Google Drive berdasarkan judul atau Document ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "judul_atau_id": {"type": "string", "description": "Judul dokumen atau ID file Google Docs"}
                },
                "required": ["judul_atau_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tulis_tambah_google_doc",
            "description": "Menambahkan teks baru, bait lirik tambahan, atau catatan revisi ke bagian akhir dokumen Google Docs yang sudah ada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "judul_atau_id": {"type": "string", "description": "Judul atau ID dokumen yang ingin ditambah"},
                    "teks_tambahan": {"type": "string", "description": "Teks tambahan yang akan dimasukkan ke akhir dokumen"}
                },
                "required": ["judul_atau_id", "teks_tambahan"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cari_google_doc",
            "description": "Mencari atau menampilkan daftar dokumen Google Docs yang ada di Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Kata kunci pencarian judul (kosongkan untuk melihat semua dokumen terbaru)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bagikan_google_doc",
            "description": "Membuka izin akses publik Google Docs dan mengambil tautan (link) untuk dikirim ke penyanyi/klien.",
            "parameters": {
                "type": "object",
                "properties": {
                    "judul_atau_id": {"type": "string", "description": "Judul atau ID dokumen yang akan dibagikan"},
                    "sebagai_editor": {"type": "boolean", "description": "True jika orang lain diizinkan mengedit, False jika hanya membaca (default: False)"}
                },
                "required": ["judul_atau_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hapus_google_doc",
            "description": "Menghapus dokumen Google Docs dengan memindahkannya ke Tong Sampah Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "judul_atau_id": {"type": "string", "description": "Judul atau ID dokumen yang ingin dihapus"}
                },
                "required": ["judul_atau_id"]
            }
        }
    }
]

FUNCTIONS = {
    "buat_google_doc": buat_google_doc,
    "baca_google_doc": baca_google_doc,
    "tulis_tambah_google_doc": tulis_tambah_google_doc,
    "cari_google_doc": cari_google_doc,
    "bagikan_google_doc": bagikan_google_doc,
    "hapus_google_doc": hapus_google_doc,
}
