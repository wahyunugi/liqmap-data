"""
Cari tangga leverage + porsinya yang paling cocok dengan heatmap CoinGlass rentang panjang (24 jam / 1 minggu / 1 bulan).

Model: aturan v6 (posisi baru = kenaikan OI per candle 5 menit, tiap sisi long & short = 100% kenaikan itu, harga
likuidasi = harga masuk x (1 -/+ 1/leverage), level hilang saat tersentuh), dengan:
  - hanya posisi yang dibuka di dalam rentang screenshot (dari tepi kiri plot),
  - tiap leverage dihitung terpisah dengan porsi 1, lalu porsinya dicari dengan kuadrat terkecil non-negatif (NNLS).
Perbandingan dilakukan di kotak harga CoinGlass sendiri (119 baris per grafik) dan per kolom waktu.
    python research/model2/fit.py
"""
import os, sys, json
import numpy as np
from scipy.optimize import nnls

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cg  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import fastmodel, inputs  # noqa: E402

TIERS = [2, 3, 4, 5, 7, 10, 15, 20, 25, 33, 50, 75, 100, 125]
ROWS = 119
COL_STEP = 3


def cg_matrix(ref, g, cols):
    edges = np.linspace(ref.p_bot, ref.p_top, ROWS + 1)
    rid = np.clip(np.searchsorted(edges, g["price"]) - 1, 0, ROWS - 1)     # baris kotak tiap baris piksel
    M = np.full((ROWS, len(cols)), np.nan)
    for k, x in enumerate(cols):
        v = g["val"][:, x]; ok = g["valid"][:, x]
        for r in range(ROWS):
            sel = ok & (rid == r)
            if sel.sum() >= 2:
                M[r, k] = np.median(v[sel])
    return M, edges


def model_matrices(df, t_end, span, cols, W, edges):
    t = df.t.values
    start = int(np.searchsorted(t, t_end - span))
    tx = t_end - span + span * (np.asarray(cols) + 0.5) / W
    snap_idx = np.clip(np.searchsorted(t + 300, tx, side="right") - 1, start, len(t) - 1)
    want = set(int(i) for i in snap_idx)
    oi = [None if v != v else float(v) for v in df.oi.values]
    out = {}
    for L in TIERS:
        got = {}
        fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values, oi, len(t) + 1, want,
                           lambda i, px, us, sd: got.__setitem__(i, np.histogram(px, edges, weights=us)[0]),
                           levs=(float(L),), weights=(1.0,), start=start)
        out[L] = np.stack([got.get(int(i), np.zeros(ROWS)) for i in snap_idx], axis=1)
    return out


def main():
    df = inputs.load("BTCUSDT")
    data = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref)
        err, t_end, span = cg.align(ref, g, df)
        cols = list(range(0, g["W"], COL_STEP))
        Y, edges = cg_matrix(ref, g, cols)
        X = model_matrices(df, t_end, span, cols, g["W"], edges)
        data[k] = (Y, X)
        print(f"{k}: kolom {len(cols)}, sel valid {np.isfinite(Y).sum()}", flush=True)
    res = {}
    for name, keys in [("D", ["D"]), ("W", ["W"]), ("M", ["M"]), ("semua", ["D", "W", "M"])]:
        A = []; b = []
        for k in keys:
            Y, X = data[k]; m = np.isfinite(Y)
            A.append(np.stack([X[L][m] for L in TIERS], 1)); b.append(Y[m])
        A = np.vstack(A); b = np.concatenate(b)
        w, _ = nnls(A, b)
        fitq = {}
        for k in ["D", "W", "M"]:
            Y, X = data[k]; m = np.isfinite(Y)
            pred = sum(w[i] * X[L][m] for i, L in enumerate(TIERS)); y = Y[m]
            r = np.corrcoef(pred, y)[0, 1] if pred.std() > 0 else 0.0
            r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
            fitq[k] = dict(pearson=round(float(r), 3), r2=round(float(r2), 3))
        tot = w.sum()
        res[name] = dict(weights={str(L): round(float(x / tot * 100), 1) for L, x in zip(TIERS, w) if x > 0},
                         scale_sum=round(float(tot), 3), quality=fitq)
        print(name, json.dumps(res[name]), flush=True)
    # pembanding: model v6 (25/50/100x, porsi 25:50:100), skala bebas
    for k in ["D", "W", "M"]:
        Y, X = data[k]; m = np.isfinite(Y)
        v6 = sum(x * X[L][m] for L, x in ((25, 25 / 175), (50, 50 / 175), (100, 100 / 175)))
        print(f"v6 pada {k}: pearson {np.corrcoef(v6, Y[m])[0, 1]:.3f}", flush=True)
    with open(os.path.join(HERE, "fit_result.json"), "w") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
