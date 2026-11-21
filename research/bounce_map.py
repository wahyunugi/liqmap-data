"""Peta pantulan: setelah harga mencetak terendah 20 hari dengan volume berat (>= 2x normal), seberapa besar pantulannya,
berapa lama, di mana berhentinya, dan apakah short DI PANTULAN lebih baik daripada short SEKARANG?

Aturan ditetapkan sebelum melihat hasil. 8 koin Binance futures per jam sejak 2020.
  kejadian  = jam pertama harga menembus terendah 20 hari sementara volume 24 jam >= 2x median 30 hari; jarak >= 7 hari.
  ayunan    = ayunan mingguan normal (simpangan baku per jam 720 jam x akar 168), dibekukan saat kejadian.
  kaki turun = dari tertinggi 7 hari sebelum kejadian ke terendah sejauh ini.
  A. Pantulan dalam 10 hari: tertinggi sesudah kejadian, dalam ayunan dan persen; berapa jam; apakah terendah baru dulu.
     Retracement = (puncak pantulan - terendah) / (tertinggi kaki - terendah).
  B. Short, target 1 ayunan turun, stop 1 ayunan naik dari harga masuk, batas 30 hari:
       sekarang (harga saat kejadian) | setelah naik +0,5 ayunan | +1 ayunan | di retracement 0,382 dan 0,5 kaki turun
     (pantulan harus datang dalam 10 hari, kalau tidak, tidak ada transaksi).
  Dipisah: harga di bawah / di atas MA200 harian (fase pasar), rasio akun >= 2,5 atau tidak.
    python research/bounce_map.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]


def short_from(H, L, j, px, sw, horizon=720):
    """Short masuk pada jam j di harga px: +1 bila turun 1 ayunan dulu, 0 bila naik 1 ayunan dulu, nan bila tidak keduanya."""
    up, dn = px * (1 + sw), px * (1 - sw)
    for k in range(j, min(len(H), j + horizon)):
        hu, hd = H[k] >= up, L[k] <= dn
        if hu and hd:
            return np.nan
        if hu:
            return 0.0
        if hd:
            return 1.0
    return np.nan


def events(sym):
    h = load(sym); H = h.high.values; L = h.low.values; C = h.close.values; t = h.t.values; n = len(h)
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    pl = pd.Series(L).rolling(480).min().shift(1).values
    ma = pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values
    rows = []; last = -10**9
    for i in range(720 + 480, n - 240):
        if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168:
            continue
        last = i; s = sw[i]; px = C[i]
        legH = H[i - 168:i + 1].max(); lo_i = L[i]
        w = slice(i + 1, i + 241)
        lows = L[w]; highs = H[w]
        new_low = lows.min() < lo_i
        jlo = i + 1 + int(np.argmin(lows)) if new_low else i
        lo = min(lo_i, lows.min())
        after = H[jlo + 1:i + 241] if jlo + 1 < i + 241 else np.array([px])
        pk = after.max() if len(after) else px; jpk = jlo + 1 + int(np.argmax(after)) if len(after) else i
        retr = (pk - lo) / (legH - lo) if legH > lo else np.nan
        res = dict(sym=sym[:-4], t=t[i], sw=s, acc=h.acc_lsr.values[i], bear=bool(C[i] < ma[i]) if ma[i] == ma[i] else np.nan,
                   bounce_sw=(pk / lo - 1) / s, bounce_pct=pk / lo - 1, hours=jpk - jlo, newlow=new_low, lowdrop=(lo / lo_i - 1),
                   retr=retr, later_lower=bool(L[jpk:jpk + 720].min() < lo) if jpk + 720 < n else np.nan)
        res["now"] = short_from(H, L, i + 1, px, s)
        for k in (0.5, 1.0):
            tgt = px * (1 + k * s); hit = np.nonzero(H[i + 1:i + 241] >= tgt)[0]
            res[f"b{k}"] = short_from(H, L, i + 1 + hit[0] + 1, tgt, s) if len(hit) else np.nan
            res[f"b{k}_hit"] = len(hit) > 0
        for fr in (0.382, 0.5):
            tgt = lo_i + fr * (legH - lo_i); hit = np.nonzero(H[i + 1:i + 241] >= tgt)[0]
            res[f"f{fr}"] = short_from(H, L, i + 1 + hit[0] + 1, tgt, s) if len(hit) else np.nan
            res[f"f{fr}_hit"] = len(hit) > 0
        rows.append(res)
    return pd.DataFrame(rows)


def summary(nm, q):
    if len(q) < 8:
        print(f"  {nm}: terlalu sedikit ({len(q)})"); return
    print(f"  {nm}: {len(q)} kejadian")
    print(f"    pantulan (dari terendah, 10 hari): median {q.bounce_sw.median():.2f} ayunan = {100 * q.bounce_pct.median():.1f}% | "
          f"kuartil {q.bounce_sw.quantile(.25):.2f} s.d. {q.bounce_sw.quantile(.75):.2f} ayunan | median {q.hours.median():.0f} jam ke puncak")
    print(f"    terendah baru dulu dalam 10 hari: {100 * q.newlow.mean():.0f}% (median {100 * q[q.newlow].lowdrop.median():.1f}% lebih rendah) | "
          f"retracement kaki turun: median {q.retr.median():.2f}, 0,382 tercapai {100 * (q.retr >= .382).mean():.0f}%, 0,5 {100 * (q.retr >= .5).mean():.0f}%, 0,618 {100 * (q.retr >= .618).mean():.0f}%")
    print(f"    setelah puncak pantulan, terendah lebih rendah dalam 30 hari: {100 * q.later_lower.mean():.0f}%")
    for c, lab in (("now", "short sekarang"), ("b0.5", "short di +0,5 ayunan"), ("b1.0", "short di +1 ayunan"), ("f0.382", "short di 0,382"), ("f0.5", "short di 0,5")):
        hitcol = c + "_hit" if c != "now" else None
        reached = q[hitcol].mean() if hitcol else 1.0
        x = q[c].dropna()
        print(f"    {lab:>22}: pantulan sampai di sana {100 * reached:.0f}% | menang {100 * x.mean():.0f}% dari {len(x)} | per peluang (tak tercapai = 0): {(2 * x.sum() - len(x)) / len(q):+.2f} ayunan")


if __name__ == "__main__":
    E = pd.concat([events(s) for s in COINS], ignore_index=True); E["yr"] = pd.to_datetime(E.t, unit="s").dt.year
    summary("SEMUA", E)
    summary("fase turun (di bawah MA200 harian)", E[E.bear == True])
    summary("fase naik (di atas MA200)", E[E.bear == False])
    summary("fase turun + rasio akun >= 2,5", E[(E.bear == True) & (E.acc >= 2.5)])
    summary("fase turun, 2024-2026", E[(E.bear == True) & (E.yr >= 2024)])
    summary("BTC+ETH fase turun", E[(E.bear == True) & E.sym.isin(["BTC", "ETH"])])
    E.to_csv("/tmp/claude-0/-home-claude/060f9c3f-9ddd-5c7b-8928-2f877765f5d6/scratchpad/bounce_events.csv", index=False)
