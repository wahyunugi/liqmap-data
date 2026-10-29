"""
Uji: apakah CoinGlass Model 2 ikut menghitung posisi yang dibuka SEBELUM tepi kiri grafik (masih terbuka & belum tersentuh)?
Simulasi dimulai H hari sebelum tepi kiri (H = 0, 1, 3, 7, 14); 1 bulan selalu H=0 (data repo mulai 28 Sep).
Campuran leverage bersama + skala per rentang (joint.py); resolusi: 24 jam & 1 minggu 5 menit, 1 bulan 1 jam.
    python research/model2/history_test.py
"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg, fit  # noqa: E402
from fit import TIERS, COL_STEP, cg_matrix  # noqa: E402
from joint import joint_fit, score  # noqa: E402
from resolution import resample  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import fastmodel, inputs  # noqa: E402


def matrices(df, t_end, span, cols, W, edges, hist_s):
    t = df.t.values
    start = int(np.searchsorted(t, t_end - span - hist_s))
    tx = t_end - span + span * (np.asarray(cols) + 0.5) / W
    step = int(t[1] - t[0])
    snap_idx = np.clip(np.searchsorted(t + step, tx, side="right") - 1, start, len(t) - 1)
    want = set(int(i) for i in snap_idx)
    oi = [None if v != v else float(v) for v in df.oi.values]
    out = {}
    for L in TIERS:
        got = {}
        fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values, oi, len(t) + 1, want,
                           lambda i, px, us, sd: got.__setitem__(i, np.histogram(px, edges, weights=us)[0]),
                           levs=(float(L),), weights=(1.0,), start=start)
        out[L] = np.stack([got.get(int(i), np.zeros(fit.ROWS)) for i in snap_idx], 1)
    return out


def main():
    df5 = inputs.load("BTCUSDT")
    d = df5[df5.t % 3600 == 0].index.min(); df1h = resample(df5.iloc[d:].reset_index(drop=True), 12)
    meta = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df5)
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols); m = np.isfinite(Y)
        meta[k] = (g, t_end, span, cols, Y, edges, m)
    def AB(k, df, hist_days):
        g, t_end, span, cols, Y, edges, m = meta[k]
        X = matrices(df, t_end, span, cols, g["W"], edges, hist_days * 86400)
        return np.stack([X[L][m] for L in TIERS], 1), Y[m]
    abM = AB("M", df1h, 0)
    for H in (0, 1, 3, 7, 14):
        ab = {"D": AB("D", df5, H), "W": AB("W", df5, H), "M": abM}
        w, f = joint_fit(ab, ["D", "W", "M"])
        sc = {k: score(ab[k][0] @ w * f[k], ab[k][1]) for k in "DWM"}
        print(json.dumps(dict(history_days=H, D=sc["D"], W=sc["W"], M=sc["M"], f={k: round(v, 3) for k, v in f.items()},
                              w_total=round(float(w.sum()), 3))), flush=True)


if __name__ == "__main__":
    main()
