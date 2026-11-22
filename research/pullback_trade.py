"""Beli pullback sesudah pantulan sebagai TRADE: stop di bawah terendah, hasil dalam R (kelipatan risiko).
Masuk = aturan waktu nyata di research/retest_strength.py (penutupan jam pertama ketika pantulan dari terendah berjalan
>= 1 ayunan mingguan dan harga kembali ke separuh bawahnya), fase turun, 8 koin. Ditetapkan sebelum melihat hasil:
  stop  = terendah berjalan - 1%
  target A = puncak pantulan berjalan;  B = 2R;  C = 3R;  batas waktu 30 hari (keluar di penutupan bila belum kena)
  biaya = 0,1% pulang-pergi (taker Binance futures kira-kira 0,05% per sisi), dihitung sebagai bagian dari R.
Bila stop dan target kena di jam yang sama, dihitung stop (anggapan terburuk).
    python research/pullback_trade.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
FEE = 0.001


def run(H, L, C, k, stop, tgt):
    e = C[k]; risk = e - stop
    for q in range(k + 1, min(k + 721, len(C))):
        if L[q] <= stop: return -1 - FEE * e / risk
        if H[q] >= tgt: return (tgt - e) / risk - FEE * e / risk
    return (C[min(k + 720, len(C) - 1)] - e) / risk - FEE * e / risk


R = []
for sym in COINS:
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h)
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    pl = pd.Series(L).rolling(480).min().shift(1).values
    ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
    acc = h.acc_lsr.values
    last = -10**9
    for i in range(720 + 480, n - 960 - 720):
        if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168:
            continue
        last = i
        if not C[i] < ma[i]:
            continue
        s = sw[i]; lo = L[i]; pk = H[i]
        for k in range(i + 1, i + 961):
            if L[k] < lo:
                lo = L[k]; pk = H[k]; continue
            if pk / lo - 1 >= s and L[k] <= lo + 0.5 * (pk - lo):
                stop = lo * 0.99; e = C[k]; r = e - stop
                if r <= 0: break
                R.append(dict(sym=sym[:-4], yr=pd.to_datetime(t[k], unit="s").year, risk_pct=100 * r / e, acc=acc[k],
                              A=run(H, L, C, k, stop, pk), B=run(H, L, C, k, stop, e + 2 * r), C3=run(H, L, C, k, stop, e + 3 * r)))
                break
            pk = max(pk, H[k])
R = pd.DataFrame(R)
for nm, q in (("8 koin", R), ("2020-2022", R[R.yr <= 2022]), ("2023-2026", R[R.yr >= 2023]), ("BTC+ETH", R[R.sym.isin(["BTC", "ETH"])]),
              ("rasio akun < 2", R[R.acc < 2]), ("rasio akun >= 2", R[R.acc >= 2])):
    print(f"{nm}: {len(q)} trade, stop median {q.risk_pct.median():.1f}% dari harga masuk")
    for c, lab in (("A", "target puncak pantulan"), ("B", "target 2R"), ("C3", "target 3R")):
        x = q[c]; print(f"   {lab}: rata-rata {x.mean():+.2f}R, median {x.median():+.2f}R, untung {100*(x > 0).mean():.0f}%, kena stop {100*(x <= -0.99).mean():.0f}%")
