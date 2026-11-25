"""Papan sinyal dan akun kertas (paper) $100 untuk website.

Sistem yang dijalankan = System v1 (Principles 30, 33, 35): 10 metode di research/arena.py, hanya peringkat 3-5,
sinyal tren dilewati saat pasar berombak (efficiency ratio 20 hari < 0,3), dieksekusi SEKALI SEHARI: pemeriksaan pagi
sesudah penutupan hari UTC (07:00 WIB), masuk di penutupan jam 07:00-08:00 WIB, stop/target sebagai order di bursa,
order bersyarat untuk breakdown short dan limit beli untuk pantulan dipasang tiap pagi.

Akun kertas mulai $100 pada PAPER_START dan diputar ulang dari data setiap kali website dibangun (deterministik). Aturan
dibekukan: setiap perubahan aturan harus dicatat di Principles dan di PAPER_RULES, karena memutar ulang dengan aturan baru
akan mengubah riwayat akun kertas.

    python research/board.py        # cetak papan hari ini
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena, arena_chop as ch  # noqa: E402

PAPER_START = pd.Timestamp("2026-11-22").timestamp()
PAPER_RULES = "v1: 10 signals, score 3 to 5, choppy filter, once a day (Principles 30, 33, 35). Frozen 22 Nov 2026."
NAMES = {"M1": "Momentum 28d", "M2": "20-day breakout", "M3": "50-day average", "M4": "Overreaction", "M5": "RSI extremes",
         "M6": "Funding extremes", "M7": "Crowd ratio", "M8": "Capitulation day", "M9": "Bounce pullback", "M10": "Breakdown short"}
EXIT = {"M1": "checked at each Monday close (07:00 WIB Tuesday): held another week while the 28-day change keeps its sign", "M2": "close beyond the opposite 10-day extreme", "M3": "close back across the 50-day average",
        "M4": "after 3 days", "M5": "RSI crosses 50, or after 10 days", "M6": "after 7 days", "M7": "after 7 days",
        "M8": "target, stop, or after 7 days", "M9": "target 2R, stop, or after 30 days", "M10": "target, stop, or after 30 days"}
WIB = 7 * 3600


def wib(ts):
    return pd.to_datetime(int(ts) + WIB, unit="s").strftime("%Y-%m-%d %H:%M")


def r2(x):
    return None if x is None or x != x else round(float(x), 2)


def morning_hours(P):
    n = len(P["C"])
    return [i + 1 for i in P["D"].i.values if i + 1 < n]


def stake(rk, equity, dist, fm=1.0):
    risk = arena.RISK_STEP * rk * equity * fm
    return risk, min(risk / dist, arena.CAP * equity)


def waiting_orders(P, c, h, equity, paper):
    """Order yang dipasang pada pagi h dan berlaku sampai pagi berikutnya, untuk satu koin."""
    H, L, C, sw, volr = P["H"], P["L"], P["C"], P["sw"], P["volr"]; n = len(C); out = []
    coin = P["sym"][:3]
    held = {(o["m"], o["coin"]) for o in paper["open"]}
    pl = pd.Series(L).rolling(480).min().shift(1).values
    # breakdown short: order jual bersyarat di terendah 20 hari pagi itu
    lvl, s = pl[h], sw[h]
    T = paper["trades"]
    fills = [] if T.empty else list(T[(T.m == "M10") & (T.coin == coin)].t_entry)
    fills += [o["t_entry"] for o in paper["open"] if o["m"] == "M10" and o["coin"] == coin]
    recent = any(P["t"][h] - f < 72 * 3600 for f in fills)
    rk = arena.rank_of(P, h, -1); fm = ch.f2("M10", P, h, -1, rk)
    why = None
    if ("M10", coin) in held: why = "already holding this trade"
    elif recent: why = "last breakdown short filled less than 3 days ago"
    elif rk < 3: why = f"score {rk}, needs 3"
    elif fm <= 0: why = "market is choppy: trend signals skipped"
    risk, notional = stake(rk, equity, s)
    out.append(dict(signal=NAMES["M10"], coin=coin, side="Short", kind="Conditional sell (stop-market) at", level=r2(lvl),
                    stop=r2(lvl * (1 + s)), target=r2(lvl * (1 - s)), score=int(rk), risk=r2(risk), position=r2(notional),
                    active=why is None, why=why, filled=any(P["t"][h] <= f for f in fills)))
    # bounce pullback: limit beli di separuh pantulan, bila ada kejadian aktif dan pantulan sudah >= 1 ayunan
    ma = P["ma200h"]; last = -10**9; ev = None
    for i in range(max(1200, h - 961), h + 1):
        if L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i] and i - last >= 168:
            last = i
            if C[i] < ma[i]: ev = i
    if ev is not None:
        lo, pk = L[ev], H[ev]
        for k in range(ev + 1, h):
            if L[k] < lo: lo, pk = L[k], H[k]
            else: pk = max(pk, H[k])
        s9 = sw[ev]
        if pk / lo - 1 >= s9:
            e50 = lo + .5 * (pk - lo); stop = lo * .99; rk9 = arena.rank_of(P, h, 1)
            why = None
            if ("M9", coin) in held: why = "already holding this trade"
            elif rk9 < 3: why = f"score {rk9}, needs 3"
            risk, notional = stake(rk9, equity, (e50 - stop) / e50)
            out.append(dict(signal=NAMES["M9"], coin=coin, side="Long", kind="Limit buy at", level=r2(e50), stop=r2(stop),
                            target=r2(e50 + 2 * (e50 - stop)), score=int(rk9), risk=r2(risk), position=r2(notional),
                            active=why is None, why=why, filled=False))
    return out


def board(PS=None):
    PS = PS or [arena.prepare(s, live=True) for s in arena.COINS]
    tend = int(PS[0]["t"][-1]) + 3600
    paper = arena.simulate(PS, arena.METHODS, PAPER_START, tend, daily=True, min_rank=3, filt=ch.f2)
    eq = paper["equity_now"]
    h = morning_hours(PS[0])[-1]
    t_check = int(PS[0]["t"][h]) + 3600                  # penutupan jam pagi = saat masuk
    # sinyal harian pada pagi terakhir: diambil atau dilewati, dan alasannya
    today = []
    for c, P in enumerate(PS):
        j = arena.np.searchsorted(P["D"].i.values, h - 1)
        for m in arena.METHODS:
            if m in ("M9", "M10"): continue
            s = arena.daily_signals(P, m, j)
            if s is None: continue
            d, dist, tgt, maxh = s; rk = arena.rank_of(P, h, d); fm = ch.f2(m, P, h, d, rk)
            e = P["C"][h]; risk, notional = stake(rk, eq, dist)
            why = None if rk >= 3 and fm > 0 else (f"score {rk}, needs 3" if rk < 3 else "market is choppy: trend signals skipped")
            today.append(dict(signal=NAMES[m], coin=P["sym"][:3], side="Long" if d > 0 else "Short", score=int(rk),
                              price=r2(e), stop=r2(e * (1 - d * dist)), target=r2(tgt), exit=EXIT[m], risk=r2(risk),
                              position=r2(notional), taken=why is None, why=why))
    orders = [o for c, P in enumerate(PS) for o in waiting_orders(P, c, h, eq, paper)]
    opn = [dict(signal=NAMES[o["m"]], coin=o["coin"], side="Long" if o["d"] > 0 else "Short", score=int(o["rank"]),
                entered=wib(o["t_entry"] + 3600), entry=r2(o["entry"]), stop=r2(o["stop"]), target=r2(o["tgt"]),
                close_by=("next check " if o["m"] == "M1" else "") + wib(o["t_ext"] + 3600 + o["maxh"] * 3600) if o["maxh"] < 10**8 else "on the exit signal",
                now=r2(o["px"]), pnl=r2(o["upnl"]), exit=EXIT[o["m"]]) for o in paper["open"]]
    T = paper["trades"]; T = T[T.why != "end"] if not T.empty else T
    closed = [] if T.empty else [dict(signal=NAMES[x.m], coin=x.coin, side="Long" if x.d > 0 else "Short", score=int(x["rank"]),
                                      entered=wib(x.t_entry + 3600), closed=wib(x.t_out + 3600), entry=r2(x.entry), exit=r2(x.exit),
                                      pnl=r2(x.pnl), R=r2(x.R), why=x.why) for _, x in T.iterrows()]
    cv = paper["curve"]
    return dict(rules=PAPER_RULES, start=wib(PAPER_START), check=wib(t_check), data_to=wib(tend),
                equity=r2(eq), cash=r2(paper["final"] if not paper["open"] else eq - sum(o["upnl"] for o in paper["open"])),
                closed_n=len(closed), wins=sum(1 for x in closed if x["pnl"] > 0),
                curve=dict(t=[int(x) for x in cv.t], v=[r2(x) for x in cv.equity]),
                today=today, orders=orders, open=opn, closed=closed[::-1],
                prices={P["sym"][:3]: r2(P["C"][-1]) for P in PS})


if __name__ == "__main__":
    import json
    print(json.dumps(board(), indent=1)[:6000])
