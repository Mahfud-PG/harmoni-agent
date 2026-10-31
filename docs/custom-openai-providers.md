# Provider OpenAI-compatible kustom

Settings → Model & Provider → Provider OpenAI-compatible kustom.

1. Isi nama, base URL (misalnya `https://api.example.com/v1`) dan API key, atau pilih tanpa autentikasi secara eksplisit.
2. Simpan profil. Tidak ada discovery, tes, atau aktivasi otomatis. Beberapa profil dapat memakai ID model upstream yang sama.
3. Opsional: Ambil `/models`. Jika gagal, ketik ID model manual dengan kapitalisasi persis.
4. Tes chat dan tes tool calling adalah tindakan terpisah, masing-masing dapat berbayar. Tes tools hanya meminta fungsi dummy; tidak menjalankan alat.
5. Simpan model tanpa tes/aktivasi. Aktifkan melalui menu Otak AI. Cadangan dapat diatur melalui perintah `/cadangan <nomor>`; spesialis melalui tab Tim Spesialis.
6. Edit profil dengan memilih profil tersimpan. Kunci kosong mempertahankan kunci lama; mengganti URL memerlukan kunci baru atau no-auth. Profil tidak menampilkan kunci yang tersimpan.
7. Alihkan tugas aktif/cadangan/spesialis sebelum menghapus model. Hapus seluruh model profil sebelum menghapus profil. Nomor entri lain tidak digeser.

## Penyimpanan dan keamanan

`DATA_ROOT/custom_providers.json` berisi metadata dan referensi opaque. Kunci disimpan terpisah di `DATA_ROOT/.provider_keys/`. File rahasia menggunakan mode 0600 pada sistem yang mendukung; Windows memakai ACL direktori pengguna yang diwarisi, **bukan** enkripsi DPAPI. Jangan bagikan folder data atau backup-nya.

Profil memakai ID acak `custom-...`, tidak ditentukan dari nama/model. Penulisan metadata/config atomik, operasi registry serta penambahan/penghapusan model memakai lock lintas proses. Pemilihan model lama masih memakai mekanisme konfigurasi aplikasi lama.

URL harus HTTP(S), tanpa userinfo, query atau fragment. HTTP dibatasi hostname localhost atau IP lokal/private. Semua redirect dinonaktifkan untuk request profil, proxy lingkungan tidak dipakai. Tidak ada peminjaman kunci OpenAI/OpenRouter untuk profil lain. Pesan error tes/discovery dan error inference profil disanitasi.

API baru `/custom-providers` dibatasi klien loopback dan origin desktop/local. Gateway lama tidak memiliki autentikasi menyeluruh; ini bukan pengganti hardening keseluruhan aplikasi. Origin `null` diperbolehkan untuk desktop file WebView.

Endpoint hanya OpenAI Chat Completions, bukan Responses API. Kompatibilitas parameter seperti `max_tokens`, `temperature`, `tools` bergantung server.

## Pengujian terisolasi

Dari direktori source:

```sh
python -m unittest discover -s tests -p test_custom_providers.py -v
python -m py_compile sari_core/custom_providers.py sari_core/model_config.py sari_core/brain.py server_core.py tests/test_custom_providers.py
node -e "const fs=require('fs'),vm=require('vm'); const s=fs.readFileSync('index.html','utf8'); let n=0; for(const m of s.matchAll(/<script[^>]*>([\\s\\S]*?)<\/script>/gi)){new vm.Script(m[1]);n++;} console.log(n+' inline scripts parsed');"
```

Unittest menggunakan temporary directory, stub modul paths, ekstraksi AST route FastAPI, dan ekstraksi blok pemilihan inference untuk menghindari startup listener/daemon dan pembacaan `.env` pengguna. HTTP mock localhost menjalankan OpenAI SDK asli untuk discovery/chat/tools/no-auth/error/redirect. Test class turunan mengulangi sebagian kasus dasar; jumlah eksekusi bukan jumlah skenario unik.

Batas verifikasi: tidak menjalankan aplikasi desktop penuh atau layanan live; aksesibilitas markup diuji statis, belum pengujian NVDA/browser interaktif. Tidak ada request provider berbayar, build installer, deploy, commit atau restart layanan.
