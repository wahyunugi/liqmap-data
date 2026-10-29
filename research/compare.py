"""
Ubah screenshot heatmap CoinGlass menjadi matriks angka, lalu bandingkan dengan model.

Tiap screenshot punya kalibrasi sendiri (REFS):
  - harga : dua titik label sumbu-y  -> USD per piksel
  - waktu : posisi x candle ke-0 dan jarak piksel per candle (dicocokkan ke candle merah di gambar)
  - warna : skala viridis (ungu -> kuning); tiap piksel dipetakan ke nilai 0..1
"""
from dataclasses import dataclass, field
import numpy as np
from PIL import Image
from matplotlib import colormaps
from scipy.stats import spearmanr, pearsonr
from scipy.ndimage import gaussian_filter1d

N = 288


@dataclass
class Ref:
    img: str
    data: str                 # file data Binance yang jendelanya = 288 baris terakhir
    y1: float; p1: float      # titik kalibrasi harga 1 (piksel y, harga)
    y2: float; p2: float      # titik kalibrasi harga 2
    x0: float; dx: float      # x candle ke-0 dan piksel per candle
    top: int; bot: int        # batas atas/bawah area plot (piksel)
    masks: list = field(default_factory=list)   # (x1,x2,y1,y2) area tertutup elemen UI
    cbar_max: float = 63.15e6  # nilai USD di ujung kuning skala warna

    def y_to_price(self, y):
        return self.p1 + (y - self.y1) * (self.p2 - self.p1) / (self.y2 - self.y1)

    @property
    def dp(self):
        return abs((self.p2 - self.p1) / (self.y2 - self.y1))


REFS = {
    # screenshot pertama (28 Okt ±11:03 WIB); ada popup "Legend" yang menutupi sebagian
    "A": Ref("ref/coinglass_m1_24h.jpg", "data/btcusdt_5m.csv",
             95, 84000, 452, 80000, 44.3, (533 - 215) / (209 - 73), 58, 774,
             [(575, 760, 555, 650), (708, 760, 650, 705), (510, 670, 700, 750)]),
    # screenshot kedua, lebih bersih & resolusi lebih tinggi (28 Okt ±11:30 WIB)
    "B": Ref("ref/coinglass_m1_24h_b.jpg", "data/btcusdt_5m_b.csv",
             116, 84000, 763, 78000, 45.6, 2.362, 74, 936,
             [(515, 675, 860, 910)]),
    # jendela sama dengan B, tetapi "Liquidity Threshold" = 1 (warna tidak terpotong) dan resolusi lebih tinggi
    "C": Ref("ref/coinglass_m1_24h_c_thr1.jpg", "data/btcusdt_5m_b.csv",
             155, 84000, 1017, 78000, 60.8, 3.153, 98, 1249,
             [(690, 900, 1145, 1210)], cbar_max=63.15e6),
    # ETH/USDT Binance, 28 Okt ±15:27 WIB, threshold 1 — uji di luar sampel (model v6 TIDAK diubah)
    "E": Ref("ref/coinglass_eth_m1_24h_thr1.jpg", "data/ethusdt_5m.csv",
             85, 2450, 597, 2250, 31.78, 1.7946, 55, 701,
             [(388, 508, 642, 682)], cbar_max=32.82e6),
}
# "Liquidity Threshold" t: warna kuning = t x nilai maksimum skala (63,15 juta). A dan B diambil pada t = 0,85.
REFS["A"].cbar_max = 0.85 * 63.15e6
REFS["B"].cbar_max = 0.85 * 63.15e6


def digitize(ref: Ref):
    a = np.asarray(Image.open(ref.img)).astype(float)
    lut = colormaps["viridis"](np.linspace(0, 1, 256))[:, :3] * 255
    rows = np.arange(ref.top, ref.bot + 1)
    cols = np.round(ref.x0 + ref.dx * np.arange(N)).astype(int)
    px = a[rows][:, cols]                                    # [baris_harga, candle, rgb]
    d = ((px[:, :, None, :] - lut[None, None]) ** 2).sum(-1)
    idx = d.argmin(-1); dist = np.sqrt(d.min(-1))
    val = idx / 255.0
    valid = dist < 40                                       # tolak warna non-viridis (teks, candle)
    for (x1, x2, y1, y2) in ref.masks:
        cm = (cols >= x1) & (cols <= x2); rm = (rows >= y1) & (rows <= y2)
        valid[np.ix_(rm, cm)] = False
    prices = ref.y_to_price(rows)
    return prices, val, valid


def candle_mask(prices, df, pad_usd=25):
    m = np.zeros((len(prices), N), bool)
    for i in range(N):
        lo, hi = df.low.iat[i] - pad_usd, df.high.iat[i] + pad_usd
        m[:, i] = (prices >= lo) & (prices <= hi)
    return m


