# liqmap-data — replika heatmap likuidasi CoinGlass + data likuidasi nyata (gratis, tanpa laptop)

Semua berjalan di **GitHub Actions** tiap jam, tanpa perangkat pribadi:
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
| `collector/` | `coinalyze.py` pengumpul data; `cftc.py` laporan mingguan CFTC; `etf.py` arus ETF spot; `premium.py` Coinbase premium; `status.py` status sumber (`logs/sources_status.json`); `check_sides.py` cek arti kolom likuidasi |
| `heatmap/` | `model.py` aturan model (PARAMS_V6 dipakai); `inputs.py` penggabung sumber data; `snapshot.py` penghitung heatmap |
| `data/binance_archive/` | arsip Binance asli dari laptop, 28 Sep – 29 Okt 2026, dibekukan (tidak ditambah lagi) |
| `data/ohlcv/`, `data/open_interest/` | harga & open interest dari Coinalyze, 1 dan 5 menit, terus bertambah |
| `data/liquidations/` | likuidasi nyata dari Coinalyze, 1 dan 5 menit |
| `data/etf/` | arus harian ETF spot BTC & ETH di AS (juta USD per ETF), dari Farside, sejak Jan 2024 (BTC) / Jul 2024 (ETH) |
| `data/premium/` | Coinbase premium per 5 menit (sejak 60 hari sebelum 30 Okt 2026) dan per jam (sejak Jun 2021) |
| `data/cftc/` | laporan mingguan CFTC untuk futures Bitcoin & Ether di CME (`cme_tff.csv`), daftar pasar yang ditemukan (`markets.json`) |
| `data/heatmap_levels/` | level aktif replika heatmap tiap jalan (tiap jam; sebelum 29 Okt 2026 11:00 WIB direncanakan tiap 4 jam) |
| `logs/` | `runs.csv` riwayat jalan; `sides_check.txt` cek kolom likuidasi |
| `research/` | jejak riset reverse-engineering: screenshot CoinGlass, skrip penilaian, uji Hyperliquid |
| `tradingview/` | indikator TradingView `liqmap.pine` (model v6 dalam Pine Script v6) |
| `site/` | website Liqmap Chart: `index.html`, `app.js`, `model.js` (model v6 dalam JavaScript), `build.py` (membangun `_site/`), `check_model.js` (cek JS = Python) |

## Website (Liqmap Chart)
Grafik interaktif ala TradingView: candle BTC/ETH dengan heatmap replika di belakangnya, liquidation map di sisi kanan
(mengikuti kursor), likuidasi nyata, open interest, dan volume. Interval 1m/5m/15m/1h/4h/1D, rentang 1D–All.

- **Diperbarui otomatis:** workflow `site` jalan setiap kali `collect` selesai (tiap jam): `python site/build.py`
  menyusun `_site/data.json` dari folder `data/`, lalu terbit ke GitHub Pages.
- **Heatmap dihitung di browser** oleh `site/model.js`, salinan model v6 (`heatmap/model.py` + pengelompokan kotak
  `snapshot.py`). Tiap kolom 5 menit = hasil `snapshot.py` bila dijalankan pada waktu itu. Kecocokan diuji 29 Okt 2026
  pada 6 titik (BTC & ETH; 5 Okt 08:00, 18 Okt 21:35, 29 Okt 10:10 WIB): semua level sama, selisih < $0,01.
  Uji ini diulang otomatis tiap jalan (`node site/check_model.js`); bila beda, workflow gagal dan website tidak diperbarui.
- **Isi:** 60 hari terakhir data 5 menit (ubah: `python site/build.py 90`), 7 hari data 1 menit. Data lama di repo tidak disentuh.
- **Interval 1D / 1W / 1M sejak 2020:** `history/binance_public.py` mengunduh arsip publik Binance (data.binance.vision,
  gratis): candle 5 menit perpetual sejak Jan 2020 dan open interest 5 menit sejak 1 Sep 2020. Disimpan di cache GitHub
  Actions (`.cache/binance`, tidak masuk repo; arsipnya tetap ada di Binance). `site/build_history.py` menyambungnya dengan
  data repo, menghitung heatmap dengan `heatmap/fastmodel.py` (aturan model v6, cepat untuk bertahun-tahun data) di penutupan
  tiap candle, dan menulis `_site/hist/` + `_site/history_report.json` (cakupan, lubang data, cek tumpang tindih dengan
  arsip Binance di repo). **Jendela = satu candle:** 1D = 24 jam (model yang dicocokkan ke CoinGlass), 1W = 7 hari,
  1M = 30 hari (aturan sama, belum dicocokkan ke CoinGlass). `heatmap/check_fastmodel.py`: fastmodel = model.py, diuji
  29 Okt 2026 untuk jendela 24 jam (3 waktu), 7 hari dan 30 hari: selisih $0. Likuidasi nyata hanya ada sejak Okt 2026.
