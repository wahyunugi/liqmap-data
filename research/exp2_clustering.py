"""Eksperimen 2 (literatur: pengelompokan volatilitas, mis. model HAR untuk bitcoin): apakah gerakan besar datang
berkelompok, sehingga satu gerakan besar menaikkan peluang gerakan besar berikutnya?

Aturan ditetapkan sebelum melihat hasil:
  gerakan besar = perubahan harga 6 jam >= 3 x ayunan 6 jam normal (simpangan baku per jam 720 jam terakhir x akar 6),
                  sama dengan research/big_moves.py. Ambang ikut naik setelah pasar bergejolak, jadi uji ini konservatif.
  Satu baris per koin per hari (00 UTC). Pertanyaan: apakah ada gerakan besar yang MULAI dalam 24 jam ke depan,
  menurut berapa lama sejak gerakan besar terakhir SELESAI (0-1 hari, 1-3, 3-7, 7-14, lebih dari 14 hari).
  Tambahan: arah gerakan besar berikutnya (searah atau berbalik) dan apakah pasar yang sangat tenang (kisaran 7 hari
  sempit dibanding biasanya) lebih sering diikuti gerakan besar.
8 koin, sejak 2020; periode 2020-21, 2022-23, 2024-26.
    python research/exp2_clustering.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
PER = ((2020, 2021), (2022, 2023), (2024, 2026))
H, K = 6, 3.0
CUT = [-1, 1, 3, 7, 14, 1e9]; LAB = ["0-1 hari", "1-3 hari", "3-7 hari", "7-14 hari", ">14 hari"]


def days(sym):
    h = load(sym); C = h.close.values; t = h.t.values; n = len(h)
    s6 = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(H)
    r6 = np.full(n, np.nan); r6[:n - H] = C[H:] / C[:n - H] - 1
    big = (np.abs(r6) >= K * s6)                       # gerakan besar yang MULAI pada jam i (diketahui pada jam i+6)
    sgn = np.sign(r6)
    rng7 = (pd.Series(h.high.values).rolling(168).max() / pd.Series(h.low.values).rolling(168).min() - 1).values
    rngp = pd.Series(rng7).rolling(24 * 365, min_periods=24 * 120).rank(pct=True).values      # kisaran 7 hari vs setahun terakhir
    rows = []
    for i in range(721 + 24 * 30, n - 24 - H):
        if t[i] % 86400:
            continue
        if not s6[i] == s6[i]:
            continue
        past = np.nonzero(big[:i - H + 1])[0]          # hanya gerakan yang sudah selesai sebelum jam i
        last = past[-1] if len(past) else None
        nxt = np.nonzero(big[i:i + 24])[0]
        rows.append(dict(sym=sym[:-4], t=t[i], since=(i - (last + H)) / 24 if last is not None else np.nan,
                         y=int(len(nxt) > 0), last_dir=sgn[last] if last is not None else np.nan,
                         next_dir=sgn[i + nxt[0]] if len(nxt) else np.nan, rngp=rngp[i]))
    return pd.DataFrame(rows)


def tab(q, col="b"):
    g = q.groupby(col, observed=False).y.agg(["size", "sum"])
    return "  ".join(f"{k}: {100 * b / a:.1f}% ({int(a)})" if a else f"{k}: -" for k, (a, b) in zip(g.index, g.values))


if __name__ == "__main__":
    D = pd.concat([days(s) for s in COINS], ignore_index=True).dropna(subset=["since"])
    D["yr"] = pd.to_datetime(D.t, unit="s").dt.year; D["b"] = pd.cut(D.since, CUT, labels=LAB)
    print(f"{len(D)} hari-koin; peluang gerakan besar mulai dalam 24 jam ke depan, semua hari: {100 * D.y.mean():.1f}%")
    print(" menurut waktu sejak gerakan besar terakhir:", tab(D))
    for a, b in PER:
        q = D[(D.yr >= a) & (D.yr <= b)]; print(f"   {a}-{b} (semua {100 * q.y.mean():.1f}%):", tab(q))
    for lab, q in (("BTC+ETH", D[D.sym.isin(["BTC", "ETH"])]), ("6 koin lain", D[~D.sym.isin(["BTC", "ETH"])])):
        print(f"   {lab} (semua {100 * q.y.mean():.1f}%):", tab(q))
    print(" per koin, 0-1 hari vs >14 hari:", {s: f"{100 * q[q.b == LAB[0]].y.mean():.0f}% vs {100 * q[q.b == LAB[-1]].y.mean():.0f}%" for s, q in D.groupby("sym")})
    # uji acak blok minggu: 0-1 hari vs lainnya
    D["wk"] = D.t // 604800; D["rec"] = D.since <= 1
    obs = D[D.rec].y.mean() - D[~D.rec].y.mean()
    wk = D.groupby(["wk", "sym"]).agg(y=("y", "sum"), n=("y", "size"), r=("rec", "sum")).reset_index()
    rng = np.random.default_rng(3); cnt = 0; M = 2000; sh = wk.r.values / wk.n.values
    for _ in range(M):
        p = rng.permutation(len(wk)); s2 = sh[p]
        a = (s2 * wk.y.values).sum() / (s2 * wk.n.values).sum(); b = ((1 - s2) * wk.y.values).sum() / ((1 - s2) * wk.n.values).sum()
        cnt += abs(a - b) >= abs(obs)
    print(f" 0-1 hari vs lainnya: selisih {100 * obs:+.1f} poin, uji acak (minggu-koin diacak) p = {cnt / M:.3f}")
    # arah
    q = D[(D.y == 1) & (D.since <= 3)].dropna(subset=["last_dir", "next_dir"])
    print(f"\n arah gerakan besar berikutnya bila yang terakhir <= 3 hari lalu: searah {100 * (q.last_dir == q.next_dir).mean():.0f}% dari {len(q)}"
          f" | setelah NAIK: naik lagi {100 * (q[q.last_dir > 0].next_dir > 0).mean():.0f}% ({(q.last_dir > 0).sum()}) | setelah TURUN: turun lagi {100 * (q[q.last_dir < 0].next_dir < 0).mean():.0f}% ({(q.last_dir < 0).sum()})")
    for a, b in PER:
        x = q[(q.yr >= a) & (q.yr <= b)]; print(f"   {a}-{b}: searah {100 * (x.last_dir == x.next_dir).mean():.0f}% dari {len(x)}")
    # pasar tenang
    Q = D.dropna(subset=["rngp"]).copy(); Q["c"] = pd.cut(Q.rngp, [0, .1, .25, .5, .75, .9, 1.0], labels=["paling sempit 10%", "10-25%", "25-50%", "50-75%", "75-90%", "paling lebar 10%"])
    print("\n menurut lebar kisaran harga 7 hari terakhir (dibanding setahun terakhir):", tab(Q, "c"))
    for a, b in PER:
        x = Q[(Q.yr >= a) & (Q.yr <= b)]; print(f"   {a}-{b}:", tab(x, "c"))
    last = D.sort_values("t").groupby("sym").tail(1)
    print("\n terakhir:", {r.sym: f"{r.since:.1f} hari sejak gerakan besar terakhir" for r in last.itertuples() if r.sym in ("BTC", "ETH")})
