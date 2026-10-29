"""
Model heatmap likuidasi buatan sendiri (reverse-engineering CoinGlass).

Input : data/btcusdt_5m.csv  (Binance futures BTCUSDT, candle 5 menit + open interest 5 menit)
Output: matriks [waktu x harga] berisi nilai posisi (USD) yang diperkirakan
        akan terlikuidasi di tiap level harga, pada tiap titik waktu.

Semua asumsi dikumpulkan di PARAMS supaya tiap iterasi tercatat jelas.
"""
import numpy as np
import pandas as pd

PARAMS_V1 = dict(
    window_candles=288,          # A9: 24 jam = 288 candle 5 menit; posisi sebelum jendela diabaikan
    oi_shift=1,                  # A1: ΔOI candle i = OI[i+1]-OI[i] (snapshot OI = awal candle)
    entry="typical",             # A4: harga masuk = (high+low+close)/3
    leverages=[10, 25, 50, 100], # A6: tingkat leverage yang diasumsikan
    lev_weights=[0.25, 0.25, 0.25, 0.25],
    mmr=0.004,                   # A7: maintenance margin rate 0,4% (asumsi tier terendah)
    long_share=0.5,              # A5: tiap kontrak = 1 long + 1 short -> porsi sama
    close_rule="proportional",   # A3: ΔOI negatif mengurangi semua level secara proporsional
    sweep=True,                  # A8: level dihapus begitu harga (high/low) menyentuhnya
    bin_usd=50.0,                # lebar bin harga untuk tampilan
)


# Versi terbaik setelah dicocokkan ke CoinGlass (BTC, 28 Okt 2026). Perubahan dari v1:
#  - leverage 25x/50x/100x (garis CoinGlass tepat di ±4%, ±2%, ±1% dari harga masuk)
#  - tanpa maintenance margin (mmr=0) -> jarak likuidasi = 1/leverage
#  - hanya data di dalam jendela 24 jam (history=0); memasukkan riwayat menurunkan kecocokan
#  - harga masuk = tengah open-close; level dikelompokkan ke bin ±0,074% (≈ $60 di BTC 81 rb)
PARAMS_V5 = dict(
    PARAMS_V1,
    leverages=[25, 50, 100],
    lev_weights=[0.2, 0.3, 0.5],   # bobot hasil grid; skor nyaris datar terhadap pilihan ini
    mmr=0.0,
    entry="ocmid",
    history=0,
    bin_pct=0.00074,
)


# Iterasi 6 (dicocokkan ke 3 screenshot BTC; bobot TIDAK di-fit, mengikuti aturan sederhana):
#  - tiap sisi (long & short) = 100% kenaikan OI dalam USD, dibagi ke 25x/50x/100x sebanding leverage
#    (25/175, 50/175, 100/175) — hasil fitting bebas memberi angka yang sama (0,15/0,29/0,57)
#  - harga masuk = rata-rata OHLC candle; margin minimum 0,01%
#  - tampilan: kotak harga 0,0744% (BTC ±$60), berjangkar di angka bulat, geser +0,025%
PARAMS_V6 = dict(
    PARAMS_V5,
    lev_weights=[25 / 175, 50 / 175, 100 / 175],
    entry="ohlc4",
    mmr=0.0001,
    bin_pct=0.000744,
    shift_pct=0.00025,
    render="coinglass",
)


def liq_price(entry, lev, mmr, side):
    """Harga likuidasi isolated-margin yang disederhanakan (tanpa biaya)."""
    if side == "long":
        return entry * (1 - 1 / lev + mmr)
    return entry * (1 + 1 / lev - mmr)


