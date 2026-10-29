"""
Replika heatmap likuidasi CoinGlass (Model 1, jendela 24 jam), model v6, dari data di repository ini.

Ambil data kapan saja (dijalankan oleh Claude atau di komputer mana pun yang punya salinan repo):
    python heatmap/snapshot.py BTCUSDT                       # candle terakhir yang ada
    python heatmap/snapshot.py ETHUSDT "2026-10-28 15:00"    # waktu lampau, jam WIB
Hasil di output/<SIMBOL>/ (tidak masuk repo): ..._levels.csv, ..._heatmap.csv, ..._heatmap.png

Dipakai juga oleh GitHub Actions tiap jalan (--save-history): level aktif disimpan ringkas ke
    data/heatmap_levels/<SIMBOL>_<YYYY-MM>.csv   (hanya menambah)
"""
import csv, os, sys
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from model import run, PARAMS_V6          # noqa: E402
import inputs                              # noqa: E402

WIB = timezone(timedelta(hours=7))
P = PARAMS_V6
N = P["window_candles"]
PAIRS = ["BTCUSDT", "ETHUSDT"]


def bins_for(last_price):
    """Kotak harga ala CoinGlass: lebar bin_pct x harga, berjangkar di angka bulat, geser shift_pct."""
    w = P["bin_pct"] * last_price
    k = 10 ** int(np.floor(np.log10(last_price)))
    off = (round(last_price / k) * k) % w
    return w, off, P["shift_pct"] * last_price


def aggregate(snap, w, off, dx):
    """Jumlahkan level ke kotak harga. Hasil: dict (nomor_kotak, sisi) -> USD."""
    out = {}
    for price, usd, side in snap:
        b = int(np.floor((price + dx - off) / w))
        out[(b, side)] = out.get((b, side), 0.0) + usd
    return out


def unique_path(path):
    base, ext = os.path.splitext(path); i = 2
    while os.path.exists(path):
        path = f"{base}_{i}{ext}"; i += 1
    return path


def compute(sym, at_wib=None):
    """Hitung heatmap. Hasil: dict berisi jendela data, snapshot level per candle, kotak harga."""
    df = inputs.load(sym)
    if at_wib:
        t_end = datetime.strptime(at_wib, "%Y-%m-%d %H:%M").replace(tzinfo=WIB).timestamp()
        df = df[df.t + 300 <= t_end].reset_index(drop=True)      # hanya candle yang sudah selesai
    if len(df) < N + 1:
        raise SystemExit(f"Data {sym} belum cukup untuk jendela 24 jam ({len(df)} candle).")
    win = df.iloc[-N:]
    n_gap = int((np.diff(win.t.values) != 300).sum())
    _, snaps = run(df, P)
    last_price = float(win.close.iat[-1])
    w, off, dx = bins_for(last_price)
    t_last = datetime.fromtimestamp(int(win.t.iat[-1]) + 300, WIB)
    levels = []
    for (b, side), usd in sorted(aggregate(snaps[-1], w, off, dx).items()):
        lo = off + b * w
        levels.append(dict(price_low=round(lo, 4), price_high=round(lo + w, 4), price_mid=round(lo + w / 2, 4),
                           side=side, usd=round(usd, 2),
                           pct_from_price=round((lo + w / 2) / last_price * 100 - 100, 3)))
    return dict(sym=sym, win=win, snaps=snaps, w=w, off=off, dx=dx, last_price=last_price,
                t_last=t_last, levels=levels, n_gap=n_gap)


SAVE_GAP_MIN = 210   # level aktif disimpan paling sering tiap ±4 jam walau collect jalan tiap jam (hemat ukuran repo;
                     # level bisa dihitung ulang kapan saja dari data 5 menit dengan snapshot.py "YYYY-MM-DD HH:MM")


