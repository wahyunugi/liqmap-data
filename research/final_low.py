"""Apakah terendah TERAKHIR punya ciri yang bisa dilihat saat itu juga?

Aturan ditetapkan sebelum melihat hasil. Kejadian = sama dengan research/bounce_map.py (jam pertama menembus terendah
20 hari dengan volume 24 jam >= 2x normal, jarak >= 7 hari), hanya fase turun (harga di bawah MA200 harian), 8 koin.
Kandidat = setiap jam dalam 10 hari sejak kejadian (termasuk jam kejadian) yang mencetak terendah baru sejak kejadian.
Terendah akhir = kandidat yang terendahnya tidak ditembus dalam 10 hari (240 jam) sesudahnya.
Ciri (semua diketahui pada akhir jam itu):
  volr24   volume 24 jam / median 30 hari          spike1h  volume jam itu / median jam 30 hari
  depth    jarak di bawah terendah kejadian (%)      dd7      turun dari tertinggi 7 hari, dalam ayunan mingguan
  acc      rasio akun long/short                     dacc24   perubahan rasio akun 24 jam (%)
  top      rasio posisi trader besar                 doi24    perubahan open interest 24 jam (%)
  doiev    perubahan open interest sejak kejadian    taker    porsi beli agresif jam itu (taker_buy / volume)
  wick     posisi penutupan dalam rentang jam (0 = di terendah, 1 = di tertinggi)
  prem     premi futures atas spot (%)               hrs      jam sejak kejadian
Uji: (1) median ciri pada terendah akhir vs bukan; (2) dalam tiap kejadian, apakah kandidat dengan ciri tertinggi
(atau terendah) adalah terendah akhir, dibanding peluang acak 1/k; (3) dipisah 2020-2022 vs 2023-2026.
    python research/final_low.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
FEATS = ["volr24", "spike1h", "depth", "dd7", "acc", "dacc24", "top", "doi24", "doiev", "taker", "wick", "prem", "hrs"]


def candidates():
    rows = []
    for sym in COINS:
        h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h)
        V = h.vol.values; sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
        v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
        v1 = (h.vol / h.vol.rolling(720, min_periods=360).median()).values
        pl = pd.Series(L).rolling(480).min().shift(1).values
        ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
        acc = h.acc_lsr.values; top = h.top_lsr.values; oi = h.oi.values
        tb = (h.taker_buy / h.vol).values; prem = ((h.close / h.spot_close - 1).values * 100) if "spot_close" in h else np.full(n, np.nan)
        last = -10**9
        for i in range(720 + 480, n - 480):
            if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168:
                continue
            last = i
            if not C[i] < ma[i]:
                continue
            run = np.inf; hi7 = H[i - 168:i + 1].max()
            for j in range(i, i + 241):
                if L[j] >= run:
                    continue
                run = L[j]
                final = L[j + 1:j + 241].min() >= L[j]
                rng = H[j] - L[j]
                rows.append(dict(sym=sym[:-4], ev=f"{sym[:-4]}{i}", yr=pd.to_datetime(t[j], unit="s").year, final=final,
                                 volr24=volr[j], spike1h=v1[j], depth=100 * (1 - L[j] / L[i]), dd7=(1 - L[j] / hi7) / sw[i],
                                 acc=acc[j], dacc24=100 * (acc[j] / acc[j - 24] - 1), top=top[j],
                                 doi24=100 * (oi[j] / oi[j - 24] - 1), doiev=100 * (oi[j] / oi[i - 1] - 1), taker=tb[j],
                                 wick=(C[j] - L[j]) / rng if rng > 0 else np.nan, prem=prem[j], hrs=j - i))
    return pd.DataFrame(rows)


def within(D, f, sign):
    """Dalam tiap kejadian: kandidat dengan nilai ciri paling ekstrem (sign=+1 tertinggi, -1 terendah) = terendah akhir?"""
    hit = exp = m = 0
    for _, g in D.groupby("ev"):
        g = g.dropna(subset=[f])
        if len(g) < 2 or not g.final.any():
            continue
        k = (g[f] * sign).idxmax(); hit += bool(g.loc[k, "final"]); exp += g.final.mean(); m += 1
    return hit, exp, m


if __name__ == "__main__":
    D = candidates()
    D.to_csv("/tmp/claude-0/-home-claude/060f9c3f-9ddd-5c7b-8928-2f877765f5d6/scratchpad/final_low_cands.csv", index=False)
    print(f"{D.ev.nunique()} kejadian fase turun, {len(D)} kandidat terendah baru, {int(D.final.sum())} terendah akhir "
          f"({D.groupby('ev').final.sum().gt(0).sum()} kejadian punya terendah akhir di dalam jendela)")
    print(f"{'ciri':>8} | median akhir vs bukan | {'dalam kejadian: tertinggi = akhir':>34} | {'terendah = akhir':>18} | 2020-22 / 2023-26 (tertinggi)")
    for f in FEATS:
        a, b = D[D.final][f].median(), D[~D.final][f].median()
        hi = within(D, f, 1); lo = within(D, f, -1)
        p1 = within(D[D.yr <= 2022], f, 1); p2 = within(D[D.yr >= 2023], f, 1)
        print(f"{f:>8} | {a:8.2f} vs {b:8.2f} | {hi[0]:3d}/{hi[2]} kena, acak {hi[1]:.1f} | {lo[0]:3d}/{lo[2]} acak {lo[1]:.1f} | "
              f"{p1[0]}/{p1[2]} (acak {p1[1]:.1f}) ; {p2[0]}/{p2[2]} (acak {p2[1]:.1f})")
    B = D[D.sym.isin(["BTC", "ETH"])]
    print("\nBTC+ETH saja:", B.ev.nunique(), "kejadian")
    for f in FEATS:
        hi = within(B, f, 1); lo = within(B, f, -1)
        print(f"{f:>8} | median {B[B.final][f].median():8.2f} vs {B[~B.final][f].median():8.2f} | tertinggi {hi[0]}/{hi[2]} acak {hi[1]:.1f} | terendah {lo[0]}/{lo[2]} acak {lo[1]:.1f}")

    # Skor sederhana (ambang dipilih SESUDAH melihat tabel per ciri di atas, jadi masih dalam-sampel):
    #   ekor bawah (wick >= 0,5) + puncak volume (spike1h >= 10 atau volr24 >= 4) + kerumunan turun (dacc24 <= -10%)
    #   + open interest turun (doi24 <= -5%)
    D["score"] = ((D.wick >= .5).astype(int) + ((D.spike1h >= 10) | (D.volr24 >= 4)).astype(int)
                  + (D.dacc24 <= -10).astype(int) + (D.doi24 <= -5).astype(int))
    print(f"\npeluang dasar: {int(D.final.sum())}/{len(D)} = {100 * D.final.mean():.0f}% jam terendah baru adalah terendah akhir")
    for nm, q in (("semua", D), ("2020-2022", D[D.yr <= 2022]), ("2023-2026", D[D.yr >= 2023]), ("BTC+ETH", D[D.sym.isin(["BTC", "ETH"])])):
        g = q.groupby("score").agg(n=("final", "size"), fin=("final", "sum"), ev=("ev", "nunique"))
        print(f"  skor, {nm}: " + "  ".join(f"{k}: {int(r.fin)}/{int(r.n)} = {100 * r.fin / r.n:.0f}% ({int(r.ev)} kejadian)" for k, r in g.iterrows()))
