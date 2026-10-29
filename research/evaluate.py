"""
Beri skor model terhadap screenshot CoinGlass.
Pilih screenshot dengan variabel lingkungan REF (default B):  REF=A python evaluate.py
"""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "heatmap"))
import os
import numpy as np, pandas as pd
from model import run, PARAMS_V1, PARAMS_V5, PARAMS_V6
from compare import (REFS, digitize, candle_mask, model_on_pixels, model_on_pixels_binned,
                     render_coinglass, tolerant_score, accuracy_report, N)

SIGMA_PCT = 17.0 / 81000                         # toleransi ketat ≈ 0,021% harga (BTC: ±$17)
BIN_PCT_TOL = 60.0 / 81000                       # toleransi selebar 1 kotak CoinGlass ≈ 0,074% (BTC: ±$60)
REF_NAME = os.environ.get("REF", "B")
REF = REFS[REF_NAME]
DF_ALL = pd.read_csv(REF.data)
DF_WIN = DF_ALL.iloc[-N:].reset_index(drop=True)
PRICES, VAL, VALID = digitize(REF)
SIGMA_USD = SIGMA_PCT * DF_WIN["close"].iat[-1]
VALID = VALID & ~candle_mask(PRICES, DF_WIN, pad_usd=25 / 81000 * DF_WIN["close"].iat[-1])  # candle & UI tak dinilai


def model_image(p, snaps=None):
    if snaps is None:
        _, snaps = run(DF_ALL, p)
    if p.get("render") == "coinglass":
        return render_coinglass(snaps, PRICES, p, DF_WIN["close"].iat[-1])
    if "bin_pct" in p:
        b = p["bin_pct"] * DF_WIN["close"].iat[-1]
        return model_on_pixels_binned(snaps, PRICES, b, offset=p.get("bin_offset", 0.0))
    return model_on_pixels(snaps, PRICES, REF.dp)


def report(p, tol_pct=SIGMA_PCT):
    """Akurasi dalam satuan CoinGlass: pearson (pola), r2 (besaran, tanpa penyesuaian skala)."""
    sig = tol_pct * DF_WIN["close"].iat[-1] / REF.dp
    return accuracy_report(model_image(p), VAL, VALID, sig, cbar_max=REF.cbar_max)


if __name__ == "__main__":
    print(f"screenshot {REF_NAME}: {REF.img}")
    for lab, p in [("v1 (tebakan awal)", PARAMS_V1), ("v5", PARAMS_V5), ("v6", PARAMS_V6)]:
        for nm, t in (("ketat 0,021%", SIGMA_PCT), ("1 kotak 0,074%", BIN_PCT_TOL)):
            r = report(p, t)
            print(f"  {lab:18s} toleransi {nm:14s}: pola (pearson) = {r['pearson']:.3f} | "
                  f"besaran (R²) = {r['r2']:.3f} | peringkat = {r['spearman']:.3f}")
