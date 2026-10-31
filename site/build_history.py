"""
Bangun data website untuk interval panjang 1D, 1W, 1M: _site/hist/<SIMBOL>_<TF>.json + _site/history_report.json.

Deret candle 5 menit + open interest = arsip publik Binance (history/binance_public.py, sejak 2020) disambung data repo
(heatmap/inputs.py) mulai candle pertama repo. Heatmap dihitung dengan heatmap/fastmodel.py (aturan model v6, sama persis
dengan model.py — lihat heatmap/check_fastmodel.py), satu snapshot di penutupan tiap candle 1D/1W/1M.
Jendela heatmap = panjang satu candle: 1D = 24 jam (model yang dicocokkan ke CoinGlass), 1W = 7 hari, 1M = 30 hari.
Candle: hari dan bulan UTC, minggu mulai Senin 00:00 UTC (seperti Binance/TradingView).

    python site/build_history.py
"""
import json, os, sys, time
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "heatmap"))
sys.path.insert(0, os.path.join(ROOT, "history"))
import inputs, fastmodel, binance_public  # noqa: E402

PAIRS = {"BTCUSDT": 1, "ETHUSDT": 2}
TFS = {"1D": 288, "1W": 2016, "1M": 8640}       # jendela heatmap (candle 5 menit)
OUT = os.path.join(ROOT, "_site", "hist")


