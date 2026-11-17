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


US_VENUES = ["coinbase", "kraken", "gemini"]
NONUS_VENUES = ["binance", "bybit", "okx", "bithumb", "upbit"]
OWN_SPOT = {"okx", "upbit"}      # tidak ada di Coinalyze: dari collector/spot.py (data/spot/5min), tanpa riwayat harian
FUT_VENUES = ["bybit", "okx"]


def regular(df, cols, step, t_start=None, nd=4):
    """Deret rapat {t0, step, <kolom>: [...]} dari DataFrame berkolom t; null = tidak ada data."""
    if df is None or not len(df):
        return None
    if t_start is not None:
        df = df[df.t >= t_start]
        if not len(df):
            return None
    df = df.sort_values("t")
    t0 = int(df.t.iat[0]); n = (int(df.t.iat[-1]) - t0) // step + 1
    out = dict(t0=t0, step=step)
    idx = ((df.t.astype("int64") - t0) // step).to_numpy()
    for k, c in cols.items():
        arr = [None] * n
        for i, v in zip(idx, df[c]):
            if not pd.isna(v):
                arr[int(i)] = round(float(v), nd)
        out[k] = arr
    return out


def mk(cat, iv, name):
    """data/markets/<cat>/<iv>/<name>*.csv (collector/markets.py)."""
    if iv == "daily":
        p = os.path.join(ROOT, "data", "markets", cat, "daily", f"{name}.csv")
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
    return months(f"markets/{cat}/{iv}/{name}_*.csv")


def pack_markets(sym, t_start, c5):
    """Spot multi-bursa (AS / non-AS), futures Bybit + OKX, funding rate rata-rata, selisih futures vs spot."""
    out = {"spot5": {}, "spotd": {}, "fut5": {}, "futd": {}}
    for v in US_VENUES + NONUS_VENUES:
        if v in OWN_SPOT:
            out["spot5"][v] = regular(months(f"spot/5min/{sym}_{v}_*.csv"), {"v": "v", "tb": "tb"}, 300, t_start, 3)
            continue
        out["spot5"][v] = regular(mk("spot", "5min", f"{sym}_{v}"), {"v": "v", "tb": "bv"}, 300, t_start, 3)
        out["spotd"][v] = regular(mk("spot", "daily", f"{sym}_{v}"), {"v": "v", "tb": "bv", "c": "c"}, 86400, None, 3)
    for v in FUT_VENUES:
        f = mk("fut", "5min", f"{sym}_{v}")
        if len(f):
            oi = mk("fut_oi", "5min", f"{sym}_{v}"); lq = mk("fut_liq", "5min", f"{sym}_{v}")
            f = f.merge(oi, on="t", how="left") if len(oi) else f.assign(oi_usd=None)
            f = f.merge(lq, on="t", how="left") if len(lq) else f.assign(l=None, s=None)
            f["oi"] = pd.to_numeric(f.oi_usd, errors="coerce") / f.c          # USD -> koin dengan harga penutupan
            out["fut5"][v] = regular(f, {"v": "v", "tb": "bv", "oi": "oi", "l": "l", "s": "s"}, 300, t_start, 3)
        fd = mk("fut", "daily", f"{sym}_{v}")
        if len(fd):
            oid = mk("fut_oi", "daily", f"{sym}_{v}")
            fd = fd.merge(oid, on="t", how="left") if len(oid) else fd.assign(oi_usd=None)
            fd["oi"] = pd.to_numeric(fd.oi_usd, errors="coerce") / fd.c
            out["futd"][v] = regular(fd, {"v": "v", "tb": "bv", "oi": "oi"}, 86400, None, 3)
    # funding rate: rata-rata Binance, Bybit, OKX yang tersedia (persen per periode, biasanya 8 jam)
    for iv, key, step, ts in (("1hour", "fund1h", 3600, t_start), ("daily", "fundd", 86400, None)):
        fr = [mk("funding", iv, f"{sym}_{v}").rename(columns={"c": v}) for v in ("binance", "bybit", "okx")]
        fr = [x for x in fr if len(x)]
        if fr:
            m = fr[0]
            for x in fr[1:]:
                m = m.merge(x, on="t", how="outer")
            m["avg"] = m[[c for c in m.columns if c != "t"]].mean(axis=1)
            out[key] = regular(m, {"p": "avg"}, step, ts, 5)
    # selisih harga futures (Binance perpetual) vs spot (Binance), persen, per 5 menit
    sp = months(f"premium/5min/{sym}_*.csv")
    if len(sp):
        b = c5[["t", "close"]].merge(sp[["t", "bn"]], on="t")
        b["bas"] = (b.close / b.bn - 1) * 100
        out["bas5"] = regular(b, {"p": "bas"}, 300, t_start, 4)
    return out


def pack_spot(sym, t_start):
    """Volume per 5 menit (koin) dan volume beli agresif (taker): spot AS (Coinbase), spot non-AS (Binance) dari
    collector/spot.py, dan futures perpetual Binance (Coinalyze, kolom bv). Deret rapat sejak t_start, null = kosong."""
    def series(df, vcol, bcol):
        if not len(df):
            return None
        df = df[df.t >= t_start]
        if not len(df):
            return None
        t0 = int(df.t.iat[0]); n = (int(df.t.iat[-1]) - t0) // 300 + 1
        v = [None] * n; b = [None] * n
        for t, x, y in zip(df.t.astype(int), df[vcol], df[bcol]):
            i = (t - t0) // 300
            v[i] = None if pd.isna(x) else round(float(x), 3); b[i] = None if pd.isna(y) else round(float(y), 3)
        return dict(t0=t0, step=300, v=v, tb=b)
    return dict(us=series(months(f"spot/5min/{sym}_coinbase_*.csv"), "v", "tb"),
                nu=series(months(f"spot/5min/{sym}_binance_*.csv"), "v", "tb"),
                fu=series(months(f"ohlcv/5min/{sym}_*.csv"), "v", "bv"))


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


STABLE_FROM = "2019-01-01"   # sebelum ini data DefiLlama belum lengkap (sebagian rantai/penerbit belum tercatat)


def pack_stable():
    """Pasokan stablecoin berpatok USD per hari (collector/stablecoins.py), miliar USD: total, USDT, USDC."""
    path = os.path.join(ROOT, "data", "stablecoins", "daily.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df = df[df.date >= STABLE_FROM].reset_index(drop=True)
    if not len(df):
        return None
    nb = lambda s: [None if pd.isna(v) else round(float(v) / 1e9, 3) for v in s]
    return dict(t=[int(pd.Timestamp(d, tz="UTC").timestamp()) for d in df.date],
                total=nb(df.total), usdt=nb(df.usdt), usdc=nb(df.usdc))


def pack_hl():
    """Posisi Hyperliquid (collector/hyperliquid.py): profil terbaru per koin + deret per jam (pangsa long)."""
    d = os.path.join(ROOT, "data", "hyperliquid")
    files = sorted(glob.glob(os.path.join(d, "summary", "*.csv")))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f) for f in files]).drop_duplicates(["t", "coin"]).sort_values("t")
    out = {}
    pct = lambda a, b: [None if (pd.isna(x) or pd.isna(y) or x + y <= 0) else round(100 * x / (x + y), 2) for x, y in zip(a, b)]
    for coin in ("BTC", "ETH"):
        g = df[df.coin == coin].reset_index(drop=True)
        prof_path = os.path.join(d, "profile", coin + ".json")
        if not len(g) or not os.path.exists(prof_path):
            continue
        g["day"] = g.t // 86400 * 86400
        sm = g.groupby("day")[["sm_nL", "sm_nS"]].sum()
        sm = sm[(sm.sm_nL + sm.sm_nS) >= 30]                # hari dengan cukup posisi di sampel akun kecil
        last = g.iloc[-1]
        num = lambda v: None if pd.isna(v) else float(v)
        out[coin + "USDT"] = dict(
            t=[int(x) for x in g.t], ls=pct(g.szL, g.szS), big=pct(g.big_szL, g.big_szS),
            cover=[None if not o else round(100 * (a + b) / 2 / o, 1) for a, b, o in zip(g.szL, g.szS, g.oi)],
            smt=[int(x) for x in sm.index], sm=pct(sm.sm_nL, sm.sm_nS), smn=[int(a + b) for a, b in zip(sm.sm_nL, sm.sm_nS)],
            last={k: num(last[k]) for k in ("t", "mark", "oi", "queried", "nL", "nS", "szL", "szS", "avgL", "avgS", "lossL", "lossS",
                                             "big_nL", "big_nS", "big_szL", "big_szS")},
            prof=json.load(open(prof_path)))
        wh = pack_whales(coin)
        if wh:
            out[coin + "USDT"]["wh"] = wh
    return out or None


