"""Eksperimen 3 (literatur: BIS Working Paper 1087 "Crypto carry"): apakah premi futures atau funding yang TINGGI
memperingatkan kejatuhan harga?

Aturan ditetapkan sebelum melihat hasil. BTC dan ETH, satu baris per hari (00 UTC), sejak 2020.
  funding  = rata-rata Binance/Bybit/OKX (persen per 8 jam), dirata-rata 3 hari sampai kemarin. Nilai "netral" bursa 0,01%.
  premi    = harga futures perpetual Binance dibanding spot Binance (persen), dirata-rata 7 hari.
  hasil    = (a) turun 1 ayunan mingguan normal sebelum naik 1, dalam 14 hari ("jatuh lebih dulu");
             (b) penurunan terdalam dalam 30 hari ke depan mencapai 2 ayunan mingguan normal ("kejatuhan");
             (c) perubahan harga 7 dan 30 hari ke depan.
Hari berurutan tumpang tindih; jumlah minggu berbeda dicetak sebagai ukuran sampel yang jujur.
    python research/exp3_carry.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race, R  # noqa: E402

PER = ((2020, 2021), (2022, 2023), (2024, 2026))


def daily(sym):
    h = load(sym); C = h.close.values; H = h.high.values; L = h.low.values; n = len(h)
    sig = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    prem = (h.close / h.spot_close - 1) * 100; prem7 = prem.rolling(168, min_periods=100).mean().values
    fr = None
    for v in ("binance", "bybit", "okx"):
        f = pd.read_csv(R + f"data/markets/funding/daily/{sym}_{v}.csv").rename(columns={"c": v})
        fr = f if fr is None else fr.merge(f, on="t", how="outer")
    fr["f"] = fr[["binance", "bybit", "okx"]].mean(axis=1); fr = fr.sort_values("t"); fr["f3"] = fr.f.rolling(3).mean().shift(1)
    rows = []
    for i in range(720, n - 720):
        if h.t.values[i] % 86400:
            continue
        s = sig[i]
        if not s == s:
            continue
        up, _ = race(H, L, i, C[i], s, s, 336, True)
        rows.append(dict(sym=sym[:3], t=h.t.values[i], down=np.nan if up != up else 1 - up, crash=float(L[i + 1:i + 721].min() / C[i] - 1 <= -2 * s),
                         f7=C[i + 168] / C[i] - 1, f30=C[i + 720] / C[i] - 1, prem7=prem7[i], p30=C[i] / C[i - 720] - 1))
    d = pd.DataFrame(rows).merge(fr[["t", "f3"]], on="t", how="left"); d["yr"] = pd.to_datetime(d.t, unit="s").dt.year
    return d


def line(name, q):
    if len(q) < 20:
        return f"  {name}: terlalu sedikit ({len(q)} hari)"
    w = q.assign(w=q.t // 604800).groupby("sym").w.nunique().sum()
    return (f"  {name}: {len(q)} hari / {w} minggu | jatuh lebih dulu {100 * q.down.mean():.0f}% | kejatuhan 30 hari {100 * q.crash.mean():.0f}% | "
            f"7 hari median {100 * q.f7.median():+.1f}% | 30 hari median {100 * q.f30.median():+.1f}%, naik {100 * (q.f30 > 0).mean():.0f}%")


if __name__ == "__main__":
    D = pd.concat([daily(s) for s in ("BTCUSDT", "ETHUSDT")], ignore_index=True).dropna(subset=["f3"])
    FB = [(-9, 0, "funding negatif"), (0, 0.005, "0 s.d. 0,005%"), (0.005, 0.015, "0,005 s.d. 0,015% (sekitar netral)"), (0.015, 0.03, "0,015 s.d. 0,03% (tinggi)"), (0.03, 9, "di atas 0,03% (sangat tinggi)")]
    P = D.dropna(subset=["prem7"]); qs = P.prem7.quantile([.1, .5, .9, .97]).values
    PB = [(-9, qs[0], f"premi terendah 10% (< {qs[0]:+.3f}%)"), (qs[0], qs[1], "bawah tengah"), (qs[1], qs[2], "atas tengah"), (qs[2], qs[3], f"tinggi (> {qs[2]:+.3f}%)"), (qs[3], 9, f"tertinggi 3% (> {qs[3]:+.3f}%)")]
    for lab, m in (("SEMUA 2020-2026", D.t > 0),) + tuple((f"{a}-{b}", (D.yr >= a) & (D.yr <= b)) for a, b in PER) + (("BTC", D.sym == "BTC"), ("ETH", D.sym == "ETH")):
        q = D[m]; print(f"\n{lab}"); print(line("semua hari (pembanding)", q))
        for lo, hi, name in FB:
            print(line(name, q[(q.f3 >= lo) & (q.f3 < hi)]))
    print("\nPREMI futures vs spot (rata-rata 7 hari), semua periode"); print(line("semua hari", P))
    for lo, hi, name in PB:
        print(line(name, P[(P.prem7 >= lo) & (P.prem7 < hi)]))
    for a, b in PER:
        q = P[(P.yr >= a) & (P.yr <= b)]; print(f" {a}-{b}:"); print(line("  semua", q)); print(line("  premi tinggi (10% teratas keseluruhan)", q[q.prem7 >= qs[2]]))
    # funding tinggi setelah harga sudah naik banyak vs tidak (apakah funding menambah sesuatu di luar "harga sudah naik")
    print("\nFUNDING TINGGI (> 0,015%) dipisah menurut kenaikan harga 30 hari sebelumnya")
    hi = D[D.f3 >= 0.015]; lo = D[D.f3 < 0.015]
    for nm, cond in (("harga 30 hari terakhir naik > 20%", lambda q: q.p30 > 0.2), ("harga 30 hari terakhir naik 0-20%", lambda q: (q.p30 > 0) & (q.p30 <= 0.2)), ("harga 30 hari terakhir turun", lambda q: q.p30 <= 0)):
        print(line(f"funding tinggi & {nm}", hi[cond(hi)])); print(line(f"funding biasa  & {nm}", lo[cond(lo)]))
    last = D.sort_values("t").groupby("sym").tail(1); print("\nterakhir:", last[["sym", "t", "f3", "prem7"]].round(4).to_string(index=False))
