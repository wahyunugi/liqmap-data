"""
Campuran leverage bersama (joint.py) + resolusi candle per rentang: apakah CoinGlass memakai candle lebih kasar untuk
rentang panjang? Dicoba kombinasi resolusi untuk 1 minggu dan 1 bulan (24 jam tetap 5 menit).
    python research/model2/joint_res.py
"""
import os, sys, json, itertools
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg  # noqa: E402
from fit import TIERS, COL_STEP, cg_matrix, model_matrices  # noqa: E402
from joint import joint_fit, score  # noqa: E402
from resolution import resample  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import inputs  # noqa: E402

RES = {"5m": 1, "15m": 3, "30m": 6, "1h": 12, "4h": 48}


def main():
    df5 = inputs.load("BTCUSDT")
    cache = {}
    meta = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df5)
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols); m = np.isfinite(Y)
        meta[k] = (g, t_end, span, cols, Y, edges, m)
    def AB(k, res):
        if (k, res) not in cache:
            g, t_end, span, cols, Y, edges, m = meta[k]; kk = RES[res]
            d = df5[df5.t % (300 * kk) == 0].index.min(); d = resample(df5.iloc[d:].reset_index(drop=True), kk)
            X = model_matrices(d, t_end, span, cols, g["W"], edges)
            cache[(k, res)] = (np.stack([X[L][m] for L in TIERS], 1), Y[m])
        return cache[(k, res)]
    rows = []
    for rw, rm in itertools.product(["5m", "15m", "30m"], ["5m", "30m", "1h", "4h"]):
        ab = {"D": AB("D", "5m"), "W": AB("W", rw), "M": AB("M", rm)}
        w, f = joint_fit(ab, ["D", "W", "M"])
        sc = {k: score(ab[k][0] @ w * f[k], ab[k][1]) for k in "DWM"}
        rows.append(dict(W=rw, M=rm, D_fit=sc["D"], W_fit=sc["W"], M_fit=sc["M"], f={k: round(v, 3) for k, v in f.items()},
                         w_total=round(float(w.sum()), 3), mean_pearson=round(float(np.mean([sc[k][0] for k in "DWM"])), 3)))
        print(json.dumps(rows[-1]), flush=True)
    rows.sort(key=lambda r: -r["mean_pearson"])
    with open(os.path.join(HERE, "joint_res_result.json"), "w") as fh:
        json.dump(rows, fh, indent=1)
    print("TERBAIK:", json.dumps(rows[0]))


if __name__ == "__main__":
    main()
