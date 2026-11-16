"""Uji teori "posisi sehat vs posisi tenggelam" (underwater): apakah porsi long (atau short) yang sedang rugi
menentukan berhasil tidaknya sebuah low/high dan arah gerakan besar?

Binance tidak membuka harga masuk tiap akun, jadi porsi ini DIPERKIRAKAN dari open interest (OI) per jam:
  - OI naik d kontrak pada jam itu  -> d kontrak baru dicatat dibuka pada harga penutupan jam itu;
  - OI turun                        -> semua kelompok harga masuk dikurangi dengan porsi yang sama (tidak diketahui siapa
                                       yang menutup; sama dengan aturan model heatmap);
  - U = porsi kontrak terbuka yang harga masuknya DI ATAS harga sekarang.
Tiap kontrak punya satu long dan satu short dengan harga masuk yang sama, maka U = porsi long yang rugi = porsi short
yang untung, dan 1 - U = porsi short yang rugi. Jadi untuk seluruh pasar "long rugi" dan "short rugi" adalah satu angka,
bukan dua. Yang membedakan adalah SIAPA yang long (rasio akun). Kelemahan perkiraan: posisi yang dibuka dan ditutup tanpa
mengubah OI tidak terlihat, jadi perkiraan menganggap posisi lebih tua daripada kenyataan. Dicek terhadap data nyata
Hyperliquid (data/hyperliquid/summary) di bagian akhir.

    python research/underwater.py      # butuh data/derived/hourly dan research/data/hourly
"""
import glob, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, events, auc, R  # noqa: E402
from big_moves import events as big_events  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
BIN = 0.0025        # lebar kotak harga masuk: 0,25% (skala log)
BURN = 24 * 90      # 90 hari pertama dibuang (isi awal buku tidak diketahui)


def underwater(sym):
    """-> DataFrame t, close, U (porsi long rugi), gap (harga / rata-rata harga masuk - 1), oi30 (OI vs puncak 30 hari)."""
    h = load(sym); C = h.close.values; oi = h.oi.values; n = len(h)
    lo = np.log(np.nanmin(h.low.values) * 0.9); nb = int((np.log(np.nanmax(h.high.values) * 1.1) - lo) / BIN) + 2
    mid = np.exp(lo + (np.arange(nb) + 0.5) * BIN)
    book = np.zeros(nb); U = np.full(n, np.nan); gap = np.full(n, np.nan); prev = np.nan; start = None
    for i in range(n):
        o = oi[i]
        if o == o and o > 0:
            b = int((np.log(C[i]) - lo) / BIN)
            if prev != prev:
                book[b] += o; start = i
            else:
                d = o - prev
                if d > 0:
                    book[b] += d
                elif d < 0:
                    book *= max(0.0, 1 + d / max(book.sum(), 1e-12))
            prev = o
        if start is not None and i - start >= BURN:
            tot = book.sum()
            if tot > 0:
                b = int((np.log(C[i]) - lo) / BIN)
                U[i] = (book[b + 1:].sum() + 0.5 * book[b]) / tot
                gap[i] = C[i] / ((book * mid).sum() / tot) - 1
    oi30 = h.oi / h.oi.rolling(720, min_periods=240).max() - 1
    return pd.DataFrame(dict(t=h.t.values, close=C, U=U, gap=gap, oi30=oi30.values, acc=h.acc_lsr.values))


def bands(q, col, cuts, labels):
    g = q.groupby(pd.cut(q[col], cuts, labels=labels), observed=False).y.agg(["size", "sum"])
    return "  ".join(f"{k}: {int(b)}/{int(a)} = {100 * b / a:.0f}%" if a else f"{k}: -" for k, (a, b) in zip(g.index, g.values))


