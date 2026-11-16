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
| `collector/` | `coinalyze.py` pengumpul data; `cftc.py` laporan mingguan CFTC; `etf.py` arus ETF spot; `stablecoins.py` pasokan stablecoin; `hyperliquid.py` posisi long/short Hyperliquid; `premium.py` Coinbase premium; `status.py` status sumber (`logs/sources_status.json`); `check_sides.py` cek arti kolom likuidasi |
| `heatmap/` | `model.py` aturan model (PARAMS_V6 dipakai); `inputs.py` penggabung sumber data; `snapshot.py` penghitung heatmap |
| `data/binance_archive/` | arsip Binance asli dari laptop, 28 Sep – 29 Okt 2026, dibekukan (tidak ditambah lagi) |
| `data/ohlcv/`, `data/open_interest/` | harga & open interest dari Coinalyze, 1 dan 5 menit, terus bertambah |
| `data/liquidations/` | likuidasi nyata dari Coinalyze, 1 dan 5 menit |
| `data/hyperliquid/` | posisi BTC/ETH akun Hyperliquid yang dilacak: `summary/<YYYY-MM>.csv` (ringkasan per jam), `profile/<KOIN>.json` (snapshot terakhir per kotak harga masuk dan harga likuidasi), `whales/` (posisi terbesar dan perubahan besar); hanya Hyperliquid, bukan Binance |
| `data/stablecoins/` | pasokan harian stablecoin berpatok USD (total, USDT, USDC; dolar), dari DefiLlama, sejak Nov 2017 (situs menampilkan sejak 2019) |
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
- **Panel "Principles":** temuan yang lolos uji ketat dan daftar hal yang terbukti tidak bekerja. Teks statis di
  `site/index.html` (ditinjau 16 Nov 2026); baris "Now" di prinsip 1 hidup (`renderRuleNow` di `site/app.js`: rasio akun
  dan rasio top trader terbaru). Uji ulang 16 Nov 2026 di 8 koin (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK; data per jam
  dari arsip Binance lewat workflow `research-data` -> `research/data/hourly`, makro FRED -> `research/data/macro.csv`):
  `research/turning_points.py`. Aturan: low/high 10 hari yang berjarak >= 3 ayunan mingguan normal dari high/low 60 hari,
  entri 24 jam setelah bertahan, menang = 2,25 ayunan searah sebelum 1,5 melawan dalam 60 hari. Hasil: rasio akun
  (skor 0,58, sama arah 2022-23 dan 2024-26, p blok-minggu 0,03) dan rasio top trader (0,65, p 0,006) bertahan; besar
  pantulan, kecepatan turunnya rasio, dan variabel makro tidak. Perbarui teks dan tanggal bila uji ulang mengubah angka.
  Tabel "Conditions now" (16 Nov 2026): zona rasio akun (<2, 2-3, >3) x rasio top trader (<1,2, 1,2-1,9, >1,9) saat ini per
  koin dan hasil masa lalu di zona itu (konstanta `RULE_LOWS` / `RULE_HIGHS` di `site/app.js`, dari
  `research/turning_points.py`). Dua rasio bersama diuji dengan melatih di 7 koin dan menguji di koin ke-8 bergantian:
  skor 0,65 (low) dan 0,62 (high). Arah gerakan besar 6 jam di 8 koin: dihitung ulang 16 Nov 2026 dengan aturan tetap di
  `research/big_moves.py` (1.672 gerakan berjarak >= 24 jam: naik 66% saat rasio akun < 1,5, 37% saat > 4; angka lama
  1.407 / 67% / 39% memakai jarak antar-kejadian yang tidak tercatat dan diganti). Bila uji diulang, perbarui konstanta
  dan teks bersama-sama.
  Hari rilis (16 Nov 2026): tanggal laporan inflasi (CPI) dan tenaga kerja AS diambil dari daftar "vintage" ALFRED
  (alfred.stlouisfed.org, seri CPIAUCSL dan PAYEMS; vintage revisi tahunan Februari dan koreksi 11 Mei 2020 dibuang),
  tanggal keputusan Fed diketik manual dan dicocokkan dengan perubahan DFEDTARU: `research/data/events.csv`.
