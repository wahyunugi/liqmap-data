# liqmap-data — pengumpul data likuidasi otomatis (gratis, tanpa laptop)

Berjalan di **GitHub Actions** tiap 4 jam. Mengambil data dari **API gratis Coinalyze** untuk
Binance BTCUSDT dan ETHUSDT perpetual, lalu menyimpannya di repository ini.

## Kenapa ada
Untuk menguji apakah heatmap likuidasi (replika CoinGlass, folder `liqmap-replica` di laptop) benar-benar
berguna: saat harga masuk zona terang, apakah likuidasi sungguhan terjadi di sana? Untuk itu dibutuhkan
riwayat likuidasi nyata. Binance tidak menyediakan riwayatnya (file historis berhenti 31 Mar 2024), dan
server gratis di Amerika diblokir Binance (error 451). Coinalyze merekam feed likuidasi bursa dan bisa
diakses dari server mana pun.

## Data yang dikumpulkan
| Folder | Isi | Satuan |
|---|---|---|
| `data/liquidations/1min`, `5min` | nilai likuidasi per interval, kolom `l` dan `s` | USD |
| `data/ohlcv/1min`, `5min` | harga open/high/low/close, volume (`v`), volume beli (`bv`), jumlah transaksi (`tx`, `btx`) | harga USDT |
| `data/open_interest/1min`, `5min` | open interest open/high/low/close | koin (BTC/ETH) |

- Kolom `t` = awal interval, detik UTC.
- File dipecah per bulan: `<SIMBOL>_<YYYY-MM>.csv`.
- `data/symbols.json` = kode simbol Coinalyze yang dipakai (dicari otomatis, tidak ditebak).
- **Arti `l` dan `s` belum dijelaskan Coinalyze.** Dugaan: `l` = likuidasi long, `s` = likuidasi short.
  Dicek otomatis tiap jalan di `logs/sides_check.txt` (likuidasi long seharusnya menumpuk di menit harga turun).

## Aturan penyimpanan
- Hanya menambah: baris lama tidak pernah dihapus/diubah, tidak ada duplikat waktu.
- Interval yang belum selesai tidak disimpan.
- Riwayat tiap jalan: `logs/runs.csv` (jumlah panggilan API, baris baru, error).

## Batasan yang perlu diingat
- **Retensi Coinalyze:** 1.500–2.000 titik per interval. 1 menit ≈ 1 hari, 5 menit ≈ 5–7 hari.
  Jadwal tiap 4 jam memberi cadangan besar; jika GitHub berhenti lebih dari ~1 hari, data 1 menit bolong
  (data 5 menit masih aman sampai ~5 hari).
- **Bukan semua likuidasi:** feed Binance hanya mengirim likuidasi terbesar per simbol per detik,
  jadi angka di sini kemungkinan lebih kecil dari total sebenarnya.
- **Waktu, bukan harga:** likuidasi diketahui per menit; harganya diperkirakan dari rentang candle menit itu.

## Kalau ada masalah
- GitHub mengirim email jika satu jalan gagal. Lihat tab **Actions**.
- Kunci API disimpan sebagai secret `COINALYZE_API_KEY` (Settings → Secrets and variables → Actions).
- Batas Coinalyze 40 panggilan/menit; tiap jalan memakai ±12–14 panggilan.
- Menit GitHub Actions: tiap jalan ±1 menit, 6 jalan/hari ≈ 180 menit/bulan.
