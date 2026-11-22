"""Sekali sehari: apakah sistem tetap jalan bila orang hanya memeriksa satu kali tiap pagi (sesudah 07:00 WIB)?
DITULIS DAN DI-COMMIT SEBELUM HASIL DILIHAT (22 Nov 2026).

Versi sekali sehari (research/arena.py, simulate(daily=True)):
  - sinyal harian dibaca pukul 07:00 WIB dan dieksekusi di harga penutupan jam 07:00-08:00 WIB (satu jam terlambat);
    keluar karena sinyal juga di jam itu.
  - stop dan target tetap jalan tiap jam (order yang menunggu di bursa).
  - batas waktu ditutup pada pemeriksaan pagi pertama sesudah waktunya habis.
  - M10 (breakdown short): tiap pagi dipasang order jual bersyarat di terendah 20 hari pagi itu, berlaku 24 jam, terisi di
    harga itu; peringkat dan saringan dihitung saat dipasang.
  - M9 (pantulan): tiap pagi dipasang limit beli di separuh pantulan (dari terendah dan puncak sampai pagi itu), stop
    terendah - 1%, target 2R; berlaku sampai pagi berikutnya.
Dibandingkan dengan versi per jam untuk: v1 (peringkat 3-5 + saringan berombak) dan versi $688 (peringkat 3-5 + poin siklus).
Penentu: 2024-2026; juga 2020-2023.
    python research/arena_daily.py
"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena, arena_chop as ch, arena_cycle as ac  # noqa: E402

if __name__ == "__main__":
    PS = [arena.prepare(s) for s in arena.COINS]; tend = int(PS[0]["t"][-1]) + 3600
    SYS = {"v1": dict(min_rank=3, filt=ch.f2), "$688": dict(min_rank=3, bonus=ac.bonus)}
    for nm, a, b in (("2024-2026 (penentu)", arena.OOS, tend), ("2020-2023", pd.Timestamp("2020-01-01").timestamp(), arena.OOS)):
        print(f"\\n=== {nm} ===")
        for s, kw in SYS.items():
            for dl in (False, True):
                r = arena.simulate(PS, arena.METHODS, a, b, daily=dl, **kw); st = ch.stats(r); T = r["trades"]
                print(f"  {s:5s} {'sekali sehari' if dl else 'per jam      '}: ${st['final']:7.0f} | turun terdalam {st['dd']:6.1f}% | "
                      f"{st['n']} trade, rugi {st['lose']}, kena stop {st['stops']}, menang {st['win']:.0f}% | rata-rata {T.R.mean():+.2f}R")
