"""Eksperimen 4 (literatur: Quantpedia "Bitcoin intraday seasonality", Gemini 2015 - Feb 2022; NYDIG): apakah kenaikan
harga terkumpul di jam tertentu (21:00-23:00 UTC = 04:00-06:00 WIB) atau hari tertentu, dan apakah masih berlaku?

Aturan ditetapkan sebelum melihat hasil. 8 koin, Binance futures per jam, sejak 2020. Jam = jam BUKA candle, UTC.
  A. Rata-rata perubahan harga per jam menurut jam dalam hari, dalam basis poin (1 bp = 0,01%), dengan galat baku yang
     dihitung per hari (satu hari = satu pengamatan per jam). Periode: 2020 - Feb 2022 (tumpang tindih dengan sampel
     penelitian), Mar 2022 - 2023, 2024 - 2026 (di luar sampel).
  B. Jendela penelitian: jam 21 dan 22 UTC (beli 21:00, jual 23:00): rata-rata per hari, % hari naik, per periode.
  C. Sesi: Asia 00-08, Eropa 08-13, AS 13-21, malam 21-24 UTC; hari kerja vs akhir pekan; hari dalam minggu.
  D. Kapan gerakan besar mulai (jam dalam hari), memakai definisi research/big_moves.py.
    python research/exp4_timeofday.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
PER = (("2020 - Feb 2022", 0, 1646092800), ("Mar 2022 - 2023", 1646092800, 1704067200), ("2024 - 2026", 1704067200, 4e9))


def frame():
    out = []
    for s in COINS:
        h = load(s); r = h.close / h.open - 1
        s6 = h.close.pct_change().rolling(720).std() * np.sqrt(6); r6 = h.close.shift(-6) / h.close - 1
        d = pd.DataFrame(dict(sym=s[:-4], t=h.t, r=r, big=(r6.abs() >= 3 * s6).astype(float).where(s6.notna())))
        out.append(d)
    D = pd.concat(out, ignore_index=True); ts = pd.to_datetime(D.t, unit="s")
    D["hr"] = ts.dt.hour; D["dow"] = ts.dt.dayofweek; D["day"] = D.t // 86400
    return D


def per_day_stat(q):
    """rata-rata (bp) dan t dari nilai per hari (rata-rata lintas koin per hari, supaya koin yang bergerak bersama tidak dihitung 8 kali)."""
    x = q.groupby("day").r.mean() * 1e4
    return x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x))), len(x), (x > 0).mean()


if __name__ == "__main__":
    D = frame()
    print("A. Rata-rata perubahan per jam (bp) menurut jam UTC [WIB = UTC+7], 8 koin; t di dalam kurung")
    cols = {}
    for name, a, b in PER + (("semua", 0, 4e9),):
        q = D[(D.t >= a) & (D.t < b)]; cols[name] = {h: per_day_stat(q[q.hr == h])[:2] for h in range(24)}
    print("  jam UTC (WIB) | " + " | ".join(f"{n:>17}" for n in cols))
    for h in range(24):
        print(f"  {h:02d} ({(h + 7) % 24:02d}) | " + " | ".join(f"{cols[n][h][0]:+6.1f} ({cols[n][h][1]:+4.1f})".rjust(17) for n in cols))
    base = {n: per_day_stat(D[(D.t >= a) & (D.t < b)])[0] for n, a, b in PER + (("semua", 0, 4e9),)}
    print("  rata-rata semua jam:", {n: round(v, 2) for n, v in base.items()})
    # konsistensi: korelasi pola 24 jam antar periode
    v = pd.DataFrame({n: [cols[n][h][0] for h in range(24)] for n, _, _ in PER}); print("  korelasi pola 24 jam antar periode:\n", v.corr().round(2).to_string())

    print("\nB. Jendela penelitian (jam 21 dan 22 UTC, beli 21:00 jual 23:00): bp per hari, t, hari, % hari naik | sisa 22 jam: bp per hari")
    for lab, sel in (("8 koin", D.sym.notna()), ("BTC", D.sym == "BTC")):
        for name, a, b in PER + (("semua", 0, 4e9),):
            q = D[sel & (D.t >= a) & (D.t < b)]
            w = q[q.hr.isin([21, 22])].groupby(["day", "sym"]).r.sum().groupby("day").mean() * 1e4
            o = q[~q.hr.isin([21, 22])].groupby(["day", "sym"]).r.sum().groupby("day").mean() * 1e4
            print(f"  {lab} {name}: jendela {w.mean():+.1f} bp (t {w.mean() / (w.std() / np.sqrt(len(w))):+.1f}, {len(w)} hari, naik {100 * (w > 0).mean():.0f}%) | sisa hari {o.mean():+.1f} bp")

    print("\nC. Sesi (bp per hari, t) per periode, 8 koin")
    SES = (("Asia 00-08 UTC (07-15 WIB)", range(0, 8)), ("Eropa 08-13 UTC (15-20 WIB)", range(8, 13)), ("AS 13-21 UTC (20-04 WIB)", range(13, 21)), ("malam 21-24 UTC (04-07 WIB)", range(21, 24)))
    for sn, hrs in SES:
        out = []
        for name, a, b in PER + (("semua", 0, 4e9),):
            q = D[(D.t >= a) & (D.t < b) & D.hr.isin(list(hrs))]; x = q.groupby(["day", "sym"]).r.sum().groupby("day").mean() * 1e4
            out.append(f"{name}: {x.mean():+.1f} ({x.mean() / (x.std() / np.sqrt(len(x))):+.1f})")
        print(f"  {sn}: " + " | ".join(out))
    print("  hari dalam minggu (bp per hari penuh UTC, t), 8 koin:")
    for name, a, b in PER + (("semua", 0, 4e9),):
        q = D[(D.t >= a) & (D.t < b)]; x = q.groupby(["day", "sym"]).agg(r=("r", "sum"), dow=("dow", "first")).reset_index().groupby("day").agg(r=("r", "mean"), dow=("dow", "first"))
        print(f"    {name}: " + "  ".join(f"{['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'][k]} {1e4 * g.r.mean():+.0f} ({g.r.mean() / (g.r.std() / np.sqrt(len(g))):+.1f})" for k, g in x.groupby("dow")))

    print("\nD. Jam mulai gerakan besar (% dari semua jam di jam itu), 8 koin; rata-rata semua jam:", f"{100 * D.big.mean():.2f}%")
    for name, a, b in PER + (("semua", 0, 4e9),):
        q = D[(D.t >= a) & (D.t < b)].dropna(subset=["big"]); g = q.groupby("hr").big.mean() * 100
        print(f"  {name}: " + " ".join(f"{h:02d}:{g[h]:.1f}" for h in range(24)))
    q = D.dropna(subset=["big"]); g = q.groupby(q.dow >= 5).big.mean() * 100; print(f"  hari kerja {g[False]:.2f}% vs akhir pekan {g[True]:.2f}%")
