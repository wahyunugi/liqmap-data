"""Eksperimen 7 (literatur: arXiv 2411.06327, arus on-chain masuk bursa memprediksi harga 1-6 jam; di sini harian):
apakah perubahan saldo dompet bursa (stablecoin masuk, BTC/ETH masuk atau keluar) memprediksi harga?

Aturan ditetapkan sebelum melihat hasil. Data: data/exchanges/reserves.csv (DefiLlama), 10 bursa dengan data lengkap
sejak 22 Des 2022 (sama dengan website). Titik tanggal d = saldo pukul 00:00 UTC hari d; dianggap diketahui d 06:00 UTC,
dan hasil diukur dari harga saat itu.
  Pembersihan: perubahan harian satu bursa yang lebih dari +-15% saldonya dianggap perubahan daftar dompet (bukan arus)
  dan dinolkan. Versi kedua: hanya Binance, OKX, Bybit (hampir tanpa lonjakan).
  Bacaan: arus bersih 7 hari = jumlah perubahan harian bersih 7 hari / saldo 7 hari lalu (persen).
     stablecoin (USDT + USDC + stablecoin lain), BTC (untuk harga BTC), ETH (untuk harga ETH).
  Hasil: perubahan harga 1, 7, 30 hari; "turun 1 ayunan mingguan normal lebih dulu" dalam 14 hari.
  A. lima kelompok sama besar; B. korelasi dengan harga 7 hari SEBELUM vs SESUDAH; C. dua paruh sampel.
    python research/exp7_reserves.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load, race, R  # noqa: E402

ALL10 = ["binance-cex", "okx", "bybit", "bitfinex", "bitget", "gate", "htx", "deribit", "kucoin", "crypto-com"]
BIG3 = ["binance-cex", "okx", "bybit"]


def flows(ex, col):
    r = pd.read_csv(R + "data/exchanges/reserves.csv"); r = r[r.exchange.isin(ex) & (r.date >= "2022-12-22")]
    r["stable"] = r.usdt + r.usdc + r.stable_other
    p = r.pivot(index="date", columns="exchange", values=col).ffill()
    d = p.diff(); pc = p.pct_change(); d[pc.abs() > 0.15] = 0.0
    net = d.sum(axis=1); bal = p.sum(axis=1)
    return pd.DataFrame(dict(f7=100 * net.rolling(7).sum() / bal.shift(7), f1=100 * net / bal.shift(1)))


def outcomes(sym):
    h = load(sym); C = h.close.values; H = h.high.values; L = h.low.values; t = h.t.values; n = len(h)
    sig = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168); rows = []
    for i in range(720, n):
        if t[i] % 86400 != 6 * 3600:
            continue
        rows.append(dict(date=pd.to_datetime(t[i], unit="s").strftime("%Y-%m-%d"),
                         r1=C[i + 24] / C[i] - 1 if i + 24 < n else np.nan, r7=C[i + 168] / C[i] - 1 if i + 168 < n else np.nan,
                         r30=C[i + 720] / C[i] - 1 if i + 720 < n else np.nan, p7=C[i] / C[i - 168] - 1,
                         down=(1 - race(H, L, i, C[i], sig[i], sig[i], 336, True)[0]) if i + 336 < n and sig[i] == sig[i] else np.nan))
    return pd.DataFrame(rows).set_index("date")


def report(name, x, o):
    q = o.join(x, how="inner").dropna(subset=["f7", "r7"])
    q["b"] = pd.qcut(q.f7, 5, labels=["keluar terbesar", "2", "3", "4", "masuk terbesar"])
    print(f"\n{name}: {len(q)} hari, {q.index[0]} s.d. {q.index[-1]}")
    for k, g in q.groupby("b", observed=False):
        print(f"  {k} ({g.f7.min():+.2f}% s.d. {g.f7.max():+.2f}% / 7 hari): 7 hari median {100 * g.r7.median():+.1f}%, naik {100 * (g.r7 > 0).mean():.0f}% | "
              f"30 hari naik {100 * (g.r30 > 0).mean():.0f}% | turun lebih dulu {100 * g.down.mean():.0f}%")
    print(f"  korelasi arus 7 hari dengan harga 7 hari SEBELUM {q.f7.corr(q.p7):+.2f}, SESUDAH {q.f7.corr(q.r7):+.2f}; arus 1 hari dengan harga 1 hari sesudah {q.f1.corr(q.r1):+.2f}")
    for a, b in (("2022-12-01", "2024-10-31"), ("2024-11-01", "2026-12-31")):
        z = q[(q.index >= a) & (q.index <= b)]
        if len(z) > 60:
            hi = z[z.f7 >= z.f7.quantile(.8)]; lo = z[z.f7 <= z.f7.quantile(.2)]
            print(f"   {a[:7]} s.d. {b[:7]}: sesudah {z.f7.corr(z.r7):+.2f} | 7 hari naik: masuk terbesar {100 * (hi.r7 > 0).mean():.0f}%, keluar terbesar {100 * (lo.r7 > 0).mean():.0f}% ({len(z)} hari)")


if __name__ == "__main__":
    oB, oE = outcomes("BTCUSDT"), outcomes("ETHUSDT")
    for ex, nm in ((ALL10, "10 bursa"), (BIG3, "Binance+OKX+Bybit")):
        s = flows(ex, "stable")
        report(f"STABLECOIN masuk bursa ({nm}) -> harga BTC", s, oB)
        report(f"STABLECOIN masuk bursa ({nm}) -> harga ETH", s, oE)
        report(f"BTC masuk bursa ({nm}) -> harga BTC", flows(ex, "btc"), oB)
        report(f"ETH masuk bursa ({nm}) -> harga ETH", flows(ex, "eth"), oE)
    s = flows(ALL10, "stable"); b = flows(ALL10, "btc"); e = flows(ALL10, "eth")
    print("\nterakhir (10 bursa, % per 7 hari):", {"stablecoin": round(s.f7.iat[-1], 2), "BTC": round(b.f7.iat[-1], 2), "ETH": round(e.f7.iat[-1], 2), "tanggal": s.index[-1]})
