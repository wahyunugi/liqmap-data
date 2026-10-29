"""
Konfigurasi terbaik sejauh ini (29 Okt 2026): satu campuran leverage untuk 24 jam / 1 minggu / 1 bulan, skala per rentang,
candle 5 menit (24 jam, 1 minggu) dan 1 jam (1 bulan), hanya posisi yang dibuka di dalam rentang.
Membandingkan beberapa tangga leverage; hasil disimpan ke final_fit.json (dipakai untuk uji dengan screenshot berikutnya).
    python research/model2/final_fit.py
"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg, fit  # noqa: E402
from fit import COL_STEP, cg_matrix  # noqa: E402
from joint import joint_fit, score  # noqa: E402
from resolution import resample  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import fastmodel, inputs  # noqa: E402

LADDERS = {
    "lengkap_14": [2, 3, 4, 5, 7, 10, 15, 20, 25, 33, 50, 75, 100, 125],
    "bursa_10": [2, 3, 5, 10, 20, 25, 50, 75, 100, 125],
    "sederhana_6": [3, 5, 10, 25, 50, 100],
    "sederhana_5": [3, 5, 10, 25, 100],
}
RES = {"D": 1, "W": 1, "M": 12}       # candle: 5 menit x


def matrices(df, t_end, span, cols, W, edges, tiers):
    t = df.t.values; step = int(t[1] - t[0])
    start = int(np.searchsorted(t, t_end - span))
    tx = t_end - span + span * (np.asarray(cols) + 0.5) / W
    snap_idx = np.clip(np.searchsorted(t + step, tx, side="right") - 1, start, len(t) - 1)
    want = set(int(i) for i in snap_idx)
    oi = [None if v != v else float(v) for v in df.oi.values]
    out = {}
    for L in tiers:
        got = {}
        fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values, oi, len(t) + 1, want,
                           lambda i, px, us, sd: got.__setitem__(i, np.histogram(px, edges, weights=us)[0]),
                           levs=(float(L),), weights=(1.0,), start=start)
        out[L] = np.stack([got.get(int(i), np.zeros(fit.ROWS)) for i in snap_idx], 1)
    return out


def prepare(sym="BTCUSDT", refs=None):
    df5 = inputs.load(sym); dfs = {}
    for k, r in RES.items():
        d = df5[df5.t % (300 * r) == 0].index.min()
        dfs[k] = resample(df5.iloc[d:].reset_index(drop=True), r)
    meta = {}
    for k, ref in (refs or cg.REFS).items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df5)
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols); m = np.isfinite(Y)
        meta[k] = (g, t_end, span, cols, Y, edges, m)
    return dfs, meta


def main():
    dfs, meta = prepare()
    allres = {}
    for name, tiers in LADDERS.items():
        ab = {}
        for k in "DWM":
            g, t_end, span, cols, Y, edges, m = meta[k]
            X = matrices(dfs[k], t_end, span, cols, g["W"], edges, tiers)
            ab[k] = (np.stack([X[L][m] for L in tiers], 1), Y[m])
        w, f = joint_fit(ab, ["D", "W", "M"])
        sc = {k: score(ab[k][0] @ w * f[k], ab[k][1]) for k in "DWM"}
        allres[name] = dict(tiers=tiers, w=[float(x) for x in w], f=f, fit=sc,
                            porsi={f"{L}x": round(float(x / w.sum() * 100), 1) for L, x in zip(tiers, w) if x > 1e-4},
                            w_total=round(float(w.sum()), 3))
        print(name, json.dumps({k: v for k, v in allres[name].items() if k not in ("w", "tiers")}), flush=True)
    with open(os.path.join(HERE, "final_fit.json"), "w") as fh:
        json.dump(allres, fh, indent=1)


if __name__ == "__main__":
    main()
