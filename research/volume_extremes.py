"""Seberapa sering volume futures 24 jam melewati 2,5x normalnya, berapa tertingginya, dan apa yang terjadi sesudahnya?
volr = volume 24 jam terakhir / median volume 24 jam selama 720 jam sebelumnya (sama dengan research/exp5_flow.py dan
panel "Big-move risk"). Dibaca sekali sehari pukul 00 UTC (sama dengan eksperimen 5). Gerakan besar = definisi
research/big_moves.py. 8 koin, Binance futures, sejak 2020.
    python research/volume_extremes.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]


def frame(sym):
    h = load(sym); C = h.close.values; n = len(h)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    s6 = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(6)
    r6 = np.full(n, np.nan); r6[:n - 6] = C[6:] / C[:n - 6] - 1
    big = np.abs(r6) >= 3 * s6
    rows = []
    for i in range(1500, n):
        if h.t.values[i] % 86400 or not volr[i - 1] == volr[i - 1]:
            continue
        nx = np.nonzero(big[i:i + 24])[0] if i + 30 < n else []
        rows.append(dict(sym=sym[:-4], t=h.t.values[i], volr=volr[i - 1], p24=C[i] / C[i - 24] - 1,
                         y=np.nan if i + 30 >= n else int(len(nx) > 0), up=np.sign(r6[i + nx[0]]) if len(nx) else np.nan,
                         f1=C[i + 24] / C[i] - 1 if i + 24 < n else np.nan, f7=C[i + 168] / C[i] - 1 if i + 168 < n else np.nan))
    # tertinggi per jam (bukan hanya 00 UTC)
    j = int(np.nanargmax(volr)); peak = (volr[j], h.t.values[j], C[j] / C[max(0, j - 24)] - 1)
    return pd.DataFrame(rows), peak


if __name__ == "__main__":
    out = [frame(s) for s in COINS]; D = pd.concat([o[0] for o in out], ignore_index=True); D["yr"] = pd.to_datetime(D.t, unit="s").dt.year
    print(f"{len(D)} hari-koin ({pd.to_datetime(D.t.min(), unit='s').date()} s.d. {pd.to_datetime(D.t.max(), unit='s').date()}); median volr {D.volr.median():.2f}")
    cuts = [0, 1, 1.3, 1.8, 2.2, 2.6, 3, 4, 99]; lab = ["<1", "1-1.3", "1.3-1.8", "1.8-2.2", "2.2-2.6", "2.6-3", "3-4", ">4"]
    D["b"] = pd.cut(D.volr, cuts, labels=lab)
    Q = D.dropna(subset=["y"])
    for nm, q in (("8 koin", Q), ("BTC", Q[Q.sym == "BTC"]), ("ETH", Q[Q.sym == "ETH"])):
        g = q.groupby("b", observed=False).agg(n=("y", "size"), big=("y", "mean"), f7=("f7", "median"))
        print(f"\n{nm}: share of days, chance of a big move starting in 24h, median 7-day change")
        for k, r in g.iterrows():
            print(f"  {k:>8}: {100 * r.n / len(q):5.1f}% of days ({int(r.n)}) | big move {100 * r.big:5.1f}% | 7 days {100 * r.f7:+.1f}%")
    H = Q[Q.volr >= 2.5]
    print(f"\nvolr >= 2.5: {len(H)} hari-koin ({100 * len(H) / len(Q):.1f}%); BTC {int((H.sym == 'BTC').sum())} hari, ETH {int((H.sym == 'ETH').sum())} hari")
    print(f"  arah gerakan besar berikutnya: naik {100 * (H.up > 0).sum() / H.up.notna().sum():.0f}% dari {int(H.up.notna().sum())}")
    print(f"  harga sudah turun 24 jam sebelumnya: {100 * (H.p24 < 0).mean():.0f}%; 7 hari kemudian naik {100 * (H.f7 > 0).mean():.0f}%, median {100 * H.f7.median():+.1f}%")
    for nm, m in (("setelah harga turun", H.p24 < 0), ("setelah harga naik", H.p24 >= 0)):
        q = H[m]; print(f"   {nm}: {len(q)} | big move {100 * q.y.mean():.0f}% | next big move up {100 * (q.up > 0).sum() / max(q.up.notna().sum(), 1):.0f}% of {int(q.up.notna().sum())} | 7 hari naik {100 * (q.f7 > 0).mean():.0f}%, median {100 * q.f7.median():+.1f}%")
    for a, b in ((2020, 2021), (2022, 2023), (2024, 2026)):
        q = H[(H.yr >= a) & (H.yr <= b)]; print(f"   {a}-{b}: {len(q)} hari, big move {100 * q.y.mean():.0f}%")
    print("\nTERTINGGI (per jam) per koin: volr, waktu, perubahan harga 24 jam sebelumnya")
    for s, (_, pk) in zip(COINS, out):
        print(f"  {s[:-4]}: {pk[0]:.1f}x pada {pd.to_datetime(pk[1], unit='s')}, harga 24 jam {100 * pk[2]:+.1f}%")
    top = D.sort_values("volr", ascending=False).head(12)
    print("\n12 bacaan harian tertinggi (semua koin):")
    for r in top.itertuples():
        print(f"  {r.sym} {pd.to_datetime(r.t, unit='s').date()}: {r.volr:.1f}x, harga 24 jam {100 * r.p24:+.1f}%, gerakan besar 24 jam {'ya' if r.y == 1 else 'tidak' if r.y == 0 else '-'}, 7 hari {100 * r.f7:+.1f}%")
    for s in ("BTC", "ETH"):
        q = D[D.sym == s]; w = q[q.volr >= 2.5].copy(); w["ep"] = (w.t.diff().fillna(1e9) > 3 * 86400).cumsum()
        print(f"\n{s}: hari dengan volr >= 2,5: {len(w)} dari {len(q)} ({100 * len(w) / len(q):.1f}%), dalam {w.ep.nunique()} episode terpisah; tertinggi harian {q.volr.max():.1f}x ({pd.to_datetime(q.t[q.volr.idxmax()], unit='s').date()})")
        print("   episode:", ", ".join(f"{pd.to_datetime(g.t.min(), unit='s').date()} ({g.volr.max():.1f}x)" for _, g in w.groupby("ep")))