WH_SHOW, WH_EV_DAYS, WH_EV_MAX = 15, 7, 40


def pack_whales(coin):
    """Posisi terbesar (snapshot terakhir) + perubahan besar WH_EV_DAYS hari terakhir, terbaru dulu (collector/hyperliquid.py)."""
    d = os.path.join(ROOT, "data", "hyperliquid", "whales")
    path = os.path.join(d, coin + ".json")
    if not os.path.exists(path):
        return None
    w = json.load(open(path))
    ev = []
    files = sorted(glob.glob(os.path.join(d, "events_*.csv")))
    if files:
        e = pd.concat([pd.read_csv(f) for f in files[-2:]])
        e = e[(e.coin == coin) & (e.t >= w["t"] - WH_EV_DAYS * 86400)].sort_values("t", ascending=False).head(WH_EV_MAX)
        ev = [dict(t=int(r.t), a=r.addr, k=r.kind, s0=float(r.sz0), s1=float(r.sz1), m=float(r.mark)) for r in e.itertuples()]
    return dict(t=w["t"], mark=w["mark"], top=w["top"][:WH_SHOW], ev=ev)


def pack_calendar(now):
    """Jadwal rilis AS berikutnya (site/calendar.csv, diisi tangan dari federalreserve.gov dan bls.gov): keputusan suku
    bunga Fed (14:00 waktu New York) dan laporan inflasi CPI (08:30 waktu New York) -> waktu UTC."""
    from zoneinfo import ZoneInfo
    path = os.path.join(HERE, "calendar.csv")
    if not os.path.exists(path):
        return []
    hhmm = {"fomc": (14, 0), "cpi": (8, 30)}
    out = []
    for r in pd.read_csv(path).itertuples():
        if r.kind not in hhmm:
            continue
        h, m = hhmm[r.kind]
        t = int(pd.Timestamp(r.date).replace(hour=h, minute=m).tz_localize(ZoneInfo("America/New_York")).timestamp())
        if t >= now - 3600:
            out.append(dict(t=t, k=r.kind))
    return sorted(out, key=lambda x: x["t"])[:6]


