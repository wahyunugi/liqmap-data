# liqmap-data — replika heatmap likuidasi CoinGlass + data likuidasi nyata (gratis, tanpa laptop)

Semua berjalan di **GitHub Actions** tiap 4 jam, tanpa perangkat pribadi:
1. Mengambil data Binance BTCUSDT dan ETHUSDT perpetual dari **API gratis Coinalyze**
   (harga, open interest, dan likuidasi nyata).
2. Menghitung **replika heatmap likuidasi CoinGlass** (Model 1, jendela 24 jam, model v6) dan
   menyimpan level likuidasi yang aktif.
3. Menyimpan semuanya ke repository ini. Data lama tidak pernah dihapus.

## Ambil data ("snatch data")
Dari salinan repository ini (Claude bisa melakukannya langsung tanpa laptop):

| Tujuan | Perintah |
|---|---|
| Heatmap terbaru | `python heatmap/snapshot.py BTCUSDT` |
| Heatmap di waktu lampau (jam WIB) | `python heatmap/snapshot.py ETHUSDT "2026-10-28 15:00"` |
| Riwayat level aktif tiap jalan | baca `data/heatmap_levels/<SIMBOL>_<YYYY-MM>.csv` |
| Likuidasi nyata | baca `data/liquidations/...` |

Hasil `snapshot.py` ada di `output/<SIMBOL>/` (tidak masuk repo): `_levels.csv` (level aktif: harga, sisi,
USD, jarak dari harga), `_heatmap.csv` (seluruh 24 jam), `_heatmap.png` (gambar).
Paket yang dibutuhkan: `pip install numpy pandas matplotlib`.

Heatmap bisa dihitung untuk **waktu mana pun sejak 29 Sep 2026** (24 jam setelah data pertama).

## Isi repository
| Folder | Isi |
|---|---|
| `collector/` | `coinalyze.py` pengumpul data; `check_sides.py` cek arti kolom likuidasi |
| `heatmap/` | `model.py` aturan model (PARAMS_V6 dipakai); `inputs.py` penggabung sumber data; `snapshot.py` penghitung heatmap |
| `data/binance_archive/` | arsip Binance asli dari laptop, 28 Sep – 29 Okt 2026, dibekukan (tidak ditambah lagi) |
| `data/ohlcv/`, `data/open_interest/` | harga & open interest dari Coinalyze, 1 dan 5 menit, terus bertambah |
| `data/liquidations/` | likuidasi nyata dari Coinalyze, 1 dan 5 menit |
| `data/heatmap_levels/` | level aktif replika heatmap tiap jalan (tiap 4 jam) |
| `logs/` | `runs.csv` riwayat jalan; `sides_check.txt` cek kolom likuidasi |
| `research/` | jejak riset reverse-engineering: screenshot CoinGlass, skrip penilaian, uji Hyperliquid |

## Data likuidasi nyata
- Kolom `t` = awal interval (detik UTC). File dipecah per bulan.
- **`l` = likuidasi LONG, `s` = likuidasi SHORT** (USD). Coinalyze tidak menjelaskannya; dibuktikan dari data
  jalan pertama (29 Okt 2026): 89% nilai `l` BTC terjadi di menit harga turun, 82% nilai `s` di menit harga naik
  (ETH: 86% dan 84%). Dicek ulang otomatis tiap jalan.
- **Menit tanpa baris di `liquidations` = tidak ada likuidasi tercatat**, bukan data hilang.
- **Bukan semua likuidasi:** feed Binance hanya mengirim likuidasi terbesar per simbol per detik.
- **Waktu, bukan harga:** harga likuidasi diperkirakan dari rentang candle menit itu.

## Sumber data heatmap & pengecekan
Model memakai candle 5 menit + open interest. `heatmap/inputs.py` memakai arsip Binance sampai 29 Okt 2026
10:00 WIB, lalu data Coinalyze sesudahnya. Pengecekan 29 Okt 2026 pada 2.021 candle tumpang tindih:
- harga sama persis (97–100% candle), volume sama (rasio median 1,0000),
- open interest Coinalyze kolom `o` = open interest Binance (selisih median 0,009%),
- heatmap 24 jam yang dihitung dari Coinalyze vs dari Binance: korelasi profil 0,99 (BTC 0,9915, ETH 0,9862),
  total USD level aktif BTC 686,6 vs 680,8 juta.

