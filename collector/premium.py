"""
Coinbase premium: selisih harga spot di Coinbase (pembeli AS) dan Binance (pembeli non-AS), dalam persen.

    premium % = (Coinbase BTC-USD / (Binance BTCUSDT x harga USDT dalam USD) - 1) x 100

Kenapa dikali harga USDT: Coinbase memakai dolar sungguhan, Binance memakai USDT yang sering diperdagangkan sedikit di
bawah/atas $1 (mis. $0,998). Tanpa penyesuaian ini selisihnya didominasi harga USDT, bukan perilaku pembeli.
Harga USDT dalam USD = candle USDT-USD di Coinbase (bila 5 menit itu tidak ada transaksi, dipakai harga terakhir).
Semua harga = harga penutupan candle; hanya candle yang sudah selesai yang disimpan.

Sumber (gratis, tanpa kunci):
  Coinbase Exchange API  api.exchange.coinbase.com/products/<ID>/candles  (BTC-USD, ETH-USD, USDT-USD)
  Binance spot           data-api.binance.vision/api/v3/klines, cadangan api.binance.com (BTCUSDT, ETHUSDT)

Penyimpanan (hanya menambah, tanpa duplikat waktu, dipecah per bulan / tahun):
  data/premium/5min/<SIMBOL>_<YYYY-MM>.csv   t, cb, bn, usdt, prem   (60 hari ke belakang saat pertama jalan)
  data/premium/1h/<SIMBOL>_<YYYY>.csv        sama, per jam           (sejak Jun 2021 saat pertama jalan)
t = waktu buka candle (detik UTC). Tiap jalan mengambil ulang 36 jam terakhir untuk menambal jalan yang terlewat.

    python collector/premium.py
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "premium")
PAIRS = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}
CB = "https://api.exchange.coinbase.com"
BN = ["https://data-api.binance.vision", "https://api.binance.com"]
UA = "liqmap-data collector (https://github.com/wahyunugi/liqmap-data)"
RES = {"5min": (300, "5m", 60 * 86400), "1h": (3600, "1h", None)}
HIST_START = int(datetime(2021, 6, 1, tzinfo=timezone.utc).timestamp())   # USDT-USD di Coinbase mulai Mei 2021
LOOKBACK = 36 * 3600


def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 + attempt * 3); continue
            raise
        except urllib.error.URLError:
            if attempt < 3:
                time.sleep(2 + attempt * 3); continue
            raise


_CB_CACHE = {}


def coinbase(product, step, t0, t1):
    """{t: close} untuk candle dengan waktu buka di [t0, t1). Maks 300 candle per permintaan: jendela 290 candle."""
    key = (product, step, t0, t1)
    if key in _CB_CACHE:
        return _CB_CACHE[key]
    out, s = {}, t0
    while s < t1:
        e = min(t1, s + 290 * step)
        q = urllib.parse.urlencode({"granularity": step,
                                    "start": datetime.fromtimestamp(s, timezone.utc).isoformat(),
                                    "end": datetime.fromtimestamp(e, timezone.utc).isoformat()})
        for row in get(f"{CB}/products/{product}/candles?{q}"):
            t = int(row[0])
            if t0 <= t < t1:
                out[t] = float(row[4])
        s = e
        time.sleep(0.15)
    _CB_CACHE[key] = out
    return out


BN_USED = []


def binance(symbol, interval, step, t0, t1):
    last_err = None
    for base in BN:
        try:
            out, s = {}, t0
            while s < t1:
                rows = get(f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&startTime={s * 1000}"
                           f"&endTime={(t1 - 1) * 1000}&limit=1000")
                if not rows:
                    break
                for k in rows:
                    t = int(k[0]) // 1000
                    if t0 <= t < t1:
                        out[t] = float(k[4])
                s = int(rows[-1][0]) // 1000 + step
                time.sleep(0.1)
            if base not in BN_USED:
                BN_USED.append(base)
            return out
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Binance spot tidak bisa diambil: {last_err!r}")


def files(res, sym):
    d = os.path.join(OUT, res)
    return sorted(f for f in os.listdir(d) if f.startswith(sym + "_")) if os.path.isdir(d) else []


def last_t(res, sym):
    fs = files(res, sym)
    if not fs:
        return None
    with open(os.path.join(OUT, res, fs[-1])) as f:
        rows = list(csv.reader(f))
    return int(rows[-1][0]) if len(rows) > 1 else None


def existing(res, sym):
    have = set()
    for fn in files(res, sym):
        with open(os.path.join(OUT, res, fn)) as f:
            have.update(int(r["t"]) for r in csv.DictReader(f))
    return have


def append(res, sym, rows):
    """rows: list (t, cb, bn, usdt, prem); hanya menambah baris yang belum ada."""
    have = existing(res, sym)
    rows = [r for r in rows if r[0] not in have]
    by = {}
    for r in rows:
        dt = datetime.fromtimestamp(r[0], timezone.utc)
        key = dt.strftime("%Y-%m") if res == "5min" else dt.strftime("%Y")
        by.setdefault(key, []).append(r)
    d = os.path.join(OUT, res); os.makedirs(d, exist_ok=True)
    for key, rs in by.items():
        path = os.path.join(d, f"{sym}_{key}.csv")
        old = []
        if os.path.exists(path):
            with open(path) as f:
                old = [tuple(x) for x in csv.reader(f)][1:]
        allr = sorted({int(x[0]): x for x in old + [tuple(map(str, r)) for r in rs]}.items())
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write("t,cb,bn,usdt,prem\n")
            for _, x in allr:
                f.write(",".join(x) + "\n")
        os.replace(tmp, path)
    return len(rows)


def run(res, sym, now):
    step, interval, backfill = RES[res]
    lt = last_t(res, sym)
    if lt is None:
        t0 = (now - backfill) if backfill else HIST_START
    else:
        t0 = min(lt + step, now - LOOKBACK)
    t0 -= t0 % step
    t1 = now - now % step                      # candle yang waktu bukanya < t1 sudah selesai
    if t1 <= t0:
        return 0, None
    cb = coinbase(PAIRS[sym], step, t0, t1)
    usd = coinbase("USDT-USD", step, t0 - 24 * 3600, t1)   # 24 jam ekstra untuk harga USDT terakhir
    bn = binance(sym, interval, step, t0, t1)
    rows, u = [], None
    for t in range(t0 - 24 * 3600 - (t0 - 24 * 3600) % step, t1, step):
        if t in usd:
            u = usd[t]
        if t < t0 or t not in cb or t not in bn or u is None:
            continue
        prem = (cb[t] / (bn[t] * u) - 1) * 100
        rows.append((t, f"{cb[t]:g}", f"{bn[t]:g}", f"{u:g}", f"{prem:.4f}"))
    n = append(res, sym, rows)
    return n, rows[-1] if rows else None


def main():
    now = int(time.time())
    bad = 0
    for res in RES:
        for sym in PAIRS:
            try:
                n, last = run(res, sym, now)
                msg = f"{res} {sym}: +{n} baris" + (f", terakhir {datetime.fromtimestamp(last[0], timezone.utc):%Y-%m-%d %H:%M} UTC premium {last[4]}%" if last else "")
                print(msg)
                status.record(f"premium_{res}_{sym}", True, msg + f" | Binance via {', '.join(BN_USED) or '-'}")
            except Exception as e:
                bad += 1
                print(f"{res} {sym}: GAGAL {e!r}", file=sys.stderr)
                status.record(f"premium_{res}_{sym}", False, repr(e))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