# bursa yang datanya ada sejak Des 2022, supaya jumlahnya tidak melonjak hanya karena bursa baru masuk daftar
RES_SET = ["binance-cex", "okx", "bybit", "bitfinex", "bitget", "gate", "htx", "deribit", "kucoin", "crypto-com"]
RES_FROM = "2022-12-22"


def pack_extras():
    """Data harian tambahan (collector/extras.py): saldo bursa, pembaca Wikipedia, likuidasi harian."""
    out = {}
    ts = lambda d: int(pd.Timestamp(d, tz="UTC").timestamp())
    p = os.path.join(ROOT, "data", "exchanges", "reserves.csv")
    if os.path.exists(p):
        r = pd.read_csv(p); r = r[r.exchange.isin(RES_SET) & (r.date >= RES_FROM)]
        r["stable"] = r.usdt + r.usdc + r.stable_other
        days = sorted(r.date.unique())
        piv = lambda col: r.pivot(index="date", columns="exchange", values=col).reindex(days).ffill()
        st, bt, et = piv("stable"), piv("btc"), piv("eth")
        full = st.notna().all(axis=1)                              # hanya hari saat semua bursa di daftar punya data
        def clean(p):
            """Lonjakan harian satu bursa > 15% dianggap perubahan daftar dompet, bukan arus (aturan research/exp7_reserves.py):
            garis = saldo nyata terakhir dikurangi jumlah perubahan bersih sesudahnya, jadi nilai terakhir tetap saldo nyata."""
            p = p[full]; d = p.diff(); d[p.pct_change().abs() > 0.15] = 0.0
            net = d.sum(axis=1).fillna(0.0); tot = p.sum(axis=1)
            return tot.iat[-1] - net[::-1].cumsum()[::-1].shift(-1, fill_value=0.0)
        st_c, bt_c, et_c = clean(st), clean(bt), clean(et)
        out["res"] = dict(t=[ts(d) for d in st.index[full]], stable=[round(v / 1e9, 3) for v in st_c],
                          BTCUSDT=[round(v) for v in bt_c], ETHUSDT=[round(v) for v in et_c],
                          n=len(RES_SET), binance=[round(v / 1e9, 3) for v in st[full]["binance-cex"]])
    p = os.path.join(ROOT, "data", "attention", "wikipedia.csv")
    if os.path.exists(p):
        a = pd.read_csv(p)
        nn = lambda s: [None if pd.isna(v) else int(v) for v in s]
        out["att"] = dict(t=[ts(d) for d in a.date], BTCUSDT=nn(a.Bitcoin), ETHUSDT=nn(a.Ethereum))
    out["liqd"] = {}
    for sym in PAIRS:
        p = os.path.join(ROOT, "data", "liquidations", "daily", sym + ".csv")
        if os.path.exists(p):
            l = pd.read_csv(p).sort_values("t")
            out["liqd"][sym] = dict(t=[int(x) for x in l.t], l=[round(v / 1e6, 2) for v in l.l], s=[round(v / 1e6, 2) for v in l.s])
    return out


REPO = os.environ.get("GITHUB_REPOSITORY", "wahyunugi/liqmap-data")


