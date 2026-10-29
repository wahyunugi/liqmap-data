"""
Satu campuran leverage untuk ketiga rentang, dengan satu faktor skala tampilan per rentang (f_k).
Model: CoinGlass_k ≈ f_k × Σ_L w_L × model_L,k   (w dan f dicari bergantian: NNLS untuk w, kuadrat terkecil untuk f).
Bedanya dengan shared.py: di sana tiap gambar dinormalkan dengan skala fit sendiri, padahal 24 jam & 1 minggu tidak bisa
melihat leverage rendah (level 2x–5x di luar rentang harga gambar), sehingga skala fit sendiri tidak sebanding.
    python research/model2/joint.py
"""
import os, sys, json
import numpy as np
from scipy.optimize import nnls
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg  # noqa: E402
from fit import TIERS, COL_STEP, cg_matrix, model_matrices  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import inputs  # noqa: E402


def score(pred, y):
    return round(float(np.corrcoef(pred, y)[0, 1]), 3), round(float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()), 3)


def joint_fit(AB, keys, iters=60):
    f = {k: 1.0 for k in keys}
    for _ in range(iters):
        A = np.vstack([AB[k][0] * f[k] for k in keys]); b = np.concatenate([AB[k][1] for k in keys])
        w, _ = nnls(A, b)
        for k in keys:
            p = AB[k][0] @ w
            f[k] = float(p @ AB[k][1] / max(p @ p, 1e-30))
        # normalisasi: f_D = 1 (skala diserap ke w)
        if "D" in f and f["D"] > 0:
            c = f["D"]; f = {k: v / c for k, v in f.items()}
    A = np.vstack([AB[k][0] * f[k] for k in keys]); b = np.concatenate([AB[k][1] for k in keys])
    w, _ = nnls(A, b)
    return w, f


def main():
    df = inputs.load("BTCUSDT")
    AB = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df)
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols)
        X = model_matrices(df, t_end, span, cols, g["W"], edges); m = np.isfinite(Y)
        AB[k] = (np.stack([X[L][m] for L in TIERS], 1), Y[m])
    w, f = joint_fit(AB, ["D", "W", "M"])
    res = {"w_total": round(float(w.sum()), 3),
           "porsi": {f"{L}x": round(float(x / w.sum() * 100), 1) for L, x in zip(TIERS, w) if x > 1e-4},
           "f": {k: round(v, 3) for k, v in f.items()}}
    for k in "DWM":
        res[f"cocok_{k}"] = score(AB[k][0] @ w * f[k], AB[k][1])
    # uji silang: w dari dua gambar; skala f gambar ke-3 dicari (1 angka), porsi tidak diubah
    for k in "DWM":
        keys = [x for x in "DWM" if x != k]
        w2, f2 = joint_fit(AB, keys) if "D" in keys else joint_fit(AB, keys)
        p = AB[k][0] @ w2; a = float(p @ AB[k][1] / max(p @ p, 1e-30))
        res[f"silang_{k}"] = score(p * a, AB[k][1])
    print(json.dumps(res, indent=1))
    with open(os.path.join(HERE, "joint_result.json"), "w") as fh:
        json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
