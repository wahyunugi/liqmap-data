"""Signal board messages to the phone (ntfy), run every hour by the collect workflow after collector/alerts.py.

1. Morning check: on the first run after the UTC day closes (07:00 WIB), the System v1 daily signals of that day are
   computed (research/arena.py daily_signals, rank_of, choppy filter research/arena_chop.py f2, as research/board.py).
   Every signal that would be taken (score 3 to 5, not filtered) is sent, with the provisional entry (the 07:00 WIB price;
   the system enters at the 07:00 to 08:00 WIB close), stop, target and exit rule.
   GREAT = score 5, or at least two different tested signals the same way on the same coin, counting trades already open
   in the paper account (the grading used in market updates). A Great message is sent with high priority.
2. Heads-up: the first hour of a UTC day in which the Binance crowd (accounts long per short) is above 3 while the paper
   account holds a short on that coin: the crowd-ratio short (method M7, crowd above 3 at the daily close) would then
   make a Great short at the next morning check. Not a signal yet; the value that counts is the last reading before
   07:00 WIB.
Messages older than 3 hours are only recorded. State in data/alerts/board_state.json, log in data/alerts/board_log.csv.

    python collector/board_alert.py
"""
import csv, json, os, sys, time
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research")); sys.path.insert(0, os.path.join(ROOT, "collector"))
import arena, arena_chop as ch, board  # noqa: E402
from alerts import send, fmt, wib  # noqa: E402

DIR = os.path.join(ROOT, "data", "alerts")
STATE, LOG = os.path.join(DIR, "board_state.json"), os.path.join(DIR, "board_log.csv")
COLS = ["t", "time_wib", "coin", "kind", "title", "sent"]


def morning(P, j, opn):
    """Signals taken at the morning check of day j for one coin -> list of dicts."""
    coin = P["sym"][:3]; i = int(P["D"].i.values[j]); out = []
    for m in arena.METHODS:
        if m in ("M9", "M10"): continue                     # these two are resting orders, shown on the board
        s = arena.daily_signals(P, m, j)
        if s is None: continue
        d, dist, tgt, maxh = s; rk = arena.rank_of(P, i, d)
        if rk < 3 or ch.f2(m, P, i, d, rk) <= 0: continue
        if any(o["coin"] == coin and o["signal"] == board.NAMES[m] for o in opn): continue   # already holding it
        e = float(P["C"][i])
        out.append(dict(m=m, signal=board.NAMES[m], coin=coin, d=d, side="Short" if d < 0 else "Long", score=int(rk),
                        price=e, stop=e * (1 - d * dist), target=tgt, exit=board.EXIT[m]))
    for x in out:
        same = {y["signal"] for y in out if y["side"] == x["side"]} | {o["signal"] for o in opn if o["coin"] == coin and o["side"] == x["side"]}
        x["great"] = x["score"] >= 5 or len(same) >= 2
    return out


def text(x):
    c = x["coin"]; tg = f"Take profit {fmt(x['target'], c)}. " if x["target"] else ""
    head = f"{c} GREAT {x['side'].upper()}" if x["great"] else f"{c} new {x['side'].lower()}"
    body = (f"{x['signal']}, score {x['score']} of 5 (risk {x['score'] * 0.5:.1f}% of the account).\n"
            f"Entry: the 07:00 to 08:00 WIB close (07:00 price {fmt(x['price'], c)}).\n"
            f"Invalidation (stop) about {fmt(x['stop'], c)}. {tg}Exit: {x['exit']}.\n"
            + ("Great = two tested signals the same way, or score 5.\n" if x["great"] else "")
            + "Details on the website signal board. Not financial advice.")
    return f"{head}: {x['signal']}", body


def run(now=None, topic=None, PS=None):
    now = now or int(time.time()); topic = topic if topic is not None else os.environ.get("NTFY_TOPIC", "").strip()
    PS = PS or [arena.prepare(s, live=True) for s in arena.COINS]
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    opn = board.board(PS)["open"]; rows = []
    for P in PS:
        coin = P["sym"][:3]; st = state.setdefault(coin, {}); D = P["D"]; j = len(D) - 1
        day_close = int(D.t.values[j]) + 3600
        msgs = []
        if st.get("day", 0) < day_close:
            st["day"] = day_close
            msgs += [(day_close, "great" if x["great"] else "signal", *text(x)) for x in morning(P, j, opn)]
        a = P["acc"][-1]; tday = int(P["t"][-1]) // 86400
        short_open = any(o["coin"] == coin and o["side"] == "Short" for o in opn)
        if a == a and a > 3 and short_open and st.get("heads_day", -1) < tday:
            st["heads_day"] = tday; tc = int(P["t"][-1]) + 3600
            msgs.append((tc, "heads-up", f"{coin} Great short may form at 07:00 WIB",
                         f"Crowd {a:.2f} accounts long per short, above 3, while a short is open.\n"
                         f"If the crowd is still above 3 at the 07:00 WIB daily close, the crowd-ratio short fires "
                         f"and joins the open short: two tested signals = Great short.\n"
                         f"Not a signal yet. Price {fmt(P['C'][-1], coin)}. Not financial advice."))
        for tc, kind, title, body in msgs:
            if now - tc > 3 * 3600: sent = "late, not sent"
            elif not topic: sent = "no topic"
            else:
                try: sent = "yes" if send(topic, title, body, 5 if kind == "great" else 4) else "failed"
                except Exception as e: sent = f"failed: {e!r}"[:80]
            rows.append(dict(t=tc, time_wib=wib(tc), coin=coin, kind=kind, title=title, sent=sent, body=body))
    json.dump(state, open(STATE + ".tmp", "w"), indent=1); os.replace(STATE + ".tmp", STATE)
    if rows:
        new = not os.path.exists(LOG)
        with open(LOG, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            if new: w.writeheader()
            w.writerows(rows)
    for r in rows: print(f"{r['time_wib']} WIB {r['coin']} {r['kind']}: {r['title']} sent={r['sent']}")
    print(f"board alerts: {len(rows)} new")
    return rows


if __name__ == "__main__":
    run()
