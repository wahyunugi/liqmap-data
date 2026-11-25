"""Short saat harga turun lagi ke separuh bawah pantulan (kondisi yang sama dengan research/retest_strength.py, waktu nyata,
fase turun, 8 koin): apakah menjual di situ dengan target terendah sebelumnya menguntungkan?
  A  stop 0,2% di atas puncak pantulan, target terendah - 0,1%, 10 hari (keluar di penutupan bila belum kena)
  B  sama, 30 hari
  C  stop 1 ayunan mingguan, target terendah, 10 hari
Biaya 0,1% pulang-pergi. Hasil dalam R. Juga: % kasus terendah jebol dalam 10 hari, menurut rasio akun.
    python research/pullback_short.py
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena  # noqa: E402
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]

R = []
for sym in COINS:
    h = arena.load(sym); H = h.high.values; L = h.low.values; C = h.close.values; n = len(h); acc = h.acc_lsr.values
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    pl = pd.Series(L).rolling(480).min().shift(1).values; ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
    last = -10**9
    for i in range(1200, n - 960 - 720):
        if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168: continue
        last = i
        if not C[i] < ma[i]: continue
        s = sw[i]; lo = L[i]; pk = H[i]
        for k in range(i + 1, i + 961):
            if L[k] < lo: lo = L[k]; pk = H[k]; continue
            if pk / lo - 1 >= s and L[k] <= lo + .5 * (pk - lo):
                e = C[k]
                def short(stop, tgt, hz=240):
                    for q in range(k + 1, min(n, k + 1 + hz)):
                        if H[q] >= stop: return -1.0 - 0.001 * e / (stop - e)
                        if L[q] <= tgt: return (e - tgt) / (stop - e) - 0.001 * e / (stop - e)
                    return (e - C[min(n - 1, k + hz)]) / (stop - e) - 0.001 * e / (stop - e)
                R.append(dict(sym=sym[:-4], acc=acc[k], broke=L[k + 1:k + 241].min() < lo,
                              A=short(pk * 1.002, lo * 0.999), B=short(pk * 1.002, lo * 0.999, 720), C=short(e * (1 + s), lo * 0.999)))
                break
            pk = max(pk, H[k])
D = pd.DataFrame(R)
for nm, q in (("semua", D), ("BTC+ETH", D[D.sym.isin(["BTC", "ETH"])]), ("BTC+ETH rasio >= 2", D[D.sym.isin(["BTC", "ETH"]) & (D.acc >= 2)]),
              ("rasio >= 2", D[D.acc >= 2]), ("rasio < 2", D[D.acc < 2])):
    print(f"{nm}: {len(q)} kasus, terendah jebol dalam 10 hari {100 * q.broke.mean():.0f}% | " +
          " | ".join(f"{c}: rata-rata {q[c].mean():+.2f}R, untung {100 * (q[c] > 0).mean():.0f}%" for c in "ABC"))
