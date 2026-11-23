"""Peringatan "big move info" ke ponsel lewat ntfy (https://ntfy.sh), dijalankan tiap jam oleh workflow collect.

Aturan (Principles 14 dan 36, research/big_move_alert.py):
  - peringatan  = jam pertama volume futures 24 jam >= 2,6x median 30 hari, sekali per episode; episode berakhir sesudah
                  24 jam berturut-turut di bawah 2,6x
  - peringatan kuat = jam pertama >= 4x di dalam episode
  - pembaruan   = condong kerumunan berbalik di dalam episode (naik <-> turun)
  - ukuran gerakan besar BM = 3x ayunan 6 jam normal; pesan memberi level naik dan turun (harga +/- 1 BM)
  - condong (lemah): rasio akun Binance < 1,5 -> naik, > 2,5 -> turun, di antaranya tidak condong
Hanya jam lengkap yang diproses, berurutan, sejak jam terakhir yang tercatat (data/alerts/state.json), sehingga dua jalan
dalam satu jam tidak mengirim dua kali. Peringatan untuk jam yang sudah lebih dari 6 jam lalu hanya dicatat (tidak dikirim).
Jalan pertama memutar ulang 30 hari terakhir tanpa mengirim, untuk mengisi status episode.
Topik ntfy dari rahasia NTFY_TOPIC; bila kosong, peringatan hanya dicatat di data/alerts/log.csv.

    python collector/alerts.py            # biasa
    python collector/alerts.py --test     # kirim satu pesan uji ke topik, lalu jalan biasa
"""
import csv, json, os, sys, time, urllib.request
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research"))
import arena  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT"]
DIR = os.path.join(ROOT, "data", "alerts")
STATE, LOG = os.path.join(DIR, "state.json"), os.path.join(DIR, "log.csv")
COLS = ["t", "time_wib", "coin", "kind", "volr", "price", "bm_pct", "up", "down", "acc", "lean", "sent"]
SITE = "https://wahyunugi.github.io/liqmap-data/"


def wib(ts):
    return pd.to_datetime(int(ts) + 7 * 3600, unit="s").strftime("%d %b %H:%M")


def fmt(v, coin):
    return f"{v:,.0f}" if coin == "BTC" else f"{v:,.2f}"


def lean_of(a):
    if a != a: return 0
    return 1 if a < 1.5 else -1 if a > 2.5 else 0


def message(r):
    c = r["coin"]; kind = r["kind"]
    head = {"alert": "big move likely", "strong": "very high volume", "flip": "crowd lean flipped"}[kind]
    lean = {1: f"slight UP lean (crowd {r['acc']:.2f} accounts long per short, under 1.5)",
            -1: f"slight DOWN lean (crowd {r['acc']:.2f} accounts long per short, over 2.5)",
            0: f"no lean (crowd {r['acc']:.2f})" if r["acc"] == r["acc"] else "no lean (crowd ratio missing)"}[r["lean"]]
    chance = "74%" if kind == "strong" else "66%"
    body = (f"Volume {r['volr']:.1f}x normal. Price {fmt(r['price'], c)}.\n"
            f"Big move size about {r['bm_pct']:.1f}%.\n"
            f"Up level {fmt(r['up'], c)} / Down level {fmt(r['down'], c)}\n"
            f"Past alerts: one level hit within 24h {chance}; up first 36%, down first 29%, neither 34%.\n"
            f"Direction: {lean}. Weak: right 56 to 60% on 8 coins, about 50% on BTC and ETH in 2024 to 2026.\n"
            f"For the full read, ask Claude: big move info. Not financial advice.")
    return f"{c} {head} ({wib(r['t'])} WIB)", body


def send(topic, title, body, prio):
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), method="POST",
                                 headers={"Title": title, "Priority": str(prio), "Tags": "warning", "Click": SITE})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status == 200


def series(sym):
    h = arena.load_live(sym)
    C = h.close.values
    s6 = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(6)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    return h.t.values, C, s6, volr, h.acc_lsr.values


def run(now=None, topic=None):
    os.makedirs(DIR, exist_ok=True)
    now = now or int(time.time()); topic = topic if topic is not None else os.environ.get("NTFY_TOPIC", "").strip()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    new = []
    for sym in COINS:
        coin = sym[:3]; t, C, s6, volr, acc = series(sym)
        st = state.get(coin)
        first = st is None
        if first:
            st = dict(last_t=int(t[-1]) - 30 * 86400, inep=False, below=0, strong=False, lean=0)
        for k in np.nonzero(t > st["last_t"])[0]:
            v = volr[k]; st["last_t"] = int(t[k])
            if not (v == v and s6[k] == s6[k]): continue
            kind = None; ln = lean_of(acc[k])
            if v >= 2.6:
                st["below"] = 0
                if not st["inep"]:
                    st.update(inep=True, strong=False, lean=ln); kind = "alert"
                elif v >= 4 and not st["strong"]:
                    kind = "strong"
                elif ln and st["lean"] and ln != st["lean"]:
                    kind = "flip"
                if v >= 4: st["strong"] = True
                if ln: st["lean"] = ln
            else:
                st["below"] += 1
                if st["below"] >= 24: st["inep"] = False
            if kind:
                bm = 3 * s6[k]; p = C[k]; tc = int(t[k]) + 3600          # jam selesai
                r = dict(t=tc, time_wib=wib(tc), coin=coin, kind=kind, volr=round(float(v), 2), price=float(p),
                         bm_pct=round(100 * bm, 2), up=float(p * (1 + bm)), down=float(p * (1 - bm)),
                         acc=float(acc[k]) if acc[k] == acc[k] else float("nan"), lean=ln, sent="")
                if first: r["sent"] = "replay"
                elif now - tc > 6 * 3600: r["sent"] = "late, not sent"
                elif not topic: r["sent"] = "no topic"
                else:
                    title, body = message(r)
                    try: r["sent"] = "yes" if send(topic, title, body, 4 if kind == "strong" else 3) else "failed"
                    except Exception as e: r["sent"] = f"failed: {e!r}"[:80]
                new.append(r)
        state[coin] = st
    json.dump(state, open(STATE + ".tmp", "w"), indent=1); os.replace(STATE + ".tmp", STATE)
    if new:
        exists = os.path.exists(LOG)
        with open(LOG, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if not exists: w.writeheader()
            for r in new:
                w.writerow({k: (round(r[k], 4) if isinstance(r[k], float) else r[k]) for k in COLS})
    for r in new:
        print(f"{r['time_wib']} WIB {r['coin']} {r['kind']}: volume {r['volr']}x, price {r['price']:.2f}, sent={r['sent']}")
    print(f"alerts: {len(new)} new; state " + ", ".join(f"{c} inep={s['inep']} last={wib(s['last_t'])}" for c, s in state.items()))
    return new


if __name__ == "__main__":
    if "--test" in sys.argv:
        tp = os.environ.get("NTFY_TOPIC", "").strip()
        if tp: print("pesan uji terkirim:", send(tp, "Liqmap test alert", "If you can read this, big move alerts will reach this phone.", 3))
        else: print("NTFY_TOPIC kosong: pesan uji tidak dikirim")
    run()
