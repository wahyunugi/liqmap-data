"""Level aktif model v6 (Binance BTCUSDT) pada candle terakhir arsip, untuk beberapa panjang jendela."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "heatmap"))
import pandas as pd
from model import run, PARAMS_V6
d = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "..", "data", "binance_archive", "BTCUSDT_5m.csv"))
end = int(sys.argv[1]) if len(sys.argv) > 1 else None          # t (detik UTC) candle terakhir yang dipakai
if end: d = d[d.t <= end]
out = {"t_last": int(d.t.iat[-1]), "close": float(d.close.iat[-1])}
for hours in (24, 72, 168):
    p = dict(PARAMS_V6, window_candles=hours * 12)
    _, s = run(d.reset_index(drop=True), p)
    out[f"{hours}h"] = [(round(a, 1), round(b, 0), c) for a, b, c in s[-1]]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "model_now.json"), "w"))
print({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()})
