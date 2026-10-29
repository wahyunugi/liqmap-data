"""
Cek: fastmodel.py harus memberi hasil yang SAMA dengan model.py (PARAMS_V6) — snapshot.py — pada data repo.
Jendela 24 jam di 3 waktu, 7 hari dan 30 hari di candle terakhir.  Keluar dengan kode 1 bila ada selisih.
    python heatmap/check_fastmodel.py
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inputs, model, fastmodel  # noqa: E402


def agg_dict(px, us, sd, B):
    b, lg, sh = fastmodel.aggregate(np.asarray(px, float), np.asarray(us, float), np.asarray(sd, np.int8), *B)
    out = {}
    for bi, a, c in zip(b, lg, sh):
        if a > 0: out[(int(bi), 0)] = a
        if c > 0: out[(int(bi), 1)] = c
    return out


def reference(df, i, window):
    """model.py dijalankan seperti snapshot.py pada waktu tutup candle i."""
    d = df.iloc[: i + 1].reset_index(drop=True)
    p = dict(model.PARAMS_V6, window_candles=window)
    _, snaps = model.run(d, p)
    lv = snaps[-1]
    return [x[0] for x in lv], [x[1] for x in lv], [0 if x[2] == "long" else 1 for x in lv]


def main():
    ok = True
    for sym in ("BTCUSDT", "ETHUSDT"):
        df = inputs.load(sym)
        n = len(df)
        cases = [(288, n // 3), (288, 2 * n // 3), (288, n - 1), (2016, n - 1), (8640, n - 1)]
        cases = [(w, i) for w, i in cases if i >= w]
        for window in sorted({w for w, _ in cases}):
            idx = {i for w, i in cases if w == window}
            got = {}
            fastmodel.simulate(df.t.values, df.open.values, df.high.values, df.low.values, df.close.values,
                               [None if v != v else float(v) for v in df.oi.values], window, idx,
                               lambda i, px, us, sd: got.__setitem__(i, (px, us, sd)))
            for i in sorted(idx):
                B = fastmodel.bins_for(float(df.close.iat[i]))
                a = agg_dict(*got[i], B)
                r = agg_dict(*reference(df, i, window), B)
                keys = set(a) | set(r)
                diff = max((abs(a.get(k, 0) - r.get(k, 0)) for k in keys), default=0)
                miss = sum(1 for k in keys if (k in a) != (k in r))
                good = miss == 0 and diff < 0.01
                ok &= good
                print(f"{sym} jendela {window:>4} candle {i}: {len(r)} kotak model.py, {len(a)} fastmodel, "
                      f"beda kotak {miss}, selisih USD maks {diff:.6f} -> {'SAMA' if good else 'BEDA'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
