"""
Model v6 cepat untuk sejarah panjang (bertahun-tahun data 5 menit).

Aturannya SAMA dengan heatmap/model.py (PARAMS_V6) dan snapshot.py; yang berbeda hanya cara menyimpan level:
  - level disimpan terurut menurut harga (SortedList), jadi "level yang tersentuh candle" diambil per rentang harga
    tanpa memeriksa semua level satu per satu;
  - pengurangan proporsional saat open interest turun dicatat sebagai satu faktor skala bersama (bukan mengalikan
    setiap level), lalu nilai asli = nilai tersimpan x faktor skala.
Jendela (window) bisa diatur: 288 candle = 24 jam (model v6 yang dicocokkan ke CoinGlass); 2016 = 7 hari; 8640 = 30 hari.

Snapshot di candle i = keadaan saat candle i ditutup, seperti snapshot.py dijalankan pada waktu itu:
perubahan OI candle i (= OI[i+1] - OI[i]) belum ikut.
Diuji terhadap model.py / snapshot.py dan site/model.js: lihat heatmap/check_fastmodel.py.
"""
from collections import deque
import math
import numpy as np
from sortedcontainers import SortedList

LEVS = (25.0, 50.0, 100.0)
WEIGHTS = tuple(l / 175.0 for l in LEVS)
MMR = 0.0001


def bins_for(price):
    """Sama dengan snapshot.bins_for: lebar 0,0744% harga, berjangkar angka bulat, geser +0,025%."""
    w = 0.000744 * price
    k = 10 ** int(math.floor(math.log10(price)))
    off = (round(price / k) * k) % w
    return w, off, 0.00025 * price


def simulate(t, o, h, l, c, oi, window, snap_at, on_snap):
    """Jalankan model pada deret candle 5 menit.
    oi[i] = open interest di AWAL candle i (seperti model.py). snap_at: himpunan indeks candle tempat snapshot diambil.
    on_snap(i, prices: np.ndarray, usd: np.ndarray, side: np.ndarray[int8]) dipanggil di tiap indeks snap_at."""
    n = len(t)
    sl = SortedList()                 # (harga, id)
    raw, sid, born, pr = [], [], [], []   # per id: nilai/skala saat dibuat, sisi (0 long, 1 short), candle lahir, harga
    alive = []
    q = deque()                       # id menurut urutan lahir (untuk batas jendela)
    S = 1.0                           # faktor skala bersama
    for i in range(n):
        lo, hi = l[i], h[i]
        # 1) sapu level yang tersentuh candle ini (lo <= harga <= hi)
        if sl:
            hit = list(sl.irange((lo, -1), (hi, math.inf)))
            for key in hit:
                sl.remove(key)
                alive[key[1]] = False
        # 2) buang level yang lahir di luar jendela (born <= i - window)
        while q and born[q[0]] <= i - window:
            j = q.popleft()
            if alive[j]:
                sl.remove((pr[j], j))
                alive[j] = False
        # 3) snapshot (perubahan OI candle i belum ikut)
        if i in snap_at:
            m = len(sl)
            px = np.empty(m); us = np.empty(m); sd = np.empty(m, dtype=np.int8)
            for k, (p, j) in enumerate(sl):
                px[k] = p; us[k] = raw[j] * S; sd[k] = sid[j]
            on_snap(i, px, us, sd)
        # 4) perubahan OI candle i
        if i + 1 < n:
            a, b = oi[i + 1], oi[i]
            dv = 0.0 if (a is None or b is None or a != a or b != b) else a - b
        else:
            dv = 0.0
        e = (o[i] + h[i] + l[i] + c[i]) / 4
        if dv > 0:
            for lev, w in zip(LEVS, WEIGHTS):
                val = dv * e * w
                for side, lp in ((0, e * (1 - 1 / lev + MMR)), (1, e * (1 + 1 / lev - MMR))):
                    if lo <= lp <= hi:
                        continue
                    j = len(raw)
                    raw.append(val / S); sid.append(side); born.append(i); alive.append(True); pr.append(lp)
                    sl.add((lp, j)); q.append(j)
        elif dv < 0 and sl:
            tot = oi[i] * e
            frac = max(0.0, 1 + dv * e / max(tot, 1e-9))
            if frac == 0.0:                      # semua level jadi nol: kosongkan saja
                for (p, j) in sl:
                    alive[j] = False
                sl.clear()
            else:
                S *= frac
                if S < 1e-150:                   # normalisasi ulang agar angka tidak terlalu kecil
                    for (p, j) in sl:
                        raw[j] *= S
                    S = 1.0
    return None


def aggregate(px, us, sd, w, off, dx):
    """Jumlahkan ke kotak harga seperti snapshot.aggregate. Hasil: (bins, long_usd, short_usd), bins terurut."""
    if len(px) == 0:
        return np.empty(0, dtype=np.int64), np.empty(0), np.empty(0)
    b = np.floor((px + dx - off) / w).astype(np.int64)
    keys = b * 2 + sd
    uk, inv = np.unique(keys, return_inverse=True)
    tot = np.bincount(inv, weights=us)
    bins = uk // 2; side = uk % 2
    ub, inv2 = np.unique(bins, return_inverse=True)
    lng = np.bincount(inv2, weights=np.where(side == 0, tot, 0.0), minlength=len(ub))
    sht = np.bincount(inv2, weights=np.where(side == 1, tot, 0.0), minlength=len(ub))
    return ub, lng, sht