def pack_archives():
    """Daftar arsip (GitHub Release bertanda archive-*, dibuat workflow "archive") + ukuran repo menurut GitHub.
    Gagal mengambil = daftar kosong (website tetap menampilkan tautan ke halaman Releases)."""
    import urllib.request
    def api(path):
        req = urllib.request.Request("https://api.github.com/" + path, headers={"Accept": "application/vnd.github+json", "User-Agent": "liqmap-site"})
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if tok:
            req.add_header("Authorization", "Bearer " + tok)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    out = dict(repo=REPO, size_mb=None, list=[])
    try:
        out["size_mb"] = round(api(f"repos/{REPO}")["size"] / 1024)
        for r in api(f"repos/{REPO}/releases?per_page=100"):
            if not r["tag_name"].startswith("archive-") or r.get("draft"):
                continue
            out["list"].append(dict(tag=r["tag_name"], t=int(pd.Timestamp(r["created_at"]).timestamp()), url=r["html_url"],
                                    files=[dict(name=a["name"], mb=round(a["size"] / 1e6, 1), url=a["browser_download_url"]) for a in r["assets"]]))
        out["list"].sort(key=lambda x: -x["t"])
    except Exception as e:
        print(f"PERINGATAN: daftar arsip tidak terambil: {e!r}")
    return out


UW_BIN, UW_BURN = 0.0025, 24 * 90


def pack_underwater(sym, c5):
    """Perkiraan porsi kontrak terbuka Binance yang harga masuknya di atas harga sekarang (= long yang sedang rugi =
    short yang sedang untung). Aturan SAMA dengan research/underwater.py (jaga agar tetap sama): per jam, kenaikan OI
    dicatat sebagai posisi baru pada harga penutupan jam itu; penurunan OI mengurangi semua kelompok harga masuk
    secara proporsional. Data: data/derived/hourly (sejak 2020) disambung jam-jam terbaru dari candle 5 menit."""
    import numpy as np
    files = sorted(glob.glob(os.path.join(ROOT, "data", "derived", "hourly", f"{sym}_20*.csv")))
    if not files:
        return None
    h = pd.concat([pd.read_csv(f, usecols=["t", "low", "high", "close", "oi"]) for f in files]).drop_duplicates("t").sort_values("t")
    last = c5[(c5.t + 300) % 3600 == 0]                         # candle 5 menit terakhir tiap jam -> penutupan jam
    g = c5.assign(ht=c5.t // 3600 * 3600).groupby("ht").agg(low=("low", "min"), high=("high", "max")).reset_index()
    new = last.assign(t=last.t // 3600 * 3600)[["t", "close", "oi"]].merge(g.rename(columns={"ht": "t"}), on="t")
    h = pd.concat([h, new[new.t > h.t.max()]], ignore_index=True)
    C = h.close.values; oi = h.oi.values; n = len(h)
    lo = np.log(np.nanmin(h.low.values) * 0.9); nb = int((np.log(np.nanmax(h.high.values) * 1.1) - lo) / UW_BIN) + 2
    mid = np.exp(lo + (np.arange(nb) + 0.5) * UW_BIN)
    book = np.zeros(nb); prev = float("nan"); start = None; tot = 0.0
    for i in range(n):
        o = oi[i]
        if o == o and o > 0:
            b = int((np.log(C[i]) - lo) / UW_BIN)
            if prev != prev:
                book[b] += o; start = i
            else:
                d = o - prev
                if d > 0:
                    book[b] += d
                elif d < 0:
                    book *= max(0.0, 1 + d / max(book.sum(), 1e-12))
            prev = o
    tot = book.sum()
    if start is None or n - start < UW_BURN or tot <= 0:
        return None
    b = int((np.log(C[-1]) - lo) / UW_BIN)
    U = (book[b + 1:].sum() + 0.5 * book[b]) / tot
    return dict(t=int(h.t.iat[-1]) + 3600, U=round(float(U), 4), avg=round(float((book * mid).sum() / tot), 2), px=float(C[-1]))


def build():
    out = {"built": int(time.time()), "days": DAYS}
    out["stable"] = pack_stable()
    out["hl"] = pack_hl()
    out["cal"] = pack_calendar(out["built"])
    out["arch"] = pack_archives()
    try:
        out["extra"] = pack_extras()
    except Exception as e:
        print(f"PERINGATAN: data tambahan gagal dikemas: {e!r}"); out["extra"] = {}
    out["cftc"] = pack_cftc()
    out["etf"] = {sym: pack_etf(sym.replace("USDT", "")) for sym in PAIRS}
    for sym, nd in PAIRS.items():
        c5 = inputs.load(sym)
        t_end = int(c5.t.iat[-1]) + 300
        try:
            uw = pack_underwater(sym, c5)
        except Exception as e:                                   # perkiraan tambahan: tidak boleh menggagalkan website
            print(f"PERINGATAN {sym}: perkiraan posisi rugi gagal: {e!r}"); uw = None
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
            spot=pack_spot(sym, int(c5.t.iat[0])),
            mk=pack_markets(sym, int(c5.t.iat[0]), c5),
            uw=uw,
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
