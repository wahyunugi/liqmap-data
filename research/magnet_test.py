"""
Uji: apakah peta likuidasi (model v6, jendela 24 jam, data Binance 5 menit sejak 2020) menunjukkan ke mana harga bergerak?

Untuk tiap akhir jam sejak 2020, model dijalankan seperti website (heatmap/fastmodel.py, aturan sama dengan model.py) dan
dicatat jumlah USD level likuidasi yang masih terbuka:
  L1, L2, L5 = long (terlikuidasi bila harga TURUN) dalam 1%, 2%, 5% di bawah harga penutupan jam itu
  S1, S2, S5 = short (terlikuidasi bila harga NAIK) dalam 1%, 2%, 5% di atas harga
  Lbig_pct / Sbig_pct = jarak (persen) ke kotak harga long / short terbesar dalam 5%, dan USD-nya (Lbig / Sbig)
Hasil: research/results/magnet_<SIMBOL>.csv (satu baris per jam). Analisis dilakukan terpisah (research/magnet_analysis.py).

    python research/magnet_test.py      # butuh arsip Binance (.cache/binance), dijalankan workflow "research"
"""
import os, sys, time
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "site")); sys.path.insert(0, os.path.join(ROOT, "heatmap")); sys.path.insert(0, os.path.join(ROOT, "history"))
import build_history, fastmodel  # noqa: E402

OUT = os.path.join(HERE, "results")
BANDS = (0.01, 0.02, 0.05)


def run(sym):
    rep = {}
    df = build_history.series(sym, rep)
    t = df.t.values.astype(np.int64)
    snap = set(int(i) for i in np.nonzero((t + 300) % 3600 == 0)[0])
    rows = []
    closes = df.close.values

    def on_snap(i, px, us, sd):
        c = float(closes[i])
        r = {"t": int(t[i]) + 300 - 3600, "close": c}          # t = waktu buka jam (sama dengan data/derived/hourly)
        if len(px):
            d = px / c - 1
            for b in BANDS:
                r[f"L{int(b * 100)}"] = float(us[(sd == 0) & (d < 0) & (d >= -b)].sum())
                r[f"S{int(b * 100)}"] = float(us[(sd == 1) & (d > 0) & (d <= b)].sum())
            w, off, dx = fastmodel.bins_for(c)
            bins, lg, sh = fastmodel.aggregate(px, us, sd, w, off, dx)
            mid = off + (bins + 0.5) * w - dx
            dd = mid / c - 1
            mL = (dd < 0) & (dd >= -0.05); mS = (dd > 0) & (dd <= 0.05)
            if mL.any():
                k = np.argmax(np.where(mL, lg, -1)); r["Lbig"] = float(lg[k]); r["Lbig_pct"] = float(dd[k] * 100)
            if mS.any():
                k = np.argmax(np.where(mS, sh, -1)); r["Sbig"] = float(sh[k]); r["Sbig_pct"] = float(dd[k] * 100)
        rows.append(r)

    oi = [None if v != v else float(v) for v in df.oi.values]
    fastmodel.simulate(t, df.open.values, df.high.values, df.low.values, df.close.values, oi, 288, snap, on_snap)
    out = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    out.to_csv(os.path.join(OUT, f"magnet_{sym}.csv"), index=False, float_format="%.6g")
    return len(out), rep.get("from"), rep.get("to")


if __name__ == "__main__":
    for s in ("BTCUSDT", "ETHUSDT"):
        t0 = time.time()
        print(s, run(s), f"{time.time() - t0:.0f} s", flush=True)
