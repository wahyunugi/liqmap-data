"""
Data pasar di luar Binance futures, untuk melihat siapa yang menggerakkan harga:
  spot    : Coinbase, Kraken (AS) dan Binance, OKX, Bybit, Upbit (non-AS): harga, volume, volume beli agresif (taker)
  futures : Bybit dan OKX perpetual: harga, volume, volume beli agresif, open interest (USD), likuidasi (USD)
  funding : funding rate Binance, Bybit, OKX (biaya berkala antara long dan short, persen per periode)
  CME     : volume dan open interest harian futures Bitcoin/Ether CME (kontrak besar + micro), dari situs CME Group

Sumber: Coinalyze API (kunci COINALYZE_API_KEY yang sama dengan collector/coinalyze.py) dan cmegroup.com (CmeWS, publik).
Simbol Coinalyze dicari dari daftar resmi (/exchanges, /spot-markets, /future-markets), bukan ditebak; pilihan dan semua
kandidat ditulis ke data/markets/symbols.json.

Penyimpanan (hanya menambah, tanpa duplikat waktu, hanya interval yang sudah selesai):
  data/markets/<kategori>/<interval>/<SIMBOL>_<bursa>_<YYYY-MM>.csv    (5min, 1hour)
  data/markets/<kategori>/daily/<SIMBOL>_<bursa>.csv                    (harian, sejak 2020; Coinalyze tidak menghapus data harian)
  data/markets/cme/<SIMBOL>.csv                                          (harian, CME)
Coinalyze hanya menyimpan 1.500-2.000 titik untuk interval intraday (5 menit = 5-7 hari), jadi harus diambil rutin.

    COINALYZE_API_KEY=... python collector/markets.py
"""
import csv, json, os, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coinalyze as cz  # noqa: E402
import status  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "markets")
COINS = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
STEP = {"5min": 300, "1hour": 3600, "daily": 86400}
LOOKBACK = {"5min": 6 * 86400, "1hour": 60 * 86400}
DAILY_FROM = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
# bursa -> (kata kunci nama di Coinalyze, quote yang dipakai)
SPOT = {"coinbase": ("coinbase", ["USD"]), "kraken": ("kraken", ["USD"]),
        "binance": ("binance", ["USDT"]), "okx": ("okx", ["USDT"]), "bybit": ("bybit", ["USDT"]), "upbit": ("upbit", ["KRW"])}
FUT = {"bybit": "bybit", "okx": "okx"}
FUNDING = {"binance": "binance", "bybit": "bybit", "okx": "okx"}
CME = {"BTCUSDT": [(8478, 5.0), (9024, 0.1)], "ETHUSDT": [(8995, 50.0), (10065, 0.1)]}   # product id, koin per kontrak


def ex_codes(client):
    ex = client.get("exchanges", {})
    return ex, {k: {e["code"] for e in ex if kw in e["name"].strip().lower()} for k, (kw, _) in SPOT.items()}


def resolve(client):
    ex, codes = ex_codes(client)
    spot = client.get("spot-markets", {}); fut = client.get("future-markets", {})
    pick, cand = {}, {"exchanges": ex}
    for sym, base in COINS.items():
        for venue, (_, quotes) in SPOT.items():
            c = [m for m in spot if m["exchange"] in codes[venue] and m.get("base_asset") == base]
            cand[f"spot/{sym}/{venue}"] = [(m["symbol"], m["symbol_on_exchange"], m.get("quote_asset"), m.get("has_buy_sell_data")) for m in c]
            for q in quotes:
                ok = [m for m in c if m.get("quote_asset") == q and m.get("has_buy_sell_data")]
                if ok:
                    pick[("spot", sym, venue)] = {"symbol": ok[0]["symbol"], "on_exchange": ok[0]["symbol_on_exchange"], "quote": q}
                    break
        for venue in set(FUT) | set(FUNDING):
            kw = venue
            vc = {e["code"] for e in ex if kw in e["name"].strip().lower()}
            c = [m for m in fut if m["exchange"] in vc and m.get("base_asset") == base and m.get("is_perpetual")
                 and m.get("quote_asset") == "USDT" and m.get("margined") == "STABLE"]
            cand[f"fut/{sym}/{venue}"] = [(m["symbol"], m["symbol_on_exchange"], m.get("oi_lq_vol_denominated_in")) for m in c]
            if c:
                pick[("fut", sym, venue)] = {"symbol": c[0]["symbol"], "on_exchange": c[0]["symbol_on_exchange"],
                                             "denom": c[0].get("oi_lq_vol_denominated_in")}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "symbols.json"), "w") as f:
        json.dump({"picked": {"/".join(k): v for k, v in pick.items()}, "candidates": cand}, f, indent=1)
    return pick


