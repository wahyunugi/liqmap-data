"""
Baca screenshot heatmap CoinGlass (rentang 24 jam / 1 minggu / 1 bulan) menjadi angka USD per piksel,
dan cocokkan sumbu waktunya dengan data candle repo.

Kalibrasi per screenshot (REFS):
  - harga : baris piksel teratas/terbawah area plot = label harga teratas/terbawah di sumbu kanan
  - warna : viridis; kuning = nilai di ujung skala warna (Liquidity Threshold = 1)
  - waktu : dicari otomatis — candle merah/hijau di gambar dicocokkan dengan high/low candle 5 menit repo
"""
import os, sys
from dataclasses import dataclass
import numpy as np
from PIL import Image
from matplotlib import colormaps
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "heatmap"))
import inputs  # noqa: E402

LUT = colormaps["viridis"](np.linspace(0, 1, 256))[:, :3] * 255
TREE = cKDTree(LUT)


@dataclass
class Ref:
    img: str
    p_top: float          # label harga teratas (= baris teratas area plot)
    p_bot: float          # label harga terbawah
    cbar: float           # USD di ujung kuning skala warna
    span_h: float         # perkiraan rentang waktu (jam), dipakai sebagai titik awal pencarian
    sym: str = "BTCUSDT"


REFS = {
    "D": Ref("ref/coinglass_24h_thr1_20261029.png", 88799, 73116, 18.52e6, 24),
    "W": Ref("ref/coinglass_1w_thr1_20261029.png", 89417, 72606, 87.75e6, 24 * 7),
    "M": Ref("ref/coinglass_1m_thr1_20261029.png", 111285, 58265, 27.18e6, 24 * 31),
}


def _longest_run(mask):
    best, cur, start, bs = 0, 0, 0, 0
    for i, m in enumerate(mask):
        if m:
            if cur == 0: start = i
            cur += 1
            if cur > best: best, bs = cur, start
        else:
            cur = 0
    return bs, bs + best - 1


def load(ref):
    a = np.asarray(Image.open(os.path.join(os.path.dirname(HERE), ref.img)).convert("RGB")).astype(float)
    dist, idx = TREE.query(a.reshape(-1, 3))
    dist = dist.reshape(a.shape[:2]); idx = idx.reshape(a.shape[:2])
    vir = dist < 30
    x0, x1 = _longest_run(vir.mean(0) > 0.5)
    y0, y1 = _longest_run(vir[:, x0:x1 + 1].mean(1) > 0.5)
    P = a[y0:y1 + 1, x0:x1 + 1]
    val = idx[y0:y1 + 1, x0:x1 + 1] / 255.0 * ref.cbar      # USD per piksel
    valid = dist[y0:y1 + 1, x0:x1 + 1] < 40
    r, g, b = P[..., 0], P[..., 1], P[..., 2]
    red = (r > 180) & (g < 110) & (b < 120)
    green = (r < 60) & (g > 150) & (b > 90) & (b < 170)
    candle = (red | green) & ~valid          # warna candle, bukan warna viridis heatmap
    rows = np.arange(y0, y1 + 1)
    price = ref.p_top + (rows - y0) * (ref.p_bot - ref.p_top) / (y1 - y0)
    return dict(val=val, valid=valid & ~candle, candle=candle, price=price, x0=x0, x1=x1, y0=y0, y1=y1, W=x1 - x0 + 1)


def candle_extent(g):
    """Per kolom: harga tertinggi dan terendah piksel candle (NaN bila tidak ada candle)."""
    W = g["W"]; hi = np.full(W, np.nan); lo = np.full(W, np.nan)
    for x in range(W):
        ys = np.nonzero(g["candle"][:, x])[0]
        if len(ys):
            hi[x] = g["price"][ys.min()]; lo[x] = g["price"][ys.max()]
    return hi, lo


def align(ref, g, df):
    """Cari waktu akhir (detik UTC) dan rentang (detik) plot yang paling cocok dengan candle repo."""
    hi, lo = candle_extent(g)
    W = g["W"]; ok = ~np.isnan(hi)
    t5, h5, l5 = df.t.values, df.high.values, df.low.values
    best = None
    t_end_guess = int(t5[-1]) + 300
    for span in np.arange(ref.span_h * 0.85, ref.span_h * 1.15 + 1e-9, ref.span_h * 0.005) * 3600:
        for t_end in range(t_end_guess - 3600, t_end_guess + 301, 300):
            edges = t_end - span + span * np.arange(W + 1) / W
            i0 = np.searchsorted(t5, edges[:-1]); i1 = np.searchsorted(t5, edges[1:])
            mh = np.full(W, np.nan); ml = np.full(W, np.nan)
            for x in np.nonzero(ok)[0]:
                a, b = i0[x], max(i1[x], i0[x] + 1)
                if a < len(t5):
                    mh[x] = h5[a:b].max(); ml[x] = l5[a:b].min()
            m = ok & ~np.isnan(mh)
            if m.sum() < W * 0.15:
                continue
            err = np.median(np.abs(np.r_[hi[m] - mh[m], lo[m] - ml[m]]))
            if best is None or err < best[0]:
                best = (err, int(t_end), float(span))
    return best


if __name__ == "__main__":
    df = inputs.load("BTCUSDT")
    for k, ref in REFS.items():
        g = load(ref)
        dp = (ref.p_top - ref.p_bot) / (g["y1"] - g["y0"])
        err, t_end, span = align(ref, g, df)
        import datetime as dt
        print(f"{k}: plot x {g['x0']}-{g['x1']} y {g['y0']}-{g['y1']} | ${dp:.1f}/px | "
              f"waktu akhir {dt.datetime.utcfromtimestamp(t_end) + dt.timedelta(hours=7):%Y-%m-%d %H:%M} WIB, "
              f"rentang {span / 3600:.1f} jam | selisih median candle ${err:.0f}")
