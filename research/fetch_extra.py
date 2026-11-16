"""
Data riset tambahan tahap 2 (workflow "research-data"): pengganti gratis untuk data yang biasanya berbayar.

  1. LIKUIDASI NYATA BINANCE, riwayat panjang (arsip publik data.binance.vision, set "liquidationSnapshot"):
       research/data/liq/<SIMBOL>.csv.gz   per 5 menit: t, long_usd, short_usd, n_long, n_short
     long_usd = nilai posisi LONG yang dilikuidasi (order likuidasi sisi SELL), short_usd = posisi SHORT (sisi BUY).
     Catatan: sejak April 2021 Binance hanya menerbitkan paling banyak satu likuidasi per simbol per detik, jadi nilai
     ini batas bawah, sama seperti data Coinalyze di data/liquidations.
  2. LIKUIDASI COINALYZE harian dan per jam sejauh yang disimpan Coinalyze (butuh COINALYZE_API_KEY):
       research/data/liq_coinalyze_daily.csv, liq_coinalyze_1hour.csv   kolom: t, sym, l, s (USD)
  3. SALDO BURSA (pengganti "arus masuk stablecoin ke bursa"): DefiLlama, kategori CEX, saldo dompet bursa per hari
     per token -> research/data/cex_reserves.csv   kolom: date, exchange, usdt, usdc, stable_other, btc, eth (jumlah token)
     Perubahan saldo harian = arus bersih masuk/keluar bursa. Hanya bursa yang membuka alamat dompetnya.
  4. PERHATIAN PUBLIK (pengganti Google Trends): jumlah pembaca harian artikel Wikipedia bahasa Inggris
     (API resmi Wikimedia, sejak Juli 2015) -> research/data/attention.csv   kolom: date, Bitcoin, Ethereum, Cryptocurrency

    python research/fetch_extra.py [liq] [coinalyze] [cex] [attention]      # tanpa argumen = semua
"""
import concurrent.futures as cf, datetime as dt, io, json, os, re, sys, time, urllib.parse, urllib.request
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "collector"))
from fetch_alts import fetch, unzip_csv, secs, UA  # noqa: E402

OUT = os.path.join(HERE, "data")
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
VISION = "https://data.binance.vision/"
LIQ_COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
STABLE_OTHER = {"FDUSD", "DAI", "TUSD", "BUSD", "USDE", "PYUSD", "USDP", "USDD", "USD1", "RLUSD"}
BTC_LIKE, ETH_LIKE = {"BTC", "WBTC", "BTCB"}, {"ETH", "WETH", "BETH", "WBETH"}


def s3_keys(prefix):
    """Semua nama file di bawah prefix (daftar S3, 1.000 per halaman)."""
    keys, marker = [], ""
    while True:
        raw = fetch(f"{S3}?prefix={urllib.parse.quote(prefix)}&marker={urllib.parse.quote(marker)}")
        txt = raw.decode()
        got = re.findall(r"<Key>([^<]+)</Key>", txt)
        keys += got
        if "<IsTruncated>true</IsTruncated>" not in txt or not got:
            return keys
        marker = got[-1]


def liq_file(url):
    raw = fetch(url)
    if raw is None:
        return None
    d = unzip_csv(raw)
    d.columns = [str(c).strip().lower() for c in d.columns]
    if "side" not in d.columns:                               # tanpa header: urutan kolom arsip Binance
        d.columns = ["time", "side", "order_type", "time_in_force", "original_quantity", "price", "average_price",
                     "order_status", "last_fill_quantity", "accumulated_fill_quantity"][:len(d.columns)]
    q = pd.to_numeric(d.get("accumulated_fill_quantity", d.get("original_quantity")), errors="coerce")
    q = q.where(q > 0, pd.to_numeric(d["original_quantity"], errors="coerce"))
    px = pd.to_numeric(d.get("average_price"), errors="coerce"); px = px.where(px > 0, pd.to_numeric(d["price"], errors="coerce"))
    usd = (q * px).fillna(0.0).values
    t = secs(d["time"]) // 300 * 300
    sell = d["side"].astype(str).str.upper().eq("SELL").values
    g = pd.DataFrame({"t": t, "long_usd": np.where(sell, usd, 0.0), "short_usd": np.where(~sell, usd, 0.0),
                      "n_long": sell.astype(int), "n_short": (~sell).astype(int)}).groupby("t", as_index=False).sum()
    return g


def liquidations(coins=LIQ_COINS, workers=24):
    os.makedirs(os.path.join(OUT, "liq"), exist_ok=True)
    try:
        top = fetch(f"{S3}?delimiter=/&prefix=data/futures/um/daily/").decode()
        print("set data harian futures di arsip Binance:", [p.split("/")[-2] for p in re.findall(r"<Prefix>([^<]+)</Prefix>", top)], flush=True)
    except Exception as e:
        print("daftar set gagal:", repr(e)[:150], flush=True)
    for sym in coins:
        try:
            keys = [k for k in s3_keys(f"data/futures/um/daily/liquidationSnapshot/{sym}/") if k.endswith(".zip")]
            if not keys:
                print(f"LIQ {sym}: tidak ada file di arsip", flush=True); continue
            with cf.ThreadPoolExecutor(workers) as ex:
                parts = [x for x in ex.map(lambda k: liq_file(VISION + k), keys) if x is not None and len(x)]
            d = pd.concat(parts).groupby("t", as_index=False).sum().sort_values("t")
            d.to_csv(os.path.join(OUT, "liq", sym + ".csv.gz"), index=False, float_format="%.0f", compression="gzip")
            day = pd.to_datetime(d.t, unit="s").dt.strftime("%Y-%m"); byyr = d.groupby(day.str[:4])[["long_usd", "short_usd"]].sum() / 1e9
            print(f"LIQ {sym}: {len(keys)} file ({keys[0].split('-liquidationSnapshot-')[-1][:10]} s.d. {keys[-1].split('-liquidationSnapshot-')[-1][:10]}), "
                  f"{len(d)} baris 5 menit, miliar USD per tahun long/short: " + ", ".join(f"{y}: {a:.1f}/{b:.1f}" for y, (a, b) in zip(byyr.index, byyr.values)), flush=True)
        except Exception as e:
            print(f"LIQ {sym} GAGAL: {e!r}"[:300], flush=True)