def path_for(cat, iv, name, t):
    if iv == "daily":
        return os.path.join(OUT, cat, iv, f"{name}.csv")
    return os.path.join(OUT, cat, iv, f"{name}_{datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m')}.csv")


def last_stored(cat, iv, name):
    d = os.path.join(OUT, cat, iv)
    if not os.path.isdir(d):
        return None
    fs = sorted(f for f in os.listdir(d) if f == f"{name}.csv" or f.startswith(f"{name}_20"))
    for f in reversed(fs):
        with open(os.path.join(d, f)) as fh:
            rows = list(csv.reader(fh))
        if len(rows) > 1:
            return int(rows[-1][0])
    return None


def append(cat, iv, name, rows, cols, now):
    step = STEP[iv]; by = {}
    for r in rows:
        t = int(r["t"])
        if t + step > now:
            continue
        by.setdefault(path_for(cat, iv, name, t), {})[t] = [r.get(c, "") for c in cols]
    added = 0
    for p, new in by.items():
        old = {}
        if os.path.exists(p):
            with open(p) as fh:
                for x in csv.DictReader(fh):
                    old[int(x["t"])] = [x[c] for c in cols]
        fresh = {t: v for t, v in new.items() if t not in old}
        if not fresh:
            continue
        old.update(fresh); added += len(fresh)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w") as fh:
            fh.write("t," + ",".join(cols) + "\n")
            for t in sorted(old):
                fh.write(f"{t}," + ",".join(str(v) for v in old[t]) + "\n")
        os.replace(tmp, p)
    return added


def fetch(client, endpoint, cat, iv, items, cols, now, extra=None, keys=None):
    """items: list (nama file, simbol Coinalyze). Satu panggilan per kelompok (maks 20 simbol)."""
    keys = keys or cols
    if not items:
        return {}
    starts = []
    for name, _ in items:
        last = last_stored(cat, iv, name)
        start = (DAILY_FROM if last is None else last + STEP[iv]) if iv == "daily" else max(now - LOOKBACK[iv], (last + STEP[iv]) if last else 0)
        starts.append(start)
    frm = min(starts)
    if frm >= now - STEP[iv]:
        return {}
    res = {}
    for i in range(0, len(items), 20):
        grp = items[i:i + 20]
        resp = client.get(endpoint, {"symbols": ",".join(s for _, s in grp), "interval": iv, "from": frm, "to": now, **(extra or {})}, cost=len(grp))
        back = {r["symbol"]: r.get("history", []) for r in resp}
        for name, s in grp:
            hist = [{"t": h["t"], **{c: h.get(k, "") for c, k in zip(cols, keys)}} for h in back.get(s, [])]
            res[name] = append(cat, iv, name, hist, cols, now)
    return res


