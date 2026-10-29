# Riset: heatmap CoinGlass rentang panjang (24 jam / 1 minggu / 1 bulan) — 29 Okt 2026

Tujuan: menentukan tangga leverage 2x–100x (dan porsinya) untuk heatmap rentang panjang, dengan mencocokkan model ke
screenshot CoinGlass, seperti model v6 dicocokkan ke Model 1.

## Bahan
- `ref/coinglass_24h_thr1_20261029.png`, `ref/coinglass_1w_thr1_20261029.png`, `ref/coinglass_1m_thr1_20261029.png`
  (Binance BTC/USDT Perpetual, **CoinGlass Model 2**, Liquidity Threshold = 1, diambil Wahyu 29 Okt 2026 ±14:30 WIB;
  model dikonfirmasi Wahyu). Menurut CoinGlass sendiri, Model 1 hanya menghitung leverage tinggi (10x, 25x, 50x, 100x)
  untuk jangka pendek, Model 2 menghitung semua leverage untuk jangka panjang (akun X @coinglass_com).
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

6. **Satu campuran + skala per rentang** (`joint.py`): masalah di langkah 5 ternyata karena 24 jam & 1 minggu tidak bisa
   melihat leverage rendah (level 2x–5x di luar rentang harga gambarnya). Dengan satu faktor skala tampilan per rentang:
   24 jam 0,74 / 1 minggu 0,92 / 1 bulan 0,73; jumlah porsi 1,13 (tiap sisi ≈ 100% kenaikan OI, sama dengan aturan v6).
7. **Resolusi candle per rentang** (`joint_res.py`): terbaik 5 menit (24 jam, 1 minggu) dan **1 jam untuk 1 bulan**:
   0,74 / 0,92 / 0,81 (R² 0,44 / 0,84 / 0,62); skala tampilan 1 / 1,34 / 0,155.
8. **Posisi sebelum tepi kiri grafik** (`history_test.py`): menambah 1, 3, 7, 14 hari sebelum tepi kiri selalu memperburuk
   (24 jam: 0,74 → 0,72 → 0,55 → 0,54 → 0,47). Model 2 hanya menghitung posisi yang dibuka di dalam rentang yang dipilih.
9. **Tangga leverage** (`final_fit.py`): tangga lengkap 14 tingkat jauh lebih cocok daripada tangga sederhana
   (1 bulan: 0,81 vs 0,65 untuk 6 tingkat), jadi CoinGlass tampaknya memakai banyak tingkat. Porsi (tangga lengkap):
   3x 9%, 4x 14%, 5x 20%, 7x 6%, 10x 2%, 15x 4%, 20x 5%, 25x 8%, 33x 6%, 50x 5%, 75x 7%, 100x 6%, 125x 9%
   (rendah 3–5x ≈ 43%, menengah 7–20x ≈ 17%, tinggi 25–125x ≈ 40%). Disimpan di `final_fit.json`.

10. **Ukuran yang sama dengan v6** (`improve.py`): v6 dinilai "ketat" dan "toleransi 1 kotak" (kedua gambar dihaluskan arah
    harga σ = 1 kotak, seperti `accuracy_report` di `research/compare.py`). Model 2 versi ini (tanpa perubahan):
    ketat 0,74 / 0,92 / 0,81; **toleransi 1 kotak 0,89 / 0,97 / 0,87** (24 jam / 1 minggu / 1 bulan).
    Pembanding v6 vs Model 1: ketat 0,83–0,86, toleransi 1 kotak 0,90–0,92; batas atas (dua screenshot CoinGlass
    jendela hampir sama) 0,98. Variasi kecil yang diuji: margin pemeliharaan 0,4% + grid kotak digeser ¼ kotak
    → toleransi 1 kotak **0,90 / 0,97 / 0,89** (rata-rata 0,919 vs 0,912 tanpa perubahan). Selisih ini kecil, belum tentu
    nyata; pilihan akhir ditentukan uji di luar sampel.

## Hal yang belum diketahui
- Kenapa skala tampilan berbeda per rentang (1 bulan ≈ 0,155 dari 24 jam). Bukan karena candle kasar, bukan karena
  peluruhan umur posisi. Untuk sekarang diperlakukan sebagai konstanta per rentang yang diukur.
- Apakah porsi dan skala ini tetap berlaku di waktu lain / koin lain (belum diuji).

## Kesimpulan sementara
- Leverage rendah (3–5x) wajib untuk rentang 1 bulan: pola naik dari 0,17 (v6) ke 0,82–0,88.
- CoinGlass tampaknya memperlakukan tiap rentang berbeda (porsi dan skala), dengan cara yang belum bisa dipastikan dari
  3 screenshot. Tiap hasil fit berasal dari SATU screenshot: belum diuji di luar sampel (risiko terlalu pas).

## Langkah berikutnya: uji di luar sampel
- Screenshot Model 2, Liquidity Threshold = 1: BTC lagi (30 Okt) dan ETH, rentang 24 jam / 1 minggu / 1 bulan.
- Daftarkan di `refs_test.json` (label harga teratas/terbawah dan angka skala warna dari gambar), lalu
  `python research/model2/validate.py`: skor "beku" = porsi DAN skala 29 Okt tanpa diubah; "skala bebas" = porsi beku,
  hanya skala dicari ulang. Bila skor beku mendekati angka di atas, model dianggap lolos.