def run(df, p):
    df = df.copy().reset_index(drop=True)
    if p["oi_shift"] == 1:
        d_oi = df["oi"].shift(-1) - df["oi"]                   # ΔOI candle i = OI[i+1]-OI[i]
    else:
        d_oi = df["oi"] - df["oi"].shift(1)                    # ΔOI candle i = OI[i]-OI[i-1]
    if p.get("amount") == "volume":                            # alternatif: pakai volume, bukan ΔOI
        d_oi = df["vol"].astype(float)
    if p.get("amount") == "oi_value":
        # perubahan NILAI open interest (USD): ikut naik saat harga naik walau tak ada posisi baru.
        # nilai OI di awal candle ≈ OI x open; di akhir ≈ OI_berikut x close. Dibagi harga masuk nanti.
        oiv0 = df["oi"] * df["open"]; oiv1 = df["oi"].shift(-1) * df["close"]
        d_oi = (oiv1 - oiv0) / ((df["open"] + df["high"] + df["low"] + df["close"]) / 4)
    E = {
        "typical": (df["high"] + df["low"] + df["close"]) / 3,
        "close": df["close"], "open": df["open"], "high": df["high"], "low": df["low"],
        "ohlc4": (df["open"] + df["high"] + df["low"] + df["close"]) / 4,
        "hl2": (df["high"] + df["low"]) / 2,
        "ocmid": (df["open"] + df["close"]) / 2,
        "next_close": df["close"].shift(-1).fillna(df["close"]),
    }
    if "vwap" in df:
        E["vwap"] = df["vwap"]                                  # harga rata-rata tertimbang volume
    entry = E[p["entry"]]

    agg = p.get("oi_block", 1)                                 # >1: ΔOI dihitung per blok k candle (bersih)
    if agg > 1:
        # ΔOI bersih per blok, diberikan ke candle terakhir blok; harga masuk = rata-rata harga blok
        blk = (np.arange(len(df)) - (len(df) - 1)) // agg       # blok sejajar dengan candle terakhir
        oi_next = df["oi"].shift(-1)
        g = pd.DataFrame({"blk": blk, "oi0": df["oi"], "oi1": oi_next, "e": entry})
        first = g.groupby("blk").oi0.transform("first"); last = g.groupby("blk").oi1.transform("last")
        is_last = g.blk != g.blk.shift(-1)
        d_oi = pd.Series(np.where(is_last, last - first, 0.0), index=df.index)
        entry = g.groupby("blk").e.transform("mean")
    if p.get("create_shift", 0):                               # geser waktu munculnya posisi
        d_oi = d_oi.shift(p["create_shift"])
    start = len(df) - p["window_candles"]
    # A10: posisi yang dibuka sebelum jendela tampilan ikut disimulasikan (pemanasan)
    sim_start = max(1, start - p.get("history", 0))
    sweep_mode = p.get("sweep_mode", "touch" if p["sweep"] else "none")
    n_entry = p.get("entry_points", 1)                         # >1: harga masuk disebar di rentang candle
    min_frac = p.get("min_doi_frac", 0.0)                      # abaikan ΔOI kecil (relatif ke OI)
    # daftar level aktif: [harga_likuidasi, nilai_usd, sisi, candle_dibuat]
    levels = []
    snapshots = []                                             # isi aktif di akhir tiap candle
    for i in range(sim_start, len(df)):
        hi, lo, cl = df.at[i, "high"], df.at[i, "low"], df.at[i, "close"]
        # 1) sapu level yang tersentuh harga candle ini
        if levels and sweep_mode == "touch":
            levels = [lv for lv in levels if not (lo <= lv[0] <= hi)]
        elif levels and sweep_mode == "close":
            levels = [lv for lv in levels if not ((lv[2] == "long" and cl <= lv[0]) or
                                                  (lv[2] == "short" and cl >= lv[0]))]
        # 2) perubahan OI
        dv = d_oi.iat[i]
        if np.isnan(dv):
            dv = 0.0
        if dv > 0 and dv >= min_frac * df.at[i, "oi"]:
            if n_entry > 1:
                ents = np.linspace(lo, hi, n_entry)
            else:
                ents = [entry.iat[i]]
            ls = p["long_share"]
            if ls == "taker":
                ls = float(df.at[i, "taker_buy"] / max(df.at[i, "vol"], 1e-9))
            for e in ents:
                usd = dv * e / len(ents)
                for lev, w in zip(p["leverages"], p["lev_weights"]):
                    for side, share in (("long", ls), ("short", 1 - ls)):
                        mm = p.get("mmr_by_lev", {}).get(lev, p["mmr"])
                        lp = liq_price(e, lev, mm, side)
                        # level yang sudah terlewati saat dibuat tidak dihitung
                        if sweep_mode == "touch" and lo <= lp <= hi:
                            continue
                        levels.append([lp, usd * w * share * 2, side, i])
                        # *2 karena long dan short masing2 bernilai penuh ΔOI (1 kontrak = 2 sisi)
        elif dv < 0 and levels and p["close_rule"] == "proportional":
            total_open = df.at[i, "oi"] * entry.iat[i]
            frac = max(0.0, 1 + dv * entry.iat[i] / max(total_open, 1e-9))
            for lv in levels:
                lv[1] *= frac
        elif dv < 0 and levels and p["close_rule"] == "recent":
            # posisi yang baru dibuka dianggap paling dulu ditutup
            need = -dv * entry.iat[i] * 2                      # nilai yang ditutup (dua sisi)
            for lv in sorted(levels, key=lambda x: -x[3]):
                if need <= 0:
                    break
                take = min(lv[1], need)
                lv[1] -= take; need -= take
            levels = [lv for lv in levels if lv[1] > 1e-6]
        lb = p.get("lookback")                                 # umur maksimum posisi (candle); None = tak terbatas
        if lb is not None:
            levels = [lv for lv in levels if lv[3] > i - lb]
        if i >= start:
            snapshots.append([(lv[0], lv[1], lv[2]) for lv in levels])
    times = df["t"].iloc[start:].to_numpy()
    return times, snapshots


