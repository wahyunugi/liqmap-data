"""
Data masukan model heatmap: candle 5 menit + open interest, satu deret tanpa lubang.

Sumber (urutan prioritas bila waktu sama):
1. data/binance_archive/<PAIR>_5m.csv  — arsip Binance dari laptop (28 Sep 2026 s/d 29 Okt 2026), dibekukan
2. data/ohlcv/5min + data/open_interest/5min — dari Coinalyze (GitHub Actions), terus bertambah

Kecocokan dua sumber diuji 29 Okt 2026 (2.021 candle tumpang tindih): harga sama persis, volume sama,
open interest Coinalyze kolom "o" (awal interval) = open interest Binance pada waktu t (selisih median 0,009%).
"""
import glob, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLS = ["t", "open", "high", "low", "close", "vol", "taker_buy", "oi"]


def _read_months(pattern):
    files = sorted(glob.glob(os.path.join(ROOT, "data", pattern)))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True).drop_duplicates("t")


def coinalyze_5m(pair):
    px = _read_months(f"ohlcv/5min/{pair}_*.csv")
    oi = _read_months(f"open_interest/5min/{pair}_*.csv")
    if px.empty or oi.empty:
        return pd.DataFrame(columns=COLS)
    df = px.merge(oi[["t", "o"]].rename(columns={"o": "oi"}), on="t", how="inner")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "vol", "bv": "taker_buy"})
    return df[COLS]


def binance_5m(pair):
    f = os.path.join(ROOT, "data", "binance_archive", f"{pair}_5m.csv")
    return pd.read_csv(f)[COLS] if os.path.exists(f) else pd.DataFrame(columns=COLS)


def load(pair, source="all"):
    """source: 'all' (Binance diutamakan, Coinalyze melanjutkan), 'binance', atau 'coinalyze'."""
    parts = {"binance": [binance_5m(pair)], "coinalyze": [coinalyze_5m(pair)],
             "all": [binance_5m(pair), coinalyze_5m(pair)]}[source]
    df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    df = df.drop_duplicates("t", keep="first").sort_values("t").reset_index(drop=True)
    return df.astype({"t": "int64"})


def gaps(df, step=300):
    """Daftar lubang (waktu_mulai, jumlah_candle_hilang)."""
    d = df.t.diff().fillna(step)
    return [(int(df.t.iat[i - 1]), int(v // step) - 1) for i, v in enumerate(d) if v != step and i > 0]
