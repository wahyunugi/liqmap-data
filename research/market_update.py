"""Numbers for a "market update": what changed since the previous update, from the collected data only.

    python research/market_update.py "2026-11-27 22:00"     # previous update time in WIB (UTC+7)

Prints per coin (BTC, ETH): price change and range since then, crowd (Binance accounts long per short), open positions,
funding per exchange (% per 8 hours), Coinbase premium, spot net aggressive buying, liquidations, Hyperliquid big-account
long share, liquidation clusters and large-account changes; then ETF flows and stablecoins; then the risk-panel cell with
the fresh crowd ratio, the liquidation map totals (research/bands.js), scores and the 200-day picture.
Run python site/build.py first so the liquidation map and the paper account use the newest data.
"""
import glob, json, os, subprocess, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research"))
import arena  # noqa: E402

WIB = 7 * 3600
RISK = [[[73, 105], [59, 98], [132, 204]], [[50, 91], [39, 101], [91, 195]], [[19, 45], [8, 53], [27, 103]]]   # site/app.js
HL_EDGES = {"BTC": list(range(52000, 72001, 2000)), "ETH": list(range(1450, 2001, 50))}


def rd(kind, sym, sub="5min", ex=None):
    pat = f"{ROOT}/data/{kind}/{sub}/{sym}_{ex + '_' if ex else ''}20*.csv"
    fs = sorted(glob.glob(pat))[-2:]
    return pd.concat([pd.read_csv(f) for f in fs]).drop_duplicates("t").sort_values("t").reset_index(drop=True)


def at(df, t, col):
    x = df[df.t <= t]
    return x[col].iloc[-1] if len(x) else np.nan


def wib(t):
    return pd.to_datetime(int(t) + WIB, unit="s").strftime("%d %b %H:%M")


def coin_block(sym, ref):
    c = sym[:3]; o = rd("ohlcv", sym); now = int(o.t.iloc[-1]); px = o.c.iloc[-1]
    p_ref = at(o, ref - 300, "c"); w = o[o.t >= ref]
    out = dict(coin=c, px=px, now=now, p_ref=p_ref)
    print(f"\n##### {c}  data to {wib(now + 300)} WIB  price {px}")
    print(f"  24h {100 * (px / at(o, now - 86400, 'c') - 1):+.2f}%  7d {100 * (px / at(o, now - 7 * 86400, 'c') - 1):+.2f}%")
    lo, hi = w.l.idxmin(), w.h.idxmax()
    print(f"  since prev: then {p_ref}, change {100 * (px / p_ref - 1):+.2f}%, low {w.l[lo]} at {wib(w.t[lo])}, high {w.h[hi]} at {wib(w.t[hi])} WIB")
    L = rd("long_short_ratio", sym)
    out["acc"] = L.r.iloc[-1]
    print(f"  crowd now {L.r.iloc[-1]:.2f} ({L.l.iloc[-1]:.1f}% long), at prev {at(L, ref, 'r'):.2f}, 24h ago {at(L, now - 86400, 'r'):.2f}")
    oi = rd("open_interest", sym)
    def oi_usd(t):
        v = at(oi, t, "c") * at(o, t, "c")
        for ex in ("bybit", "okx"):
            v += at(rd("markets", sym, "fut_oi/5min", ex), t, "oi_usd")
        return v
    a, b, d = oi_usd(now), oi_usd(now - 86400), oi_usd(ref)
    print(f"  open positions (Binance+Bybit+OKX, USD) {a / 1e9:.2f}B, 24h {100 * (a / b - 1):+.2f}%, since prev {100 * (a / d - 1):+.2f}%"
          f" | Binance in coins 24h {100 * (oi.c.iloc[-1] / at(oi, now - 86400, 'c') - 1):+.2f}%")
    fund = {ex: round(rd("markets", sym, "funding/1hour", ex).c.iloc[-1], 4) for ex in ("binance", "bybit", "okx")}
    print(f"  funding latest %/8h {fund}")
    pr = rd("premium", sym); p24 = pr[pr.t > now - 86400]
    print(f"  Coinbase premium 24h avg {p24.prem.mean():+.4f}% latest {pr.prem.iloc[-1]:+.4f}%")
    for ex in ("coinbase", "binance"):
        s = rd("spot", sym, "5min", ex); s = s[s.t > now - 86400].merge(o[["t", "c"]], on="t", how="left")
        print(f"  spot {ex} 24h net aggressive buy ${((2 * s.tb - s.v) * s.c).sum() / 1e6:+.0f}M")
    lq = rd("liquidations", sym); l24 = lq[lq.t > now - 86400]; lr = lq[lq.t >= ref]
    print(f"  liquidations 24h longs ${l24.l.sum() / 1e6:.1f}M shorts ${l24.s.sum() / 1e6:.1f}M | since prev longs ${lr.l.sum() / 1e6:.1f}M shorts ${lr.s.sum() / 1e6:.1f}M")
    hs = pd.read_csv(sorted(glob.glob(f"{ROOT}/data/hyperliquid/summary/*.csv"))[-1]); hs = hs[hs.coin == c]
    r, rp = hs.iloc[-1], hs[hs.t <= ref].iloc[-1]
    big = lambda r: 100 * r.big_szL / (r.big_szL + r.big_szS)
    print(f"  Hyperliquid big long share {big(r):.1f}% (prev {big(rp):.1f}%), all {100 * r.szL / (r.szL + r.szS):.1f}%")
    pf = json.load(open(f"{ROOT}/data/hyperliquid/profile/{c}.json")); e = HL_EDGES[c]
    for side in ("liqL", "liqS"):
        bk = {f"{e[i]}-{e[i + 1]}": 0 for i in range(len(e) - 1)}
        for k, v in pf[side].items():
            for i in range(len(e) - 1):
                if e[i] <= float(k) < e[i + 1]: bk[f"{e[i]}-{e[i + 1]}"] += round(v)
        print(f"  HL {side} {c}: " + ", ".join(f"{k}:{v}" for k, v in bk.items() if v))
    wv = pd.read_csv(sorted(glob.glob(f"{ROOT}/data/hyperliquid/whales/events_*.csv"))[-1])
    wv = wv[(wv.coin == c) & (wv.t >= ref)]; dv = (wv.sz1 - wv.sz0) * wv.mark
    print(f"  large accounts since prev: {len(wv)} changes, toward long ${dv[dv > 0].sum() / 1e6:.0f}M, toward short ${-dv[dv < 0].sum() / 1e6:.0f}M")
    h = arena.load_live(sym); v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).iloc[-1]
    out["volr"] = volr
    return out


