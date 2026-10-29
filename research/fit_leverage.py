"""
Iterasi 2: daripada menebak sebaran leverage, biarkan data CoinGlass yang "memberi tahu".

Ide: tiap kombinasi (leverage, sisi long/short) menghasilkan satu gambar heatmap G_k.
Karena semua langkah model bersifat aditif, heatmap total = Σ w_k · G_k.
Bobot w_k (≥ 0) dicari dengan non-negative least squares agar paling mirip CoinGlass.
Bobot yang keluar besar = leverage yang kemungkinan dipakai CoinGlass.
"""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "heatmap"))
import itertools
import numpy as np
from scipy.optimize import nnls
from scipy.stats import spearmanr, pearsonr
from model import run, PARAMS_V1
from compare import model_on_pixels
from evaluate import DF_ALL, PRICES, VAL, VALID, REF

LEVS = [5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 100, 125]


def basis(base):
    cols, names = [], []
    for L in LEVS:
        for side, share in (("long", 1.0), ("short", 0.0)):
            p = dict(base, leverages=[L], lev_weights=[1.0], long_share=share)
            _, snaps = run(DF_ALL, p)
            cols.append(model_on_pixels(snaps, PRICES, REF.dp))
            names.append(f"{L}x-{side}")
    return cols, names


def fit(base, label, verbose=True):
    cols, names = basis(base)
    m = VALID
    X = np.stack([c[m] for c in cols], 1)
    scale = X.max(0); scale[scale == 0] = 1
    Xs = X / scale
    y = VAL[m]
    w, _ = nnls(Xs, y)
    pred = Xs @ w
    r = pearsonr(pred, y)[0]; rho = spearmanr(pred, y).correlation
    if verbose:
        print(f"[{label}] pearson={r:.3f} spearman={rho:.3f}")
        tot = w.sum() or 1
        for n, wi in sorted(zip(names, w), key=lambda t: -t[1])[:8]:
            if wi > 0:
                print(f"     {n:>10}: {wi/tot:5.1%}")
    return r, rho, dict(zip(names, w / (w.sum() or 1)))


if __name__ == "__main__":
    variants = {
        "v1 struktur (typical, shift1, mmr0.4%, close proporsional)": dict(PARAMS_V1),
        "shift0": dict(PARAMS_V1, oi_shift=0),
        "entry=close": dict(PARAMS_V1, entry="close"),
        "mmr=0": dict(PARAMS_V1, mmr=0.0),
        "tanpa pengurangan saat OI turun": dict(PARAMS_V1, close_rule="none"),
    }
    for k, v in variants.items():
        fit(v, k)
