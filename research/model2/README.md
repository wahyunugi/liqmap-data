# Riset: heatmap CoinGlass rentang panjang (24 jam / 1 minggu / 1 bulan) — 29 Okt 2026

Tujuan: menentukan tangga leverage 2x–100x (dan porsinya) untuk heatmap rentang panjang, dengan mencocokkan model ke
screenshot CoinGlass, seperti model v6 dicocokkan ke Model 1.

## Bahan
- `ref/coinglass_24h_thr1_20261029.png`, `ref/coinglass_1w_thr1_20261029.png`, `ref/coinglass_1m_thr1_20261029.png`
  (Binance BTC/USDT Perpetual, Liquidity Threshold = 1, diambil Wahyu 29 Okt 2026 ±14:30 WIB). Model CoinGlass yang
  dipilih di halaman belum dicatat (perlu dikonfirmasi: Model 1/2/3). Tampilannya halus dan mengisi harga jauh,
  berbeda dari screenshot Model 1 lama (garis-garis tipis), jadi kemungkinan model "semua leverage".
- Data candle 5 menit + OI dari repo (`heatmap/inputs.py`), sampai 29 Okt 07:25 UTC.

## Langkah dan hasil
1. **Sumbu waktu** dicari otomatis dengan mencocokkan candle di gambar dengan candle repo (`cg.py`):
   semua berakhir 29 Okt 14:30 WIB; rentang 24,0 jam / 167,2 jam / 744 jam (= 31 hari, panjang bulan Oktober);
   selisih median candle $16 / $48 / $90 (±1 piksel).
2. **Kotak harga CoinGlass**: ±119 baris per grafik, apa pun rentangnya (≈ $132 / $141 / $446 per kotak).
3. **Fit porsi leverage** (`fit.py`, NNLS, tiap leverage disimulasikan terpisah, hanya posisi yang dibuka di dalam
   rentang). Kecocokan pola (Pearson) / besaran (R²) per screenshot:

   | Rentang | v6 (25/50/100x) | Fit sendiri | Porsi terbesar |
   |---|---|---|---|
   | 24 jam | 0,63 | 0,80 / 0,51 | 125x 21%, 100x 18%, 75x 17%, 25x 14% |
   | 1 minggu | 0,79 | 0,93 / 0,84 | 125x 17%, 25x 16%, 75x 13%, 100x 13% |
   | 1 bulan | 0,17 | 0,82 / 0,66 (candle 1 jam: 0,88 / 0,76) | 5x 22%, 4x 16%, 3x 10%, 15x 11% |

4. **Skala besaran berbeda per rentang**: jumlah porsi 0,56 (24 jam), 0,75 (1 minggu), 0,10 (1 bulan).
   Diuji dua penjelasan, keduanya gagal menyamakan skala:
   - candle lebih kasar untuk rentang panjang (`resolution.py`): skala 1 bulan tetap 0,10–0,22;
   - peluruhan posisi lama exp(−umur/τ), τ = 12 jam s/d 7 hari (`decay.py`): rasio skala 1 minggu : 1 bulan tetap 4–7x.
5. **Satu campuran untuk ketiganya** (`shared.py`): tidak cocok. Bersama: 0,52 / 0,77 / 0,81; uji silang
   (porsi dari 2 screenshot, dinilai di yang ke-3): 24 jam 0,51, 1 minggu 0,59, 1 bulan 0,34.

## Kesimpulan sementara
- Leverage rendah (3–5x) wajib untuk rentang 1 bulan: pola naik dari 0,17 (v6) ke 0,82–0,88.
- CoinGlass tampaknya memperlakukan tiap rentang berbeda (porsi dan skala), dengan cara yang belum bisa dipastikan dari
  3 screenshot. Tiap hasil fit berasal dari SATU screenshot: belum diuji di luar sampel (risiko terlalu pas).

## Langkah berikutnya
- Screenshot uji: rentang yang sama untuk ETH, dan BTC di waktu lain; nilai porsi per rentang tanpa diubah.
- Konfirmasi model CoinGlass mana yang dipakai di screenshot ini.
