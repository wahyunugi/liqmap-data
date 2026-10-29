"""
Satu campuran leverage untuk ketiga screenshot (24 jam, 1 minggu, 1 bulan), dengan skala besaran sendiri per rentang.
Langkah: (1) fit tiap screenshot -> skala s_k; (2) bagi gambar CoinGlass dengan s_k; (3) satu NNLS bersama.
Diuji dua tangga: lengkap (14 tingkat) dan sederhana (6 tingkat). Juga uji silang: porsi dari 2 screenshot, nilai di yang ke-3.
    python research/model2/shared.py
"""
import os, sys, json
import numpy as np
from scipy.optimize import nnls
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cg  # noqa: E402
from fit import TIERS, COL_STEP, cg_matrix, model_matrices  # noqa: E402
sys.path.insert(0, os.path.join(cg.ROOT, "heatmap"))
import inputs  # noqa: E402

SIMPLE = [3, 5, 10, 25, 50, 100]


def score(pred, y):
    return round(float(np.corrcoef(pred, y)[0, 1]), 3), round(float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()), 3)


def main():
    df = inputs.load("BTCUSDT")
    data = {}
    for k, ref in cg.REFS.items():
        g = cg.load(ref); _, t_end, span = cg.align(ref, g, df)
        cols = list(range(0, g["W"], COL_STEP)); Y, edges = cg_matrix(ref, g, cols)
        data[k] = (Y, model_matrices(df, t_end, span, cols, g["W"], edges))
    out = {}
    for name, tiers in (("lengkap", TIERS), ("sederhana", SIMPLE)):
        def A_of(k):
            Y, X = data[k]; m = np.isfinite(Y); return np.stack([X[L][m] for L in tiers], 1), Y[m]
        s = {}
        for k in "DWM":
            A, y = A_of(k); w, _ = nnls(A, y); s[k] = w.sum()
        def joint(keys):
            A = np.vstack([A_of(k)[0] for k in keys]); b = np.concatenate([A_of(k)[1] / s[k] for k in keys])
            w, _ = nnls(A, b); return w / w.sum()
        w = joint("DWM")
        res = {"porsi": {f"{L}x": round(float(x * 100), 1) for L, x in zip(tiers, w) if x > 0.0005},
               "skala": {k: round(float(s[k]), 3) for k in "DWM"}}
        for k in "DWM":
            A, y = A_of(k); res[f"bersama_{k}"] = score(A @ w * s[k], y)
        for k in "DWM":                                   # uji silang
            other = [x for x in "DWM" if x != k]; wo = joint(other)
            A, y = A_of(k); a2, _ = nnls((A @ wo)[:, None], y)
            res[f"silang_{k}"] = score(A @ wo * a2[0], y)
        out[name] = res
        print(name, json.dumps(res), flush=True)
    with open(os.path.join(HERE, "shared_result.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
