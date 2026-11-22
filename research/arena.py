"""Arena: metode masuk dari literatur, tiap trade diberi peringkat 1-5 dari data website, diuji pada akun tiruan $100.

ATURAN DI FILE INI DITULIS DAN DI-COMMIT SEBELUM HASIL DILIHAT (22 Nov 2026). Pemenang dipilih pada 2024-01-01 sampai
akhir data (out-of-sample); 2020-2023 hanya untuk melihat. Tidak ada parameter yang disetel ke hasil.

DATA  BTC dan ETH, Binance futures per jam (research/data, data/derived/hourly) sejak 2020; funding harian rata-rata
      Binance/Bybit/OKX (data/markets/funding/daily, persen per 8 jam); rasio akun Binance (BTC sejak Sep 2020, ETH sejak
      Des 2021). Sinyal harian dibaca pada penutupan hari UTC (jam 23); masuk di harga penutupan itu.

AKUN  Mulai $100, berbunga majemuk. Risiko per trade = peringkat x 0,5% modal (peringkat 1 = 0,5% ... 5 = 2,5%).
      Ukuran posisi = risiko / jarak stop. Total nilai posisi terbuka <= 3x modal (posisi baru dikecilkan bila perlu).
      Biaya 0,05% per sisi dari nilai posisi. Funding dibayar/diterima per jam dari funding harian (long bayar bila
      positif). Stop dan target diperiksa per jam (high/low); bila keduanya kena di jam yang sama dihitung stop.
      Satu posisi per metode per koin; sinyal berlawanan menutup posisi lama di penutupan lalu membuka yang baru.
      Modal dicatat harian termasuk untung/rugi belum terealisasi (untuk penurunan terdalam).

AYUNAN  s = simpangan baku perubahan per jam 720 jam terakhir x akar 168 (ayunan mingguan normal, seperti di website).

METODE (sumber):
  M1 Momentum deret waktu (Moskowitz, Ooi, Pedersen 2012; Liu dan Tsyvinski 2021, momentum kripto 1-4 minggu):
     tiap Senin, arah = tanda perubahan 28 hari; tahan 7 hari (diperpanjang bila arah sama). Stop 2s.
  M2 Breakout Donchian 20 hari (aturan Turtle; Hudson dan Urquhart 2021; Quantpedia "max"): long bila penutupan > tertinggi
     20 hari sebelumnya, short bila < terendah 20 hari. Keluar bila penutupan menembus ekstrem 10 hari lawan. Stop 1s.
  M3 Rata-rata bergerak 50 hari (Corbet dkk. 2019; Grobys dkk. 2020): long saat penutupan memotong ke atas MA50, short saat
     memotong ke bawah; keluar pada potongan berlawanan. Stop 2s.
  M4 Reaksi berlebih (Caporale dan Plastun 2019): perubahan harian > 2 simpangan baku harian (30 hari) -> arah berlawanan,
     tahan 3 hari, stop 1s.
  M5 RSI 14 hari (Wilder; uji pembalikan jangka pendek kripto): long bila RSI < 25, short bila > 75; keluar saat RSI
     melewati 50 atau 10 hari. Stop 1s.
  M6 Funding ekstrem (He dkk. 2022 "Fundamentals of Perpetual Futures"; BIS WP 1087 crypto carry): funding 3 hari di atas
     persentil 90 (365 hari sebelumnya) -> short; di bawah persentil 10 -> long. Tahan 7 hari, stop 1s.
  M7 Kerumunan berlawanan (prinsip 1 dan 9 website): rasio akun < 1,5 -> long; > 3 -> short. Tahan 7 hari, stop 1s.
  M8 Kapitulasi (prinsip 21): turun > 5% dalam sehari dengan volume 24 jam >= 2,5x normal -> long, tahan 7 hari,
     target 1s, stop 1s.
  M9 Pantulan (prinsip 28 L4, per jam): fase turun, sesudah tembus terendah 20 hari dengan volume >= 2x, pantulan >= 1s,
     beli di separuh pantulan, stop terendah - 1%, target 2R, maks 30 hari.
  M10 Breakdown (prinsip 20/28, per jam): jam pertama menembus terendah 20 hari (jarak >= 3 hari) -> short di penutupan,
     stop 1s, target 1s, maks 30 hari.
  ENS Semua sinyal M1-M10 dalam satu akun (batas 3x berlaku bersama).

PERINGKAT 1-5 (sama untuk semua metode) = 1 + jumlah kondisi pendukung dari website yang terpenuhi saat masuk:
  a. fase: long dan harga > MA200 harian, atau short dan harga < MA200         (prinsip 2, 4-tahun/200 hari)
  b. kerumunan: long dan rasio akun < 2, atau short dan rasio akun >= 2,5        (prinsip 1, 9, 20)
  c. funding: long dan funding 3 hari < 0,005%, atau short dan > 0,01%          (prinsip 9, 12; eksperimen 3)
  d. momentum: arah sama dengan tanda perubahan 28 hari                          (M1, literatur momentum)
  Data yang belum ada dihitung tidak terpenuhi.
Juga dijalankan versi RATA (risiko tetap 1,5% = peringkat 3) untuk melihat apakah peringkat menambah nilai.

    python research/arena.py
"""
import os, sys, warnings, json
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turning_points import load  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINS = ["BTCUSDT", "ETHUSDT"]
FEE, CAP, RISK_STEP = 0.0005, 3.0, 0.005
METHODS = ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10"]
OOS = pd.Timestamp("2024-01-01").timestamp()