- **Pane "RSI 14"** (tepat di bawah harga): RSI 14 candle (Wilder 1978, perataan Wilder) dari candle yang sedang
  ditampilkan, garis 70/50/30, dan divergensi reguler dengan aturan yang sama seperti indikator bawaan TradingView "RSI
  Divergence Indicator": titik balik RSI = lebih rendah/tinggi dari 5 candle di kiri dan kanan, dibandingkan dengan titik
  balik sebelumnya 5 sampai 60 candle sebelumnya. Bullish = harga lower low tetapi RSI higher low; bearish = harga higher
  high tetapi RSI lower high. Panah + garis di pane RSI, garis putus-putus di harga (40 divergensi terakhir). Muncul 5
  candle terlambat karena titik balik baru pasti setelah 5 candle. Dihitung di browser (`site/app.js`, `rsiCalc`,
  `rsiDivergences`); RSI dicek sama persis (selisih 0) dengan perhitungan Wilder di Python pada 400 hari data BTC.
- **Panel "Hyperliquid positions":** posisi long dan short NYATA (bukan perkiraan) milik akun Hyperliquid yang dilacak,
  per harga masuk atau harga likuidasi, plus pangsa long dari waktu ke waktu. Di Binance posisi tiap akun tidak terlihat,
  jadi harga masuk long dan short tidak bisa dipisahkan (metode klasifikasi transaksi Lee dan Ready 1991 / bulk volume
  classification yang digabung perubahan open interest sudah diuji pada data repo dan gagal: di pasar turun hampir semua
  posisi baru terbaca short dan buku long habis dalam beberapa minggu). Hyperliquid mempublikasikan posisi setiap akun
  (API `info`, tipe `clearinghouseState`). `collector/hyperliquid.py` tiap jam (maks 7 menit) membaca kira-kira 7.000
  akun terbesar/teraktif dari leaderboard publik (4.000 nilai akun terbesar + 3.000 volume 30 hari terbesar, dibangun
  ulang tiap hari UTC): semua akun pemegang posisi BTC/ETH ditanya ulang tiap jam, sisanya bergiliran (seluruh semesta
  terputar kira-kira tiap 6 jam), plus 300 akun kecil acak per jam sebagai pembanding. Daftar pemegang posisi disimpan di
  cache GitHub Actions (`.cache/hyperliquid`), bukan di repo. Cakupan 14 Nov 2026: sekitar 30 sampai 40% kontrak terbuka
  Hyperliquid. **Ini data Hyperliquid saja.** Uji satu snapshot 14 Nov 2026: akun kecil sama-sama condong long di kedua
  bursa (Hyperliquid 67% BTC / 60% ETH per jumlah posisi vs Binance 76% / 79% per akun), tetapi akun besar berlawanan
  arah (Hyperliquid 43% / 49% long per ukuran vs "top trader" Binance 68% / 66%), dan funding 90 hari kedua bursa hanya
  berkorelasi 0,25 (BTC) / 0,45 (ETH). Riwayat per jam ini akan diuji terhadap rasio Binance setelah 2 sampai 4 minggu;
  sampai saat itu jangan dipakai sebagai wakil Binance.
- **Panel "Big-move risk"** (16 Nov 2026): TIDAK meramal apakah gerakan besar akan terjadi; menunjukkan ke arah mana
  gerakan besar di masa lalu pergi saat kondisi seperti sekarang. Gerakan besar = perubahan harga 6 jam >= 3 x ayunan
  6 jam normal (simpangan baku perubahan per jam 720 jam terakhir x akar 6). Dua bacaan: rasio akun Binance (<1,5,
  1,5-2,5, >2,5) dan sisi tumpukan likuidasi yang lebih besar dalam 2% dari harga di peta likuidasi 24 jam (long di
  bawah vs short di atas; selisih < 5% dianggap seimbang). Tabel = BTC + ETH, Sep 2020 - Nov 2026, 502 gerakan
  (konstanta `RISK` / `RISK_PILE` di `site/app.js`, dari `python research/big_moves.py`, yang juga mencetak hasil per
  periode). Paling stabil: rasio > 2,5 -> hanya 25-29% naik di tiga periode. Prinsip 5 dikoreksi dengan uji yang sama:
  42% naik bila short di atas lebih besar vs 59% bila long di bawah lebih besar (angka lama 32% tidak bisa direproduksi
  dengan aturan tetap). Tumpukan dihitung di browser dari kotak harga (selisih beberapa persen dari model Python yang
  memakai harga level persis). Baris jadwal: keputusan Fed dan rilis CPI berikutnya dari `site/calendar.csv` (diketik
  tangan dari federalreserve.gov dan bls.gov/schedule/news_release/cpi.htm; jadwal 2027 masih tentatif, PERBARUI tiap
  akhir tahun), diubah ke WIB oleh `pack_calendar` di `site/build.py`.
