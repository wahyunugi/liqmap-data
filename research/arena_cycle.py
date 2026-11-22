"""Arena + siklus 4 tahun (prinsip 7). ATURAN DITULIS DAN DI-COMMIT SEBELUM HASIL DILIHAT (22 Nov 2026).

Fase dari tanggal halving H (diketahui jauh sebelumnya): 2016-07-09, 2020-05-11, 2024-04-20.
  naik     H sampai H + 540 hari         (puncak siklus 2017 dan 2021 datang 526 dan 548 hari sesudah halving;
                                          jendela ini sudah bisa diketahui sebelum 2024)
  turun    H + 540 sampai H + 905 hari   (dasar 2018 dan 2022 kira-kira satu tahun sesudah puncak)
  pulih    H + 905 sampai halving berikut -> diperlakukan condong long seperti fase naik
Condong long = fase naik atau pulih; condong short = fase turun.
Dasar = sistem arena semua metode, hanya peringkat 3-5 (prinsip 30), risiko 0,5% x peringkat, batas 3x.
  C0  dasar (tanpa siklus)
  C1  siklus sebagai kondisi ke-5: +1 peringkat bila arah trade searah fase (maks 5)
  C2  aturan Wahyu: di fase condong long, short hanya bila peringkat >= 4 ("potensi pullback tinggi");
      di fase condong short, long hanya bila peringkat >= 4
  C3  ketat: fase condong long -> tidak ada short; fase condong short -> tidak ada long
Dilaporkan per tahun kalender (akun $100 baru tiap tahun) dan 2024-2026 bersambung (penentu), juga separuh risiko.
    python research/arena_cycle.py
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena  # noqa: E402

HALV = [pd.Timestamp(x).timestamp() for x in ("2016-07-09", "2020-05-11", "2024-04-20")]


def phase(ts):
    h = max(x for x in HALV if x <= ts); d = (ts - h) / 86400
    return 1 if d < 540 else (-1 if d < 905 else 1)


def bonus(d, ts): return 1 if d == phase(ts) else 0
def gate2(d, rk, ts): return d == phase(ts) or rk >= 4
def gate3(d, rk, ts): return d == phase(ts)


VARS = {"C0": dict(), "C1": dict(bonus=bonus), "C2": dict(gate=gate2), "C3": dict(gate=gate3)}

if __name__ == "__main__":
    PS = [arena.prepare(s) for s in arena.COINS]; tend = int(PS[0]["t"][-1]) + 3600
    for st, lab in ((None, "risiko penuh"), (0.0025, "separuh risiko")):
        print(f"\n=== {lab} ===")
        print("tahun  fase(awal->akhir) | " + " | ".join(VARS))
        for y in range(2020, 2027):
            a = pd.Timestamp(f"{y}-01-01").timestamp(); b = min(pd.Timestamp(f"{y + 1}-01-01").timestamp(), tend)
            cells = []
            for v, kw in VARS.items():
                r = arena.simulate(PS, arena.METHODS, a, b, min_rank=3, step=st, **kw); cells.append(f"${r['final']:.0f} ({r['dd']:.0f}%)")
            print(f"{y}  {'+' if phase(a) > 0 else '-'}->{'+' if phase(b - 1) > 0 else '-'} | " + " | ".join(cells))
        for nm, a in (("2024-2026 bersambung", arena.OOS), ("2020-2026 bersambung", pd.Timestamp("2020-01-01").timestamp())):
            cells = []
            for v, kw in VARS.items():
                r = arena.simulate(PS, arena.METHODS, a, tend, min_rank=3, step=st, **kw); cells.append(f"{v} ${r['final']:.0f} ({r['dd']:.0f}%)")
            print(f"{nm}: " + " | ".join(cells))
    print("\nfase sekarang (22 Nov 2026):", "condong long (pulih)" if phase(pd.Timestamp('2026-11-22').timestamp()) > 0 else "condong short")
