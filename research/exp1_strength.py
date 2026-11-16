"""Eksperimen 1 (literatur: Quantpedia, "Revisiting trend-following and mean-reversion strategies in Bitcoin"):
apakah membeli saat harga KUAT (level tertinggi N hari) lebih baik daripada membeli saat harga JATUH (terendah N hari)?

Aturan ditetapkan sebelum melihat hasil:
 A. Replikasi harfiah (harian, penutupan 00 UTC): bila penutupan hari ini = tertinggi (atau terendah) N hari terakhir,
    berapa perubahan harga 1 hari dan 7 hari berikutnya, dibanding semua hari. N = 10, 20, 50.
 B. Uji dengan ukuran menang kita (per jam): entri long pada jam pertama harga menembus tertinggi (atau terendah) 20 hari,
    entri berjarak >= 72 jam per koin, menang = naik 2,25 ayunan mingguan normal sebelum turun 1,5 dalam 60 hari (sama
    dengan research/turning_points.py), dan versi seimbang: naik 1 ayunan sebelum turun 1 dalam 30 hari.
    Pembanding: entri acak tiap 72 jam di periode yang sama.
8 koin, Binance futures, sejak 2020. Periode: 2020-21, 2022-23, 2024-26.
    python research/exp1_strength.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
PER = ((2020, 2021), (2022, 2023), (2024, 2026))


def part_a():
    rows = []
    for s in COINS:
        h = load(s); d = h[h.t % 86400 == 82800][["t", "close"]].reset_index(drop=True)      # penutupan jam 23 = akhir hari UTC
        c = d.close
        for N in (10, 20, 50):
            hi = c >= c.rolling(N).max(); lo = c <= c.rolling(N).min()
            for k in (1, 7):
                f = c.shift(-k) / c - 1
                for lab, m in (("tertinggi", hi), ("terendah", lo), ("semua hari", c.notna())):
                    q = pd.DataFrame(dict(sym=s[:-4], N=N, k=k, kind=lab, t=d.t[m], f=f[m])).dropna(); rows.append(q)
    A = pd.concat(rows); A["yr"] = pd.to_datetime(A.t, unit="s").dt.year
    print("A. Perubahan harga setelah penutupan di tertinggi / terendah N hari (8 koin digabung): rata-rata, median, % naik, jumlah hari")
    for N in (10, 20, 50):
        for k in (1, 7):
            out = []
            for lab in ("tertinggi", "terendah", "semua hari"):
                q = A[(A.N == N) & (A.k == k) & (A.kind == lab)]
                out.append(f"{lab}: {100 * q.f.mean():+.2f}% / {100 * q.f.median():+.2f}% / {100 * (q.f > 0).mean():.0f}% ({len(q)})")
            print(f"  N={N}, {k} hari ke depan | " + " | ".join(out))
    print("  per periode, N=20, 7 hari ke depan (rata-rata / % naik / hari):")
    for a, b in PER:
        out = []
        for lab in ("tertinggi", "terendah", "semua hari"):
            q = A[(A.N == 20) & (A.k == 7) & (A.kind == lab) & (A.yr >= a) & (A.yr <= b)]
            out.append(f"{lab}: {100 * q.f.mean():+.2f}% / {100 * (q.f > 0).mean():.0f}% ({len(q)})")
        print(f"    {a}-{b} | " + " | ".join(out))
    print("  BTC saja, N=20, 7 hari ke depan:")
    for a, b in PER + ((2020, 2026),):
        out = []
        for lab in ("tertinggi", "terendah", "semua hari"):
            q = A[(A.sym == "BTC") & (A.N == 20) & (A.k == 7) & (A.kind == lab) & (A.yr >= a) & (A.yr <= b)]
            out.append(f"{lab}: {100 * q.f.mean():+.2f}% / {100 * (q.f > 0).mean():.0f}% ({len(q)})")
        print(f"    {a}-{b} | " + " | ".join(out))


def entries(sym, N=480, gap=72):
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h)
    sig = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    ph = pd.Series(H).rolling(N).max().shift(1).values; pl = pd.Series(L).rolling(N).min().shift(1).values
    rows = []; last = {"kuat": -10**9, "jatuh": -10**9, "acak": -10**9}
    for i in range(max(N, 721), n - 1):
        s = sig[i]
        if not s == s:
            continue
        kinds = []
        if H[i] > ph[i]: kinds.append("kuat")
        if L[i] < pl[i]: kinds.append("jatuh")
        kinds.append("acak")
        for k in kinds:
            if i - last[k] < gap:
                continue
            last[k] = i
            y, _ = race(H, L, i, C[i], 2.25 * s, 1.5 * s, 1440, True)
            y1, _ = race(H, L, i, C[i], s, s, 720, True)
            f30 = C[i + 720] / C[i] - 1 if i + 720 < n else np.nan
            rows.append(dict(sym=sym[:-4], t=t[i], kind=k, y=y, y1=y1, f30=f30))
    return pd.DataFrame(rows)


def part_b():
    E = pd.concat([entries(s) for s in COINS], ignore_index=True); E["yr"] = pd.to_datetime(E.t, unit="s").dt.year; E["wk"] = E.t // 604800
    def line(q):
        out = []
        for k in ("kuat", "jatuh", "acak"):
            x = q[q.kind == k]; a = x.dropna(subset=["y"]); b = x.dropna(subset=["y1"])
            out.append(f"{k}: {100 * a.y.mean():.0f}% | {100 * b.y1.mean():.0f}% | 30 hari median {100 * x.f30.median():+.1f}% ({len(a)} entri, {x.groupby('sym').wk.nunique().sum()} minggu)")
        return " || ".join(out)
    print("\nB. Entri long di tembusan tertinggi 20 hari (kuat), terendah 20 hari (jatuh), dan acak: menang 2,25:1,5 | menang 1:1 | 30 hari")
    print("  semua:", line(E))
    for a, b in PER:
        print(f"  {a}-{b}:", line(E[(E.yr >= a) & (E.yr <= b)]))
    print("  BTC+ETH:", line(E[E.sym.isin(["BTC", "ETH"])]))
    print("  6 koin lain:", line(E[~E.sym.isin(["BTC", "ETH"])]))
    # selisih terhadap acak per koin-periode (apakah arah sama di tiap koin)
    g = E.dropna(subset=["y1"]).groupby(["sym", "kind"]).y1.mean().unstack()
    print("  menang 1:1 per koin:", {s: f"kuat {100 * r.kuat:.0f} / jatuh {100 * r.jatuh:.0f} / acak {100 * r.acak:.0f}" for s, r in g.iterrows()})
    # uji acak blok minggu: kuat vs jatuh pada ukuran 1:1
    q = E[E.kind.isin(["kuat", "jatuh"])].dropna(subset=["y1"]); obs = q[q.kind == "kuat"].y1.mean() - q[q.kind == "jatuh"].y1.mean()
    wk = q.groupby(["wk", "kind"]).y1.agg(["sum", "size"]).reset_index(); rng = np.random.default_rng(7); weeks = wk.wk.unique(); cnt = 0; M = 3000
    lab = dict(zip(weeks, range(len(weeks)))); idx = wk.wk.map(lab).values; isK = (wk.kind == "kuat").values
    for _ in range(M):
        flip = rng.random(len(weeks)) < 0.5; k2 = isK ^ flip[idx]
        a = wk["sum"].values[k2].sum() / max(wk["size"].values[k2].sum(), 1); b = wk["sum"].values[~k2].sum() / max(wk["size"].values[~k2].sum(), 1)
        cnt += abs(a - b) >= abs(obs)
    print(f"  kuat vs jatuh (1:1): selisih {100 * obs:+.1f} poin; uji acak per minggu p = {cnt / M:.3f} ({len(weeks)} minggu)")


if __name__ == "__main__":
    part_a(); part_b()