- **Garis Fibonacci** (kotak centang "Fibonacci", 16 Nov 2026): retracement 0,236 / 0,382 / 0,5 / 0,618 / 0,786 dari
  ayunan terbesar di bagian grafik yang sedang terlihat (high tertinggi dan low terendah; yang lebih dulu menentukan
  arah), skala log (langkah persen sama), dihitung ulang saat grafik digeser atau diperbesar (`fibCalc` di
  `site/app.js`). Catatan: di uji Principles, 0,618 tidak lebih baik dari 0,5 atau 0,7; garis ini alat bantu baca, bukan
  sinyal teruji.
- **Posisi terbesar dan perubahan besar Hyperliquid** (di dalam panel Hyperliquid, 16 Nov 2026): 15 posisi BTC/ETH
  terbesar di antara akun yang dilacak (alamat, sisi, ukuran, harga masuk, hasil sejauh ini, harga likuidasi, nilai akun)
  dan daftar perubahan posisi >= $5 juta antara dua pengecekan (buka, tutup, tambah, kurangi, ganti sisi) 7 hari
  terakhir. Data: `data/hyperliquid/whales/<KOIN>.json` (60 posisi terbesar, ditimpa tiap jam) dan
  `events_<YYYY-MM>.csv`. Posisi terakhir tiap akun disimpan di cache Actions (`.cache/hyperliquid/state.json`); bila
  cache hilang, satu jam pertama tidak mencatat kejadian. Batas: dibaca sejam sekali (waktu = waktu cek, bukan waktu
  transaksi), akun yang sebelumnya tidak punya posisi dicek ulang kira-kira tiap 6 jam, sebagian akun terbesar adalah
  market maker atau satu kaki lindung nilai. Belum diuji sebagai sinyal.
- **CVDD tidak ditampilkan** (dicek 16 Nov 2026): satu-satunya sumber gratis yang ditemukan, API BGeometrics
  (bitcoin-data.com/v1/cvdd), memberi $14.105 pada 15 Nov 2026 dan $4.699 pada 21 Nov 2022, sedangkan angka yang
  dikutip analis (grafik Axel Adler Jr., CryptoQuant) $46.985 pada 15 Nov 2026 dan dasar 2022 berada di sekitar harga
  $15.500. Rasio kedua deret juga tidak tetap (3,33 kali di Nov 2026, 3,56 kali di Jan 2026), jadi tidak bisa
  disetarakan dengan satu faktor. Menampilkan deret yang tidak cocok dengan definisi yang dipakai umum akan menyesatkan.
  Jalan keluar bila diinginkan: hitung sendiri dari Coin Days Destroyed harian (butuh sumber data on-chain).
- **Posisi rugi ("underwater"), prinsip 8 dan kolom "Longs in loss"** (16 Nov 2026): `research/underwater.py`. Tiap
  kontrak punya satu long dan satu short dengan harga masuk yang sama, jadi porsi long yang rugi = porsi short yang
  untung (satu angka, bukan empat kelompok). Perkiraan dari OI per jam: OI naik = posisi baru pada harga penutupan jam
  itu, OI turun = semua kelompok harga masuk dikurangi proporsional; U = porsi kontrak dengan harga masuk di atas harga
  sekarang. Hasil di 8 koin sejak 2020: di low dengan U > 95% menang 37% (91 kejadian) vs 49% lainnya, searah di tiga
  periode, tetapi uji acak per blok minggu memberi p kira-kira 0,24 (belum kokoh); di high tidak ada beda (33% vs 40%,
  p 0,47); arah gerakan besar: sama informasinya dengan rasio akun (korelasi 0,6) dan tidak menambah apa-apa di dalam
  tiap zona rasio; dalamnya penurunan OI dari puncak 30 hari tidak berpengaruh. Perkiraan dicek kasar terhadap data
  nyata Hyperliquid (bursa lain): BTC 94% vs 82% rata-rata selama 51 jam, korelasi per jam 0,75; ETH 97% vs 89%,
  korelasi 0,15. Angka di website dihitung `pack_underwater` di `site/build.py` dengan aturan yang sama.
- **Fondasi website** (tertulis di bagian "Archive and foundation"): (1) apa pun yang layak diingat masuk ke
  "Principles": tiap gagasan diuji dulu dengan aturan tetap, lalu ditulis beserta angka dan tanggalnya, berhasil atau
  tidak; yang gagal tetap dicatat supaya tidak diuji ulang; skrip uji disimpan di `research/`. (2) Website dirancang
  berjalan terus tanpa dirawat (lihat "Penyimpanan dan arsip").
