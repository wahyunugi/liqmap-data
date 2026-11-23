"""Peringatan "big move info": kapan dikirim, ke mana condongnya, target dan batal (invalidation).
ATURAN DITULIS DAN DI-COMMIT SEBELUM HASIL DILIHAT (23 Nov 2026).

Peringatan (per koin, per jam): jam pertama volume 24 jam >= 2,6x median 30 hari (prinsip 14: 32% peluang gerakan besar
dalam 24 jam). Satu episode berakhir bila volume < 2,6x selama 24 jam berturut-turut; peringatan berikutnya hanya pada
episode baru. Peringatan kuat: jam pertama >= 4x di dalam episode (47%).
Ukuran gerakan besar BM = 3 x ayunan 6 jam normal (simpangan baku perubahan per jam 720 jam x akar 6), seperti panel risiko.
Harga masuk = penutupan jam peringatan.
Target = harga +/- 1 BM ke arah condong; batal = 1 BM ke arah sebaliknya (1:1). Juga dilaporkan 2:1 (target 1 BM, batal
0,5 BM). Mana yang kena lebih dulu dalam 24 jam dan 72 jam (high/low per jam; keduanya di jam yang sama = batal).
Aturan condong (yang dibandingkan, ditetapkan sekarang):
  C1 kerumunan: rasio akun < 1,5 -> naik; > 2,5 -> turun; di antaranya tidak condong          (prinsip 1, panel risiko)
  C2 kerumunan x tumpukan likuidasi 2% (sel panel risiko, hanya BTC/ETH sampai 2 Nov 2026): % naik sel >= 55 -> naik,
     <= 45 -> turun, di antaranya tidak condong
  C3 seperti C1, tetapi bila harga turun > 5% dalam 24 jam -> naik                              (prinsip 21)
  C4 pembanding: searah perubahan 24 jam terakhir (ikut arus)
Dinilai: untuk peringatan yang condong, % target lebih dulu; dipisah 2020-2023 dan 2024-2026; BTC+ETH dan 8 koin
(C2 hanya BTC+ETH). Peringatan dipakai bila aturannya benar di kedua periode.
    python research/big_move_alert.py
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
ROOT = arena.ROOT
RISK = [[[73, 105], [59, 98], [132, 204]], [[50, 91], [39, 101], [91, 195]], [[19, 45], [8, 53], [27, 103]]]   # app.js


def race(H, L, k, e, up, dn, hours):
    for q in range(k + 1, min(k + 1 + hours, len(H))):
        hu, hd = H[q] >= up, L[q] <= dn
        if hu and hd: return "both"
        if hu: return "up"
        if hd: return "down"
    return "none"


def events(sym):
    h = arena.load(sym); H, L, C, t = h.high.values, h.low.values, h.close.values, h.t.values; n = len(C)
    s6 = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(6)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    acc = h.acc_lsr.values; r24 = pd.Series(C).pct_change(24).values
    pile = None
    if sym in ("BTCUSDT", "ETHUSDT"):
        m = pd.read_csv(os.path.join(ROOT, f"research/results/magnet_{sym}.csv"))[["t", "L2", "S2"]]
        pile = h[["t"]].merge(m, on="t", how="left")
    rows = []; inep = False; below = 0; strong = False
    for k in range(1200, n - 73):
        v = volr[k]
        if not v == v or not s6[k] == s6[k]: continue
        if v >= 2.6:
            below = 0
            kind = None
            if not inep: inep, strong, kind = True, False, "alert"
            elif v >= 4 and not strong: kind = "strong"
            if v >= 4: strong = True
            if kind:
                bm = 3 * s6[k]; e = C[k]; a = acc[k]
                lean = {}
                lean["C1"] = None if not a == a else (1 if a < 1.5 else -1 if a > 2.5 else 0)
                lean["C3"] = 1 if r24[k] == r24[k] and r24[k] < -0.05 else lean["C1"]
                lean["C4"] = 1 if r24[k] > 0 else -1
                if pile is not None and a == a:
                    L2, S2 = pile.L2.values[k], pile.S2.values[k]
                    if L2 == L2 and S2 == S2 and L2 + S2 > 0:
                        i = 0 if a < 1.5 else 1 if a <= 2.5 else 2
                        j = 2 if abs(L2 - S2) / (L2 + S2) < 0.05 else (1 if S2 > L2 else 0)
                        u, nn = RISK[i][j]; p = 100 * u / nn
                        lean["C2"] = 1 if p >= 55 else -1 if p <= 45 else 0
                rec = dict(sym=sym[:-4], t=int(t[k]), yr=pd.to_datetime(t[k], unit="s").year, kind=kind, volr=v, bm=bm)
                for hz in (24, 72):
                    rec[f"s{hz}"] = race(H, L, k, e, e * (1 + bm), e * (1 - bm), hz)          # 1:1, arah naik/turun
                    rec[f"u2_{hz}"] = race(H, L, k, e, e * (1 + bm), e * (1 - 0.5 * bm), hz)   # 2:1 untuk condong naik
                    rec[f"d2_{hz}"] = race(H, L, k, e, e * (1 + 0.5 * bm), e * (1 - bm), hz)   # 2:1 untuk condong turun
                for c, d in lean.items(): rec[c] = d
                rows.append(rec)
        else:
            below += 1
            if below >= 24: inep = False
    return pd.DataFrame(rows)


def score(q, rule, hz, geo):
    q = q[q[rule].isin([1, -1])] if rule in q else q.iloc[0:0]
    if q.empty: return "-"
    if geo == "1:1":
        res = np.where(q[rule] == 1, q[f"s{hz}"].map({"up": 1, "down": 0, "both": 0, "none": np.nan}),
                       q[f"s{hz}"].map({"down": 1, "up": 0, "both": 0, "none": np.nan}))
    else:
        res = np.where(q[rule] == 1, q[f"u2_{hz}"].map({"up": 1, "down": 0, "both": 0, "none": np.nan}),
                       q[f"d2_{hz}"].map({"down": 1, "up": 0, "both": 0, "none": np.nan}))
    res = pd.Series(res, dtype=float); dec = res.notna().sum()
    return f"{int(np.nansum(res))}/{dec} = {100 * np.nanmean(res):.0f}% ({len(q)} condong, {len(q) - dec} tak kena keduanya)" if dec else "-"


if __name__ == "__main__":
    E = pd.concat([events(s) for s in COINS], ignore_index=True)
    E.to_csv(os.path.join(ROOT, "research/results/big_move_alerts.csv"), index=False)
    for kind in ("alert", "strong"):
        Q = E[E.kind == kind]
        print(f"\n===== peringatan {'2,6x' if kind == 'alert' else 'kuat 4x'}: {len(Q)} di 8 koin, BTC+ETH {Q.sym.isin(['BTC', 'ETH']).sum()} =====")
        for hz in (24, 72):
            any_ = Q[f"s{hz}"].isin(["up", "down", "both"]).mean()
            print(f"  dalam {hz} jam salah satu sisi 1 BM tersentuh: {100 * any_:.0f}% | naik lebih dulu {100 * (Q[f's{hz}'] == 'up').mean():.0f}%, turun {100 * (Q[f's{hz}'] == 'down').mean():.0f}%")
        for rule in ("C1", "C2", "C3", "C4"):
            for geo in ("1:1", "2:1"):
                for hz in (24, 72):
                    parts = []
                    for nm, q in (("BTC+ETH 20-23", Q[Q.sym.isin(["BTC", "ETH"]) & (Q.yr <= 2023)]), ("BTC+ETH 24-26", Q[Q.sym.isin(["BTC", "ETH"]) & (Q.yr >= 2024)]),
                                  ("8 koin 20-23", Q[Q.yr <= 2023]), ("8 koin 24-26", Q[Q.yr >= 2024])):
                        parts.append(f"{nm}: {score(q, rule, hz, geo)}")
                    print(f"  {rule} {geo} {hz}j | " + " | ".join(parts))
