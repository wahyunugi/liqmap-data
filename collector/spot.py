"""
Volume spot per 5 menit, dipisah pembeli agresif vs penjual agresif, untuk dua kelompok:
  AS     : Coinbase (BTC-USD, ETH-USD)  - bursa utama pembeli AS dan penyimpan kebanyakan ETF
  non-AS : Binance spot (BTCUSDT, ETHUSDT) - bursa spot terbesar di luar AS

"Agresif" = pihak yang memakai market order (taker), yaitu yang menggerakkan harga.
  Binance : candle 5 menit memuat volume beli taker (kolom ke-10 kline).
  Coinbase: tidak ada di candle, jadi dihitung dari daftar transaksi. Kolom "side" Coinbase = sisi MAKER
            (dokumentasi: "The side of a trade indicates the maker order side"), jadi side == "sell" = taker membeli.

Penyimpanan (hanya menambah, tanpa duplikat waktu, hanya candle 5 menit yang sudah selesai):
  data/spot/5min/<SIMBOL>_<binance|coinbase>_<YYYY-MM>.csv   kolom t, v, tb (v = volume koin, tb = volume beli taker)
  Coinbase juga kolom n (jumlah transaksi).
Riwayat awal: Binance 60 hari; Coinbase 24 jam (transaksi diambil per 1.000, ±20.000-50.000 transaksi BTC per jam).
Tiap jalan Coinbase mengambil transaksi dari yang terbaru mundur sampai akhir candle terakhir yang tersimpan, dibatasi
waktu per produk (BUDGET_S); bila batas tercapai, hanya candle yang tercakup penuh yang disimpan (lubang tercatat di
logs/sources_status.json).

    python collector/spot.py
"""
import csv, json, os, sys, time, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "spot", "5min")
PAIRS = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}
BN = ["https://data-api.binance.vision", "https://api.binance.com"]
CB = "https://api.exchange.coinbase.com"
UA = "liqmap-data collector (https://github.com/wahyunugi/liqmap-data)"
STEP = 300
BN_BACKFILL = 60 * 86400
CB_BACKFILL = 24 * 3600
LOOKBACK = 36 * 3600
BUDGET_S = 300


def get(url):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(1.5 * (attempt + 1)); continue
            raise
        except urllib.error.URLError:
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1)); continue
            raise


def files(sym, venue):
    return sorted(f for f in os.listdir(OUT) if f.startswith(f"{sym}_{venue}_")) if os.path.isdir(OUT) else []


def last_t(sym, venue):
    for fn in reversed(files(sym, venue)):
        with open(os.path.join(OUT, fn)) as f:
            rows = list(csv.reader(f))
        if len(rows) > 1:
            return int(rows[-1][0])
    return None