def cme(now):
    out = {}
    for sym, prods in CME.items():
        rows = {}
        for pid, units in prods:
            url = f"https://www.cmegroup.com/CmeWS/mvc/Volume/LastTotals/{pid}?days=30"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (liqmap-data collector)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read())
            for d in j.get("vdate", []):
                t = int(datetime.strptime(d["formattedDate"], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp())
                e = rows.setdefault(t, {"t": t, "vol_coins": 0.0, "oi_coins": 0.0, "n": 0})
                e["vol_coins"] += float(d["futureVolume"]) * units; e["oi_coins"] += float(d["futureOi"]) * units; e["n"] += 1
        full = [r for r in rows.values() if r["n"] == len(prods)]
        p = os.path.join(OUT, "cme", f"{sym}.csv"); old = {}
        if os.path.exists(p):
            with open(p) as fh:
                old = {int(x["t"]): x for x in csv.DictReader(fh)}
        for r in full:                                   # CME merevisi angka sementara: timpa dengan angka terbaru
            old[r["t"]] = {"t": r["t"], "vol_coins": round(r["vol_coins"], 2), "oi_coins": round(r["oi_coins"], 2)}
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write("t,vol_coins,oi_coins\n")
            for t in sorted(old):
                fh.write(f"{t},{old[t]['vol_coins']},{old[t]['oi_coins']}\n")
        out[sym] = len(full)
    return out


def main():
    now = int(time.time())
    key = os.environ.get("COINALYZE_API_KEY", "").strip()
    bad = 0
    if key:
        client = cz.Client(key)
        try:
            pick = resolve(client)
            spot = [(f"{sym}_{v}", pick[("spot", sym, v)]["symbol"]) for sym in COINS for v in SPOT if ("spot", sym, v) in pick]
            fut = [(f"{sym}_{v}", pick[("fut", sym, v)]["symbol"]) for sym in COINS for v in FUT if ("fut", sym, v) in pick]
            fnd = [(f"{sym}_{v}", pick[("fut", sym, v)]["symbol"]) for sym in COINS for v in FUNDING if ("fut", sym, v) in pick]
            jobs = [("ohlcv-history", "spot", "5min", spot, ["c", "v", "bv"], None),
                    ("ohlcv-history", "fut", "5min", fut, ["c", "v", "bv"], None),
                    ("open-interest-history", "fut_oi", "5min", fut, ["oi_usd"], {"convert_to_usd": "true"}),
                    ("liquidation-history", "fut_liq", "5min", fut, ["l", "s"], {"convert_to_usd": "true"}),
                    ("funding-rate-history", "funding", "1hour", fnd, ["c"], None)]
            if datetime.fromtimestamp(now, timezone.utc).hour == 0 or not os.path.isdir(os.path.join(OUT, "spot", "daily")):
                jobs += [("ohlcv-history", "spot", "daily", spot, ["c", "v", "bv"], None),
                         ("ohlcv-history", "fut", "daily", fut, ["c", "v", "bv"], None),
                         ("open-interest-history", "fut_oi", "daily", fut, ["oi_usd"], {"convert_to_usd": "true"}),
                         ("funding-rate-history", "funding", "daily", fnd, ["c"], None)]
            for endpoint, cat, iv, items, cols, extra in jobs:
                keys = ["c"] if cat == "fut_oi" else None
                try:
                    r = fetch(client, endpoint, cat, iv, items, cols, now, extra, keys)
                    status.record(f"markets_{cat}_{iv}", True, f"baris baru {r}")
                except Exception as e:
                    bad += 1; status.record(f"markets_{cat}_{iv}", False, repr(e)); print(f"{cat}/{iv}: GAGAL {e!r}", file=sys.stderr)
            print(f"Coinalyze: {client.calls} panggilan; simbol {len(spot)} spot, {len(fut)} futures, {len(fnd)} funding")
        except Exception as e:
            bad += 1; status.record("markets_resolve", False, repr(e)); print(f"resolve GAGAL {e!r}", file=sys.stderr)
    else:
        print("COINALYZE_API_KEY kosong: bagian Coinalyze dilewati")
    try:
        r = cme(now); status.record("markets_cme", True, f"hari lengkap {r}"); print("CME", r)
    except Exception as e:
        bad += 1; status.record("markets_cme", False, repr(e)); print(f"CME GAGAL {e!r}", file=sys.stderr)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
