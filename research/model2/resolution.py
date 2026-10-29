"""
Uji: apakah CoinGlass memakai candle lebih kasar (15m/30m/1h/...) untuk rentang lebih panjang?
Untuk tiap screenshot dan tiap resolusi: fit NNLS porsi leverage, catat pola (pearson), besaran (R²) dan total skala.
Bila resolusinya benar, total skala (jumlah porsi) mendekati 1 seperti model v6 (tiap sisi = 100% kenaikan OI).
    python research/model2/resolution.py
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.optimize import nnls
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg, fit  # noqa: E402
from fit import TIERS, COL_STEP, cg_matrix, model_matrices  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import inputs  # noqa: E402


def resample(df, k):
    if k == 1:
        return df
    g = (df.t - df.t.iat[0]) // (300 * k)
    out = df.groupby(g).agg(t=("t", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                            close=("close", "last"), vol=("vol", "sum"), oi=("oi", "first")).reset_index(drop=True)
    return out


def main():
    df5 = inputs.load("BTCUSDT")
    rows = []
    for key, ref in cg.REFS.items():
        g = cg.load(ref)
        err, t_end, span = cg.align(ref, g, df5)
        cols = list(range(0, g["W"], COL_STEP))
        Y, edges = cg_matrix(ref, g, cols)
        m = np.isfinite(Y)
        for k, name in [(1, "5m"), (3, "15m"), (6, "30m"), (12, "1h"), (24, "2h"), (48, "4h"), (288, "1d")]:
            # sejajarkan blok candle kasar dengan jam bulat UTC
            d = df5[df5.t % (300 * k) == 0].index.min()
            d = resample(df5.iloc[d:].reset_index(drop=True), k)
            X = model_matrices(d, t_end, span, cols, g["W"], edges)
            A = np.stack([X[L][m] for L in TIERS], 1); b = Y[m]
            w, _ = nnls(A, b); pred = A @ w
            r = np.corrcoef(pred, b)[0, 1]; r2 = 1 - ((b - pred) ** 2).sum() / ((b - b.mean()) ** 2).sum()
            top = sorted(((float(x / w.sum() * 100), L) for L, x in zip(TIERS, w) if x > 0), reverse=True)[:4]
            rows.append(dict(ref=key, res=name, pearson=round(float(r), 3), r2=round(float(r2), 3),
                             scale=round(float(w.sum()), 3), top=[f"{L}x {p:.0f}%" for p, L in top]))
            print(json.dumps(rows[-1]), flush=True)
    with open(os.path.join(HERE, "resolution_result.json"), "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