def bucket(t, tf):
    """Waktu buka candle (UTC, detik) untuk tiap waktu t (array)."""
    t = np.asarray(t, dtype=np.int64)
    day = t // 86400
    if tf == "1D":
        return day * 86400
    if tf == "1W":                               # 1 Jan 1970 = Kamis; +3 hari -> minggu mulai Senin
        return ((day + 3) // 7 * 7 - 3) * 86400
    d = pd.DatetimeIndex(pd.to_datetime(t, unit="s", utc=True))
    first = pd.to_datetime({"year": d.year, "month": d.month, "day": 1}, utc=True)
    return ((first - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy(dtype=np.int64)


def coinalyze_lsr(sym):
    import glob
    fs = sorted(glob.glob(os.path.join(ROOT, "data", "long_short_ratio", "5min", f"{sym}_*.csv")))
    if not fs:
        return pd.DataFrame(columns=["t", "cz_r"])
    c = pd.concat([pd.read_csv(f) for f in fs]).drop_duplicates("t")
    return pd.DataFrame({"t": c.t.astype("int64"), "cz_r": pd.to_numeric(c.r, errors="coerce")})


def series(sym, report):
    repo = inputs.load(sym)
    try:
        hist = binance_public.load(sym)
    except Exception as e:                       # belum ada arsip (misalnya dijalankan lokal tanpa unduhan)
        hist = pd.DataFrame(columns=["t", "open", "high", "low", "close", "vol", "oi"])
        report["history_error"] = str(e)[:200]
    r = report
    if len(hist):
        r["history_from"] = str(pd.to_datetime(hist.t.min(), unit="s"))
        r["history_rows"] = int(len(hist))
        r["history_oi_coverage_pct"] = round(float(hist.oi.notna().mean() * 100), 2)
        r["history_oi_glitches_removed"] = getattr(binance_public.load, "glitches", None)
        # cek tumpang tindih dengan arsip Binance di repo (dari laptop, 28 Sep - 29 Okt 2026)
        arch = inputs.binance_5m(sym)
        m = hist.merge(arch, on="t", suffixes=("_h", "_r"))
        if len(m):
            r["overlap_candles"] = int(len(m))
            r["overlap_close_equal_pct"] = round(float((m.close_h.round(4) == m.close_r.round(4)).mean() * 100), 2)
            d = ((m.oi_h - m.oi_r).abs() / m.oi_r).dropna()
            r["overlap_oi_median_diff_pct"] = round(float(d.median() * 100), 5) if len(d) else None
            r["overlap_oi_p95_diff_pct"] = round(float(d.quantile(0.95) * 100), 5) if len(d) else None
            # waktu OI arsip publik vs arsip repo: geser -1/0/+1 candle, cari selisih terkecil
            for sh in (-300, 0, 300):
                mm = hist[["t", "oi"]].assign(t=hist.t + sh).merge(arch[["t", "oi"]], on="t", suffixes=("_h", "_r"))
                dd = ((mm.oi_h - mm.oi_r).abs() / mm.oi_r).dropna()
                r[f"overlap_oi_median_diff_pct_shift{sh:+d}s"] = round(float(dd.median() * 100), 5) if len(dd) else None
        # cakupan OI: tanggal pertama, dan bulan-bulan sesudahnya yang OI-nya kurang dari 95%
        has = hist[hist.oi.notna()]
        if len(has):
            r["oi_first"] = str(pd.to_datetime(has.t.min(), unit="s"))
            after = hist[hist.t >= has.t.min()].copy()
            after["m"] = pd.to_datetime(after.t, unit="s").dt.strftime("%Y-%m")
            cov = after.groupby("m").oi.apply(lambda x: x.notna().mean() * 100)
            r["oi_months_below_95pct"] = {k: round(float(v), 1) for k, v in cov[cov < 95].items()}
    first_repo = int(repo.t.min())
    h = hist[hist.t < first_repo][["t", "open", "high", "low", "close", "vol", "oi"]]
    df = pd.concat([h, repo[["t", "open", "high", "low", "close", "vol", "oi"]]], ignore_index=True)
    df = df.drop_duplicates("t").sort_values("t").reset_index(drop=True)
    # rasio long/short Binance: arsip publik (sampai kemarin), sisanya dari Coinalyze (data/long_short_ratio, 5 menit)
    if len(hist) and "acc_lsr" in hist.columns:
        df = df.merge(hist[["t", "acc_lsr", "top_lsr"]], on="t", how="left")
    else:
        df["acc_lsr"] = np.nan; df["top_lsr"] = np.nan
    cz = coinalyze_lsr(sym)
    if len(cz):
        df = df.merge(cz, on="t", how="left")
        miss = df.acc_lsr.isna() & df.cz_r.notna() & (df.t > (hist.t.max() if len(hist) else 0))
        df.loc[miss, "acc_lsr"] = df.loc[miss, "cz_r"]
        both = df.acc_lsr.notna() & df.cz_r.notna() & ~miss
        if both.any():                               # cek: Coinalyze r = rasio akun Binance?
            r["lsr_coinalyze_vs_archive_median_diff_pct"] = round(float(((df.cz_r[both] / df.acc_lsr[both] - 1).abs()).median() * 100), 3)
            r["lsr_overlap_points"] = int(both.sum())
        r["lsr_filled_from_coinalyze"] = int(miss.sum())
        df = df.drop(columns=["cz_r"])
    steps = df.t.diff().dropna()
    r["candles"] = int(len(df))
    r["from"] = str(pd.to_datetime(df.t.min(), unit="s"))
    r["to"] = str(pd.to_datetime(df.t.max() + 300, unit="s"))
    r["gaps"] = int((steps != 300).sum())
    r["missing_minutes_total"] = int(((steps[steps != 300] - 300) / 60).sum())
    r["oi_coverage_pct"] = round(float(df.oi.notna().mean() * 100), 2)
    # 10 perubahan OI 5 menit terbesar (sesudah pembersihan), untuk memeriksa sisa data rusak
    oiv = pd.to_numeric(df.oi, errors="coerce").astype("float64")
    ch = (oiv.shift(-1) - oiv) / oiv
    top = ch.abs().dropna().nlargest(10).index
    r["largest_oi_changes"] = [[str(pd.to_datetime(df.t[i], unit="s")), round(float(oiv[i]), 1),
                                round(float(oiv[i + 1]), 1), round(float(ch[i] * 100), 2)] for i in top]
    return df


def build_tf(df, sym, nd, tf, B):
    t = df.t.values
    keys = bucket(t, tf)
    starts = np.r_[0, np.nonzero(np.diff(keys))[0] + 1]
    ends = np.r_[starts[1:] - 1, len(df) - 1]
    oi = df.oi.values
    bars = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": [], "oi": [], "tclose": [], "lsr": [], "tpr": []}
    acc, top = df.acc_lsr.values, df.top_lsr.values
    for a, e in zip(starts, ends):
        bars["t"].append(int(keys[a]))
        bars["o"].append(round(float(df.open.iat[a]), nd))
        bars["h"].append(round(float(df.high.values[a:e + 1].max()), nd))
        bars["l"].append(round(float(df.low.values[a:e + 1].min()), nd))
        bars["c"].append(round(float(df.close.iat[e]), nd))
        bars["v"].append(round(float(df.vol.values[a:e + 1].sum()), 1))
        x = oi[e + 1] if e + 1 < len(df) and oi[e + 1] == oi[e + 1] else oi[e]     # OI saat candle ditutup
        bars["oi"].append(None if x != x else round(float(x), 1))
        bars["tclose"].append(int(t[e]) + 300)
        for k, arr in (("lsr", acc), ("tpr", top)):              # rata-rata rasio long/short selama candle
            seg = arr[a:e + 1]; seg = seg[~np.isnan(seg)]
            bars[k].append(round(float(seg.mean()), 3) if len(seg) else None)
    window = TFS[tf]
    snaps = {}
    fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values,
                       [None if v != v else float(v) for v in oi], window, set(int(e) for e in ends),
                       lambda i, px, us, sd: snaps.__setitem__(i, fastmodel.aggregate(px, us, sd, *B)))
    start, bins, L, S = [0], [], [], []
    for e in ends:
        e = int(e)
        if e in snaps and e >= window:
            b, lg, sh = snaps[e]
            lk = np.rint(lg / 1000).astype(np.int64); sk = np.rint(sh / 1000).astype(np.int64)
            keep = (lk > 0) | (sk > 0)                      # nilai < $500 dibulatkan ke 0 dan tidak disimpan
            b, lk, sk = b[keep], lk[keep], sk[keep]
            if len(b):
                bins.extend(np.r_[b[0], np.diff(b)].tolist()); L.extend(lk.tolist()); S.extend(sk.tolist())
        start.append(len(bins))
    out = dict(tf=tf, window=window, B=list(B), unit="USD x1000", **bars,
               snap=dict(start=start, b=bins, L=L, S=S))
    path = os.path.join(OUT, f"{sym}_{tf}.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return len(bars["t"]), len(bins), os.path.getsize(path)


def crowd(df, sym):
    """Rasio akun long/short harian vs perubahan harga 30 hari kemudian (dibagi lima kelompok sama besar).
    Juga deret 5 menit 70 hari terakhir untuk interval < 1D di website."""
    day = pd.to_datetime(df.t, unit="s").dt.floor("D")
    g = df.groupby(day)
    d = pd.DataFrame({"close": g.close.last(), "lsr": g.acc_lsr.mean(), "tpr": g.top_lsr.mean()})
    d["fwd30"] = (d.close.shift(-30) / d.close - 1) * 100
    x = d.dropna(subset=["lsr", "fwd30"])
    out = {"from": str(x.index.min().date()) if len(x) else None, "to": str(x.index.max().date()) if len(x) else None}
    if len(x) >= 200:
        edges = x.lsr.quantile([0, .2, .4, .6, .8, 1]).round(3).tolist()
        q = pd.cut(x.lsr, [-np.inf] + edges[1:-1] + [np.inf], labels=False)
        def stats(mask):
            y = x[mask]; qq = q[mask]
            rows = []
            for k in range(5):
                f = y.fwd30[qq == k]
                rows.append(dict(days=int(len(f)), median=round(float(f.median()), 2) if len(f) else None,
                                 up=round(float((f > 0).mean() * 100), 1) if len(f) else None))
            return dict(rows=rows, base_up=round(float((y.fwd30 > 0).mean() * 100), 1), days=int(len(y)),
                        base_median=round(float(y.fwd30.median()), 2))
        out.update(edges=edges, all=stats(np.ones(len(x), bool)), recent=stats(x.index >= "2023-01-01"),
                   recent_from="2023-01-01")
    lat = d.dropna(subset=["lsr"])
    if len(lat):
        out["latest_day"] = str(lat.index[-1].date()); out["latest_lsr"] = round(float(lat.lsr.iat[-1]), 3)
        out["latest_tpr"] = None if pd.isna(lat.tpr.iat[-1]) else round(float(lat.tpr.iat[-1]), 3)
    # 5 menit, 70 hari terakhir
    tail = df[df.t >= df.t.max() - 70 * 86400]
    t0 = int(tail.t.iat[0]); n = (int(tail.t.iat[-1]) - t0) // 300 + 1
    a = [None] * n; b = [None] * n
    for tt, v1, v2 in zip(tail.t.astype(int), tail.acc_lsr, tail.top_lsr):
        i = (tt - t0) // 300
        a[i] = None if pd.isna(v1) else round(float(v1), 3); b[i] = None if pd.isna(v2) else round(float(v2), 3)
    out["m5"] = dict(t0=t0, step=300, acc=a, top=b)
    with open(os.path.join(OUT, f"{sym}_crowd.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return {k: out.get(k) for k in ("from", "to", "edges", "latest_day", "latest_lsr")}


def main():
    os.makedirs(OUT, exist_ok=True)
    report = {"built": int(time.time())}
    for sym, nd in PAIRS.items():
        t0 = time.time()
        rep = report.setdefault(sym, {})
        df = series(sym, rep)
        repo = inputs.load(sym)
        B = fastmodel.bins_for(float(repo.close.iat[-1]))   # kotak harga sama dengan grafik 5m/15m/1h di website
        for tf in TFS:
            nb, ne, size = build_tf(df, sym, nd, tf, B)
            rep[tf] = dict(bars=nb, cells=ne, file_mb=round(size / 1e6, 2))
        rep["crowd"] = crowd(df, sym)
        rep["seconds"] = round(time.time() - t0, 1)
        print(sym, json.dumps(rep))
    with open(os.path.join(ROOT, "_site", "history_report.json"), "w") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
