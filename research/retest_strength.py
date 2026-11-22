"""Saat pullback sesudah pantulan kembali dekat terendah: apakah ada "tanda kekuatan" yang membedakan retest yang
bertahan dari yang jebol? Aturan ditetapkan sebelum melihat hasil.

Kejadian dan puncak pantulan sama dengan research/after_bounce.py (fase turun, puncak >= 48 jam sebelum akhir jendela
10 hari). Kandidat = setiap jam dalam 30 hari sesudah puncak, sebelum terendah pantulan jebol, yang mencetak terendah
baru sejak puncak DAN berada di separuh bawah pantulan (terendah jam itu <= terendah + 50% x tinggi pantulan).
Tanda (dari research/final_low.py, ambang sama, tidak disetel ulang):
  ekor bawah (wick >= 0,5), puncak volume (volume jam >= 10x atau 24 jam >= 4x normal),
  kerumunan turun (rasio akun -10% dalam 24 jam), open interest turun (-5% dalam 24 jam).
Hasil:
  akhir  = tidak ada terendah lebih rendah dalam 10 hari (pullback selesai di jam itu)
  jebol  = terendah pantulan jebol dalam 10 hari
  menang = masuk long di penutupan jam itu: harga naik 1 ayunan mingguan sebelum turun 1 ayunan, dalam 30 hari
           (definisi sama dengan prinsip 10; masuk acak menang 51%)
    python research/retest_strength.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]

rows = []
for sym in COINS:
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h)
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    v1 = (h.vol / h.vol.rolling(720, min_periods=360).median()).values
    pl = pd.Series(L).rolling(480).min().shift(1).values
    ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
    acc = h.acc_lsr.values; oi = h.oi.values
    last = -10**9
    for i in range(720 + 480, n - 240 - 720 - 720):
        if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168:
            continue
        last = i
        if not C[i] < ma[i]:
            continue
        w = L[i + 1:i + 241]; jlo = i + 1 + int(np.argmin(w)) if w.min() < L[i] else i; lo = min(L[i], w.min())
        a = H[jlo + 1:i + 241]
        if not len(a):
            continue
        jpk = jlo + 1 + int(np.argmax(a)); pk = a.max()
        if jpk > i + 240 - 48:
            continue
        run = np.inf; s = sw[i]
        for k in range(jpk + 1, jpk + 721):
            if L[k] < lo:
                break
            if L[k] >= run:
                continue
            run = L[k]
            if (L[k] - lo) > 0.5 * (pk - lo):
                continue
            rng = H[k] - L[k]; wick = (C[k] - L[k]) / rng if rng > 0 else np.nan
            sc = (int(wick >= .5) + int(v1[k] >= 10 or volr[k] >= 4) + int(acc[k] / acc[k - 24] - 1 <= -.10)
                  + int(oi[k] / oi[k - 24] - 1 <= -.05))
            nxt = L[k + 1:k + 241]
            up, dn = C[k] * (1 + s), C[k] * (1 - s); win = np.nan
            for q in range(k + 1, k + 721):
                if L[q] <= dn: win = 0; break
                if H[q] >= up: win = 1; break
            rows.append(dict(sym=sym[:-4], ev=f"{sym[:-4]}{i}", yr=pd.to_datetime(t[k], unit="s").year, score=sc,
                             wick=wick >= .5, final=nxt.min() >= L[k], broke=nxt.min() < lo, win=win,
                             pos=(L[k] - lo) / (pk - lo), hasacc=acc[k] == acc[k] and acc[k - 24] == acc[k - 24]))
D = pd.DataFrame(rows)
def show(q, nm):
    g = q.groupby("score").agg(n=("final", "size"), ev=("ev", "nunique"), final=("final", "mean"), broke=("broke", "mean"), win=("win", "mean"))
    print(f"{nm}: {len(q)} jam kandidat dari {q.ev.nunique()} kejadian | semua: akhir {100*q.final.mean():.0f}%, jebol {100*q.broke.mean():.0f}%, menang {100*q.win.mean():.0f}%")
    for k, r in g.iterrows():
        print(f"   skor {k}: {int(r.n)} jam ({int(r.ev)} kejadian)  akhir {100*r.final:.0f}%  jebol {100*r.broke:.0f}%  menang {100*r.win:.0f}%")
    hi = q[q.score >= 2]; lo_ = q[q.score <= 1]
    print(f"   skor >=2: {len(hi)} jam, menang {100*hi.win.mean():.0f}%, jebol {100*hi.broke.mean():.0f}% | skor <=1: menang {100*lo_.win.mean():.0f}%, jebol {100*lo_.broke.mean():.0f}%")
    print(f"   ekor bawah saja: ya menang {100*q[q.wick].win.mean():.0f}% ({int(q.wick.sum())}), tidak {100*q[~q.wick].win.mean():.0f}%")
A = D[D.hasacc]
show(A, "8 koin (dengan data rasio akun)")
show(A[A.yr <= 2022], "2020-2022"); show(A[A.yr >= 2023], "2023-2026"); show(A[A.sym.isin(["BTC", "ETH"])], "BTC+ETH")

# Satu masuk per kejadian (jam kandidat PERTAMA di separuh bawah), supaya jam yang berdempetan tidak dihitung berkali-kali.
F = D.groupby("ev").head(1)
for nm, q in (("8 koin", F), ("2020-2022", F[F.yr <= 2022]), ("2023-2026", F[F.yr >= 2023]), ("BTC+ETH", F[F.sym.isin(["BTC", "ETH"])])):
    print(f"masuk pertama per kejadian, {nm}: {int(q.win.sum())}/{int(q.win.notna().sum())} menang = {100*q.win.mean():.0f}%, "
          f"terendah pantulan jebol dalam 10 hari {100*q.broke.mean():.0f}%, kedalaman masuk median {100*q.pos.median():.0f}% dari tinggi pantulan")

# Versi waktu nyata (tanpa melihat ke depan): terendah berjalan sejak kejadian, puncak berjalan sesudah terendah itu.
# Masuk long sekali per kejadian, di penutupan jam pertama ketika (a) pantulan dari terendah berjalan sudah >= 1 ayunan
# mingguan dan (b) harga turun kembali ke separuh bawah pantulan itu. Dicari sampai 40 hari sesudah kejadian.
R = []
for sym in COINS:
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h)
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    pl = pd.Series(L).rolling(480).min().shift(1).values
    ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
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
                up, dn = C[k] * (1 + s), C[k] * (1 - s); win = np.nan
                for q in range(k + 1, k + 721):
                    if L[q] <= dn: win = 0; break
                    if H[q] >= up: win = 1; break
                R.append(dict(sym=sym[:-4], yr=pd.to_datetime(t[k], unit="s").year, win=win,
                              broke=L[k + 1:k + 241].min() < lo, hrs=k - i, bounce=(pk / lo - 1) / s))
                break
            pk = max(pk, H[k])
R = pd.DataFrame(R)
for nm, q in (("8 koin", R), ("2020-2022", R[R.yr <= 2022]), ("2023-2026", R[R.yr >= 2023]), ("BTC+ETH", R[R.sym.isin(["BTC", "ETH"])])):
    print(f"waktu nyata, {nm}: {int(q.win.sum())}/{int(q.win.notna().sum())} menang = {100*q.win.mean():.0f}%, terendah jebol dalam 10 hari "
          f"{100*q.broke.mean():.0f}%, masuk median {q.hrs.median()/24:.1f} hari sesudah kejadian, pantulan sebelum masuk median {q.bounce.median():.1f} ayunan")
