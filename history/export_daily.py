"""
Ringkasan harian (hari UTC) dari arsip publik Binance perpetual sejak 2020, disimpan ke repo untuk analisis:
  data/derived/<SIMBOL>_1d.csv

Kolom:
  date, open, high, low, close, vol (koin), taker_buy_vol (koin dibeli agresif),
  oi_close (open interest di akhir hari, koin; dari arsip + data repo), oi_max, oi_min,
  top_pos_ratio   rata-rata harian rasio long/short "top trader" menurut ukuran posisi (sum_toptrader_long_short_ratio)
  top_acc_ratio   rata-rata harian rasio long/short "top trader" menurut jumlah akun (count_toptrader_long_short_ratio)
  all_acc_ratio   rata-rata harian rasio long/short semua akun (count_long_short_ratio)
  taker_ratio     rata-rata harian rasio volume beli/jual agresif (sum_taker_long_short_vol_ratio)
Kolom rasio kosong bila file metrics hari itu tidak memuatnya.
Arsip diunduh oleh history/binance_public.py (cache GitHub Actions); dijalankan workflow "export".

    python history/export_daily.py
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "heatmap"))
import binance_public as bp  # noqa: E402
import inputs  # noqa: E402

OUT = os.path.join(ROOT, "data", "derived")
RATIOS = {"sum_toptrader_long_short_ratio": "top_pos_ratio", "count_toptrader_long_short_ratio": "top_acc_ratio",
          "count_long_short_ratio": "all_acc_ratio", "sum_taker_long_short_vol_ratio": "taker_ratio"}


def klines_taker(sym):
    frames = []
    for sub in ("klines", "klines_daily"):
        d = os.path.join(bp.CACHE, sym, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".zip"):
                k = bp._read_zip_csv(os.path.join(d, f))
                frames.append(pd.DataFrame({"t": (bp._ms(k.iloc[:, 0]) // 1000).astype("int64"),
                                            "tb": pd.to_numeric(k.iloc[:, 9], errors="coerce")}))
    return pd.concat(frames).drop_duplicates("t") if frames else pd.DataFrame(columns=["t", "tb"])


def ratios(sym):
    d = os.path.join(bp.CACHE, sym, "metrics"); out = []
    if not os.path.isdir(d):
        return pd.DataFrame()
    for f in sorted(os.listdir(d)):
        if not f.endswith(".zip"):
            continue
        m = bp._read_zip_csv(os.path.join(d, f))
        day = f.split("-metrics-")[1][:10]
        row = {"date": day}
        for src, dst in RATIOS.items():
            row[dst] = pd.to_numeric(m[src], errors="coerce").mean() if src in m.columns else np.nan
        out.append(row)
    return pd.DataFrame(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    for sym in bp.PAIRS:
        h = bp.load(sym)
        repo = inputs.load(sym)
        first_repo = int(repo.t.min())
        df = pd.concat([h[h.t < first_repo], repo[["t", "open", "high", "low", "close", "vol", "oi"]]], ignore_index=True)
        df = df.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        df = df.merge(klines_taker(sym), on="t", how="left")
        df["date"] = pd.to_datetime(df.t, unit="s").dt.strftime("%Y-%m-%d")
        g = df.groupby("date")
        out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                            "vol": g.vol.sum().round(3), "taker_buy_vol": g.tb.sum(min_count=1).round(3),
                            "oi_close": g.oi.last(), "oi_max": g.oi.max(), "oi_min": g.oi.min()})
        r = ratios(sym)
        if len(r):
            out = out.join(r.set_index("date"), how="left")
        out = out.reset_index()
        path = os.path.join(OUT, f"{sym}_1d.csv")
        out.to_csv(path, index=False, float_format="%.6g")
        print(sym, len(out), "hari", out.date.iat[0], "s/d", out.date.iat[-1], "| kolom", list(out.columns))


if __name__ == "__main__":
    main()
