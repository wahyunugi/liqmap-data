"""Bandingkan profil harga likuidasi NYATA Hyperliquid (hl_summary.json) dengan model v6 (model_now.json)."""
import json, numpy as np
import pandas as pd
def spearmanr(a, b):
    class R: pass
    r = R(); r.correlation = np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1]; return r
s = json.load(open("hl_summary.json")); m = json.load(open("model_now.json"))
mark = s["mark"]; K = 40
real = np.array(s["profLong"]) + np.array(s["profShort"])
dev = (np.arange(2 * K) - K) * 0.25                      # batas bawah tiap kotak, % dari harga
def model_prof(levels):
    out = np.zeros(2 * K)
    for price, usd, side in levels:
        k = int(np.floor((price / mark - 1) * 100 / 0.25)) + K
        if 0 <= k < 2 * K: out[k] += usd
    return out
def dist_share(p):
    d = np.abs(dev + 0.125)
    return [float(round(100 * p[(d > a) & (d <= b)].sum() / p.sum(), 1)) for a, b in [(0, 1), (1, 2), (2, 4), (4, 10)]]
print(f"Harga acuan {mark:,.0f} (Hyperliquid) | Binance close {m['close']:,.1f}")
print("Porsi nilai menurut jarak dari harga, hanya dalam ±10%:   <1%  1-2%  2-4%  4-10%")
print(f"  Hyperliquid nyata                                     {dist_share(real)}")
for w in ("24h", "72h", "168h"):
    mp = model_prof(m[w])
    print(f"  model Binance jendela {w:>4}                          {dist_share(mp)}  | korelasi bentuk: pearson {np.corrcoef(real, mp)[0,1]:+.2f}, peringkat {spearmanr(real, mp).correlation:+.2f}")
lo = dev < 0
print(f"\nPorsi di bawah harga (likuidasi long): nyata {real[lo].sum()/real.sum():.0%}, model 24h {model_prof(m['24h'])[lo].sum()/model_prof(m['24h']).sum():.0%}")
top = np.argsort(real)[::-1][:5]
print("5 kotak terbesar nyata (% dari harga, juta USD):", [(float(round(dev[k]+0.125, 2)), float(round(real[k]/1e6, 1))) for k in top])
mp = model_prof(m["24h"]); top = np.argsort(mp)[::-1][:5]
print("5 kotak terbesar model 24h                    :", [(float(round(dev[k]+0.125, 2)), float(round(mp[k]/1e6, 1))) for k in top])