- **Syarat GitHub Pages:** di akun GitHub Free, Pages hanya untuk repo **publik**; repo privat butuh GitHub Pro, dan
  situsnya tetap bisa dibuka siapa saja yang tahu alamatnya. Aktifkan: Settings → Pages → Source: **GitHub Actions**.
  Selama Pages belum aktif, workflow tetap membangun dan mengecek, tanpa gagal.
- **Panel "CME institutions" (laporan CFTC):** di bawah grafik utama. Posisi bersih (long − short) tiap kelompok di
  futures Bitcoin/Ether CME: hedge fund ("leveraged funds"), asset manager, dealer (bank), pemain kecil; tabel per minggu
  (ikut kursor). Sumber: CFTC Public Reporting Environment, dataset `gpe5-46if` ("Traders in Financial Futures", futures
  saja), gratis tanpa kunci; diambil `collector/cftc.py` tiap jalan `collect` ke `data/cftc/cme_tff.csv`. CFTC terbit
  tiap Jumat untuk posisi hari Selasa, jadi angkanya berubah seminggu sekali. Kontrak besar + micro dijumlahkan dalam koin
  (satuan dari spesifikasi CME: Bitcoin 5 BTC, Micro Bitcoin 0,1 BTC, Ether 50 ETH, Micro Ether 0,1 ETH). Dicek 30 Okt 2026:
  laporan 20 Okt 2026, kontrak Bitcoin besar 21.040 kontrak, sama dengan angka CFTC; sisi long semua kelompok + spread
  = open interest (BTC 108.962,3 BTC, ETH 1.424.935 ETH).
- **Pane "Coinbase premium"** (paling bawah di grafik utama): selisih harga spot Coinbase (pembeli AS) vs Binance spot,
  dalam persen, rata-rata per candle. Rumus: Coinbase BTC-USD / (Binance BTCUSDT x harga USDT-USD di Coinbase) - 1;
  dikali harga USDT karena USDT sering tidak tepat $1 (30 Okt 2026: $0,998; tanpa penyesuaian selisihnya -0,1 s/d -0,28%,
  sesudahnya 0 s/d -0,07%). Sumber: Coinbase Exchange API dan Binance spot (`data-api.binance.vision`, bisa diakses dari
  server GitHub; `api.binance.com` cadangan), gratis tanpa kunci. Diambil `collector/premium.py` tiap jalan `collect`.
  Interval < 1D memakai nilai 5 menit, 1D/1W/1M rata-rata harian dari data per jam.
- **Panel "US spot ETF flows":** arus bersih harian semua ETF spot BTC atau ETH di AS (batang), dan rincian per ETF untuk
  hari yang ditunjuk kursor + jumlah 5 hari, 20 hari, dan sejak peluncuran. Sumber: rekap Farside Investors
  (`farside.co.uk/btc/`, `/eth/`, halaman "all data" sekali sehari), diambil `collector/etf.py` tiap jalan `collect`.
  Dicek 30 Okt 2026: jumlah seluruh hari BTC = $57.691,3 jt, sama dengan baris Total Farside ($57.691 jt).
  Angka satu hari terbit setelah pasar AS tutup (±04.00 WIB) dan bisa direvisi esok harinya; tiap jalan menimpa
  tanggal yang sama dengan angka terbaru.
- **Status sumber tambahan:** `logs/sources_status.json` (berhasil/gagal terakhir per sumber, tanpa perlu membuka log GitHub).
- **Alamat:** `https://wahyunugi.github.io/liqmap-data/`

## Indikator TradingView (`tradingview/liqmap.pine`)
Model v6 yang sama, dihitung langsung di grafik TradingView dari data TradingView sendiri (candle 5 menit + open
interest, simbol bawaan `<grafik>_OI`, misalnya `BINANCE:BTCUSDT.P_OI`). Tidak membaca data dari repo ini.
- **Isi:** zona heatmap (zona terbesar sebagai kotak dari terbentuk sampai tersentuh), liquidation map di kanan candle
  terakhir, dan tabel 10 level terbesar (format sama dengan `snapshot.py`) untuk dicocokkan.
