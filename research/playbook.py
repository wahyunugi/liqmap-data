"""Strategi masuk bertahap (playbook) dari Principles, diuji sebagai trade. ATURAN INI DITULIS DAN DI-COMMIT SEBELUM
HASILNYA DILIHAT (22 Nov 2026); varian di bawah adalah seluruh varian yang diuji, tidak ada yang ditambah sesudahnya.

Umum: 8 koin Binance futures per jam sejak 2020. Risiko per setup = 1% modal bila seluruh rencana posisi terisi dan stop
kena. Biaya 0,1% pulang-pergi dari nilai posisi. Funding tidak dihitung. Hasil per setup dalam % modal.
Bila stop dan level lain kena di jam yang sama: level diisi dulu, lalu stop (anggapan terburuk).

LONG, setup pantulan (prinsip 22, 26, 27): kejadian = jam pertama menembus terendah 20 hari dengan volume 24 jam >= 2x
normal, jarak >= 7 hari, harga di bawah MA200 (fase turun). Sesudah kejadian (sampai 40 hari) dilacak terendah berjalan
(lo) dan tertinggi sesudahnya (pk). Siap bila pk/lo - 1 >= 1 ayunan mingguan (ayunan saat kejadian). Order beli limit:
  E50 = lo + 50% (pk - lo),  E75 = lo + 25% (pk - lo),  E90 = lo + 10% (pk - lo)
Sebelum order pertama terisi, terendah baru me-reset lo dan pk. Begitu terisi, lo dan pk dibekukan.
Stop = lo - 1%. Ukuran rencana: unit = 1% modal / (E50 - stop) (sehingga rugi <= 1% bila semua tahap terisi... untuk
tahap di bawah E50 ruginya lebih kecil). Keluar di target, stop, atau 30 hari sesudah isi pertama (harga penutupan).
  L0  100% di E50, target pk                               (patokan = prinsip 27)
  L1  50% di E50, 50% di E75, target pk
  L2  1/3 di E50, 1/3 di E75, 1/3 di E90, target pk
  L3  seperti L0 tetapi ukuran 100% bila rasio akun < 2 saat terisi, 50% bila >= 2
  L4  seperti L0, target 2R (E50 + 2 x (E50 - stop))
  L5  seperti L1, target 2R dari E50

SHORT, setup breakdown (prinsip 20): jam pertama menembus terendah 20 hari, jarak >= 3 hari, semua fase.
Masuk di penutupan jam itu (C). Stop = C x (1 + ayunan), unit = 1% modal / (C x ayunan).
  S0  100% di C, target C x (1 - ayunan)                    (patokan = prinsip 20)
  S1  seperti S0, ukuran menurut rasio akun: >= 3 -> 100%, 2,5 sampai 3 -> 50%, < 2,5 -> 0% (lewati)
  S2  50% di C, 50% limit jual di C x (1 + 0,5 ayunan), stop sama, target C x (1 - ayunan)
  S3  seperti S0, target C x (1 - 2 ayunan)
    python research/playbook.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
FEE = 0.001; MAXH = 720


def trade(H, L, C, k0, side, legs, stop, tgt, unit, first=0):
    """legs: [(fraksi, harga limit atau None = isi di C[k0])]. side +1 long, -1 short. Hasil: % modal.
    first: jam yang targetnya tidak dihitung (jam pengisian limit pertama, urutan di dalam jam tidak diketahui)."""
    filled = []; pending = []
    for f, px in legs:
        (filled if px is None else pending).append((f, C[k0] if px is None else px))
    end = min(k0 + MAXH, len(C) - 1)
    for q in range(k0 + 1, end + 1):
        for f, px in list(pending):
            if (side > 0 and L[q] <= px) or (side < 0 and H[q] >= px):
                filled.append((f, px)); pending.remove((f, px))
        hit_stop = (L[q] <= stop) if side > 0 else (H[q] >= stop)
        if hit_stop:
            return pnl(filled, stop, side, unit)
        if q > first and ((side > 0 and H[q] >= tgt) or (side < 0 and L[q] <= tgt)):
            return pnl(filled, tgt, side, unit)
    return pnl(filled, C[end], side, unit)


def pnl(filled, exit_px, side, unit):
    return 100 * sum(f * unit * (side * (exit_px - px) - FEE * px) for f, px in filled)


def long_setups(sym):
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h); acc = h.acc_lsr.values
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    pl = pd.Series(L).rolling(480).min().shift(1).values
    ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
    out = []; last = -10**9
    for i in range(720 + 480, n - 960 - MAXH):
        if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168:
            continue
        last = i
        if not C[i] < ma[i]:
            continue
        s = sw[i]; lo = L[i]; pk = H[i]
        for k in range(i + 1, i + 961):
            if L[k] < lo:
                lo = L[k]; pk = H[k]; continue
            e50 = lo + .5 * (pk - lo)
            if pk / lo - 1 >= s and L[k] <= e50:
                e75 = lo + .25 * (pk - lo); e90 = lo + .1 * (pk - lo); stop = lo * .99
                # baris k sendiri: E50 terisi di jam k; tahap lebih dalam bisa terisi di jam yang sama -> dicek mulai k
                unit = 0.01 / (e50 - stop); t2r = e50 + 2 * (e50 - stop)
                k0 = k - 1  # supaya trade() memeriksa jam k untuk pengisian dan stop
                Cm = C.copy(); Cm[k0] = e50   # isi "pasar" pada E50
                a = acc[k]; m3 = 1.0 if a == a and a < 2 else 0.5
                out.append(dict(sym=sym[:-4], yr=pd.to_datetime(t[k], unit="s").year,
                    L0=trade(H, L, Cm, k0, 1, [(1, None)], stop, pk, unit, k),
                    L1=trade(H, L, Cm, k0, 1, [(.5, None), (.5, e75)], stop, pk, unit, k),
                    L2=trade(H, L, Cm, k0, 1, [(1/3, None), (1/3, e75), (1/3, e90)], stop, pk, unit, k),
                    L3=trade(H, L, Cm, k0, 1, [(m3, None)], stop, pk, unit, k),
                    L4=trade(H, L, Cm, k0, 1, [(1, None)], stop, t2r, unit, k),
                    L5=trade(H, L, Cm, k0, 1, [(.5, None), (.5, e75)], stop, t2r, unit, k)))
                break
            pk = max(pk, H[k])
    return out


def short_setups(sym):
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h); acc = h.acc_lsr.values
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    pl = pd.Series(L).rolling(480).min().shift(1).values
    out = []; last = -10**9
    for i in range(720 + 480, n - MAXH):
        if not (L[i] < pl[i] and sw[i] == sw[i]) or i - last < 72:
            continue
        last = i; s = sw[i]; c = C[i]; unit = 0.01 / (c * s); a = acc[i]
        m1 = np.nan if a != a else (1.0 if a >= 3 else .5 if a >= 2.5 else 0.0)
        out.append(dict(sym=sym[:-4], yr=pd.to_datetime(t[i], unit="s").year, acc=a,
            S0=trade(H, L, C, i, -1, [(1, None)], c * (1 + s), c * (1 - s), unit),
            S1=np.nan if m1 != m1 else trade(H, L, C, i, -1, [(m1, None)], c * (1 + s), c * (1 - s), unit),
            S2=trade(H, L, C, i, -1, [(.5, None), (.5, c * (1 + .5 * s))], c * (1 + s), c * (1 - s), unit),
            S3=trade(H, L, C, i, -1, [(1, None)], c * (1 + s), c * (1 - 2 * s), unit)))
    return out


def report(D, cols, title):
    print(title)
    for nm, q in (("8 koin", D), ("2020-2022", D[D.yr <= 2022]), ("2023-2026", D[D.yr >= 2023]), ("BTC+ETH", D[D.sym.isin(["BTC", "ETH"])]),
                  ("BTC+ETH 2023-2026", D[D.sym.isin(["BTC", "ETH"]) & (D.yr >= 2023)])):
        parts = []
        for c in cols:
            x = q[c].dropna(); x = x[x != 0] if c in ("S1", "L3") else x
            parts.append(f"{c}: n {len(x)}, rata-rata {x.mean():+.2f}%, total {x.sum():+.0f}%, untung {100*(x > 0).mean():.0f}%")
        print(f"  {nm}: " + " | ".join(parts))


if __name__ == "__main__":
    Lg = pd.DataFrame([r for s in COINS for r in long_setups(s)])
    Sh = pd.DataFrame([r for s in COINS for r in short_setups(s)])
    report(Lg, ["L0", "L1", "L2", "L3", "L4", "L5"], "LONG pantulan (% modal per setup, risiko 1%)")
    report(Sh, ["S0", "S1", "S2", "S3"], "SHORT breakdown (% modal per setup, risiko 1%)")