- **Prinsip 9, bahan bakar short squeeze** (16 Nov 2026): `research/squeeze_setup.py`, BTC + ETH, satu baris per hari
  sejak 2020, hasil = naik 1 ayunan mingguan normal sebelum turun 1 dalam 14 hari (rata-rata 52%). Rasio akun < 1,5: 58%
  (356 minggu); > 2,5: 41%. Funding rata-rata 3 hari < -0,005%: 46% (50 minggu, hampir semua 2020-2022). OI 7 hari > +5%
  saat harga 7 hari <= 0: 53% (66% di 2023-24, 41% di 2025-26). Funding negatif + OI naik: 16 minggu saja, terlalu
  sedikit. Kesimpulan: hanya rasio akun yang bertahan.
- **Panel "Stablecoin supply":** pasokan semua stablecoin berpatok dolar AS, USDT, dan USDC (miliar USD, garis) dan
  perubahan pasokan total 30 hari (batang; naik = dolar baru masuk ke kripto, turun = dolar keluar), plus tabel perubahan
  7 hari, 30 hari, 1 tahun untuk hari yang ditunjuk kursor. Sama untuk BTC dan ETH. Sumber: DefiLlama
  (`stablecoins.llama.fi/stablecoincharts/all`, `?stablecoin=1` USDT, `?stablecoin=2` USDC; gratis tanpa kunci),
  seluruh riwayat diambil ulang `collector/stablecoins.py` tiap jalan `collect` karena DefiLlama merevisi angka; baris
  hari ini terus berubah sampai hari berganti (UTC). Dicek 4 Nov 2026: USDT $178,1 miliar dan USDC $70,9 miliar sama dengan daftar
  `stablecoins.llama.fi/stablecoins`. Ditampilkan sejak 2019 karena catatan sebelumnya belum lengkap.
- **Pane "Long vs short" + panel "Crowd positioning":** rasio akun long/short Binance (semua akun, jumlah akun) dan rasio
  long/short top trader (20% akun dengan saldo margin terbesar, menurut ukuran posisi). Sumber: arsip publik Binance
  (file metrics 5 menit, `count_long_short_ratio` dan `sum_toptrader_long_short_ratio`, sampai kemarin) dan Coinalyze
  (`data/long_short_ratio/`, rasio semua akun, untuk hari ini; dicek 31 Okt 2026: rata-rata harian 24–29 Okt sama
  dengan arsip Binance sampai 3 desimal). Panel membagi semua hari (BTC sejak Sep 2020, ETH sejak Des 2021) menjadi
  lima kelompok sama besar menurut rasio harian, lalu menampilkan perubahan harga 30 hari kemudian (median dan
  persentase naik), untuk seluruh periode dan sejak 2023. Dihitung di `site/build_history.py` (`crowd()`), ditulis ke
  `_site/hist/<SIMBOL>_crowd.json`.
- **Pane "Spot net buying":** volume spot yang dibeli dengan market order dikurangi yang dijual dengan market order
  (pihak yang menggerakkan harga), per candle, untuk spot AS (Coinbase BTC-USD/ETH-USD) dan non-AS (Binance spot
  BTCUSDT/ETHUSDT), plus futures Binance (Coinalyze) di label. Garis = total berjalan, keduanya mulai dari nol pada
  candle pertama yang punya data kedua bursa. Sumber: `collector/spot.py` -> `data/spot/5min/`. Binance dari kolom
  beli taker di kline 5 menit (riwayat 60 hari). Coinbase dihitung per transaksi dari API publik (kolom `side` = sisi
  maker, jadi `sell` = taker membeli; riwayat mulai 1 Nov 2026). Dicek 2 Nov 2026: volume 5 menit hasil hitungan
  transaksi sama persis dengan candle resmi Coinbase (12 dari 12 candle).
- **Bursa lain (2 Nov 2026):** `collector/markets.py` (Coinalyze, kunci yang sama) mengambil spot Coinbase, Kraken,
  Gemini (kelompok AS) dan Binance, Bybit, Bithumb (non-AS), futures perpetual Bybit dan OKX (harga, volume, beli
  agresif, open interest USD, likuidasi USD), serta funding rate Binance/Bybit/OKX; 5 menit/1 jam (Coinalyze hanya
  menyimpan ±1.500-2.000 titik) dan harian sejak 2020. `collector/spot.py` menambah OKX spot (statistik taker 5 menit
  OKX, `ts` = akhir candle, dicek terhadap transaksi BTC-USDT) dan Upbit (per transaksi, `ask_bid` = sisi taker, dicek
  dari pantulan harga bid/ask). Data spot Coinalyze dicek 2 Nov 2026 terhadap hitungan transaksi sendiri: volume dan
  beli agresif Coinbase dan Binance sama persis (299 dan 345 candle). Upbit dan OKX spot tidak tersedia di Coinalyze.
  CME harian (CmeWS) ditolak (HTTP 403) dari server GitHub, jadi tidak dikumpulkan; posisi CME tetap dari laporan CFTC.