- **Urutan hitung sama dengan `model.py`:** diuji 29 Okt 2026 dengan salinan Python dari loop indikator pada data yang
  sama: selisih $0. Dengan sumber open interest berbeda (Coinalyze vs arsip Binance, beda median 0,009%) hasilnya
  bergeser: 10 level terbesar sama 9–10 dari 10, korelasi 0,99, selisih per kotak sampai ±$5 juta. Sumber TradingView
  belum diuji: bandingkan tabelnya dengan `python heatmap/snapshot.py <SIMBOL> "<waktu di baris Levels at>"`.
- **Batas TradingView:** maks 500 kotak (heatmap tidak penuh seperti website), grafik minimal 5 menit, perhitungan
  hanya beberapa hari terakhir (input "Days to draw") karena batas waktu eksekusi; tidak ada data likuidasi nyata.

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

## Agar tetap jalan 5 tahun tanpa henti
Penjagaan yang sudah terpasang (29 Okt 2026):
- **Aturan 60 hari GitHub** (workflow terjadwal di repo publik dimatikan bila 60 hari tanpa aktivitas): bot `collect`
  membuat commit data tiap jam, cara yang sama dengan alat keepalive populer (keepalive-workflow, mode commit).
  Bila data berhenti masuk, commit berhenti, tetapi cek kesehatan di bawah mengirim email jauh sebelum 60 hari.
- **Cek kesehatan** (`collector/health.py`, tiap jalan `collect`): gagal + email bila candle/OI 5 menit terbaru > 3 jam,
  atau (sekali sehari, jalan jam 00 UTC) ukuran repo menurut GitHub > 900 MB.
- **Versi paket dikunci** di `requirements.txt` (numpy 2.5.4, pandas 3.1.0; diuji 29 Okt 2026), Python 3.12.
- **Dependabot** (`.github/dependabot.yml`) mengusulkan versi baru GitHub Actions sebulan sekali lewat pull request;
  klik **Merge** bila pemeriksaan hijau. Versi Actions yang usang suatu saat dihentikan GitHub dan membuat workflow gagal.
- **Level heatmap disimpan tiap ±4 jam** (`SAVE_GAP_MIN` di `heatmap/snapshot.py`) walau `collect` jalan tiap jam;
  level bisa dihitung ulang kapan saja dari data 5 menit. Pertumbuhan repo ≈ 0,56 MB/hari ≈ 205 MB/tahun → ±1 GB
  setelah ±5 tahun (data saja; riwayat git ikut bertambah, dipantau lewat cek ukuran di atas).

Yang harus dijaga pemilik:
- Email notifikasi GitHub Actions aktif (Settings akun → Notifications → Actions → "Only notify for failed workflows").
  Email jadwal dikirim ke orang yang terakhir mengubah jadwal (`cron`) atau yang terakhir mengaktifkan ulang workflow.
- Token `liqmap-trigger` untuk cron-job.org: bila diberi tanggal kedaluwarsa, perpanjang sebelum tanggal itu; bila bocor, hapus di halaman token lalu buat baru (lihat "Pemicu tiap jam dari luar").
- Akun GitHub dan akun Coinalyze tetap aktif; kunci API Coinalyze tidak dicabut (ganti di Settings → Secrets bila perlu).
- Sesekali `git pull` di laptop (folder liqmap-replica) sebagai cadangan di luar GitHub.

## Bila repo mendekati 1 GB (perkiraan ±tahun ke-4–5) atau setelah 5 tahun
GitHub menyarankan repo < 1 GB (sangat disarankan < 5 GB); ukuran itu termasuk seluruh riwayat git, jadi mengompres atau
memindahkan file di repo yang sama tidak mengecilkannya. Caranya: mulai repo baru dan jadikan repo lama arsip.
1. Ganti nama repo ini menjadi `liqmap-data-<tahun mulai>-<tahun akhir>` (Settings → General → Repository name).
2. Buat repo publik baru bernama `liqmap-data`, salin kode (`collector/`, `heatmap/`, `site/`, `research/`, `.github/`,
   README, requirements.txt) dan data 90 hari terakhir (cukup untuk heatmap dan website).
3. Di repo baru: isi secret `COINALYZE_API_KEY`, aktifkan Pages (Source: GitHub Actions), jalankan `collect` sekali.
   Alamat website tetap `https://wahyunugi.github.io/liqmap-data/` karena namanya sama.