def coinalyze():
    import coinalyze as cz
    key = os.environ.get("COINALYZE_API_KEY")
    if not key:
        print("COINALYZE: tidak ada kunci, dilewati", flush=True); return
    c = cz.Client(key); syms = cz.resolve_symbols(c); now = int(time.time())
    for iv, frm in (("daily", 1577836800), ("1hour", now - 2100 * 3600)):
        rows = []
        for p, m in syms.items():
            r = c.get("liquidation-history", {"symbols": m["symbol"], "interval": iv, "from": frm, "to": now, "convert_to_usd": "true"})
            for h in (r[0]["history"] if r else []):
                rows.append(dict(t=h["t"], sym=p, l=h.get("l"), s=h.get("s")))
        d = pd.DataFrame(rows)
        if len(d):
            d.sort_values(["sym", "t"]).to_csv(os.path.join(OUT, f"liq_coinalyze_{iv}.csv"), index=False, float_format="%.0f")
        print(f"COINALYZE {iv}: {len(d)} baris" + (f", {pd.to_datetime(d.t.min(), unit='s')} s.d. {pd.to_datetime(d.t.max(), unit='s')}" if len(d) else ""), flush=True)


def cex(top_n=14):
    allp = json.loads(fetch("https://api.llama.fi/protocols"))
    ex = sorted([p for p in allp if p.get("category") == "CEX"], key=lambda p: -(p.get("tvl") or 0))[:top_n]
    print("CEX DefiLlama:", [(p["slug"], round((p.get("tvl") or 0) / 1e9, 1)) for p in ex], flush=True)
    rows = {}
    for p in ex:
        try:
            j = json.loads(fetch(f"https://api.llama.fi/protocol/{p['slug']}"))
            n = 0
            for chain, cv in (j.get("chainTvls") or {}).items():
                if "-" in chain or chain in ("borrowed", "staking", "pool2"):
                    continue
                perday = {}                                    # satu titik per hari per rantai: yang terakhir menang
                for e in cv.get("tokens") or []:               # (hari berjalan muncul dua kali: 00:00 dan "sekarang")
                    perday[dt.datetime.fromtimestamp(int(e["date"]), dt.timezone.utc).strftime("%Y-%m-%d")] = e
                for date, e in perday.items():
                    r = rows.setdefault((date, p["slug"]), dict(usdt=0.0, usdc=0.0, stable_other=0.0, btc=0.0, eth=0.0))
                    for tok, amt in (e.get("tokens") or {}).items():
                        u = tok.upper()
                        k = "usdt" if u == "USDT" else "usdc" if u == "USDC" else "stable_other" if u in STABLE_OTHER else "btc" if u in BTC_LIKE else "eth" if u in ETH_LIKE else None
                        if k and amt:
                            r[k] += float(amt); n += 1
            print(f"  {p['slug']}: {n} titik token", flush=True)
        except Exception as e:
            print(f"  {p['slug']} GAGAL: {e!r}"[:200], flush=True)
    d = pd.DataFrame([dict(date=k[0], exchange=k[1], **v) for k, v in rows.items()]).sort_values(["exchange", "date"])
    d = d.drop_duplicates(["exchange", "date"], keep="last")
    d.to_csv(os.path.join(OUT, "cex_reserves.csv"), index=False, float_format="%.6g")
    g = d.groupby("exchange").agg(first=("date", "min"), last=("date", "max"), days=("date", "size"), usdt_last=("usdt", "last"), btc_last=("btc", "last"))
    print(g.to_string(), flush=True)


def attention(articles=("Bitcoin", "Ethereum", "Cryptocurrency")):
    end = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d"); cols = {}
    for a in articles:
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{a}/daily/20150701/{end}"
        req = urllib.request.Request(url, headers={"User-Agent": UA + " wahyunugi"})
        with urllib.request.urlopen(req, timeout=60) as r:
            items = json.load(r)["items"]
        cols[a] = pd.Series({f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}": i["views"] for i in items})
        print(f"WIKI {a}: {len(items)} hari, terakhir {items[-1]['timestamp'][:8]} = {items[-1]['views']}", flush=True)
    pd.DataFrame(cols).sort_index().to_csv(os.path.join(OUT, "attention.csv"), index_label="date")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    want = sys.argv[1:] or ["liq", "coinalyze", "cex", "attention"]
    for name, fn in (("liq", liquidations), ("coinalyze", coinalyze), ("cex", cex), ("attention", attention)):
        if name in want:
            try:
                fn()
            except Exception as e:
                print(f"{name.upper()} GAGAL: {e!r}"[:400], flush=True)
