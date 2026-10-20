"""Harmoni Agent - Putaran Sinkronisasi & Pencadangan Otomatis.

INI PENGGANTI THREAD YANG MATI.

Dulu sinkronisasi dinyalakan dari dalam `main()` milik `bot_otomatis.py`. Tetapi
`main()` itu hanya berjalan kalau `bot_otomatis.py` dijalankan langsung sebagai
program, sedangkan arsitektur sekarang memakai `service_background.py` ->
`server_core.py` yang hanya mengambil beberapa fungsi dari `bot_otomatis.py`.
Akibatnya sinkronisasi TIDAK PERNAH menyala walau mesinnya lengkap.

Putaran ini dinyalakan dari `server_core.py` (startup_event), sama seperti
listener WhatsApp/Telegram/Email, sehingga pasti berjalan dan tahan restart.

Tugasnya dua, dengan jarak yang berbeda:
  * Membuat ZIP cadangan  : sesuai "cadangan_interval_jam" (bawaan 1x sehari)
  * Menyinkronkan ke Drive: sesuai "interval_menit" (bawaan tiap 10 menit),
                            hanya bila sinkronisasi sedang NYALA
"""

import asyncio
from datetime import datetime

from sari_core import sinkronisasi_config as cfg

JEDA_AWAL_DETIK = 45   # beri kesempatan layanan lain menyala lebih dulu
TIK_DETIK = 60         # seberapa sering putaran ini terbangun untuk memeriksa

# Waktu sinkronisasi terakhir (di ingatan). Setiap aplikasi dinyalakan, satu kali
# sinkronisasi langsung dijalankan supaya tidak perlu menunggu sepuluh menit.
_terakhir_sinkron = None

# Berapa kali sinkronisasi gagal berturut-turut. Dipakai supaya Telegram hanya
# dikabari setelah gagal beberapa kali, bukan setiap kali.
_gagal_beruntun = 0


def _kirim_laporan_galat(pesan: str) -> None:
    """Kabari pengguna lewat Telegram kalau ada yang gagal.

    HANYA untuk kegagalan. Kalau setiap keberhasilan juga dikirim, Telegram
    pengguna akan penuh pesan setiap sepuluh menit.
    """
    try:
        from drive_api import kirim_notif
        kirim_notif(f"⚠️ Sinkronisasi Drive bermasalah:\n{pesan}")
    except Exception:
        pass


async def sinkronisasi_loop():
    """Putaran utama. Dijalankan sebagai tugas latar oleh server_core."""
    global _terakhir_sinkron, _gagal_beruntun

    print("[Sinkronisasi] Putaran mulai. Menunggu layanan lain siap...")
    await asyncio.sleep(JEDA_AWAL_DETIK)

    while True:
        try:
            pengaturan = cfg.muat()

            # ---- 1. Cadangan otomatis (tidak bergantung pada Drive) ----
            try:
                from sari_core import cadangan
                if cadangan.cadangan_perlu_dibuat():
                    print("[Sinkronisasi] Waktunya membuat cadangan berkala...")
                    hasil = await asyncio.to_thread(cadangan.buat_cadangan)
                    if hasil.get("berhasil"):
                        print(f"[Sinkronisasi] {hasil['pesan']}")
                    else:
                        print(f"[Sinkronisasi] Cadangan gagal: {hasil.get('pesan')}")
            except Exception as e_cad:
                print(f"[Sinkronisasi] Bagian cadangan bermasalah: {e_cad}")

            # ---- 2. Sinkronisasi ke Google Drive ----
            pengaturan = cfg.muat()   # baca ulang, pengguna bisa mengubah kapan saja
            if pengaturan.get("aktif"):
                try:
                    jarak = max(1, int(pengaturan.get("interval_menit") or 10)) * 60
                    sekarang = datetime.now()
                    waktunya = (
                        _terakhir_sinkron is None
                        or (sekarang - _terakhir_sinkron).total_seconds() >= jarak
                    )
                    if waktunya:
                        from sari_core.drive_sync_engine import run_sync_cycle
                        laporan = await asyncio.to_thread(run_sync_cycle)
                        _terakhir_sinkron = sekarang
                        if laporan.get("berhasil"):
                            _gagal_beruntun = 0
                            print(f"[Sinkronisasi] Selesai: {laporan.get('pesan')}")
                        else:
                            _gagal_beruntun += 1
                            print(f"[Sinkronisasi] Gagal: {laporan.get('pesan')}")
                            # Kabari hanya pada kegagalan ke-3, 10, dan 30 supaya
                            # Telegram pengguna tidak penuh pesan.
                            if _gagal_beruntun in (3, 10, 30):
                                _kirim_laporan_galat(
                                    f"{_gagal_beruntun} kali berturut-turut gagal.\n"
                                    f"{laporan.get('pesan')}"
                                )
                except Exception as e_sync:
                    print(f"[Sinkronisasi] Sinkronisasi bermasalah: {e_sync}")
            else:
                _terakhir_sinkron = None   # supaya saat dinyalakan langsung jalan

        except Exception as e:
            print(f"[Sinkronisasi] Kesalahan tak terduga: {e}")

        await asyncio.sleep(TIK_DETIK)


def jalankan_sekali() -> dict:
    """Sinkronkan sekarang juga (dipakai tombol 'Sinkronkan Sekarang')."""
    from sari_core.drive_sync_engine import run_sync_cycle
    return run_sync_cycle()
