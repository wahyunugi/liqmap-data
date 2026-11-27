"""Peringatan "gerakan cepat sedang terjadi": pelengkap peringatan volume 24 jam (Principle 36).
ATURAN DITULIS SEBELUM HASIL DILIHAT (27 Nov 2026), sesudah 27 Nov 21:00-22:00 WIB: BTC -3,7% dalam satu jam dari hari
yang sepi; volume 24 jam tetap 1,0x sehingga peringatan lama tidak menyala.

Definisi (per koin, jam lengkap):
  sigma1 = simpangan baku perubahan per jam 720 jam; BM = 3 x sigma1 x akar 6 (ukuran gerakan besar, sama dengan panel risiko)
  F  = |perubahan 1 jam| >= 0,5 BM                                     (aturan utama)
  F2 = |perubahan 2 jam| >= 0,6 BM                                     (pembanding)
  V  = volume 1 jam >= 5x median volume per jam 30 hari                (pembanding)
  jeda 12 jam per koin sesudah satu peringatan.
Diukur dari penutupan jam peringatan (kenyataannya pesan tiba sekitar 20 sampai 60 menit kemudian):
  - berapa kali per bulan per koin (gangguan)
  - dalam 24 jam, mana yang kena lebih dulu: lanjut 0,5 BM searah gerakan, atau balik 0,5 BM berlawanan
  - perubahan 24 jam searah gerakan (median)
  - cakupan: dari semua gerakan besar (|close k+6 / close k - 1| >= BM, satu per 12 jam), berapa yang diawali peringatan
    di dalam 6 jam itu, dan berapa sisa gerakan sesudah peringatan
Dipisah 2020-2023 dan 2024-2026; 8 koin.
    python research/fast_move_alert.py
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
CUT = pd.Timestamp("2024-01-01").timestamp()


def race(H, L, k, up, dn, hours=24):
    for q in range(k + 1, min(k + 1 + hours, len(H))):
        hu, hd = H[q] >= up, L[q] <= dn
        if hu and hd: return "both"
        if hu: return "up"
        if hd: return "down"
    return "none"


def run(sym):
    h = arena.load(sym); H, L, C, t, V = h.high.values, h.low.values, h.close.values, h.t.values, h.vol.values
    r = pd.Series(C).pct_change()
    s1 = r.rolling(720).std().values; bm = 3 * s1 * np.sqrt(6)
    r1 = r.values; r2 = pd.Series(C).pct_change(2).values
    vmed = pd.Series(V).rolling(720, min_periods=360).median().values
    trig = {"F": np.abs(r1) >= 0.5 * bm, "F2": np.abs(r2) >= 0.6 * bm, "V": V >= 5 * vmed}
    dirn = {"F": np.sign(r1), "F2": np.sign(r2), "V": np.sign(r1)}
    rows = []
    for name, f in trig.items():
        last = -10**9
        for k in range(1200, len(C) - 25):
            if not (f[k] and bm[k] == bm[k]) or k - last < 12: continue
            last = k; d = dirn[name][k] or 1; e = C[k]; b = bm[k]
            up, dn = (e * (1 + .5 * b), e * (1 - .5 * b))
            w = race(H, L, k, up, dn)
            res = "none" if w == "none" else "both" if w == "both" else ("cont" if (w == "up") == (d > 0) else "rev")
            rows.append(dict(rule=name, coin=sym[:3], t=t[k], d=d, res=res, r24=d * (C[k + 24] / e - 1) / b))
    # gerakan besar dan cakupan
    big = []; last = -10**9
    for k in range(1200, len(C) - 7):
        if bm[k] == bm[k] and abs(C[k + 6] / C[k] - 1) >= bm[k] and k - last >= 12:
            last = k; d = np.sign(C[k + 6] - C[k]); total = d * (C[k + 6] / C[k] - 1)
            cov = {}
            for name, f in trig.items():
                hit = [q for q in range(k + 1, k + 7) if f[q] and np.sign(r1[q] if name != "F2" else r2[q]) == d]
                cov[name] = (d * (C[k + 6] / C[hit[0]] - 1) / total) if hit else np.nan
            big.append(dict(coin=sym[:3], t=t[k], **{f"left_{n}": v for n, v in cov.items()}))
    return pd.DataFrame(rows), pd.DataFrame(big), (t[-1] - t[1200]) / (30 * 86400)


def main():
    A, B, months = [], [], {}
    for s in COINS:
        a, b, m = run(s); A.append(a); B.append(b); months[s[:3]] = m
    A = pd.concat(A); B = pd.concat(B)
    A["period"] = np.where(A.t < CUT, "2020-2023", "2024-2026"); B["period"] = np.where(B.t < CUT, "2020-2023", "2024-2026")
    mo = sum(months.values())
    print("ALERTS AFTER THE FAST MOVE (24h race, 0.5 BM each way)")
    for (rule, per), g in A.groupby(["rule", "period"]):
        n = len(g); c = (g.res == "cont").mean(); rv = (g.res == "rev").mean(); no = (g.res == "none").mean()
        print(f" {rule:3} {per}: n={n:5d}  continue first {100*c:4.0f}%  reverse first {100*rv:4.0f}%  neither {100*no:3.0f}%"
              f"  median 24h move in its direction {g.r24.median():+.2f} BM")
    for rule, g in A.groupby("rule"):
        print(f" {rule}: {len(g)/mo:.1f} alerts per coin per month")
    for c in ("BTC", "ETH"):
        g = A[(A.coin == c) & (A.rule == "F")]
        print(f" {c} F: n={len(g)}, continue {100*(g.res=='cont').mean():.0f}%, reverse {100*(g.res=='rev').mean():.0f}%")
    print("\nCOVERAGE OF BIG MOVES (|6h move| >= 1 BM)")
    for per, g in B.groupby("period"):
        txt = "  ".join(f"{n}: caught {100*g[f'left_{n}'].notna().mean():.0f}%, move left after alert {100*g[f'left_{n}'].median():.0f}%"
                        for n in ("F", "F2", "V"))
        print(f" {per} n={len(g)}  {txt}")
    A.to_csv(os.path.join(arena.ROOT, "research/results/fast_move_alerts.csv"), index=False)


if __name__ == "__main__":
    main()
