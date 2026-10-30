"""
Bangun website Liqmap Chart ke folder _site/ (dipakai GitHub Actions, workflow "site").

    python site/build.py            # 60 hari terakhir (default)
    python site/build.py 90         # 90 hari terakhir

Isi _site/:
  index.html, app.js, model.js  — salinan dari folder site/
  data.json                     — data untuk grafik:
     c5  candle 5 menit + open interest (SAMA dengan masukan heatmap/inputs.py), N hari + 7 hari pemanasan heatmap
     c1  candle 1 menit + open interest 1 menit (Coinalyze), 7 hari terakhir
     l5, l1  likuidasi nyata 5 dan 1 menit (Coinalyze), N hari terakhir
Heatmap TIDAK dihitung di sini: model.js (salinan model v6 dalam JavaScript) menghitungnya di browser.
Data lama di repo tidak disentuh; website hanya menampilkan N hari terakhir supaya tetap ringan.
"""
import glob, json, os, shutil, sys, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "heatmap"))
import inputs  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
DAYS_1M = 7
WARMUP = 7                                 # hari pemanasan heatmap: jendela terpanjang di website = 7 hari
PAIRS = {"BTCUSDT": 1, "ETHUSDT": 2}       # desimal harga
OUT = os.path.join(ROOT, "_site")


def months(pattern):
    files = sorted(glob.glob(os.path.join(ROOT, "data", pattern)))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True).drop_duplicates("t").sort_values("t")


def r(x, nd):
    return [None if pd.isna(v) else round(float(v), nd) for v in x]


def pack_liq(df, t0):
    df = df[df.t >= t0]
    return dict(t=df.t.astype(int).tolist(), l=r(df.l, 0), s=r(df.s, 0), first=int(df.t.min()) if len(df) else None)


COT_GROUPS = ["dealer", "am", "lev", "oth", "nr"]       # lihat collector/cftc.py


def pack_cftc():
    """Laporan CFTC mingguan (data/cftc/cme_tff.csv) -> per koin, posisi dalam satuan koin, semua kontrak CME
    (besar + micro) dijumlahkan: kontrak x satuan kontrak. Long/short tanpa posisi spread (spread = long dan short
    sekaligus milik trader yang sama, jadi tidak mengubah posisi bersih)."""
    path = os.path.join(ROOT, "data", "cftc", "cme_tff.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, dtype={"code": str})
    cols = ["oi"] + [f"{g}_{s}" for g in COT_GROUPS for s in ("l", "s", "sp") if f"{g}_{s}" in df.columns]
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0) * df.units
    out = {}
    for coin, sym in (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT")):
        d = df[df.coin == coin]
        if not len(d):
            continue
        g = d.groupby("date")[cols].sum().sort_index()
        last = d[d.date == d.date.max()]
        out[sym] = dict(t=[int(pd.Timestamp(x, tz="UTC").timestamp()) for x in g.index],
                        **{c: [round(float(v), 1) for v in g[c]] for c in cols},
                        markets=[dict(market=m, units=float(u), oi_coins=round(float(o), 1))
                                 for m, u, o in zip(last.market, last.units, last.oi)])
    return out


def pack_premium(sym, t_start):
    """Coinbase premium (collector/premium.py): 5 menit sejak t_start (deret rapat, null = tidak ada data) dan rata-rata
    harian (hari UTC, dari data per jam sejak Jun 2021) untuk interval 1D/1W/1M."""
    out = {}
    p5 = months(f"premium/5min/{sym}_*.csv")
    if len(p5):
        p5 = p5[p5.t >= t_start]
        if len(p5):
            t0 = int(p5.t.iat[0]); n = (int(p5.t.iat[-1]) - t0) // 300 + 1
            arr = [None] * n
            for t, v in zip(p5.t.astype(int), p5.prem):
                arr[(t - t0) // 300] = round(float(v), 4)
            out["m5"] = dict(t0=t0, step=300, p=arr)
    p1 = months(f"premium/1h/{sym}_*.csv")
    if len(p1):
        day = (p1.t.astype(int) // 86400) * 86400
        g = p1.groupby(day).prem.mean()
        d0 = int(g.index[0]); n = (int(g.index[-1]) - d0) // 86400 + 1
        arr = [None] * n
        for t, v in g.items():
            arr[(int(t) - d0) // 86400] = round(float(v), 4)
        out["d1"] = dict(t0=d0, step=86400, p=arr)
    return out or None


def pack_etf(coin):
    """Arus harian ETF spot AS (collector/etf.py), juta USD per ETF per hari bursa."""
    path = os.path.join(ROOT, "data", "etf", f"{coin}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    cols = [c for c in df.columns if c not in ("date", "total")]
    nn = lambda s: [None if pd.isna(v) else round(float(v), 1) for v in s]
    return dict(t=[int(pd.Timestamp(d, tz="UTC").timestamp()) for d in df.date], total=nn(df.total),
                cols=cols, v={c: nn(df[c]) for c in cols})


def build():
    out = {"built": int(time.time()), "days": DAYS}
    out["cftc"] = pack_cftc()
    out["etf"] = {sym: pack_etf(sym.replace("USDT", "")) for sym in PAIRS}
    for sym, nd in PAIRS.items():
        c5 = inputs.load(sym)
        t_end = int(c5.t.iat[-1]) + 300
        c5 = c5[c5.t >= t_end - (DAYS + WARMUP) * 86400].reset_index(drop=True)
        steps = c5.t.diff().dropna()
        if (steps != 300).any():
            print(f"PERINGATAN {sym}: {int((steps != 300).sum())} lubang di data 5 menit (heatmap mengikuti urutan candle)")
        px1 = months(f"ohlcv/1min/{sym}_*.csv")
        oi1 = months(f"open_interest/1min/{sym}_*.csv")
        c1 = px1.merge(oi1[["t", "c"]].rename(columns={"c": "oi"}), on="t", how="left") if len(oi1) else px1.assign(oi=None)
        c1 = c1[c1.t >= c1.t.max() - DAYS_1M * 86400]
        t0 = t_end - DAYS * 86400
        out[sym] = dict(
            c5=dict(t=c5.t.astype(int).tolist(), o=r(c5.open, nd), h=r(c5.high, nd), l=r(c5.low, nd), c=r(c5.close, nd),
                    v=r(c5.vol, 3), oi=r(c5.oi, 3)),
            c1=dict(t=c1.t.astype(int).tolist(), o=r(c1.o, nd), h=r(c1.h, nd), l=r(c1.l, nd), c=r(c1.c, nd),
                    v=r(c1.v, 3), oi=r(c1.oi, 3)),
            l5=pack_liq(months(f"liquidations/5min/{sym}_*.csv"), t0),
            l1=pack_liq(months(f"liquidations/1min/{sym}_*.csv"), c1.t.min()),
            prem=pack_premium(sym, int(c5.t.iat[0])),
        )
        print(f"{sym}: {len(c5)} candle 5m, {len(c1)} candle 1m, "
              f"{len(out[sym]['l5']['t'])} baris likuidasi 5m, data sampai {pd.to_datetime(t_end, unit='s')} UTC")
    os.makedirs(OUT, exist_ok=True)
    for f in ("index.html", "app.js", "model.js"):
        shutil.copy(os.path.join(HERE, f), os.path.join(OUT, f))
    with open(os.path.join(OUT, "data.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"_site/data.json {os.path.getsize(os.path.join(OUT, 'data.json')) / 1e6:.2f} MB")


if __name__ == "__main__":
    build()