def funding_daily(sym):
    fs = []
    for ex in ("binance", "bybit", "okx"):
        d = pd.read_csv(os.path.join(ROOT, f"data/markets/funding/daily/{sym}_{ex}.csv")).set_index("t").c
        fs.append(d.rename(ex))
    return pd.concat(fs, axis=1).mean(axis=1)            # %/8h, rata-rata bursa yang ada


def rsi(x, n=14):
    d = np.diff(x, prepend=x[0]); up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).values


def prepare(sym):
    h = load(sym).reset_index(drop=True)
    H, L, C, t = h.high.values, h.low.values, h.close.values, h.t.values
    sw = pd.Series(C).pct_change().rolling(720).std().values * np.sqrt(168)
    fd = funding_daily(sym); day = (t // 86400) * 86400
    fund_h = pd.Series(day).map(fd).ffill().fillna(0).values / 100 / 8      # pecahan per jam
    # harian: indeks jam penutupan hari (jam 23 UTC)
    ends = np.nonzero(((t + 3600) % 86400) == 0)[0]
    D = pd.DataFrame(dict(i=ends, t=t[ends], c=C[ends]))
    D["hi"] = [H[max(0, e - 23):e + 1].max() for e in ends]; D["lo"] = [L[max(0, e - 23):e + 1].min() for e in ends]
    D["ma50"] = D.c.rolling(50).mean(); D["ma200"] = D.c.rolling(200, min_periods=150).mean()
    D["hi20"] = D.hi.rolling(20).max().shift(1); D["lo20"] = D.lo.rolling(20).min().shift(1)
    D["hi10"] = D.hi.rolling(10).max().shift(1); D["lo10"] = D.lo.rolling(10).min().shift(1)
    D["r1"] = D.c.pct_change(); D["sd30"] = D.r1.rolling(30).std(); D["r28"] = D.c.pct_change(28)
    D["rsi"] = rsi(D.c.values)
    D["acc"] = h.acc_lsr.values[ends]
    D["f3"] = pd.Series(D.t.values).map(lambda x: fd.loc[x - 2 * 86400:x].mean() if len(fd.loc[x - 2 * 86400:x]) else np.nan).values
    D["fp90"] = pd.Series(D.f3).rolling(365, min_periods=180).quantile(.9).shift(1)
    D["fp10"] = pd.Series(D.f3).rolling(365, min_periods=180).quantile(.1).shift(1)
    v24 = h.vol.rolling(24).sum(); volr = (v24 / v24.rolling(720, min_periods=360).median()).values
    D["volr"] = volr[ends]; D["sw"] = sw[ends]; D["dow"] = pd.to_datetime(D.t, unit="s").dt.dayofweek
    D = D.reset_index(drop=True)
    from types import SimpleNamespace
    rec = [SimpleNamespace(**r) for r in D.to_dict("records")]
    return dict(sym=sym, H=H, L=L, C=C, t=t, sw=sw, fund=fund_h, D=D, rec=rec, volr=volr,
                acc=h.acc_lsr.values, ma200h=pd.Series(C).rolling(24 * 200, min_periods=24 * 150).mean().values)


def rank_of(P, k, d):
    """Peringkat 1-5 untuk arah d (+1/-1) di jam k, memakai hari lengkap terakhir sampai jam k."""
    j = np.searchsorted(P["D"].i.values, k, side="right") - 1
    if j < 0:
        return 1
    r = P["rec"][j]; n = 0
    if r.ma200 == r.ma200 and ((d > 0 and r.c > r.ma200) or (d < 0 and r.c < r.ma200)): n += 1
    a = P["acc"][k]
    if a == a and ((d > 0 and a < 2) or (d < 0 and a >= 2.5)): n += 1
    if r.f3 == r.f3 and ((d > 0 and r.f3 < 0.005) or (d < 0 and r.f3 > 0.01)): n += 1
    if r.r28 == r.r28 and np.sign(r.r28) == d: n += 1
    return 1 + n


def daily_signals(P, m, j):
    """Sinyal masuk metode m pada hari j -> (arah, jarak stop pecahan, target harga atau None, maks jam) atau None."""
    r = P["rec"][j]; s = r.sw
    if not s == s:
        return None
    c = r.c
    if m == "M1":
        if r.dow == 0 and r.r28 == r.r28 and r.r28 != 0:
            return (int(np.sign(r.r28)), 2 * s, None, 7 * 24)
    elif m == "M2":
        if r.hi20 == r.hi20 and c > r.hi20: return (1, s, None, 10**9)
        if r.lo20 == r.lo20 and c < r.lo20: return (-1, s, None, 10**9)
    elif m == "M3":
        p = P["rec"][j - 1] if j > 0 else None
        if p is not None and r.ma50 == r.ma50 and p.ma50 == p.ma50:
            if p.c <= p.ma50 and c > r.ma50: return (1, 2 * s, None, 10**9)
            if p.c >= p.ma50 and c < r.ma50: return (-1, 2 * s, None, 10**9)
    elif m == "M4":
        if r.sd30 == r.sd30 and abs(r.r1) > 2 * r.sd30: return (-int(np.sign(r.r1)), s, None, 3 * 24)
    elif m == "M5":
        if r.rsi < 25: return (1, s, None, 10 * 24)
        if r.rsi > 75: return (-1, s, None, 10 * 24)
    elif m == "M6":
        if r.fp90 == r.fp90 and r.f3 > r.fp90: return (-1, s, None, 7 * 24)
        if r.fp10 == r.fp10 and r.f3 < r.fp10: return (1, s, None, 7 * 24)
    elif m == "M7":
        if r.acc == r.acc and r.acc < 1.5: return (1, s, None, 7 * 24)
        if r.acc == r.acc and r.acc > 3: return (-1, s, None, 7 * 24)
    elif m == "M8":
        if r.r1 < -0.05 and r.volr >= 2.5: return (1, s, c * (1 + s), 7 * 24)
    return None


def daily_exit(P, m, j, d):
    """Keluar berbasis sinyal pada penutupan hari j untuk posisi arah d."""
    r = P["rec"][j]
    if m == "M2":
        return (d > 0 and r.lo10 == r.lo10 and r.c < r.lo10) or (d < 0 and r.hi10 == r.hi10 and r.c > r.hi10)
    if m == "M3":
        return r.ma50 == r.ma50 and ((d > 0 and r.c < r.ma50) or (d < 0 and r.c > r.ma50))
    if m == "M5":
        return (d > 0 and r.rsi >= 50) or (d < 0 and r.rsi <= 50)
    return False


def hourly_signals(P):
    """M9 dan M10: {jam: (metode, arah, harga stop, target, maks jam)}."""
    H, L, C, t, sw, volr = P["H"], P["L"], P["C"], P["t"], P["sw"], P["volr"]; n = len(C)
    pl = pd.Series(L).rolling(480).min().shift(1).values; ma = P["ma200h"]; out = {}
    last = -10**9
    for i in range(1200, n):
        if L[i] < pl[i] and sw[i] == sw[i] and i - last >= 72:
            last = i; out.setdefault(i, []).append(("M10", -1, C[i] * (1 + sw[i]), C[i] * (1 - sw[i]), 720))
    last = -10**9
    for i in range(1200, n):
        if not (L[i] < pl[i] and volr[i] >= 2 and sw[i] == sw[i]) or i - last < 168:
            continue
        last = i
        if not C[i] < ma[i]:
            continue
        s = sw[i]; lo = L[i]; pk = H[i]
        for k in range(i + 1, min(n, i + 961)):
            if L[k] < lo:
                lo = L[k]; pk = H[k]; continue
            e50 = lo + .5 * (pk - lo)
            if pk / lo - 1 >= s and L[k] <= e50:
                stop = lo * .99
                out.setdefault(k, []).append(("M9", 1, stop, e50 + 2 * (e50 - stop), 720, e50))
                break
            pk = max(pk, H[k])
    return out


def simulate(PS, methods, t0, t1, ranked=True, log=None, min_rank=1, step=None):
    n = len(PS[0]["C"]); eq = 100.0; cash = 100.0; pos = {}; curve = []; trades = []
    for P in PS:
        if "HS" not in P: P["HS"] = hourly_signals(P)
    HS = [P["HS"] for P in PS]
    dayend = [set(P["D"].i.values) for P in PS]; jmap = [dict(zip(P["D"].i.values, range(len(P["D"])))) for P in PS]
    t = PS[0]["t"]

    def mtm(k):
        return cash + sum(p["q"] * p["d"] * (PS[p["c"]]["C"][k] - p["e"]) for p in pos.values())

    def close(key, px, k, why):
        nonlocal cash
        p = pos.pop(key); g = p["q"] * p["d"] * (px - p["e"]) - FEE * p["q"] * px
        cash += g; trades.append(dict(m=key[0], coin=PS[key[1]]["sym"][:3], d=p["d"], t_in=int(t[p["k"]]), t_out=int(t[k]),
                                      rank=p["rank"], pnl=g + p["fpaid"], fund=p["fpaid"], R=(g + p["fpaid"]) / p["risk"] if p["risk"] else 0, why=why))

    def open_(m, c, d, k, e, stop, tgt, maxh):
        nonlocal cash
        P = PS[c]; dist = abs(e - stop) / e
        if dist <= 0: return
        rk = rank_of(P, k, d) if ranked else 3
        if rk < min_rank: return
        E = mtm(k); risk = (step or RISK_STEP) * rk * E; notional = risk / dist
        used = sum(p["q"] * PS[p["c"]]["C"][k] for p in pos.values())
        notional = min(notional, max(0.0, CAP * E - used))
        if notional <= 0: return
        q = notional / e; cash -= FEE * notional
        pos[(m, c)] = dict(c=c, d=d, e=e, q=q, stop=stop, tgt=tgt, k=k, maxh=maxh, rank=rk, risk=q * abs(e - stop), fpaid=-FEE * notional)

    k0 = int(np.searchsorted(t, t0)); k1 = int(np.searchsorted(t, t1))
    for k in range(max(k0, 1), min(k1, n)):
        for key in list(pos):
            p = pos[key]; P = PS[p["c"]]
            f = -p["d"] * P["fund"][k] * p["q"] * P["C"][k]; cash += f; p["fpaid"] += f
            hit_stop = P["L"][k] <= p["stop"] if p["d"] > 0 else P["H"][k] >= p["stop"]
            if hit_stop: close(key, p["stop"], k, "stop"); continue
            if p["tgt"] is not None and ((p["d"] > 0 and P["H"][k] >= p["tgt"]) or (p["d"] < 0 and P["L"][k] <= p["tgt"])):
                close(key, p["tgt"], k, "target"); continue
            if k - p["k"] >= p["maxh"]: close(key, P["C"][k], k, "time")
        for c, P in enumerate(PS):
            for sig in HS[c].get(k, []):
                m = sig[0]
                if m not in methods or (m, c) in pos: continue
                if m == "M9":
                    _, d, stop, tgt, maxh, e = sig; open_(m, c, d, k, e, stop, tgt, maxh)
                    if (m, c) in pos and P["L"][k] <= stop: close((m, c), stop, k, "stop")   # terisi lalu stop di jam yang sama
                else:
                    _, d, stop, tgt, maxh = sig; open_(m, c, d, k, P["C"][k], stop, tgt, maxh)
            if k in dayend[c]:
                j = jmap[c][k]
                for m in methods:
                    if m in ("M9", "M10"): continue
                    key = (m, c)
                    if key in pos and daily_exit(P, m, j, pos[key]["d"]): close(key, P["C"][k], k, "signal")
                    s = daily_signals(P, m, j)
                    if s is None: continue
                    d, dist, tgt, maxh = s
                    if key in pos:
                        if pos[key]["d"] == d:
                            pos[key]["k"] = k; continue                      # arah sama: perpanjang waktu tahan
                        close(key, P["C"][k], k, "reverse")
                    e = P["C"][k]; open_(m, c, d, k, e, e * (1 - d * dist), tgt, maxh)
        if k in dayend[0]:
            curve.append((int(t[k]), mtm(k)))
    for key in list(pos):
        close(key, PS[pos[key]["c"]]["C"][min(k1, n) - 1], min(k1, n) - 1, "end")
    cv = pd.DataFrame(curve, columns=["t", "equity"]); cv.loc[len(cv)] = [int(t[min(k1, n) - 1]), cash]
    dd = (cv.equity / cv.equity.cummax() - 1).min() * 100
    return dict(final=cash, dd=dd, trades=pd.DataFrame(trades), curve=cv)


if __name__ == "__main__":
    PS = [prepare(s) for s in COINS]
    tend = int(PS[0]["t"][-1]) + 3600
    periods = (("2020-2023 (dalam sampel)", pd.Timestamp("2020-01-01").timestamp(), OOS),
               ("2024-2026 (UJI, penentu pemenang)", OOS, tend), ("2020-2026 penuh", pd.Timestamp("2020-01-01").timestamp(), tend))
    res = {}; allT = []
    for name, a, b in periods:
        print(f"\n=== {name}: akun $100 ===")
        rows = []
        for m in METHODS + ["ENS"]:
            ms = METHODS if m == "ENS" else [m]
            r = simulate(PS, ms, a, b, ranked=True); f = simulate(PS, ms, a, b, ranked=False)
            T = r["trades"]
            rows.append((m, r["final"], r["dd"], len(T), 100 * (T.pnl > 0).mean() if len(T) else 0, f["final"], f["dd"]))
            if name.startswith("2020-2026") and m != "ENS":
                allT.append(T.assign(period=np.where(T.t_in < OOS, "IS", "OOS")))
            res[(name, m)] = r
        rows.sort(key=lambda x: -x[1])
        for m, fin, dd, nt, wr, ff, fdd in rows:
            print(f"  {m:>4}: berperingkat ${fin:8.2f} (turun terdalam {dd:6.1f}%) | {nt:4d} trade, untung {wr:3.0f}% | rata ${ff:8.2f} ({fdd:6.1f}%)")
    A = pd.concat(allT)
    print("\nApakah peringkat mengurutkan hasil? (semua trade M1-M10, R = untung/rugi dalam kelipatan risiko)")
    for per in ("IS", "OOS"):
        q = A[A.period == per]; g = q.groupby("rank").agg(n=("R", "size"), R=("R", "mean"), win=("pnl", lambda x: 100 * (x > 0).mean()))
        print(f"  {per}: " + "  ".join(f"peringkat {k}: {int(v.n)} trade, rata-rata {v.R:+.2f}R, untung {v.win:.0f}%" for k, v in g.iterrows()))
    out = os.path.join(ROOT, "research/results/arena_trades.csv"); A.to_csv(out, index=False); print("trade:", out)
