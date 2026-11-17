"""Eksperimen 9 (literatur: arXiv 2608.21888, harga cenderung berbalik setelah gerakan agresif, dengan gerakan karena
likuidasi disebut sebagai uji yang belum dilakukan): apa yang terjadi setelah hari (atau jam) likuidasi besar?

Aturan ditetapkan sebelum melihat hasil. BTC dan ETH, likuidasi Binance dari Coinalyze.
  HARIAN (data/liquidations/daily, sejak Okt 2022): hari likuidasi long besar = likuidasi long hari itu >= 4 x median
  90 hari sebelumnya; sama untuk short. Hari UTC selesai pukul 00:00 UTC; masuk pada harga saat itu.
  Hasil: perubahan harga 1, 3, 7 hari; "naik 1 ayunan mingguan normal lebih dulu" dalam 14 hari.
  Karena hari likuidasi long hampir selalu hari harga jatuh, pembanding yang adil = hari dengan penurunan harga yang sama
  besar (dalam satuan ayunan harian normal) tetapi likuidasi tidak besar.
  PER JAM (research/data/liq_coinalyze_1hour.csv, kira-kira 68 hari): jam likuidasi teratas 2% -> harga 1 dan 3 jam
  berikutnya. Sampel kecil, hanya pendahuluan.
    python research/exp9_liquidations.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race, R  # noqa: E402


def daily(sym):
    h = load(sym); C = h.close.values; H = h.high.values; L = h.low.values; t = h.t.values; n = len(h)
    pos = {int(x): i for i, x in enumerate(t)}
    sigd = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(24); sigw = sigd * np.sqrt(7)
    q = pd.read_csv(R + f"data/liquidations/daily/{sym}.csv").sort_values("t")
    q["lx"] = q.l / q.l.shift(1).rolling(90, min_periods=60).median(); q["sx"] = q.s / q.s.shift(1).rolling(90, min_periods=60).median()
    rows = []
    for r in q.itertuples():
        i = pos.get(int(r.t) + 86400 - 3600)              # candle jam terakhir hari itu; penutupannya = 00:00 UTC hari berikut
        j = pos.get(int(r.t) - 3600)
        if i is None or j is None or i + 336 >= n or not sigd[i] == sigd[i] or not r.lx == r.lx:
            continue
        up, _ = race(H, L, i + 1, C[i], sigw[i], sigw[i], 336, True)
        rows.append(dict(sym=sym[:3], t=int(r.t), lx=r.lx, sx=r.sx, move=(C[i] / C[j] - 1) / sigd[i],
                         r1=C[i + 24] / C[i] - 1, r3=C[i + 72] / C[i] - 1, r7=C[i + 168] / C[i] - 1, up=up))
    return pd.DataFrame(rows)


def line(nm, g):
    if len(g) < 5:
        return f"  {nm}: terlalu sedikit ({len(g)})"
    return (f"  {nm}: {len(g)} hari | 1 hari median {100 * g.r1.median():+.2f}%, naik {100 * (g.r1 > 0).mean():.0f}% | 3 hari naik {100 * (g.r3 > 0).mean():.0f}% | "
            f"7 hari median {100 * g.r7.median():+.1f}%, naik {100 * (g.r7 > 0).mean():.0f}% | naik 1 ayunan lebih dulu {100 * g.up.mean():.0f}%")


if __name__ == "__main__":
    D = pd.concat([daily(s) for s in ("BTCUSDT", "ETHUSDT")], ignore_index=True); D["yr"] = pd.to_datetime(D.t, unit="s").dt.year
    print(f"HARIAN: {len(D)} hari-koin, {pd.to_datetime(D.t.min(), unit='s').date()} s.d. {pd.to_datetime(D.t.max(), unit='s').date()}")
    print(line("semua hari", D))
    bl = D.lx >= 4; bs = D.sx >= 4
    print(line("likuidasi LONG besar (>= 4x median 90 hari)", D[bl])); print(line("likuidasi SHORT besar", D[bs]))
    print(" pembanding adil: hari harga turun lebih dari 1,5 ayunan harian normal")
    dn = D.move <= -1.5
    print(line("  turun besar DAN likuidasi long besar", D[dn & bl])); print(line("  turun besar, likuidasi long TIDAK besar", D[dn & ~bl]))
    up_ = D.move >= 1.5
    print(" hari harga naik lebih dari 1,5 ayunan harian normal")
    print(line("  naik besar DAN likuidasi short besar", D[up_ & bs])); print(line("  naik besar, likuidasi short TIDAK besar", D[up_ & ~bs]))
    for a, b in ((2022, 2024), (2025, 2026)):
        m = (D.yr >= a) & (D.yr <= b); print(f" {a}-{b}:"); print(line("  turun besar + likuidasi long besar", D[m & dn & bl])); print(line("  turun besar, likuidasi biasa", D[m & dn & ~bl]))
    for s in ("BTC", "ETH"):
        m = D.sym == s; print(f" {s}:"); print(line("  turun besar + likuidasi long besar", D[m & dn & bl])); print(line("  turun besar, likuidasi biasa", D[m & dn & ~bl]))
    # regresi sederhana: harga 1 dan 3 hari ke depan pada besar gerakan dan log likuidasi sisi yang searah
    Z = D[D.move < 0].copy(); Z["ll"] = np.log(Z.lx.clip(lower=0.05))
    for k in ("r1", "r3", "r7"):
        X = np.column_stack([np.ones(len(Z)), Z.move, Z.ll]); b_ = np.linalg.lstsq(X, Z[k] * 100, rcond=None)[0]
        res = Z[k] * 100 - X @ b_; se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * res.var())
        print(f" hari turun, {k}: tiap kelipatan e likuidasi long -> {b_[2]:+.2f} poin persen (t {b_[2] / se[2]:+.1f}); tiap 1 ayunan turun -> {b_[1]:+.2f} (t {b_[1] / se[1]:+.1f})")

    print("\nPER JAM (pendahuluan):")
    q = pd.read_csv(R + "research/data/liq_coinalyze_1hour.csv")
    for sym in ("BTCUSDT", "ETHUSDT"):
        h = load(sym)[["t", "open", "close"]]; x = q[q.sym == sym].merge(h, on="t")
        x["r0"] = x.close / x.open - 1; x["n1"] = x.close.shift(-1) / x.close - 1; x["n3"] = x.close.shift(-3) / x.close - 1
        tot = x.l + x.s; hi = x[tot >= tot.quantile(.98)].dropna(subset=["n3"])
        L_ = hi[hi.l > hi.s]; S_ = hi[hi.s >= hi.l]
        print(f"  {sym[:3]}: {len(x)} jam ({pd.to_datetime(x.t.min(), unit='s').date()} s.d. {pd.to_datetime(x.t.max(), unit='s').date()}); jam likuidasi teratas 2%: {len(hi)}"
              f" | long dominan ({len(L_)}): jam berikut median {100 * L_.n1.median():+.2f}%, naik {100 * (L_.n1 > 0).mean():.0f}%, 3 jam naik {100 * (L_.n3 > 0).mean():.0f}%"
              f" | short dominan ({len(S_)}): jam berikut naik {100 * (S_.n1 > 0).mean():.0f}%, 3 jam naik {100 * (S_.n3 > 0).mean():.0f}%")
    last = D.sort_values("t").groupby("sym").tail(1); print("\nterakhir:", last[["sym", "t", "lx", "sx", "move"]].round(2).to_string(index=False))
