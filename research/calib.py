"""Kalibrasi sumbu waktu screenshot: cocokkan piksel candle merah ke data high/low Binance."""
import numpy as np, pandas as pd
from PIL import Image


def calibrate(img, data, y1, p1, y2, p2, xl, xr, yt, yb, scales=None):
    a = np.asarray(Image.open(img)).astype(int)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    cm = (R > 150) & (G < 120) & (B < 150)
    cm[:yt] = False; cm[yb:] = False; cm[:, :xl] = False; cm[:, xr:] = False
    ys, xs = np.where(cm)
    y2p = lambda y: p1 + (y - y1) * (p2 - p1) / (y2 - y1)
    cols = np.unique(xs)
    hi = {c: y2p(ys[xs == c].min()) for c in cols}; lo = {c: y2p(ys[xs == c].max()) for c in cols}
    d = pd.read_csv(data)
    approx = (xr - xl) / 288
    scales = scales or np.arange(approx * 0.98, approx * 1.02, 0.002)
    res = []
    end = len(d) - 1
    w = d.iloc[end - 287:end + 1].reset_index(drop=True)
    for sc in scales:
        for off in np.arange(xl - 5 * sc, xl + 5 * sc, 0.25):
            x = np.round(off + sc * np.arange(288)).astype(int)
            err = [max(0, hi[xx] - w.high[i]) + max(0, w.low[i] - lo[xx]) for i, xx in enumerate(x) if xx in hi]
            if len(err) < 40:
                continue
            res.append((np.mean(err), sc, off, len(err)))
    res.sort()
    e, sc, off, n = res[0]
    # posisi candle terakhir data relatif ke tepi kanan plot (dalam satuan candle)
    last_x = off + sc * 287
    return dict(err=e, dx=sc, x0=off, n=n, last_candle_x=last_x, right_edge=xr,
                candles_beyond_data=(xr - last_x) / sc)
