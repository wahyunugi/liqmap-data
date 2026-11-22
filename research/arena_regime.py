"""Arena + aturan menurut jenis pasar (aturan "cair"). DITULIS DAN DI-COMMIT SEBELUM HASIL DILIHAT (22 Nov 2026).

Jenis pasar per koin per hari, dari hari lengkap terakhir sebelum masuk; hanya ukuran yang sudah dipakai, ambang sama:
  berombak  ER20 < 0,3 (Kaufman efficiency ratio 20 hari, seperti prinsip 33)
  naik      harga > MA200 harian dan perubahan 28 hari > 0
  turun     harga < MA200 dan perubahan 28 hari < 0
  berbalik  selain itu (bergerak lurus tetapi melawan fase 200 hari: reli di pasar turun atau koreksi di pasar naik)
Aturan per jenis (dari logika dan prinsip lama, tidak disetel). Catatan sebelum uji: trade melawan tren di pasar naik/turun
paling tinggi bernilai 3 (poin fase dan tren tidak mungkin didapat), jadi syarat "peringkat 4-5" pada rancangan di chat
diganti dengan membatasi metodenya:
  naik      long dari semua sinyal; short hanya dari M7 (rasio kerumunan > 3)
  turun     short dari semua sinyal; long hanya dari M8 dan M9 (kapitulasi dan pantulan, dirancang untuk pasar turun),
            sehingga poin kerumunan + funding saja tidak bisa meloloskan long (masalah 2022)
  berombak  sinyal tren (M1, M2, M3, M10) dilewati; sinyal lain dengan taruhan separuh
  berbalik  taruhan separuh dan hanya peringkat 4-5
Dasar pembanding = sistem v1: semua metode, peringkat 3-5, saringan berombak F2 (prinsip 33).
  RG   aturan di atas
  RGF  sama, tanpa taruhan separuh (memisahkan efek pemilihan dari efek taruhan kecil)
Ukuran: penurunan terdalam, trade rugi, kena stop, lalu akhir akun. Penentu 2024-2026; per tahun juga.
Cek keterlambatan: porsi hari tiap jenis, rata-rata lama satu jenis bertahan, dan perubahan harga 30 hari sesudahnya
per jenis (bila jenis pasar tidak memberi tahu apa-apa tentang 30 hari ke depan, keterlambatannya terlalu besar).
    python research/arena_regime.py
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena, arena_chop as ch  # noqa: E402

TREND = {"M1", "M2", "M3", "M10"}


def regime(r):
    if r is None or not (r.er20 == r.er20 and r.ma200 == r.ma200 and r.r28 == r.r28):
        return "unknown"
    if r.er20 < 0.3: return "chop"
    if r.c > r.ma200 and r.r28 > 0: return "bull"
    if r.c < r.ma200 and r.r28 < 0: return "bear"
    return "turn"


def make(halve=True):
    h = 0.5 if halve else 1.0
    def f(m, P, k, d, rk):
        g = regime(ch.day_row(P, k))
        if g == "bull": return 1.0 if d > 0 or m == "M7" else 0.0
        if g == "bear": return 1.0 if d < 0 or m in ("M8", "M9") else 0.0
        if g == "chop": return 0.0 if m in TREND else h
        if g == "turn": return h if rk >= 4 else 0.0
        return 1.0
    return f


VARS = {"v1": dict(filt=ch.f2), "RG": dict(filt=make(True)), "RGF": dict(filt=make(False))}

if __name__ == "__main__":
    PS = [arena.prepare(s) for s in arena.COINS]; tend = int(PS[0]["t"][-1]) + 3600
    print("cek jenis pasar (hari, porsi, lama rata-rata bertahan, perubahan 30 hari berikutnya median / naik%):")
    for P in PS:
        D = P["D"].copy(); D["g"] = [regime(r) for r in P["rec"]]; D["f30"] = D.c.shift(-30) / D.c - 1
        D = D[D.g != "unknown"]; runs = (D.g != D.g.shift()).cumsum(); ln = D.groupby(runs).g.agg(["first", "size"])
        for g in ("bull", "bear", "chop", "turn"):
            q = D[D.g == g]; L = ln[ln["first"] == g]["size"]
            print(f"  {P['sym'][:3]} {g:5s}: {100*len(q)/len(D):3.0f}% hari, bertahan rata-rata {L.mean():4.1f} hari, "
                  f"30 hari kemudian median {100*q.f30.median():+5.1f}%, naik {100*(q.f30 > 0).mean():3.0f}%")
    for nm, a, b in (("2024-2026 bersambung (penentu)", arena.OOS, tend), ("2020-2023 bersambung", pd.Timestamp("2020-01-01").timestamp(), arena.OOS)):
        print(f"\n=== {nm} ===")
        for v, kw in VARS.items():
            s = ch.stats(arena.simulate(PS, arena.METHODS, a, b, min_rank=3, **kw))
            print(f"  {v:4s}: ${s['final']:6.0f} | turun terdalam {s['dd']:6.1f}% | {s['n']} trade, rugi {s['lose']}, kena stop {s['stops']}, menang {s['win']:.0f}% | untung/turun {s['ratio']:.1f}")
    print("\nper tahun: akhir $ (turun terdalam %, trade rugi)")
    for y in range(2020, 2027):
        a = pd.Timestamp(f"{y}-01-01").timestamp(); b = min(pd.Timestamp(f"{y + 1}-01-01").timestamp(), tend); cells = []
        for v, kw in VARS.items():
            s = ch.stats(arena.simulate(PS, arena.METHODS, a, b, min_rank=3, **kw)); cells.append(f"{v} ${s['final']:.0f} ({s['dd']:.0f}%, {s['lose']})")
        print(f"  {y}: " + " | ".join(cells))
