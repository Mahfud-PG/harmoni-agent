import os
import datetime
from fpdf import FPDF
from pathlib import Path

def buat_nota_pdf(nama_klien: str, daftar_layanan: list, harga_layanan: list, total_biaya: int) -> str:
    """
    Membuat file PDF Nota Tagihan untuk klien.
    :param nama_klien: Nama klien.
    :param daftar_layanan: List string layanan (misal ["Mixing 1 Lagu", "Mastering"]).
    :param harga_layanan: List integer harga masing-masing layanan.
    :param total_biaya: Total semua biaya.
    :return: Path file PDF yang dihasilkan.
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Title / Kop Surat
    pdf.set_font("Arial", 'B', 24)
    # Nama usaha bisa diatur pengguna lewat variabel lingkungan NAMA_USAHA.
    import os as _os
    _nama_usaha = _os.getenv("NAMA_USAHA", "").strip() or "NOTA PEMBAYARAN"
    pdf.cell(0, 15, _nama_usaha, ln=True, align='C')
    
    pdf.set_font("Arial", 'I', 12)
    pdf.cell(0, 8, "Music Production, Mixing & Mastering", ln=True, align='C')
    pdf.cell(0, 8, "=========================================================", ln=True, align='C')
    pdf.ln(5)
    
    # Info Nota
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "NOTA TAGIHAN (INVOICE)", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(50, 8, "Tanggal", 0, 0)
    pdf.cell(0, 8, f": {datetime.datetime.now().strftime('%d %B %Y')}", 0, 1)
    
    pdf.cell(50, 8, "Nama Klien", 0, 0)
    pdf.cell(0, 8, f": {nama_klien}", 0, 1)
    pdf.ln(5)
    
    # Header Tabel
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(130, 10, "Deskripsi Layanan", 1, 0, 'C')
    pdf.cell(60, 10, "Harga", 1, 1, 'C')
    
    # Isi Tabel
    pdf.set_font("Arial", '', 12)
    for layanan, harga in zip(daftar_layanan, harga_layanan):
        pdf.cell(130, 10, f" {layanan}", 1, 0, 'L')
        # Format harga dengan pemisah ribuan
        harga_str = f"Rp {int(harga):,}".replace(',', '.')
        pdf.cell(60, 10, f" {harga_str}", 1, 1, 'R')
        
    # Total
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(130, 10, " TOTAL BIAYA", 1, 0, 'R')
    total_str = f"Rp {int(total_biaya):,}".replace(',', '.')
    pdf.cell(60, 10, f" {total_str}", 1, 1, 'R')
    
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 11)
    pdf.cell(0, 8, "Terima kasih atas kepercayaannya.", ln=True, align='C')
    
    try:
        from sari_core.paths import OUTPUT_DIR
        output_dir = OUTPUT_DIR
    except ImportError:
        # Cadangan: hitung folder data pengguna SENDIRI, jangan pakai folder skrip.
        # Versi lama memakai folder program, sehingga nota PDF tersimpan di folder
        # aplikasi - bukan di folder hasil kerja pengguna.
        _akar = Path(__file__).resolve().parent
        if (_akar / "MODE_TERPASANG").exists():
            _dasar = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            output_dir = Path(_dasar) / "HarmoniAgent" / "File" / "Output"
        else:
            output_dir = _akar / "File" / "Output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = output_dir / f"Nota_{nama_klien.replace(' ', '_')}_{int(datetime.datetime.now().timestamp())}.pdf"
    pdf.output(str(filename))
    
    return str(filename)
