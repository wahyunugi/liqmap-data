"""Uji: short pada jam pertama harga menembus terendah 20 hari (cermin eksperimen 1), menurut rasio akun Binance.
Menang = turun 1 ayunan mingguan normal sebelum naik 1, dalam 30 hari. Entri berjarak >= 72 jam per koin. 8 koin sejak 2020.
    python research/short_fresh_lows.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
rows = []
for s in COINS:
    h = load(s); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; acc = h.acc_lsr.values; n = len(h)
    sig = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168); pl = pd.Series(L).rolling(480).min().shift(1).values
    last = -10**9
    for i in range(721, n - 1):
        if not sig[i] == sig[i] or not L[i] < pl[i] or i - last < 72:
            continue
        last = i; yl, _ = race(H, L, i, C[i], sig[i], sig[i], 720, True)
        rows.append(dict(sym=s[:-4], t=t[i], acc=acc[i], win=np.nan if yl != yl else 1 - yl))
D = pd.DataFrame(rows).dropna(subset=["win"]); D["yr"] = pd.to_datetime(D.t, unit="s").dt.year
f = lambda q: f"{100 * q.win.mean():.0f}% dari {len(q)}"
for lab, q in (("semua", D), ("2020-21", D[D.yr <= 2021]), ("2022-23", D[(D.yr >= 2022) & (D.yr <= 2023)]), ("2024-26", D[D.yr >= 2024]),
               ("BTC+ETH 2024-26", D[D.sym.isin(["BTC", "ETH"]) & (D.yr >= 2024)])):
    print(lab, f(q))
A = D.dropna(subset=["acc"])
for lab, m in (("rasio < 2", A.acc < 2), ("2-2,5", (A.acc >= 2) & (A.acc < 2.5)), ("2,5-3", (A.acc >= 2.5) & (A.acc < 3)), (">= 3", A.acc >= 3)):
    print("rasio akun", lab, f(A[m]), "| 2024-26", f(A[m & (A.yr >= 2024)]))
