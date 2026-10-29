# Uji: posisi BTC nyata Hyperliquid vs model heatmap (Binance, v6)

Diambil 29 Okt 2026 ±09:03–09:16 WIB.

- `hl_summary.json` — ringkasan 833 posisi BTC nyata dari API publik Hyperliquid (clearinghouseState),
  4.717 akun teratas di leaderboard (diurutkan nilai akun, lalu volume bulanan). Cakupan: 32% sisi long dan
  35% sisi short dari open interest BTC Hyperliquid (43.332 BTC). Sampel condong ke akun besar/aktif.
- `model_now.py` → `model_now.json` — level aktif model v6 pada Binance BTCUSDT candle 09:00 WIB (jendela 24/72/168 jam).
- `compare_hl.py` → `hasil_perbandingan.txt` — perbandingan profil harga likuidasi (kotak 0,25%, ±10%).

Temuan utama:
1. Leverage maksimum BTC di Hyperliquid = 40x (dari API `meta`), jadi tingkat 50x/100x model tidak ada di sana.
2. Setelan leverage tidak menentukan harga likuidasi: posisi bersetelan 40x punya median jarak likuidasi 10,2%
   dari harga masuk (teori 1/40 = 2,5%); 20x → 54% (teori 5%). Penyebab: 85% nilai posisi memakai cross margin,
   sehingga seluruh saldo akun ikut menjamin.
3. Hanya 5,8% nilai posisi punya harga likuidasi dalam ±4% dari harga; 54% lebih jauh dari 25%.
   Model mengasumsikan 100% dalam ±4% (pada saat dibuka).
4. Bentuk profil harga likuidasi nyata vs model: korelasi ≈ 0 (pearson −0,01 s/d +0,14 untuk jendela 24–168 jam).
Keterbatasan: satu waktu, sampel condong ke akun besar, posisi Hyperliquid segala umur, beda bursa
(tidak bisa memisahkan efek "beda bursa" dari efek "asumsi leverage salah" hanya dari data ini).