def append(sym, venue, rows, cols):
    """rows: dict t -> tuple sesuai cols. Hanya menambah t yang belum ada."""
    os.makedirs(OUT, exist_ok=True)
    by = {}
    for t, r in rows.items():
        by.setdefault(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m"), {})[t] = r
    added = 0
    for ym, new in by.items():
        path = os.path.join(OUT, f"{sym}_{venue}_{ym}.csv")
        old = {}
        if os.path.exists(path):
            with open(path) as f:
                for x in csv.DictReader(f):
                    old[int(x["t"])] = tuple(x[c] for c in cols)
        fresh = {t: r for t, r in new.items() if t not in old}
        if not fresh:
            continue
        old.update(fresh); added += len(fresh)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write("t," + ",".join(cols) + "\n")
            for t in sorted(old):
                f.write(f"{t}," + ",".join(str(v) for v in old[t]) + "\n")
        os.replace(tmp, path)
    return added


def binance(sym, now):
    lt = last_t(sym, "binance")
    t0 = (now - BN_BACKFILL) if lt is None else min(lt + STEP, now - LOOKBACK)
    t0 -= t0 % STEP
    t1 = now - now % STEP
    last_err = None
    for base in BN:
        try:
            rows, s = {}, t0
            while s < t1:
                ks = get(f"{base}/api/v3/klines?symbol={sym}&interval=5m&startTime={s * 1000}&endTime={(t1 - 1) * 1000}&limit=1000")
                if not ks:
                    break
                for k in ks:
                    t = int(k[0]) // 1000
                    if t0 <= t < t1:
                        rows[t] = (f"{float(k[5]):.6g}", f"{float(k[9]):.6g}")
                s = int(ks[-1][0]) // 1000 + STEP
                time.sleep(0.1)
            return append(sym, "binance", rows, ("v", "tb")), base
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Binance spot gagal: {last_err!r}")


def coinbase(sym, now):
    prod = PAIRS[sym]
    lt = last_t(sym, "coinbase")
    cut = (now - CB_BACKFILL) if lt is None else lt + STEP
    cut -= cut % STEP
    end = now - now % STEP                         # hanya candle yang selesai sebelum 'end'
    agg, after, earliest, pages, start = {}, None, None, 0, time.time()
    reached = False
    while True:
        url = f"{CB}/products/{prod}/trades?limit=1000" + (f"&after={after}" if after else "")
        tr = get(url); pages += 1
        if not tr:
            reached = True; break
        for x in tr:
            ts = datetime.fromisoformat(x["time"].replace("Z", "+00:00")).timestamp()
            if ts < cut:
                reached = True; continue
            b = int(ts) - int(ts) % STEP
            if b >= end:
                continue
            a = agg.setdefault(b, [0.0, 0.0, 0])
            sz = float(x["size"]); a[0] += sz; a[2] += 1
            if x["side"] == "sell":                # maker menjual -> taker membeli
                a[1] += sz
            earliest = ts if earliest is None else min(earliest, ts)
        after = tr[-1]["trade_id"]
        if reached or time.time() - start > BUDGET_S:
            break
        time.sleep(0.12)
    if not reached:                                # batas waktu: buang candle yang mungkin belum lengkap
        first_full = (int(earliest) - int(earliest) % STEP + STEP) if earliest else end
        agg = {b: a for b, a in agg.items() if b >= first_full}
    rows = {b: (f"{a[0]:.6g}", f"{a[1]:.6g}", a[2]) for b, a in agg.items()}
    n = append(sym, "coinbase", rows, ("v", "tb", "n"))
    return n, pages, reached


UPBIT = {"BTCUSDT": "KRW-BTC", "ETHUSDT": "KRW-ETH"}


def okx(sym, now):
    """OKX spot: statistik volume taker 5 menit semua pasangan spot koin itu (rubik taker-volume, ±2 hari ke belakang).
    Kolom [ts, sellVol, buyVol]; ts = AKHIR candle (dicek 2 Nov 2026 terhadap transaksi BTC-USDT: angka ts cocok dengan
    transaksi 5 menit SEBELUMNYA), jadi t = ts - 300."""
    ccy = sym.replace("USDT", "")
    j = get(f"https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy={ccy}&instType=SPOT&period=5m")
    end = now - now % STEP
    rows = {}
    for r in j.get("data", []):
        t = int(r[0]) // 1000 - STEP
        if t + STEP <= end:
            sell, buy = float(r[1]), float(r[2])
            rows[t] = (f"{sell + buy:.6g}", f"{buy:.6g}")
    return append(sym, "okx", rows, ("v", "tb"))


def upbit(sym, now):
    """Upbit (Korea, KRW): dihitung per transaksi. ask_bid = sisi taker (dicek 2 Nov 2026: transaksi BID lebih mahal dari
    ASK di sebelahnya 451 kali, lebih murah 33 kali). Paging per hari (days_ago) karena kursor hanya berlaku dalam satu hari."""
    mkt = UPBIT[sym]
    lt = last_t(sym, "upbit")
    cut = (now - CB_BACKFILL) if lt is None else lt + STEP
    cut -= cut % STEP
    end = now - now % STEP
    agg, earliest, pages, start, reached = {}, None, 0, time.time(), False
    for days_ago in (None, 1, 2):
        cursor = None
        while True:
            q = f"https://api.upbit.com/v1/trades/ticks?market={mkt}&count=500" + (f"&cursor={cursor}" if cursor else "") + (f"&days_ago={days_ago}" if days_ago else "")
            tr = get(q); pages += 1
            if not tr:
                break
            for x in tr:
                ts = x["timestamp"] / 1000
                if ts < cut:
                    reached = True; continue
                b = int(ts) - int(ts) % STEP
                if b >= end:
                    continue
                a = agg.setdefault(b, [0.0, 0.0, 0]); a[0] += x["trade_volume"]; a[2] += 1
                if x["ask_bid"] == "BID":
                    a[1] += x["trade_volume"]
                earliest = ts if earliest is None else min(earliest, ts)
            cursor = tr[-1]["sequential_id"]
            if reached or time.time() - start > BUDGET_S:
                break
            time.sleep(0.12)
        if reached or time.time() - start > BUDGET_S:
            break
    if not reached:
        first_full = (int(earliest) - int(earliest) % STEP + STEP) if earliest else end
        agg = {b: a for b, a in agg.items() if b >= first_full}
    n = append(sym, "upbit", {b: (f"{a[0]:.6g}", f"{a[1]:.6g}", a[2]) for b, a in agg.items()}, ("v", "tb", "n"))
    return n, pages, reached


def main():
    now = int(time.time())
    bad = 0
    for sym in PAIRS:
        try:
            n, base = binance(sym, now)
            status.record(f"spot_binance_{sym}", True, f"+{n} candle 5 menit via {base}")
            print(f"Binance spot {sym}: +{n}")
        except Exception as e:
            bad += 1; status.record(f"spot_binance_{sym}", False, repr(e)); print(f"Binance spot {sym}: GAGAL {e!r}", file=sys.stderr)
        try:
            n, pages, reached = coinbase(sym, now)
            msg = f"+{n} candle 5 menit, {pages} halaman transaksi" + ("" if reached else " (BATAS WAKTU: ada lubang sebelum data ini)")
            status.record(f"spot_coinbase_{sym}", reached, msg)
            print(f"Coinbase {sym}: {msg}")
        except Exception as e:
            bad += 1; status.record(f"spot_coinbase_{sym}", False, repr(e)); print(f"Coinbase {sym}: GAGAL {e!r}", file=sys.stderr)
        try:
            n = okx(sym, now); status.record(f"spot_okx_{sym}", True, f"+{n} candle 5 menit"); print(f"OKX spot {sym}: +{n}")
        except Exception as e:
            bad += 1; status.record(f"spot_okx_{sym}", False, repr(e)); print(f"OKX {sym}: GAGAL {e!r}", file=sys.stderr)
        try:
            n, pages, reached = upbit(sym, now)
            msg = f"+{n} candle 5 menit, {pages} halaman transaksi" + ("" if reached else " (BATAS WAKTU: ada lubang sebelum data ini)")
            status.record(f"spot_upbit_{sym}", reached, msg); print(f"Upbit {sym}: {msg}")
        except Exception as e:
            bad += 1; status.record(f"spot_upbit_{sym}", False, repr(e)); print(f"Upbit {sym}: GAGAL {e!r}", file=sys.stderr)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