4. Di repo lama: Settings → General → **Archive this repository** (hanya-baca; data tetap ada dan bisa dibaca).
5. Bila butuh data lama untuk riset: salin dari repo arsip; tidak ada data yang dihapus.

## Pemicu tiap jam dari luar (cron-job.org)
Jadwal bawaan GitHub (`cron` di `collect.yml`) tidak dijamin tepat waktu: 29–30 Okt 2026 jadwal "tiap jam" hanya jalan
±tiap 4–6 jam (13.09, 18.58, 23.18 UTC). GitHub memang menunda atau melewatkan jadwal saat servernya sibuk. Solusinya:
layanan jadwal gratis di luar GitHub memanggil API GitHub tiap jam untuk menjalankan `collect` (lalu `site` ikut jalan).
Jadwal bawaan tetap dipasang sebagai cadangan; dua jalan berdekatan tidak merusak data (antre lewat `concurrency`,
baris yang sama tidak dobel).

1. **Token GitHub khusus** (hanya bisa menjalankan workflow repo ini, tidak bisa mengubah kode):
   GitHub → foto profil → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** →
   **Generate new token**. Isi: Token name `liqmap-trigger`; Expiration **No expiration** (boleh untuk token sesempit ini; atau pilih tanggal dan catat);
   Repository access **Only select repositories** → `liqmap-data`; Permissions → Repository permissions →
   **Actions: Read and write** (yang lain biarkan). **Generate token**, salin (hanya tampil sekali).
2. **cron-job.org** (gratis): daftar, lalu **Create cronjob**.
   - URL: `https://api.github.com/repos/wahyunugi/liqmap-data/actions/workflows/collect.yml/dispatches`
   - Jadwal: tiap jam, menit ke-5.
   - Tab **Advanced**: Request method **POST**; Headers:
     `Accept: application/vnd.github+json`, `Authorization: Bearer <token dari langkah 1>`,
     `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`; Request body: `{"ref":"main"}`.
   - Simpan, lalu **Test run**: berhasil bila jawabannya HTTP **204**. Di tab **Actions → collect** muncul jalan baru
     dengan pemicu `workflow_dispatch`.
3. **Bila token diberi tanggal kedaluwarsa, perpanjang sebelum tanggal itu** (Regenerate di halaman token, lalu ganti header Authorization di cron-job.org).
   Bila lupa: cron-job.org menerima HTTP 401, `collect` kembali hanya ikut jadwal bawaan GitHub (data tetap masuk,
   lebih jarang); aktifkan email kegagalan di cron-job.org supaya tahu.

Panggilan API yang sama diuji 30 Okt 2026 dari sesi ini (`POST .../workflows/collect.yml/dispatches`, ref main): jalan
`collect` langsung dimulai dan selesai sukses.

## Operasional
- **Jadwal:** tiap jam lewat cron-job.org (lihat di atas) + jadwal bawaan GitHub menit ke-17 sebagai cadangan.
  Jalankan manual: tab **Actions → collect → Run workflow**.
- **Retensi Coinalyze:** 1 menit ≈ 1 hari, 5 menit ≈ 5–7 hari. Jika GitHub berhenti > ~1 hari, data 1 menit bolong;
  5 menit aman sampai ~5 hari. Heatmap memakai data 5 menit.
- **Aturan penyimpanan:** hanya menambah, tanpa duplikat waktu, interval belum selesai tidak disimpan.
- **Gagal?** GitHub mengirim email; lihat tab **Actions** dan `logs/runs.csv`.
- **Kunci API:** secret `COINALYZE_API_KEY` (Settings → Secrets and variables → Actions). Batas Coinalyze
  40 panggilan/menit; tiap jalan ±14.
- **Menit GitHub Actions:** repo publik = tanpa batas. Diukur 29 Okt 2026: `collect` ±25 detik, `site` ±20 detik per jalan; 24 jalan/hari.
- **Ukuran repo:** ±0,77 MB/hari bertambah, ≈ 280 MB/tahun (diukur 29 Okt 2026 dari ukuran file per hari, dua koin: candle + OI 1 menit ±390 KB, level heatmap ±280 KB karena disimpan tiap jam, data 5 menit + likuidasi ±100 KB). Riwayat git ikut bertambah tiap commit (belum diukur). Batas GitHub: repo idealnya < 1 GB, satu file maks 100 MB (file bulanan terbesar ±3,6 MB).
