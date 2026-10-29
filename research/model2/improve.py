"""
Perbaikan model 2 + ukuran kecocokan yang sama dengan v6.
Ukuran: (a) ketat = per kotak CoinGlass; (b) toleransi 1 kotak = kedua gambar dihaluskan arah harga (gauss, σ = 1 kotak),
sama seperti accuracy_report v6 (research/compare.py) yang memakai σ = lebar toleransi.
Variasi model: margin pemeliharaan (0,01% / 0,4%), pergeseran grid kotak (±½ kotak, langkah ¼), dan pergeseran tampilan.
Campuran leverage bersama + skala per rentang; candle 5 menit (24 jam, 1 minggu), 1 jam (1 bulan).
    python research/model2/improve.py
"""
import os, sys, json, itertools
import numpy as np
from scipy.ndimage import gaussian_filter1d
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg, fit  # noqa: E402
from fit import TIERS, COL_STEP, ROWS  # noqa: E402
from joint import joint_fit  # noqa: E402
from resolution import resample  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import fastmodel, inputs  # noqa: E402

SUB = 4
RES = {"D": 1, "W": 1, "M": 12}


def cg_rows(ref, g, cols):
    edges = np.linspace(ref.p_bot, ref.p_top, ROWS + 1)
    rid = np.clip(np.searchsorted(edges, g["price"]) - 1, 0, ROWS - 1)
    M = np.full((ROWS, len(cols)), np.nan)
    for k, x in enumerate(cols):
        v = g["val"][:, x]; ok = g["valid"][:, x]
        for r in range(ROWS):
            sel = ok & (rid == r)
            if sel.sum() >= 2:
                M[r, k] = np.median(v[sel])
    return M


def fine_model(df, t_end, span, cols, W, ref, mmr, shift_pct):
    fastmodel.MMR = mmr
    t = df.t.values; step = int(t[1] - t[0])
    start = int(np.searchsorted(t, t_end - span))
    tx = t_end - span + span * (np.asarray(cols) + 0.5) / W
    snap_idx = np.clip(np.searchsorted(t + step, tx, side="right") - 1, start, len(t) - 1)
    want = set(int(i) for i in snap_idx)
    oi = [None if v != v else float(v) for v in df.oi.values]
    box = (ref.p_top - ref.p_bot) / ROWS
    edges = np.linspace(ref.p_bot - box, ref.p_top + box, (ROWS + 2) * SUB + 1)   # 1 kotak cadangan di atas & bawah
    out = {}
    for L in TIERS:
        got = {}
        fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values, oi, len(t) + 1, want,
                           lambda i, px, us, sd: got.__setitem__(i, np.histogram(px * (1 + shift_pct), edges, weights=us)[0]),
                           levs=(float(L),), weights=(1.0,), start=start)
        out[L] = np.stack([got.get(int(i), np.zeros(len(edges) - 1)) for i in snap_idx], 1)
    fastmodel.MMR = 0.0001
    return out


def rebin(F, s):
    """baris halus -> kotak CoinGlass, dengan grid digeser s/SUB kotak."""
    n = F.shape[0]; idx = np.arange(n) + s - SUB          # buang 1 kotak cadangan bawah
    r = np.floor_divide(idx, SUB); ok = (r >= 0) & (r < ROWS)
    out = np.zeros((ROWS, F.shape[1]))
    np.add.at(out, r[ok], F[ok])
    return out


def scores(pred, Y):
    m = np.isfinite(Y)
    y = Y[m]; p = pred[m]
    strict = np.corrcoef(p, y)[0, 1]
    Yf = np.where(m, Y, 0.0)
    ps = gaussian_filter1d(pred, 1.0, axis=0)[m]; ys = gaussian_filter1d(Yf, 1.0, axis=0)[m]
    tol = np.corrcoef(ps, ys)[0, 1]
    r2 = 1 - ((ys - ps) ** 2).sum() / ((ys - ys.mean()) ** 2).sum()
    return round(float(strict), 3), round(float(tol), 3), round(float(r2), 3)


def main():
    df5 = inputs.load("BTCUSDT"); dfs = {}
    for k, r in RES.items():
        d = df5[df5.t % (300 * r) == 0].index.min(); dfs[k] = resample(df5.iloc[d:].reset_index(drop=True), r)
    meta = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df5)
        cols = list(range(0, g["W"], COL_STEP))
        meta[k] = (ref, g, t_end, span, cols, cg_rows(ref, g, cols))
    results = []
    for mmr, shift in itertools.product((0.0001, 0.004), (0.0, 0.00025)):
        fine = {k: fine_model(dfs[k], t_end, span, cols, g["W"], ref, mmr, shift)
                for k, (ref, g, t_end, span, cols, Y) in meta.items()}
        for s in range(-2, 3):
            ab = {}; Xs = {}
            for k, (ref, g, t_end, span, cols, Y) in meta.items():
                X = {L: rebin(fine[k][L], s) for L in TIERS}; Xs[k] = X; m = np.isfinite(Y)
                ab[k] = (np.stack([X[L][m] for L in TIERS], 1), Y[m])
            w, f = joint_fit(ab, ["D", "W", "M"])
            sc = {}
            for k, (ref, g, t_end, span, cols, Y) in meta.items():
                pred = sum(w[i] * Xs[k][L] for i, L in enumerate(TIERS)) * f[k]
                sc[k] = scores(pred, Y)
            row = dict(mmr=mmr, shift=shift, grid_shift_box=s / SUB, ketat=[sc[k][0] for k in "DWM"],
                       toleransi_1kotak=[sc[k][1] for k in "DWM"], r2_tol=[sc[k][2] for k in "DWM"],
                       rata_tol=round(float(np.mean([sc[k][1] for k in "DWM"])), 3))
            results.append(row); print(json.dumps(row), flush=True)
    results.sort(key=lambda r: -r["rata_tol"])
    print("TERBAIK:", json.dumps(results[0]))
    json.dump(results, open(os.path.join(HERE, "improve_result.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
