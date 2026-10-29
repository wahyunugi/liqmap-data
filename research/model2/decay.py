"""
Uji: apakah CoinGlass mengecilkan posisi lama (peluruhan menurut umur)? nilai = nilai x exp(-umur / tau).
Fit porsi leverage (NNLS) bersama untuk 24 jam + 1 minggu + 1 bulan; bila tau benar, satu set porsi cocok untuk ketiganya.
    python research/model2/decay.py
"""
import os, sys, json
import numpy as np
from scipy.optimize import nnls
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg  # noqa: E402
from fit import TIERS, COL_STEP, ROWS, cg_matrix  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import fastmodel, inputs  # noqa: E402

TAUS_H = [None, 168, 72, 24, 12]          # jam; None = tanpa peluruhan


def matrices(df, t_end, span, cols, W, edges):
    t = df.t.values
    start = int(np.searchsorted(t, t_end - span))
    tx = t_end - span + span * (np.asarray(cols) + 0.5) / W
    snap_idx = np.clip(np.searchsorted(t + 300, tx, side="right") - 1, start, len(t) - 1)
    want = set(int(i) for i in snap_idx)
    oi = [None if v != v else float(v) for v in df.oi.values]
    out = {tau: {} for tau in TAUS_H}
    for L in TIERS:
        got = {}
        def snap(i, px, us, sd, bn):
            age_h = (i - bn) * 5 / 60
            got[i] = {tau: np.histogram(px, edges, weights=us * (1.0 if tau is None else np.exp(-age_h / tau)))[0] for tau in TAUS_H}
        fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values, oi, len(t) + 1, want, snap,
                           levs=(float(L),), weights=(1.0,), start=start, with_born=True)
        for tau in TAUS_H:
            out[tau][L] = np.stack([got[int(i)][tau] if int(i) in got else np.zeros(ROWS) for i in snap_idx], 1)
    return out


def main():
    df = inputs.load("BTCUSDT")
    data = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df)
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols)
        data[k] = (Y, matrices(df, t_end, span, cols, g["W"], edges))
    for tau in TAUS_H:
        # per screenshot (skala) dan bersama
        line = {"tau_h": tau}
        for k in "DWM":
            Y, X = data[k]; m = np.isfinite(Y)
            A = np.stack([X[tau][L][m] for L in TIERS], 1); w, _ = nnls(A, Y[m]); line[f"scale_{k}"] = round(float(w.sum()), 3)
        A = []; b = []
        for k in "DWM":
            Y, X = data[k]; m = np.isfinite(Y)
            A.append(np.stack([X[tau][L][m] for L in TIERS], 1)); b.append(Y[m])
        w, _ = nnls(np.vstack(A), np.concatenate(b))
        for k in "DWM":
            Y, X = data[k]; m = np.isfinite(Y)
            pred = np.stack([X[tau][L][m] for L in TIERS], 1) @ w; y = Y[m]
            line[f"joint_{k}"] = (round(float(np.corrcoef(pred, y)[0, 1]), 3),
                                  round(float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()), 3))
        line["joint_weights"] = {f"{L}x": round(float(x / w.sum() * 100), 1) for L, x in zip(TIERS, w) if x > 0}
        line["joint_scale"] = round(float(w.sum()), 3)
        print(json.dumps(line), flush=True)


if __name__ == "__main__":
    main()