## Hasil reverse-engineering (model v6 vs CoinGlass)
| Uji | Pola, toleransi ketat (±0,021% harga) | Pola, toleransi 1 kotak CoinGlass (±0,074%) | Besaran USD (R², ketat) |
|---|---|---|---|
| BTC — screenshot A/B/C (dipakai untuk mencocokkan) | 0,83 / 0,85 / 0,86 | 0,90 / 0,91 / 0,92 | 0,69 / 0,71 / 0,71 |
| **ETH — uji luar sampel, model tidak diubah** | **0,80** | **0,90** | **0,54** |
| v1 (tebakan buta awal), BTC C | 0,11 | 0,23 | negatif |

- **Pola** = korelasi linear (Pearson) piksel-demi-piksel antara heatmap model dan CoinGlass, satuan USD.
- **Batas atas:** dua screenshot CoinGlass dari jendela waktu hampir sama cocok 0,98 satu sama lain.
- **Toleransi "1 kotak"** = lebar kotak harga CoinGlass sendiri (BTC ≈ $60, ETH ≈ $1,8).

### Aturan yang ditemukan
1. **Posisi baru = kenaikan open interest per candle 5 menit** (OI[i+1] − OI[i]); penurunan OI tidak mengurangi level.
2. **Tiap sisi (long dan short) = 100% kenaikan itu dalam USD**, dibagi ke **25x / 50x / 100x sebanding leverage**
   (25/175, 50/175, 100/175).
3. **Harga likuidasi = harga masuk × (1 ∓ 1/leverage)**, margin minimum ±0,01%; harga masuk = rata-rata OHLC candle.
   Semua posisi diperlakukan sebagai *isolated margin* (cross margin tidak bisa dihitung dari data publik).
4. **Level hilang saat harga menyentuhnya.**
5. **Hanya data di dalam jendela 24 jam.**
6. **Tampilan:** kotak harga ≈ 0,074%, berjangkar di angka bulat, geser +0,025%.
7. **Slider "Liquidity Threshold" t:** warna kuning = t × angka maksimum skala warna.

### Uji terhadap posisi nyata Hyperliquid (`research/hyperliquid/`, 29 Okt 2026)
833 posisi BTC nyata (32–35% open interest BTC Hyperliquid): leverage maksimum 40x; posisi bersetelan 40x
punya median jarak likuidasi 10,2% dari harga masuk (teori 2,5%), karena 85% nilai memakai cross margin;
hanya 5,8% nilai berada dalam ±4% dari harga. Korelasi profil harga likuidasi nyata vs model ≈ 0.
Artinya: heatmap = peta **di mana uang baru masuk**, bukan jaminan di mana likuidasi terjadi.
Keterbatasan: satu waktu, sampel condong ke akun besar, beda bursa.

## Keterbatasan
- Sisa selisih di toleransi ketat ≈ level meleset ±1 kotak harga (dugaan: CoinGlass memakai data di dalam candle).
- Uji luar sampel baru satu koin (ETH) dan satu waktu. Model 2 dan 3 belum dipelajari.
- Data CoinGlass dibaca dari screenshot, bukan data mentah mereka.
- **Belum terbukti berguna untuk prediksi.** Uji "hit-rate" (apakah likuidasi nyata terjadi saat harga masuk
  zona terang) bisa dilakukan setelah 2–4 minggu data likuidasi terkumpul.

## Memeriksa apakah aturan CoinGlass masih cocok (disarankan sebulan sekali)
Ambil screenshot heatmap CoinGlass (Liquidity Threshold = 1) bersamaan dengan data, tambahkan referensi baru di
`research/compare.py` (contoh "E"), lalu dari folder `research`: `REF=E python evaluate.py`. Jika pola
(toleransi 1 kotak) turun jauh di bawah ±0,85, aturannya perlu dicari ulang.

## Operasional
- **Jadwal:** tiap 4 jam (menit ke-17). Jalankan manual: tab **Actions → collect → Run workflow**.
- **Retensi Coinalyze:** 1 menit ≈ 1 hari, 5 menit ≈ 5–7 hari. Jika GitHub berhenti > ~1 hari, data 1 menit bolong;
  5 menit aman sampai ~5 hari. Heatmap memakai data 5 menit.
- **Aturan penyimpanan:** hanya menambah, tanpa duplikat waktu, interval belum selesai tidak disimpan.
- **Gagal?** GitHub mengirim email; lihat tab **Actions** dan `logs/runs.csv`.
- **Kunci API:** secret `COINALYZE_API_KEY` (Settings → Secrets and variables → Actions). Batas Coinalyze
  40 panggilan/menit; tiap jalan ±14.
- **Menit GitHub Actions:** ±1–2 menit per jalan, 6 jalan/hari ≈ 180–360 menit/bulan (gratis 2.000/bulan untuk repo privat).
- **Ukuran repo:** ±0,2–0,3 MB/hari bertambah.
