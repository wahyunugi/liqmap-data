"""Eksperimen 5 (literatur: arXiv 2607.27070, "Early-warning signals across seven crypto-perpetual liquidation cascades":
sebelum gelombang likuidasi, porsi beli/jual agresif menjadi sangat stabil dan satu sisi): apakah arus order yang satu
sisi atau yang "terlalu stabil" mendahului gerakan besar, dan apakah arahnya memberi tahu arah gerakan?

Aturan ditetapkan sebelum melihat hasil. 8 koin, Binance futures per jam, sejak 2020.
  porsi beli agresif per jam = volume beli agresif (taker buy) / volume total.
  Tiga bacaan dari 24 jam terakhir, dibaca pada 00 UTC tiap hari:
    imb   = porsi beli agresif 24 jam (berbobot volume) dikurangi 0,5 -> positif = pembeli lebih agresif
    stab  = simpangan baku porsi beli per jam selama 24 jam, dibagi median simpangan baku yang sama selama 30 hari
            terakhir -> di bawah 1 = arus lebih stabil dari biasanya ("variansi menyempit" menurut makalah)
    satu  = berapa dari 24 jam terakhir yang porsi belinya di sisi yang sama dengan imb
  Hasil: (a) apakah gerakan besar mulai dalam 24 jam ke depan (definisi research/big_moves.py);
         (b) bila mulai, ke arah mana; (c) perubahan harga 24 jam ke depan.
  Karena gerakan besar mengelompok (eksperimen 2), (a) juga dihitung hanya pada hari yang gerakan besar terakhirnya
  sudah lebih dari 3 hari lalu.
    python research/exp5_flow.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
PER = ((2020, 2021), (2022, 2023), (2024, 2026))
H, K = 6, 3.0


def days(sym):
    h = load(sym); C = h.close.values; t = h.t.values; n = len(h)
    share = (h.taker_buy / h.vol).where(h.vol > 0)
    imb = (h.taker_buy.rolling(24).sum() / h.vol.rolling(24).sum() - 0.5).values
    sd24 = share.rolling(24).std(); stab = (sd24 / sd24.rolling(720, min_periods=360).median()).values
    above = (share > 0.5).astype(float).rolling(24).sum().values
    s6 = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(H)
    r6 = np.full(n, np.nan); r6[:n - H] = C[H:] / C[:n - H] - 1
    big = np.abs(r6) >= K * s6
    rows = []
    for i in range(721 + 720, n - 24 - H):
        if t[i] % 86400 or not s6[i] == s6[i] or not imb[i - 1] == imb[i - 1]:
            continue
        j = i - 1                                               # bacaan memakai jam yang sudah selesai
        past = np.nonzero(big[:i - H + 1])[0]; nxt = np.nonzero(big[i:i + 24])[0]
        rows.append(dict(sym=sym[:-4], t=t[i], imb=imb[j], stab=stab[j], satu=max(above[j], 24 - above[j]),
                         since=(i - (past[-1] + H)) / 24 if len(past) else np.nan, y=int(len(nxt) > 0),
                         dirn=np.sign(r6[i + nxt[0]]) if len(nxt) else np.nan, f24=C[i + 24] / C[i] - 1))
    return pd.DataFrame(rows)


def tab(q, col, val="y"):
    g = q.groupby(col, observed=False)[val].agg(["size", "mean"])
    return "  ".join(f"{k}: {100 * m:.1f}% ({int(a)})" if a else f"{k}: -" for k, (a, m) in zip(g.index, g.values))


if __name__ == "__main__":
    D = pd.concat([days(s) for s in COINS], ignore_index=True).dropna(subset=["imb", "stab"]); D["yr"] = pd.to_datetime(D.t, unit="s").dt.year
    D["stab_b"] = pd.cut(D.stab, [0, .7, .85, 1.0, 1.2, 1.5, 99], labels=["<0,70 (paling stabil)", "0,70-0,85", "0,85-1,0", "1,0-1,2", "1,2-1,5", ">1,5 (paling bergejolak)"])
    D["satu_b"] = pd.cut(D.satu, [0, 14, 17, 20, 24], labels=["12-14 jam", "15-17", "18-20", "21-24 jam (sangat satu sisi)"])
    D["imb_b"] = pd.cut(D.imb * 100, [-50, -2, -1, -0.3, 0.3, 1, 2, 50], labels=["jual > 2 poin", "jual 1-2", "jual 0,3-1", "seimbang", "beli 0,3-1", "beli 1-2", "beli > 2 poin"])
    print(f"{len(D)} hari-koin; gerakan besar mulai dalam 24 jam: {100 * D.y.mean():.1f}% | median porsi beli 24 jam - 50%: {100 * D.imb.median():+.2f} poin")
    calm = D[D.since > 3]
    for name, col in (("kestabilan arus (stab)", "stab_b"), ("jam satu sisi", "satu_b"), ("ketimpangan (imb)", "imb_b")):
        print(f"\n(a) peluang gerakan besar 24 jam, menurut {name}:"); print("  semua hari:", tab(D, col)); print("  hanya hari tenang (>3 hari sejak gerakan besar):", tab(calm, col))
        for a, b in PER:
            print(f"   {a}-{b}:", tab(D[(D.yr >= a) & (D.yr <= b)], col))
    B = D[D.y == 1].dropna(subset=["dirn"]).copy(); B["up"] = (B.dirn > 0).astype(float)
    print(f"\n(b) arah gerakan besar berikutnya ({len(B)} kasus, naik {100 * B.up.mean():.0f}%), menurut ketimpangan arus 24 jam sebelumnya:")
    print("  semua:", tab(B, "imb_b", "up"))
    for a, b in PER:
        print(f"   {a}-{b}:", tab(B[(B.yr >= a) & (B.yr <= b)], "imb_b", "up"))
    B["sell"] = B.imb < -0.01; print("  ringkas: jual agresif > 1 poin -> naik", f"{100 * B[B.sell].up.mean():.0f}% ({B.sell.sum()}) | beli agresif > 1 poin -> naik {100 * B[B.imb > 0.01].up.mean():.0f}% ({(B.imb > 0.01).sum()}) | lainnya {100 * B[(B.imb.abs() <= 0.01)].up.mean():.0f}%")
    D["up24"] = (D.f24 > 0).astype(float)
    print("\n(c) harga 24 jam ke depan naik (% hari), menurut ketimpangan:", tab(D, "imb_b", "up24"))
    g = D.groupby("imb_b", observed=False).f24.median() * 100; print("    median perubahan 24 jam:", "  ".join(f"{k}: {v:+.2f}%" for k, v in g.items()))
    for a, b in PER:
        print(f"   {a}-{b}:", tab(D[(D.yr >= a) & (D.yr <= b)], "imb_b", "up24"))
    print("\n korelasi antar bacaan:", D[["imb", "stab", "satu"]].corr().round(2).values.tolist())
