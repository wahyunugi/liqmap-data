"""Alat bantu iterasi: skor rata-rata di screenshot A dan B untuk satu set parameter."""
import os, importlib, numpy as np
import evaluate as E
from model import run

_ctx = {}
def ctx(name):
    if name not in _ctx:
        os.environ["REF"] = name
        importlib.reload(E)
        _ctx[name] = (E.REF, E.DF_ALL, E.DF_WIN, E.PRICES, E.VAL, E.VALID)
    return _ctx[name]

def score_on(name, p, render=None):
    from compare import tolerant_score, model_on_pixels_binned, model_on_pixels
    ref, dfa, dfw, prices, val, valid = ctx(name)
    _, snaps = run(dfa, p)
    g = render(snaps, prices, ref, dfw) if render else (
        model_on_pixels_binned(snaps, prices, p["bin_pct"] * dfw.close.iat[-1], p.get("bin_offset", 0))
        if "bin_pct" in p else model_on_pixels(snaps, prices, ref.dp))
    return tolerant_score(g, val, valid, sigma_px=E.SIGMA_USD / ref.dp)[0]

def score_both(p, render=None):
    a = score_on("A", p, render); b = score_on("B", p, render)
    return (a + b) / 2, a, b

def report_on(name, p, render=None):
    from compare import accuracy_report, model_on_pixels_binned, model_on_pixels
    ref, dfa, dfw, prices, val, valid = ctx(name)
    _, snaps = run(dfa, p)
    g = render(snaps, prices, ref, dfw) if render else (
        model_on_pixels_binned(snaps, prices, p["bin_pct"] * dfw.close.iat[-1], p.get("bin_offset", 0))
        if "bin_pct" in p else model_on_pixels(snaps, prices, ref.dp))
    return accuracy_report(g, val, valid, E.SIGMA_USD / ref.dp)

def report_both(p, render=None):
    a = report_on("A", p, render); b = report_on("B", p, render)
    return {k: round((a[k] + b[k]) / 2, 3) for k in a}
