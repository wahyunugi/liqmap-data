"""Cari bobot (leverage x sisi) terbaik dengan NNLS di screenshot A+B, render dengan grid CoinGlass."""
import numpy as np
from scipy.optimize import nnls
from scipy.ndimage import gaussian_filter1d
from scipy.stats import pearsonr
from tune import ctx
from model import run
from compare import model_on_pixels_binned
import evaluate as E

BIN_W = 60.3; BIN_OFF = 80000 % 60.3


def render(snaps, prices, dx):
    s2 = [[(a + dx, b, c) for (a, b, c) in snap] for snap in snaps]
    return model_on_pixels_binned(s2, prices, BIN_W, BIN_OFF)


def basis_stack(p, levs, dx, refs=("A", "B")):
    X, y = [], []
    for name in refs:
        ref, dfa, dfw, prices, val, valid = ctx(name)
        sig = E.SIGMA_USD / ref.dp
        cols = []
        for L in levs:
            for share in (1.0, 0.0):
                q = dict(p, leverages=[L], lev_weights=[1.0], long_share=share)
                _, s = run(dfa, q)
                g = gaussian_filter1d(render(s, prices, dx) * 0.5 / 63.15e6, sig, axis=0)
                cols.append(g[valid])
        X.append(np.stack(cols, 1))
        y.append(gaussian_filter1d(np.where(valid, val, 0.0), sig, axis=0)[valid])
    return X, y


def fit(p, levs=(25, 50, 100), dx=30, verbose=True):
    X, y = basis_stack(p, levs, dx)
    Xa, ya = np.vstack(X), np.concatenate(y)
    w, _ = nnls(Xa, ya)
    names = [f"{L}x-{s}" for L in levs for s in ("long", "short")]
    per = [pearsonr(Xi @ w, yi)[0] for Xi, yi in zip(X, y)]
    if verbose:
        print("bobot (pengali nilai USD):", {n: round(v, 2) for n, v in zip(names, w)})
        print("pearson A=%.3f B=%.3f" % tuple(per))
    return w, per


if __name__ == "__main__":
    from model import PARAMS_V5
    for ep in (1, 9):
        for dx in (20, 30):
            print(f"--- sebar={ep}, geser={dx}$")
            fit(dict(PARAMS_V5, entry_points=ep), dx=dx)
