"""Ukuran yang mudah dibaca: berapa garis kuat CoinGlass yang juga muncul di model (harga ±toleransi)."""
import numpy as np
from lines import extract
from evaluate import DF_ALL
from model import run


def recall(p, tol_usd=60, vmin=0.3, min_len=8, top_frac=0.25):
    L = extract()
    strong = L[(L.v >= vmin) & (L.end - L.start >= min_len)]
    _, snaps = run(DF_ALL, p)
    # level model "kuat" = 25% teratas nilai di snapshot itu
    hit = 0
    for _, r in strong.iterrows():
        k = min(int(r.start) + 2, len(snaps) - 1)
        snap = snaps[k]
        if not snap:
            continue
        px = np.array([s[0] for s in snap]); v = np.array([s[1] for s in snap])
        thr = np.quantile(v, 1 - top_frac)
        near = (np.abs(px - r.price) <= tol_usd) & (v >= thr)
        hit += bool(near.any())
    return hit, len(strong)


if __name__ == "__main__":
    from model import PARAMS_V1, PARAMS_V5
    for lab, p in [("v1", PARAMS_V1), ("v5", PARAMS_V5)]:
        h, n = recall(p)
        print(f"{lab}: {h}/{n} garis kuat CoinGlass ditemukan di model (±$60) = {h/n:.0%}")


def precision(p, tol_usd=60, top_frac=0.25, cols=(150, 200, 250)):
    """Dari level model yang kuat, berapa persen yang di CoinGlass juga ada garisnya (±tol)."""
    from evaluate import PRICES, VAL, VALID
    _, snaps = run(DF_ALL, p)
    ok = tot = 0
    for k in cols:
        snap = snaps[k]
        px = np.array([s[0] for s in snap]); v = np.array([s[1] for s in snap])
        vis = (px > PRICES.min()) & (px < PRICES.max())
        px, v = px[vis], v[vis]
        strong = px[v >= np.quantile(v, 1 - top_frac)]
        for x in strong:
            rows = np.abs(PRICES - x) <= tol_usd
            if not VALID[rows, k].any():
                continue
            tot += 1
            ok += bool((VAL[rows, k][VALID[rows, k]] > 0.06).any())
    return ok, tot
