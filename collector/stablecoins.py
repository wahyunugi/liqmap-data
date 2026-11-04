"""
Pasokan stablecoin dolar (uang tunai di dalam kripto), harian, dari DefiLlama (stablecoins.llama.fi, gratis, tanpa kunci).

Apa ini: stablecoin = token yang nilainya dipatok 1 dolar AS (USDT dari Tether, USDC dari Circle, dll.). Pasokan naik
berarti dolar baru masuk ke kripto (penerbit mencetak token baru karena ada yang menyetor dolar); turun berarti dolar
keluar (token ditukar balik ke dolar lalu dimusnahkan). Ini salah satu ukuran "likuiditas" khusus kripto.

Penyimpanan: data/stablecoins/daily.csv, satu baris per hari UTC:
  date, total (semua stablecoin berpatok USD, dolar), usdt, usdc
Seluruh riwayat (sejak Nov 2017) diambil ulang tiap jalan karena DefiLlama merevisi angka; baris hari ini terus
diperbarui sepanjang hari. File hanya ditimpa bila ketiga permintaan berhasil.

    python collector/stablecoins.py
"""
import csv, json, os, sys, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "stablecoins")
BASE = "https://stablecoins.llama.fi/stablecoincharts/all"
SERIES = {"total": "", "usdt": "?stablecoin=1", "usdc": "?stablecoin=2"}   # id 1 = USDT, id 2 = USDC (daftar /stablecoins)
UA = "liqmap-data collector (https://github.com/wahyunugi/liqmap-data)"


def fetch(q):
    req = urllib.request.Request(BASE + q, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.load(r)
    out = {}
    for x in rows:
        v = (x.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if v is None:
            continue
        d = datetime.fromtimestamp(int(x["date"]), timezone.utc).strftime("%Y-%m-%d")
        out[d] = float(v)
    return out


def parse_rows(series):
    dates = sorted(series["total"])
    return [[d] + [("%.0f" % series[k][d]) if d in series[k] else "" for k in SERIES] for d in dates]


def main():
    try:
        series = {k: fetch(q) for k, q in SERIES.items()}
        rows = parse_rows(series)
        if len(rows) < 1000:
            raise RuntimeError(f"riwayat terlalu pendek ({len(rows)} hari)")
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, "daily.csv")
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["date"] + list(SERIES)); w.writerows(rows)
        os.replace(tmp, path)
        last = rows[-1]
        msg = f"{len(rows)} hari, {rows[0][0]} s/d {last[0]}, total ${float(last[1]) / 1e9:.1f}B"
        print("stablecoins:", msg)
        status.record("stablecoins", True, msg)
    except Exception as e:  # sumber gratis; jangan gagalkan seluruh koleksi
        print("stablecoins GAGAL:", e)
        status.record("stablecoins", False, str(e)[:200])


if __name__ == "__main__":
    main()
