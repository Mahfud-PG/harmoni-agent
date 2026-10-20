---
name: mixing-audio
description: Standar prosedur teknis mixing vokal dan instrumen di PG Studio.
tags:
- mixing
- audio
- vokal
- mastering
- lagu
- musik
- reaper
- daw
---

# Standar Prosedur Mixing Audio (PG Studio)

Gunakan panduan ini setiap kali pengguna meminta bantuan teknis seputar mixing musik, pengolahan vokal, atau mastering lagu.

## 1. Rantai Pengolahan Vokal (Vocal Chain)
1. **Pembersihan Frekuensi (Subtractive EQ):**
   - High-Pass Filter (Low Cut) di 75 Hz - 85 Hz untuk membuang gemuruh (rumble) mikrofon.
   - Bersihkan resonansi tajam di frekuensi hidung (boxy) sekitar 300 Hz - 500 Hz (potong sempit 1-2 dB).
   - Bersihkan frekuensi harsh/menusuk di 2.5 kHz - 4 kHz jika suara terlalu sengau.
2. **Pengendalian Desis (De-Esser):**
   - Target frekuensi sibilance di area 5 kHz - 7.5 kHz.
   - Atur reduksi gain maksimal 3 dB - 5 dB saat huruf "S" atau "T" muncul.
3. **Kompresi Dua Tahap (Two-Stage Compression):**
   - **Tahap 1 (Peak Tamer - gaya 1176):** Fast attack, fast release, rasio 4:1. Hanya menangkap puncak vokal tertinggi (gain reduction 2-3 dB).
   - **Tahap 2 (Body & Smooth - gaya LA-2A):** Slow attack, release lembut. Menghaluskan dinamika keseluruhan vokal (gain reduction 2-4 dB).
4. **Pewarnaan (Additive EQ):**
   - Tambahkan 'air band' lembut di atas 10 kHz (High Shelf +1.5 dB) untuk kesan mahal dan terbuka.
   - Tambahkan kehangatan (warmth) di 200 Hz jika vokal terdengar terlalu tipis.
5. **Ruang & Kedalaman (Reverb & Delay via Send Track):**
   - Gunakan bus terpisah (Send/Return), jangan taruh 100% wet di insert langsung.
   - Reverb: Plate untuk vokal utama, low cut reverb di bawah 300 Hz agar tidak berlumpur (Abbey Road trick).
   - Delay: Stereo slapback atau 1/4 note berirama dengan high-cut di atas 4 kHz.

## 2. Standar Loudness Mastering
- **Target Streaming Digital (YouTube, Spotify, Apple Music):**
  - Integrated Loudness: **-14 LUFS** (toleransi ±1 LUFS).
  - True Peak Ceiling: **-1.0 dBFS** (mencegah distorsi inter-sample saat dikonversi ke MP3/AAC).
- **Format Master Ekspor:**
  - WAV 24-bit / 48 kHz (arsip kualitas tinggi).
  - MP3 320 kbps (pratinjau cepat klien).