def to_grid(times, snapshots, lo, hi, bin_usd):
    edges = np.arange(lo, hi + bin_usd, bin_usd)
    grid = np.zeros((len(times), len(edges) - 1))
    for k, snap in enumerate(snapshots):
        if not snap:
            continue
        px = np.array([s[0] for s in snap]); val = np.array([s[1] for s in snap])
        idx = np.searchsorted(edges, px) - 1
        ok = (idx >= 0) & (idx < grid.shape[1])
        np.add.at(grid[k], idx[ok], val[ok])
    centers = (edges[:-1] + edges[1:]) / 2
    return grid, centers


if __name__ == "__main__":
    # python model.py [file_csv] [v1|v5]
    import sys
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    path = sys.argv[1] if len(sys.argv) > 1 else "data/btcusdt_5m.csv"
    p = PARAMS_V1 if (len(sys.argv) > 2 and sys.argv[2] == "v1") else PARAMS_V6
    df = pd.read_csv(path)
    times, snaps = run(df, p)
    px_now = df["close"].iat[-1]
    bin_usd = p.get("bin_pct", 0.00074) * px_now
    grid, centers = to_grid(times, snaps, px_now * 0.94, px_now * 1.06, bin_usd)
    last = grid[-1]
    print(f"harga terakhir {px_now:,.1f} | level aktif: {len(snaps[-1])}")
    print("10 level likuidasi terbesar saat ini (harga, juta USD):")
    for j in sorted(np.argsort(last)[::-1][:10]):
        side = "long " if centers[j] < px_now else "short"
        print(f"  {centers[j]:>10,.0f}  {side}  {last[j]/1e6:6.1f}")
    win = df.iloc[-p["window_candles"]:]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(grid.T, aspect="auto", origin="lower", cmap="viridis",
              extent=[0, len(times), centers[0], centers[-1]],
              vmax=np.quantile(grid[grid > 0], 0.995))
    ax.plot(np.arange(len(times)) + 0.5, win["close"].values, color="white", lw=0.8)
    ax.set_xlabel("candle 5 menit (jendela 24 jam)"); ax.set_ylabel("harga")
    ax.set_title("Heatmap likuidasi — model sendiri")
    fig.savefig("heatmap_model.png", dpi=90, bbox_inches="tight")
    print("gambar -> heatmap_model.png")
