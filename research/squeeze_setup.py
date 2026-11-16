"""Uji "bahan bakar short squeeze": apakah (a) funding negatif, (b) OI naik saat harga datar/turun, (c) rasio akun rendah
diikuti kenaikan harga? BTC dan ETH, satu baris per hari (00 UTC), sejak 2020.
  funding = rata-rata Binance/Bybit/OKX (persen per 8 jam), dirata-rata 3 hari; "jelas negatif" = di bawah -0,005%
  OI naik saat harga tidak naik = OI 7 hari > +5% dan harga 7 hari <= 0
  hasil = perubahan harga 7 hari ke depan, dan apakah +1 ayunan mingguan normal tercapai sebelum -1 dalam 14 hari
Hari berurutan saling tumpang tindih, jadi jumlah minggu berbeda dicetak sebagai ukuran sampel yang jujur.
    python research/squeeze_setup.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race, R  # noqa: E402


def daily(sym):
    h = load(sym); C = h.close.values; H = h.high.values; L = h.low.values
    sig = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    fr = None
    for v in ("binance", "bybit", "okx"):
        f = pd.read_csv(R + f"data/markets/funding/daily/{sym}_{v}.csv").rename(columns={"c": v})
        fr = f if fr is None else fr.merge(f, on="t", how="outer")
    fr["f"] = fr[["binance", "bybit", "okx"]].mean(axis=1); fr = fr.sort_values("t"); fr["f3"] = fr.f.rolling(3).mean().shift(1)   # sampai kemarin
    rows = []
    for i in range(720, len(h) - 336):
        if h.t.values[i] % 86400:
            continue
        s = sig[i]
        if not s == s:
            continue
        y, _ = race(H, L, i, C[i], s, s, 336, True)
        rows.append(dict(sym=sym[:3], t=h.t.values[i], f7=C[i + 168] / C[i] - 1, y=y, p7=C[i] / C[i - 168] - 1,
                         oi7=h.oi.values[i] / h.oi.values[i - 168] - 1, acc=h.acc_lsr.values[i]))
    d = pd.DataFrame(rows).merge(fr[["t", "f3"]], on="t", how="left")
    d["yr"] = pd.to_datetime(d.t, unit="s").dt.year
    return d


def line(name, q):
    if len(q) < 15:
        return f"  {name}: terlalu sedikit ({len(q)} hari)"
    return (f"  {name}: {len(q)} hari / {q.assign(w=q.t // 604800).groupby('sym').w.nunique().sum()} minggu | 7 hari ke depan median {100 * q.f7.median():+.1f}%, "
            f"naik {100 * (q.f7 > 0).mean():.0f}% | naik 1 ayunan lebih dulu {100 * q.y.mean():.0f}%")


if __name__ == "__main__":
    D = pd.concat([daily(s) for s in ("BTCUSDT", "ETHUSDT")], ignore_index=True).dropna(subset=["f3", "oi7"])
    neg = D.f3 < -0.005; build = (D.oi7 > 0.05) & (D.p7 <= 0); low = D.acc < 1.5
    for lab, m in (("SEMUA", D.t > 0), ("2020-2022", D.yr <= 2022), ("2023-2024", (D.yr >= 2023) & (D.yr <= 2024)), ("2025-2026", D.yr >= 2025)):
        q = D[m]; print(f"\n{lab}")
        print(line("semua hari (pembanding)", q))
        print(line("funding jelas negatif (< -0,005%)", q[neg[m]]))
        print(line("funding positif (> +0,005%)", q[q.f3 > 0.005]))
        print(line("OI naik > 5% saat harga tidak naik", q[build[m]]))
        print(line("rasio akun < 1,5", q[low[m]]))
        print(line("rasio akun > 2,5", q[q.acc > 2.5]))
        print(line("funding negatif DAN OI naik saat harga tidak naik", q[(neg & build)[m]]))
        print(line("funding negatif DAN rasio akun < 2", q[(neg & (D.acc < 2))[m]]))
        print(line("funding negatif DAN rasio akun >= 2,5", q[(neg & (D.acc >= 2.5))[m]]))
    last = D.sort_values("t").groupby("sym").tail(1)
    print("\nterakhir:", last[["sym", "t", "f3", "oi7", "p7", "acc"]].round(4).to_string(index=False))
