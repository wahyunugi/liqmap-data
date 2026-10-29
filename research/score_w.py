"""Skor Pearson (satuan CoinGlass) untuk parameter + bobot per (leverage, sisi), grid bin CoinGlass."""
import numpy as np
from tune import ctx
from model import run
from fit_weights import render
from compare import accuracy_report
import evaluate as E

W0 = {(25, "long"): .19, (25, "short"): .15, (50, "long"): .34, (50, "short"): .37,
      (100, "long"): .69, (100, "short"): .69}


def image(name, p, W=W0, dx=20):
    ref, dfa, dfw, prices, val, valid = ctx(name)
    g = 0
    for (L, side), w in W.items():
        q = dict(p, leverages=[L], lev_weights=[1.0], long_share=1.0 if side == "long" else 0.0)
        _, s = run(dfa, q)
        g = g + w * render(s, prices, dx) * 0.5
    return g


def rep(p, W=W0, dx=20, names=("A", "B", "C")):
    out = []
    for n in names:
        ref, dfa, dfw, prices, val, valid = ctx(n)
        out.append(accuracy_report(image(n, p, W, dx), val, valid, E.SIGMA_USD / ref.dp, cbar_max=ref.cbar_max))
    return {k: round(float(np.mean([o[k] for o in out])), 3) for k in out[0]}, [round(o["pearson"], 3) for o in out]