def main():
    ref = int((pd.Timestamp(sys.argv[1]) - pd.Timedelta(hours=7)).timestamp())
    res = [coin_block(s, ref) for s in ("BTCUSDT", "ETHUSDT")]
    st = pd.read_csv(f"{ROOT}/data/stablecoins/daily.csv")
    print(f"\nstablecoins {st.date.iloc[-1]} ${st.total.iloc[-1] / 1e9:.2f}B, 1d {(st.total.iloc[-1] - st.total.iloc[-2]) / 1e9:+.2f}B, 7d {(st.total.iloc[-1] - st.total.iloc[-8]) / 1e9:+.2f}B")
    for c in ("BTC", "ETH"):
        e = pd.read_csv(f"{ROOT}/data/etf/{c}.csv").tail(4)
        big = "IBIT" if c == "BTC" else "ETHA"
        print(f"ETF {c}: " + ", ".join(f"{r.date} {r.total:+.1f}{' (partial: ' + big + ' missing)' if r[big] != r[big] else ''}" for _, r in e.iterrows()))
    bands = json.loads(subprocess.run(["node", f"{ROOT}/research/bands.js"], capture_output=True, text=True, check=True).stdout)
    print("\nliquidation map totals $M within 1/2/3/5/8% (longs below | shorts above)")
    for r in res:
        b = bands[r["coin"] + "USDT"]; L, S = b["L"][1], b["S"][1]
        j = None if L + S <= 0 or abs(L - S) / (L + S) < 0.05 else (1 if S > L else 0)
        a = r["acc"]; i = 0 if a < 1.5 else 1 if a <= 2.5 else 2
        cell = RISK[i][2 if j is None else j]
        side = {None: "about even", 1: "more shorts above", 0: "more longs below"}[j]
        print(f"  {r['coin']} at {b['t']} px {b['px']}: L {b['L']} | S {b['S']}")
        print(f"     risk panel: crowd {a:.2f} (row {['<1.5', '1.5-2.5', '>2.5'][i]}), within 2% {side} -> {cell[0]} up of {cell[1]} = {100 * cell[0] / cell[1]:.0f}% up;"
              f" 24h volume {r['volr']:.1f}x normal")
    for s in ("BTCUSDT", "ETHUSDT"):
        P = arena.prepare(s, live=True); k = len(P["C"]) - 1; rc = P["rec"][-1]
        print(f"  {s[:3]} 200-day avg {rc.ma200:,.0f} ({100 * (P['C'][-1] / rc.ma200 - 1):+.1f}%), 28d {100 * rc.r28:+.1f}%, 20-day range {rc.lo20:,.0f} to {rc.hi20:,.0f},"
              f" 3-day funding {rc.f3:.4f}, score long {arena.rank_of(P, k, 1)} short {arena.rank_of(P, k, -1)}")


if __name__ == "__main__":
    main()
