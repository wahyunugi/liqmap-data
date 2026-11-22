"""Arena + saringan pasar berombak. ATURAN DITULIS DAN DI-COMMIT SEBELUM HASIL DILIHAT (22 Nov 2026).

Dasar = sistem arena semua metode, hanya peringkat 3-5 (prinsip 30), TANPA poin siklus. Ukuran berombak dibaca dari
hari lengkap terakhir sebelum masuk, ambang baku dari literatur (tidak disetel):
  ER20  Kaufman efficiency ratio 20 hari = |perubahan 20 hari| / jumlah |perubahan harian| (0 berombak, 1 lurus).
        Berombak bila ER20 < 0,3.
  ADX14 Wilder: berombak bila ADX14 < 20.
  CI14  Choppiness Index (Dreiss): berombak bila CI14 > 61,8.
Metode tren = M1, M2, M3, M10 (momentum, breakout, MA50, breakdown); lainnya metode pembalikan.
  F0  tanpa saringan
  F1  ER20 berombak -> taruhan semua trade separuh
  F2  ER20 berombak -> lewati trade metode tren (pembalikan tetap)
  F3  ADX14 berombak -> lewati trade metode tren
  F4  CI14 berombak -> taruhan semua trade separuh
  CY  poin siklus (prinsip 31), untuk dibandingkan dengan ukuran yang sama
Ukuran keberhasilan (permintaan Wahyu: lebih sedikit trade rugi dan penurunan lebih dangkal lebih penting daripada untung
besar): penurunan terdalam, jumlah trade rugi, kena stop, lalu akhir akun dan untung dibagi penurunan terdalam.
Penentu: 2024-2026 bersambung; per tahun kalender ditampilkan.
    python research/arena_chop.py
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena, arena_cycle  # noqa: E402

TREND = {"M1", "M2", "M3", "M10"}


def day_row(P, k):
    j = np.searchsorted(P["D"].i.values, k, side="right") - 1
    return P["rec"][j] if j >= 0 else None


def f1(m, P, k, d, rk):
    r = day_row(P, k); return 0.5 if r is not None and r.er20 == r.er20 and r.er20 < 0.3 else 1.0
def f2(m, P, k, d, rk):
    r = day_row(P, k); return 0.0 if m in TREND and r is not None and r.er20 == r.er20 and r.er20 < 0.3 else 1.0
def f3(m, P, k, d, rk):
    r = day_row(P, k); return 0.0 if m in TREND and r is not None and r.adx14 == r.adx14 and r.adx14 < 20 else 1.0
def f4(m, P, k, d, rk):
    r = day_row(P, k); return 0.5 if r is not None and r.ci14 == r.ci14 and r.ci14 > 61.8 else 1.0


VARS = {"F0": {}, "F1": dict(filt=f1), "F2": dict(filt=f2), "F3": dict(filt=f3), "F4": dict(filt=f4), "CY": dict(bonus=arena_cycle.bonus)}


def stats(r):
    T = r["trades"]; gain = r["final"] - 100
    return dict(final=r["final"], dd=r["dd"], n=len(T), lose=int((T.pnl <= 0).sum()), stops=int((T.why == "stop").sum()),
                win=100 * (T.pnl > 0).mean() if len(T) else 0, ratio=gain / abs(r["dd"]) if r["dd"] else np.nan)


if __name__ == "__main__":
    PS = [arena.prepare(s) for s in arena.COINS]; tend = int(PS[0]["t"][-1]) + 3600
    for nm, a in (("2024-2026 bersambung (penentu)", arena.OOS), ("2020-2023 bersambung", pd.Timestamp("2020-01-01").timestamp())):
        b = tend if nm.startswith("2024") else arena.OOS
        print(f"\n=== {nm} ===")
        for v, kw in VARS.items():
            s = stats(arena.simulate(PS, arena.METHODS, a, b, min_rank=3, **kw))
            print(f"  {v}: ${s['final']:7.0f} | turun terdalam {s['dd']:6.1f}% | {s['n']} trade, rugi {s['lose']}, kena stop {s['stops']}, menang {s['win']:.0f}% | untung/turun {s['ratio']:.1f}")
    print("\nper tahun: akhir $ (turun terdalam %, trade rugi)")
    print("tahun | " + " | ".join(VARS))
    for y in range(2020, 2027):
        a = pd.Timestamp(f"{y}-01-01").timestamp(); b = min(pd.Timestamp(f"{y + 1}-01-01").timestamp(), tend); cells = []
        for v, kw in VARS.items():
            s = stats(arena.simulate(PS, arena.METHODS, a, b, min_rank=3, **kw)); cells.append(f"${s['final']:.0f} ({s['dd']:.0f}%, {s['lose']})")
        print(f"{y} | " + " | ".join(cells))