def model_on_pixels(snaps, prices, dp):
    """Jumlahkan nilai level model ke baris piksel harga yang sama dengan screenshot."""
    edges = np.concatenate([[prices[0] + dp / 2], prices - dp / 2])[::-1]
    g = np.zeros((len(prices), N))
    for k, snap in enumerate(snaps):
        if not snap:
            continue
        p = np.array([s[0] for s in snap]); v = np.array([s[1] for s in snap])
        j = np.searchsorted(edges, p) - 1
        ok = (j >= 0) & (j < len(prices))
        col = np.zeros(len(prices)); np.add.at(col, j[ok], v[ok])
        g[:, k] = col[::-1]
    return g


def model_on_pixels_binned(snaps, prices, bin_usd, offset=0.0):
    """Level dikelompokkan ke bin harga selebar bin_usd; tiap baris piksel di dalam bin
    diberi nilai total bin tersebut (meniru sumbu-y CoinGlass yang berupa ember harga)."""
    g = np.zeros((len(prices), N))
    pb = np.floor((prices - offset) / bin_usd)
    for k, snap in enumerate(snaps):
        if not snap:
            continue
        p = np.array([s[0] for s in snap]); v = np.array([s[1] for s in snap])
        b = np.floor((p - offset) / bin_usd)
        ub, inv = np.unique(b, return_inverse=True)
        lookup = dict(zip(ub, np.bincount(inv, weights=v)))
        g[:, k] = [lookup.get(x, 0.0) for x in pb]
    return g


def tolerant_score(model_g, cg_val, valid, sigma_px=1.5):
    """Korelasi yang toleran selisih harga kecil: kedua gambar dihaluskan arah harga (σ piksel)."""
    cg = np.where(valid, cg_val, 0.0)
    gs = gaussian_filter1d(model_g, sigma_px, axis=0)
    cs = gaussian_filter1d(cg, sigma_px, axis=0)
    m = valid
    return spearmanr(gs[m], cs[m]).correlation, pearsonr(gs[m], cs[m])[0]


def accuracy_report(model_g, cg_val, valid, sigma_px, cbar_max=63.15e6):
    """Metrik dalam satuan yang sama dengan CoinGlass (model diubah ke skala warna 0..1 = 0..cbar_max).
    pearson : kemiripan pola (0..1)
    r2      : porsi variasi CoinGlass yang dijelaskan model TANPA penyesuaian skala apa pun
    """
    g = np.clip(model_g / cbar_max, 0, 1)
    cg = np.where(valid, cg_val, 0.0)
    gs = gaussian_filter1d(g, sigma_px, axis=0)
    cs = gaussian_filter1d(cg, sigma_px, axis=0)
    m = valid
    pe = pearsonr(gs[m], cs[m])[0]
    sp = spearmanr(gs[m], cs[m]).correlation
    r2 = 1 - ((gs[m] - cs[m]) ** 2).sum() / ((cs[m] - cs[m].mean()) ** 2).sum()
    return dict(pearson=pe, spearman=sp, r2=r2)


def model_on_pixels_split(snaps, prices, bin_usd, offset=0.0):
    """Seperti model_on_pixels_binned, tetapi nilai tiap level dibagi ke DUA bin terdekat
    secara proporsional jaraknya (interpolasi linear), bukan dimasukkan ke satu bin saja."""
    g = np.zeros((len(prices), N))
    pb = np.floor((prices - offset) / bin_usd)
    for k, snap in enumerate(snaps):
        if not snap:
            continue
        p = np.array([s[0] for s in snap]); v = np.array([s[1] for s in snap])
        x = (p - offset) / bin_usd - 0.5                    # posisi relatif terhadap pusat bin
        b0 = np.floor(x); f = x - b0
        keys = np.concatenate([b0, b0 + 1]); vals = np.concatenate([v * (1 - f), v * f])
        ub, inv = np.unique(keys, return_inverse=True)
        lookup = dict(zip(ub, np.bincount(inv, weights=vals)))
        g[:, k] = [lookup.get(x_, 0.0) for x_ in pb]
    return g


def render_coinglass(snaps, prices, p, last_price):
    """Render level model persis seperti tampilan CoinGlass (temuan iterasi 6):
    - harga dikelompokkan ke kotak selebar bin_pct x harga (BTC: ±$60,3)
    - grid kotak berjangkar di angka bulat (kelipatan 10^k terdekat, BTC: 80.000)
    - seluruh level digeser shift_pct ke atas (konvensi gambar CoinGlass)"""
    w = p["bin_pct"] * last_price
    k = 10 ** int(np.floor(np.log10(last_price)))
    anchor = round(last_price / k) * k
    off = anchor % w
    dx = p.get("shift_pct", 0.0) * last_price
    s2 = [[(a + dx, b, c) for (a, b, c) in snap] for snap in snaps]
    return model_on_pixels_binned(s2, prices, w, off)