def save_history(r):
    """Simpan level aktif ke data/heatmap_levels (hanya menambah; satu waktu tidak disimpan dua kali;
    dilewati bila simpanan terakhir di file bulan ini < SAVE_GAP_MIN menit sebelumnya)."""
    ts = r["t_last"].strftime("%Y-%m-%d %H:%M")
    path = os.path.join(ROOT, "data", "heatmap_levels", f"{r['sym']}_{r['t_last']:%Y-%m}.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, newline="") as f:
            times = {row["time_wib"] for row in csv.DictReader(f)}
        if ts in times:
            return 0
        if times:
            last = datetime.strptime(max(times), "%Y-%m-%d %H:%M").replace(tzinfo=WIB)
            if (r["t_last"] - last).total_seconds() < SAVE_GAP_MIN * 60:
                return 0
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["time_wib", "price_mid", "side", "usd", "pct_from_price", "price_now"])
        if new:
            wr.writeheader()
        for lv in r["levels"]:
            if lv["usd"] >= 1:
                wr.writerow(dict(time_wib=ts, price_mid=lv["price_mid"], side=lv["side"], usd=round(lv["usd"]),
                                 pct_from_price=lv["pct_from_price"], price_now=r["last_price"]))
    return len(r["levels"])


def write_outputs(r, plot=True):
    sym, w, off, dx, win, snaps = r["sym"], r["w"], r["off"], r["dx"], r["win"], r["snaps"]
    tag = r["t_last"].strftime("%Y%m%d_%H%M") + "WIB"
    outdir = os.path.join(ROOT, "output", sym); os.makedirs(outdir, exist_ok=True)
    p_lv = unique_path(os.path.join(outdir, f"{sym}_{tag}_levels.csv"))
    pd.DataFrame(r["levels"]).to_csv(p_lv, index=False)
    p_hm = unique_path(os.path.join(outdir, f"{sym}_{tag}_heatmap.csv"))
    with open(p_hm, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f); wr.writerow(["time_wib", "price_mid", "usd"])
        for t, snap in zip(win.t.values, snaps):
            ts = datetime.fromtimestamp(int(t) + 300, WIB).strftime("%Y-%m-%d %H:%M")
            agg = {}
            for (b, _s), usd in aggregate(snap, w, off, dx).items():
                agg[b] = agg.get(b, 0.0) + usd
            for b, usd in sorted(agg.items()):
                wr.writerow([ts, round(off + b * w + w / 2, 4), round(usd, 2)])
    p_png = None
    if plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        lp = r["last_price"]
        b0, b1 = int(np.floor((lp * 0.95 - off) / w)), int(np.floor((lp * 1.05 - off) / w))
        grid = np.zeros((b1 - b0 + 1, N))
        for k, snap in enumerate(snaps):
            for (b, _s), usd in aggregate(snap, w, off, dx).items():
                if b0 <= b <= b1:
                    grid[b - b0, k] += usd
        fig, ax = plt.subplots(figsize=(12, 6))
        im = ax.imshow(grid / 1e6, aspect="auto", origin="lower", cmap="viridis",
                       extent=[0, N, off + b0 * w, off + (b1 + 1) * w])
        ax.plot(np.arange(N) + 0.5, win.close.values, color="white", lw=0.7)
        fig.colorbar(im, label="juta USD")
        ax.set_title(f"{sym} — replika heatmap likuidasi 24 jam, s/d {r['t_last']:%Y-%m-%d %H:%M} WIB")
        ax.set_xlabel("candle 5 menit"); ax.set_ylabel("harga")
        p_png = unique_path(os.path.join(outdir, f"{sym}_{tag}_heatmap.png"))
        fig.savefig(p_png, dpi=90, bbox_inches="tight"); plt.close(fig)
    return p_lv, p_hm, p_png


def report(r):
    print(f"{r['sym']} s/d {r['t_last']:%Y-%m-%d %H:%M} WIB | harga {r['last_price']:,.2f}"
          + (f" | PERINGATAN: {r['n_gap']} lubang data di jendela ini" if r["n_gap"] else ""))
    top = sorted(r["levels"], key=lambda x: -x["usd"])[:10]
    print("10 level terbesar:")
    for x in sorted(top, key=lambda x: x["price_mid"]):
        print(f"  {x['price_mid']:>12,.2f}  {x['side']:5s}  {x['usd']/1e6:7.2f} juta USD  ({x['pct_from_price']:+.2f}%)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--save-history" in sys.argv:                    # mode GitHub Actions
        for sym in PAIRS:
            r = compute(sym)
            report(r)
            print(f"  disimpan {save_history(r)} level ke data/heatmap_levels")
    elif args:
        r = compute(args[0].upper(), args[1] if len(args) > 1 else None)
        report(r)
        print("File:", *write_outputs(r, plot="--no-plot" not in sys.argv), sep="\n  ")
    else:
        raise SystemExit(__doc__)