if __name__ == "__main__":
    W = {s: underwater(s) for s in COINS}
    CUT = [0, .5, .7, .85, .95, 1.001]; LAB = ["<50%", "50-70%", "70-85%", "85-95%", ">95%"]
    for side, name in (("bottom", "LOW (entri long)"), ("top", "HIGH (entri short)")):
        E = pd.concat([events(s, side).merge(W[s][["t", "U", "gap", "oi30"]], on="t", how="left") for s in COINS], ignore_index=True)
        Q = E.dropna(subset=["y", "U"]).copy(); Q["Ux"] = Q.U if side == "bottom" else 1 - Q.U     # porsi sisi yang "terjebak"
        who = "long rugi" if side == "bottom" else "short rugi"
        print(f"\n=== {name}: {len(Q)} kejadian, menang {100 * Q.y.mean():.0f}% ===")
        print(f" skor (AUC) porsi {who}: {auc(Q.Ux, Q.y):.2f} | jarak harga dari rata-rata harga masuk: {auc(Q.gap, Q.y):.2f} | OI vs puncak 30 hari: {auc(Q.oi30, Q.y):.2f} | rasio akun: {auc(Q.acc, Q.y):.2f}")
        for a, b in ((2020, 2022), (2023, 2024), (2025, 2026)):
            m = (Q.yr >= a) & (Q.yr <= b); print(f"   {a}-{b}: AUC porsi {who} {auc(Q[m].Ux, Q[m].y):.2f}, OI vs puncak {auc(Q[m].oi30, Q[m].y):.2f}, n={m.sum()}")
        print(f" menang menurut porsi {who}:", bands(Q, "Ux", CUT, LAB))
        print(" BTC+ETH saja:", bands(Q[Q.sym.isin(["BTC", "ETH"])], "Ux", CUT, LAB))
        print(" menang menurut OI vs puncak 30 hari:", bands(Q, "oi30", [-1, -.3, -.2, -.1, -.05, 0.001], ["turun >30%", "20-30%", "10-20%", "5-10%", "<5%"]))
        A = Q.dropna(subset=["acc"]); A["crowd"] = np.where(A.acc >= 2.5, "rasio akun >= 2,5", "rasio akun < 2,5"); A["trap"] = np.where(A.Ux >= 0.85, f"{who} >= 85%", f"{who} < 85%")
        g = A.groupby(["crowd", "trap"]).y.agg(["size", "mean"]); print(" gabungan:", {f"{a} & {b}": f"{100 * m:.0f}% dari {int(n)}" for (a, b), (n, m) in zip(g.index, g.values)})

    # arah gerakan besar dan imbal hasil 7 hari menurut U (BTC + ETH)
    B = pd.concat([big_events(s, need_acc=False).merge(W[s][["t", "U"]], on="t", how="left") for s in ("BTCUSDT", "ETHUSDT")]).dropna(subset=["U"])
    B["y"] = B.up; B["yr"] = pd.to_datetime(B.t, unit="s").dt.year
    print(f"\n=== GERAKAN BESAR BTC+ETH: {len(B)}, naik {100 * B.up.mean():.0f}% ===")
    print(" naik menurut porsi long rugi:", bands(B, "U", CUT, LAB))
    for a, b in ((2020, 2022), (2023, 2026)):
        print(f"   {a}-{b}:", bands(B[(B.yr >= a) & (B.yr <= b)], "U", [0, .5, .85, 1.001], ["<50%", "50-85%", ">85%"]))
    print("\n=== IMBAL HASIL 7 HARI (satu baris per hari, 00 UTC), menurut porsi long rugi ===")
    for s in ("BTCUSDT", "ETHUSDT"):
        w = W[s]; w["f7"] = w.close.shift(-168) / w.close - 1; d = w[(w.t % 86400 == 0)].dropna(subset=["U", "f7"])
        g = d.groupby(pd.cut(d.U, CUT, labels=LAB), observed=False).f7.agg(["size", "median", lambda x: (x > 0).mean()])
        print(f" {s[:3]}:", "  ".join(f"{k}: median {100 * m:+.1f}%, naik {100 * u:.0f}% ({int(n)} hari)" for k, (n, m, u) in zip(g.index, g.values)))

    print("\n=== CEK TERHADAP DATA NYATA HYPERLIQUID (bursa lain; hanya pembanding kasar) ===")
    hl = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(R + "data/hyperliquid/summary/*.csv"))])
    for s in ("BTCUSDT", "ETHUSDT"):
        g = hl[hl.coin == s[:3]].merge(W[s][["t", "U"]], on="t").dropna(subset=["U", "lossL"])
        if len(g):
            print(f" {s[:3]}: {len(g)} jam bersama | perkiraan Binance long rugi {100 * g.U.mean():.0f}% (terakhir {100 * g.U.iat[-1]:.0f}%) | "
                  f"Hyperliquid nyata long rugi {100 * g.lossL.mean():.0f}% (terakhir {100 * g.lossL.iat[-1]:.0f}%), short rugi {100 * g.lossS.mean():.0f}% | korelasi per jam {g.U.corr(g.lossL):.2f}")
        w = W[s].dropna(subset=["U"]).iloc[-1]; print(f"   sekarang ({pd.to_datetime(w.t, unit='s')}): long rugi {100 * w.U:.0f}%, harga {100 * w.gap:+.1f}% dari rata-rata harga masuk, OI {100 * w.oi30:+.0f}% dari puncak 30 hari")
