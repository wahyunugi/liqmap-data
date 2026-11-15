"""
Data riset tambahan (sekali jalan, lewat workflow "research-data"):
  1. Koin lain dari arsip publik Binance (data.binance.vision), per jam, untuk menguji ulang temuan BTC/ETH di pasar lain:
       research/data/hourly/<SIMBOL>.csv.gz   kolom: t (awal jam, detik UTC), open, high, low, close, vol (koin),
       taker_buy (koin dibeli agresif), oi (open interest akhir jam, koin), acc_lsr (rata-rata jam rasio akun
       long/short semua akun), top_lsr (rata-rata jam rasio long/short top trader menurut ukuran posisi)
     Sumber: futures/um/monthly/klines/<SYM>/1h (+ harian untuk bulan berjalan) dan futures/um/daily/metrics/<SYM>.
     Nilai OI <= 0 dibuang (arsip publik kadang berisi 0).
  2. Data makro harian dari FRED (fred.stlouisfed.org/graph/fredgraph.csv, tanpa kunci):
       research/data/macro.csv   kolom: date + DFEDTARU (batas atas suku bunga Fed), DTWEXBGS (indeks dolar luas),
       DGS10 dan DGS2 (imbal hasil obligasi AS 10 dan 2 tahun), SP500, NASDAQCOM, VIXCLS (indeks volatilitas saham)

    python research/fetch_alts.py [SIMBOL ...]
"""
import concurrent.futures as cf, datetime as dt, io, os, sys, time, urllib.error, urllib.request, zipfile
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")
BASE = "https://data.binance.vision/data/futures/um"
COINS = ["SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
FRED = ["DFEDTARU", "DTWEXBGS", "DGS10", "DGS2", "SP500", "NASDAQCOM", "VIXCLS"]
UA = "liqmap-data research (https://github.com/wahyunugi/liqmap-data)"


def fetch(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError("gagal mengunduh " + url)


def unzip_csv(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        b = z.read(z.namelist()[0])
    header = not b.split(b"\n", 1)[0][:1].isdigit()
    return pd.read_csv(io.BytesIO(b), header=0 if header else None)


def secs(x):
    x = np.asarray(x, dtype="float64")
    return (np.where(x > 1e14, x / 1000.0, x) // 1000).astype("int64")


def klines(url):
    raw = fetch(url)
    if raw is None:
        return None
    k = unzip_csv(raw)
    return pd.DataFrame({"t": secs(k.iloc[:, 0]), "open": k.iloc[:, 1], "high": k.iloc[:, 2], "low": k.iloc[:, 3],
                         "close": k.iloc[:, 4], "vol": k.iloc[:, 5], "taker_buy": k.iloc[:, 9]}).apply(pd.to_numeric, errors="coerce")


def metrics(url):
    raw = fetch(url)
    if raw is None:
        return None
    m = unzip_csv(raw)
    ct = m["create_time"]
    if pd.api.types.is_numeric_dtype(ct):
        ts = secs(ct)
    else:
        ts = ((pd.to_datetime(ct, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64").values
    ts = (np.round(ts / 300) * 300).astype("int64")
    d = pd.DataFrame({"t": ts, "oi": pd.to_numeric(m["sum_open_interest"], errors="coerce")})
    for src, dst in (("count_long_short_ratio", "acc_lsr"), ("sum_toptrader_long_short_ratio", "top_lsr")):
        d[dst] = pd.to_numeric(m[src], errors="coerce") if src in m.columns else np.nan
    d.loc[d.oi <= 0, "oi"] = np.nan
    d["h"] = d.t // 3600 * 3600
    g = d.sort_values("t").groupby("h")
    return pd.DataFrame({"oi": g.oi.last(), "acc_lsr": g.acc_lsr.mean(), "top_lsr": g.top_lsr.mean()}).reset_index().rename(columns={"h": "t"})


def coin(sym, today=None, workers=24):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    first = today.replace(day=1)
    ku = []
    y, m = 2020, 1
    while (y, m) < (first.year, first.month):
        ku.append(f"{BASE}/monthly/klines/{sym}/1h/{sym}-1h-{y}-{m:02d}.zip"); y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    d = (first - dt.timedelta(days=1)).replace(day=1)
    while d < today:
        ku.append(f"{BASE}/daily/klines/{sym}/1h/{sym}-1h-{d.isoformat()}.zip"); d += dt.timedelta(days=1)
    mu = []; d = dt.date(2020, 9, 1)
    while d < today:
        mu.append(f"{BASE}/daily/metrics/{sym}/{sym}-metrics-{d.isoformat()}.zip"); d += dt.timedelta(days=1)
    with cf.ThreadPoolExecutor(workers) as ex:
        kf = [x for x in ex.map(klines, ku) if x is not None]
        mf = [x for x in ex.map(metrics, mu) if x is not None]
    px = pd.concat(kf).drop_duplicates("t").sort_values("t")
    out = px.merge(pd.concat(mf).drop_duplicates("t", keep="last"), on="t", how="left") if mf else px.assign(oi=np.nan, acc_lsr=np.nan, top_lsr=np.nan)
    out = out.dropna(subset=["close"]).reset_index(drop=True)
    os.makedirs(os.path.join(OUT, "hourly"), exist_ok=True)
    out.to_csv(os.path.join(OUT, "hourly", sym + ".csv.gz"), index=False, float_format="%.8g", compression="gzip")
    return len(out), len(kf), len(mf), str(pd.to_datetime(out.t.iat[0], unit="s")), str(pd.to_datetime(out.t.iat[-1], unit="s")), round(float(out.oi.notna().mean()), 3)


def macro():
    cols = {}
    for s in FRED:
        try:
            raw = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2019-01-01")
            d = pd.read_csv(io.BytesIO(raw)); d.columns = ["date", s]
            cols[s] = pd.to_numeric(d.set_index("date")[s], errors="coerce")
            print("FRED", s, len(d), d.date.iat[-1], flush=True)
        except Exception as e:
            print("FRED GAGAL", s, repr(e)[:120], flush=True)
    if cols:
        os.makedirs(OUT, exist_ok=True)
        pd.DataFrame(cols).sort_index().to_csv(os.path.join(OUT, "macro.csv"), index_label="date")


if __name__ == "__main__":
    macro()
    for s in sys.argv[1:] or COINS:
        t0 = time.time()
        try:
            print(s, coin(s), f"{time.time() - t0:.0f} s", flush=True)
        except Exception as e:
            print(s, "GAGAL", repr(e)[:200], flush=True)
