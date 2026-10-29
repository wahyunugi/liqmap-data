"""Gambar perbandingan akhir: CoinGlass vs model v6, untuk BTC (screenshot C) dan ETH (uji luar sampel)."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "heatmap"))
import os, importlib
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from PIL import Image
from model import PARAMS_V6

fig, ax = plt.subplots(2, 2, figsize=(15, 13))
for row, name in enumerate(["C", "E"]):
    os.environ["REF"] = name
    import evaluate as E
    importlib.reload(E)
    ref = E.REF
    e = [0, 288, E.PRICES[-1], E.PRICES[0]]
    x0 = int(round(ref.x0)); x1 = int(round(ref.x0 + ref.dx * 288))
    ax[row, 0].imshow(np.asarray(Image.open(ref.img))[ref.top:ref.bot + 1, x0:x1], aspect="auto", extent=e)
    coin = "BTC" if name == "C" else "ETH"
    ax[row, 0].set_title(f"CoinGlass — Binance {coin}/USDT, Model 1, 24 jam")
    g = np.clip(E.model_image(PARAMS_V6) / ref.cbar_max, 0, 1)
    r1 = E.report(PARAMS_V6, E.SIGMA_PCT); r2 = E.report(PARAMS_V6, E.BIN_PCT_TOL)
    ax[row, 1].imshow(g, aspect="auto", cmap="viridis", vmin=0, vmax=1, extent=e)
    ax[row, 1].plot(np.arange(288) + 0.5, E.DF_WIN.close.values, color="white", lw=0.6)
    tag = "dicocokkan" if name == "C" else "UJI LUAR SAMPEL, model tidak diubah"
    ax[row, 1].set_title(f"Model v6 ({tag})\nkorelasi pola: {r1['pearson']:.2f} ketat | {r2['pearson']:.2f} per kotak harga")
    for a in ax[row]:
        a.set_xlabel("candle 5 menit (jendela 24 jam)")
    ax[row, 0].set_ylabel(f"harga {coin} (USD)")
fig.tight_layout(); fig.savefig("perbandingan_final.png", dpi=80)
print("ok")
