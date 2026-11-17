"""Eksperimen 6 (literatur: FalconX 2024; Mazur dan Polyzos 2025): apa yang terjadi setelah rentetan arus keluar (atau
masuk) ETF spot AS, dan apakah arus ETF mendahului atau mengikuti harga?

Aturan ditetapkan sebelum melihat hasil. Data: data/etf/<BTC|ETH>.csv (Farside, juta US$, per hari bursa AS).
  Angka tanggal d dianggap baru diketahui pada d+1 jam 06:00 UTC (13:00 WIB); semua hasil diukur dari harga saat itu.
  rentetan = hari bursa berturut-turut dengan total < 0 (keluar) atau > 0 (masuk).
  A. Kejadian = hari rentetan mencapai panjang N (N = 3, 5, 7); hasil = perubahan harga 7 dan 30 hari, "turun 1 ayunan
     mingguan normal lebih dulu" dalam 14 hari. Pembanding = semua hari bursa.
  B. Kejadian = hari arus masuk pertama setelah rentetan keluar >= 5 hari ("uang kembali").
  C. Jumlah arus 10 hari bursa terakhir, dibagi 5 kelompok sama besar.
  D. Siapa duluan: korelasi arus harian dengan perubahan harga 5 hari SEBELUM vs 5 hari SESUDAH.
Sampel kecil: BTC sejak Jan 2024, ETH sejak Jul 2024. Jumlah episode terpisah dicetak.
    python research/exp6_etf.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race, R  # noqa: E402


def frame(coin):
    e = pd.read_csv(R + f"data/etf/{coin}.csv")[["date", "total"]].dropna()
    h = load(coin + "USDT"); C = h.close.values; Hh = h.high.values; L = h.low.values; t = h.t.values; n = len(h)
    pos = {int(x): i for i, x in enumerate(t)}
    sig = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    rows = []
    for r in e.itertuples():
        ts = int(pd.Timestamp(r.date, tz="UTC").timestamp()) + 86400 + 6 * 3600
        i = pos.get(ts)
        if i is None or i < 24 * 6:
            continue
        b5 = pos.get(int(pd.Timestamp(r.date, tz="UTC").timestamp()) - 5 * 86400 + 21 * 3600)
        rows.append(dict(date=r.date, flow=r.total, i=i,
                         f7=C[i + 168] / C[i] - 1 if i + 168 < n else np.nan,
                         f30=C[i + 720] / C[i] - 1 if i + 720 < n else np.nan,
                         down=(1 - race(Hh, L, i, C[i], sig[i], sig[i], 336, True)[0]) if i + 336 < n and sig[i] == sig[i] else np.nan,
                         p5=C[pos[int(pd.Timestamp(r.date, tz="UTC").timestamp()) + 21 * 3600]] / C[b5] - 1 if b5 is not None and pos.get(int(pd.Timestamp(r.date, tz="UTC").timestamp()) + 21 * 3600) is not None else np.nan,
                         n5=C[i + 120] / C[i] - 1 if i + 120 < n else np.nan))
    d = pd.DataFrame(rows)
    sgn = np.sign(d.flow); run = []; k = 0
    for j, s in enumerate(sgn):
        k = (k + 1) if (j and s == sgn.iat[j - 1] and s != 0) else (1 if s != 0 else 0); run.append(k * s)
    d["run"] = run; d["sum10"] = d.flow.rolling(10).sum()
    return d


def line(name, q, ep=None):
    if len(q) < 5:
        return f"  {name}: terlalu sedikit ({len(q)})"
    x = f" / {ep} episode" if ep is not None else ""
    return (f"  {name}: {len(q)} hari{x} | 7 hari median {100 * q.f7.median():+.1f}%, naik {100 * (q.f7 > 0).mean():.0f}% | "
            f"30 hari median {100 * q.f30.median():+.1f}%, naik {100 * (q.f30 > 0).mean():.0f}% | turun lebih dulu {100 * q.down.mean():.0f}%")


if __name__ == "__main__":
    for coin in ("BTC", "ETH"):
        d = frame(coin); print(f"\n===== {coin}: {len(d)} hari bursa, {d.date.iat[0]} s.d. {d.date.iat[-1]}; rentetan sekarang: {int(d.run.iat[-1])} =====")
        print(line("semua hari bursa (pembanding)", d))
        print("A. hari rentetan mencapai N:")
        for N in (3, 5, 7):
            for sgn, nm in ((-1, "keluar"), (1, "masuk")):
                q = d[d.run == sgn * N]; print(line(f"{nm} {N} hari berturut-turut", q, len(q)))
        print("   daftar rentetan keluar >= 5 hari (tanggal hari ke-5, panjang akhir, harga 30 hari setelah hari ke-5):")
        st = d[d.run == -5]
        for r in st.itertuples():
            j = r.Index; L_ = 5
            while j + 1 < len(d) and d.run.iat[j + 1] <= -(L_ + 1): j += 1; L_ += 1
            print(f"     {r.date}: panjang {L_} hari, 7 hari {100 * r.f7:+.1f}%, 30 hari {100 * r.f30:+.1f}%" if r.f30 == r.f30 else f"     {r.date}: panjang {L_} hari (belum 30 hari)")
        prev = d.run.shift(1); first_in = d[(d.flow > 0) & (prev <= -5)]
        print("B. hari arus masuk pertama setelah rentetan keluar >= 5:"); print(line("uang kembali", first_in, len(first_in)))
        for r in first_in.itertuples():
            print(f"     {r.date}: 7 hari {100 * r.f7:+.1f}%, 30 hari {100 * r.f30:+.1f}%" if r.f30 == r.f30 else f"     {r.date}: belum 30 hari")
        q = d.dropna(subset=["sum10"]); q["b"] = pd.qcut(q.sum10, 5, labels=["keluar terbesar", "2", "3", "4", "masuk terbesar"])
        print("C. jumlah arus 10 hari bursa (kelompok sama besar):")
        for k, g in q.groupby("b", observed=False):
            print(line(f"{k} ({g.sum10.min():+.0f} s.d. {g.sum10.max():+.0f} juta US$)", g))
        z = d.dropna(subset=["p5", "n5"])
        print(f"D. korelasi arus hari itu dengan harga 5 hari SEBELUMNYA {z.flow.corr(z.p5):+.2f}, dengan 5 hari SESUDAHNYA {z.flow.corr(z.n5):+.2f} ({len(z)} hari)")
        for a, b in (("2024-01-01", "2025-06-30"), ("2025-07-01", "2026-12-31")):
            zz = z[(z.date >= a) & (z.date <= b)]; print(f"   {a[:7]} s.d. {b[:7]}: sebelum {zz.flow.corr(zz.p5):+.2f}, sesudah {zz.flow.corr(zz.n5):+.2f} ({len(zz)} hari)")