- **Pane "Futures vs spot · funding":** garis = harga perpetual Binance vs spot Binance (persen), batang = funding rate
  rata-rata Binance/Bybit/OKX (persen per 8 jam).
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

## Penyimpanan dan arsip (fondasi: website berjalan terus tanpa dirawat)
Diukur 16 Nov 2026: ukuran repo menurut GitHub 15 MB (1 Nov) -> 175 MB (16 Nov), naik kira-kira 10 MB per hari
(sebagian dari itu impor sekali jalan: data riset dan ringkasan historis). Dengan laju itu 1 GB tercapai sekitar
Februari 2027, BUKAN tahun ke-4 atau ke-5 seperti perkiraan lama. Ukuran sebenarnya setelah dipadatkan (`git gc
--aggressive` di salinan lokal) hanya 36 MB; angka GitHub lebih besar karena tiap pembaruan per jam disimpan sebagai
paket terpisah, dan kapan GitHub memadatkannya tidak diketahui.

Batas GitHub (docs.github.com, dicek 16 Nov 2026): repo "idealnya di bawah 1 GB, sangat disarankan di bawah 5 GB";
ini anjuran, tidak ada pemutusan otomatis, tetapi GitHub bisa mengirim email meminta perbaikan. File tunggal > 100 MB
ditolak. Website Pages: hasil terbit maksimal 1 GB (sekarang kira-kira 10 MB) dan 100 GB lalu lintas per bulan.
Release: total ukuran dan lalu lintas TIDAK dibatasi.

**Yang sudah otomatis (workflow `archive`, `.github/workflows/archive.yml`):** tiap tanggal 1, dan kapan pun ukuran repo
>= 600 MB (paling sering sekali per 7 hari), seluruh isi repo diterbitkan sebagai Release `archive-<tanggal>`:
`...-files.tar.gz` (semua file: data, kode, riset, README) dan `...-full-history.bundle` (seluruh riwayat git; pulihkan
dengan `git clone <file>.bundle`). Ukuran file di Release dicocokkan dengan file lokal sebelum dianggap berhasil.
Workflow ini tidak mengubah atau menghapus apa pun di repo. Daftar arsip tampil di website (bagian "Archive and
foundation", diambil `pack_archives` di `site/build.py` dari API GitHub saat website dibangun).

**Yang BELUM selesai:** arsip tidak mengecilkan repo, karena riwayat git tetap ada. Pilihan untuk benar-benar
menghentikan pertumbuhan, belum dikerjakan:
1. (disarankan) Simpan data per jam di luar riwayat git: tiap jalan `collect` mengunduh paket data dari sebuah Release,
   menambah data baru, lalu mengunggah paket baru; branch `main` hanya berisi kode. Pertumbuhan repo menjadi hampir nol.
   Mengubah cara semua workflow (collect, site, export, research) membaca data, jadi harus dimigrasi dengan uji jalan
   paralel dan diawasi.
2. Memampatkan riwayat `main` menjadi satu commit secara berkala (force-push). Dua hal belum pasti: token bawaan Actions
   kemungkinan ditolak karena commit baru memuat file workflow, dan GitHub baru mengurangi angka ukuran setelah
   pembersihan internalnya, yang waktunya tidak diketahui.
3. Cara manual (selalu bisa): ganti nama repo ini menjadi `liqmap-data-<tahun>`, buat repo baru `liqmap-data` berisi
   kode dan data 90 hari terakhir, isi secret `COINALYZE_API_KEY`, aktifkan Pages (Source: GitHub Actions), jalankan
   `collect` sekali, lalu arsipkan repo lama (Settings -> Archive this repository). Alamat website tidak berubah.
Cek kesehatan (`collector/health.py`) tetap mengirim email bila ukuran repo melewati 900 MB.

**Yang tetap bisa menghentikan website, apa pun penyimpanannya:** GitHub mengubah layanan gratisnya; sumber data tutup
atau berubah (arsip Binance, Coinalyze, Farside, DefiLlama, Hyperliquid); kunci Coinalyze kedaluwarsa; pemicu luar
(cron-job.org) berhenti. Jadi "berjalan selamanya" adalah tujuan rancangan, bukan jaminan.

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
