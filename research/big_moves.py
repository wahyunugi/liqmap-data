"""Uji arah "gerakan besar": ke mana harga bergerak saat gerakan besar terjadi, menurut (a) rasio akun long/short Binance
dan (b) sisi tumpukan likuidasi yang lebih besar di peta likuidasi (model v6). Dasar panel "Big-move risk" di website.

Definisi (tetap, tidak disetel ke hasil):
  gerakan besar = perubahan harga penutupan dalam 6 jam ke depan >= 3 x ayunan 6 jam normal
                  (ayunan normal = simpangan baku perubahan per jam selama 720 jam terakhir x akar 6);
                  kejadian berjarak minimal 24 jam per koin; rasio dan peta dibaca pada jam SEBELUM gerakan dimulai.
  rasio akun    = acc_lsr (akun long per akun short, semua akun Binance), tersedia sejak Sep 2020 (BTC) / Des 2021 (alt).
  tumpukan      = USD level likuidasi yang belum tersentuh dalam 2% dari harga: short di atas (S2) vs long di bawah (L2),
                  dari research/results/magnet_<SIMBOL>.csv (research/magnet_test.py), hanya BTC dan ETH.

    python research/big_moves.py        # butuh data/derived/hourly, research/data/hourly, research/results/magnet_*.csv
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, R  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
H, K, GAP = 6, 3.0, 24


def events(sym, need_acc=True):
    h = load(sym); C = h.close.values; acc = h.acc_lsr.values; t = h.t.values
    s1 = pd.Series(C).pct_change().rolling(720).std().values
    rows = []; last = -10**9
    for i in range(721, len(C) - H):
        s = s1[i] * np.sqrt(H)
        if not s == s or (need_acc and not acc[i] == acc[i]) or i - last < GAP:
            continue
        r = C[i + H] / C[i] - 1
        if abs(r) >= K * s:
            rows.append((sym[:-4], t[i], acc[i], 1 if r > 0 else 0, 100 * r)); last = i
    return pd.DataFrame(rows, columns=["sym", "t", "acc", "up", "ret"])


def tab(q, by):
    g = q.groupby(by, observed=False).up.agg(["size", "sum"])
    return "  ".join(f"{k}: {int(b)}/{int(a)} = {100 * b / a:.0f}%" if a else f"{k}: -" for k, (a, b) in zip(g.index, g.values))


if __name__ == "__main__":
    E = pd.concat([events(s) for s in COINS], ignore_index=True)
    E["yr"] = pd.to_datetime(E.t, unit="s").dt.year
    fine = pd.cut(E.acc, [0, 1.5, 2, 2.5, 3, 4, 99])
    print(f"8 koin: {len(E)} gerakan besar, {100 * E.up.mean():.0f}% naik")
    print("  naik menurut rasio akun:", tab(E, fine))
    for a, b in ((2020, 2023), (2024, 2026)):
        m = (E.yr >= a) & (E.yr <= b); print(f"  {a}-{b}:", tab(E[m], fine[m]))
    b3 = E[(E.sym == "BTC") & (E.acc >= 3)]; print(f"  BTC, rasio >= 3: {int(b3.up.sum())}/{len(b3)} naik")

    P = []
    for s in ("BTCUSDT", "ETHUSDT"):
        q = events(s, need_acc=False)
        P.append(q.merge(pd.read_csv(R + f"research/results/magnet_{s}.csv")[["t", "L2", "S2"]], on="t", how="left"))
    P = pd.concat(P, ignore_index=True); P["yr"] = pd.to_datetime(P.t, unit="s").dt.year
    P["band"] = pd.cut(P.acc, [0, 1.5, 2.5, 99], labels=["<1.5", "1.5-2.5", ">2.5"])
    P["pile"] = np.where(P.S2 > P.L2, "short di atas lebih besar", "long di bawah lebih besar")
    P.loc[P.S2.isna() | P.L2.isna() | (P.S2 == P.L2), "pile"] = None
    A = P.dropna(subset=["acc"])
    print(f"\nBTC + ETH: {len(P)} gerakan besar sejak 2020 ({len(A)} dengan rasio akun), median ukuran BTC "
          f"{P[P.sym == 'BTC'].ret.abs().median():.1f}%, ETH {P[P.sym == 'ETH'].ret.abs().median():.1f}%, "
          f"{A.assign(w=A.t // 604800).w.nunique()} minggu berbeda")
    print("  naik menurut rasio akun:", tab(A, "band"))
    for a, b in ((2020, 2022), (2023, 2024), (2025, 2026)):
        print(f"  {a}-{b}:", tab(A[(A.yr >= a) & (A.yr <= b)], "band"))
    for s in ("BTC", "ETH"):
        print(f"  {s}:", tab(A[A.sym == s], "band"))
    Q = P.dropna(subset=["pile"])
    print("  naik menurut tumpukan likuidasi (2%):", tab(Q, "pile"))
    for a, b in ((2020, 2022), (2023, 2026)):
        print(f"  {a}-{b}:", tab(Q[(Q.yr >= a) & (Q.yr <= b)], "pile"))
    J = A.dropna(subset=["pile"])
    print("  gabungan (rasio x tumpukan):")
    for k, q in J.groupby("band", observed=False):
        print(f"    {k}:", tab(q, "pile"))
