"""
Sejarah panjang dari arsip publik Binance (https://data.binance.vision), gratis tanpa kunci API.

  candle 5 menit perpetual USDT-M : data/futures/um/monthly/klines/<SYM>/5m/  (BTCUSDT tersedia sejak 2020-01)
                                    data/futures/um/daily/klines/<SYM>/5m/    (bulan berjalan)
  open interest 5 menit            : data/futures/um/daily/metrics/<SYM>/      (BTCUSDT sejak 2020-09-01;
                                    kolom sum_open_interest, satuan koin; create_time UTC + 5 menit = waktu nilai;
                                    ETHUSDT baru tersedia sejak 2021-12-01)

File zip disimpan di .cache/binance/ (tidak masuk repo; GitHub Actions menyimpannya di cache). Unduhan bertahap:
file yang sudah ada tidak diunduh lagi. Arsip ini milik Binance dan tetap tersedia di sana, jadi tidak disalin ke repo.

    python history/binance_public.py            # unduh/perbarui BTCUSDT dan ETHUSDT
"""
import concurrent.futures as cf
import datetime as dt
import io, os, sys, time, urllib.error, urllib.request, zipfile
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache", "binance")
BASE = "https://data.binance.vision/data/futures/um"
PAIRS = ["BTCUSDT", "ETHUSDT"]
KLINES_FROM = dt.date(2020, 1, 1)
METRICS_FROM = dt.date(2020, 9, 1)
OI_GLITCH = 0.10


def _get(url, path):
    """Unduh url ke path. Hasil: 'ok', 'have', atau 'missing' (404)."""
    if os.path.exists(path):
        return "have"
    for k in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "missing"
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"gagal mengunduh {url}")


def _months(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _days(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def jobs(sym, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    last_day = today - dt.timedelta(days=1)
    first_of_month = today.replace(day=1)
    out = []
    for y, m in _months(KLINES_FROM, first_of_month - dt.timedelta(days=1)):
        name = f"{sym}-5m-{y}-{m:02d}.zip"
        out.append(("kl_month", f"{BASE}/monthly/klines/{sym}/5m/{name}", os.path.join(CACHE, sym, "klines", name)))
    # hari-hari bulan berjalan + bulan lalu (file bulanan bulan lalu bisa belum terbit di awal bulan)
    prev_month_start = (first_of_month - dt.timedelta(days=1)).replace(day=1)
    for d in _days(prev_month_start, last_day):
        name = f"{sym}-5m-{d.isoformat()}.zip"
        out.append(("kl_day", f"{BASE}/daily/klines/{sym}/5m/{name}", os.path.join(CACHE, sym, "klines_daily", name)))
    for d in _days(METRICS_FROM, last_day):
        name = f"{sym}-metrics-{d.isoformat()}.zip"
        out.append(("metrics", f"{BASE}/daily/metrics/{sym}/{name}", os.path.join(CACHE, sym, "metrics", name)))
    return out


def download(sym, workers=16):
    js = jobs(sym)
    res = {"ok": 0, "have": 0, "missing": []}
    with cf.ThreadPoolExecutor(workers) as ex:
        for (kind, url, path), r in zip(js, ex.map(lambda j: _get(j[1], j[2]), js)):
            if r == "missing":
                res["missing"].append(os.path.basename(path))
            else:
                res[r] += 1
    return res


def _read_zip_csv(path):
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    first = raw.split(b"\n", 1)[0]
    header = not first[:1].isdigit()
    return pd.read_csv(io.BytesIO(raw), header=0 if header else None)


def _ms(x):
    x = np.asarray(x, dtype="float64")
    return np.where(x > 1e14, x / 1000.0, x)          # sebagian file memakai mikrodetik


def load(sym):
    """Gabungan candle 5 menit + open interest (awal candle). Kolom: t, open, high, low, close, vol, oi."""
    kdir = os.path.join(CACHE, sym, "klines"); ddir = os.path.join(CACHE, sym, "klines_daily")
    frames = []
    for d in (kdir, ddir):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".zip"):
                    k = _read_zip_csv(os.path.join(d, f))
                    k = k.iloc[:, :6]; k.columns = ["t", "open", "high", "low", "close", "vol"]
                    k["t"] = (_ms(k.t) // 1000).astype("int64")
                    frames.append(k)
    px = pd.concat(frames, ignore_index=True).drop_duplicates("t").sort_values("t")
    mdir = os.path.join(CACHE, sym, "metrics"); mf = []
    if os.path.isdir(mdir):
        for f in sorted(os.listdir(mdir)):
            if f.endswith(".zip"):
                m = _read_zip_csv(os.path.join(mdir, f))
                ct = m["create_time"]
                if pd.api.types.is_numeric_dtype(ct):
                    ts = (_ms(ct) // 1000).astype("int64")
                else:
                    ts = ((pd.to_datetime(ct, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64")
                # create_time dibulatkan ke 5 menit, lalu +5 menit: nilai berlabel T = open interest di T + 5 menit.
                # Diuji 29 Okt 2026 vs arsip Binance di repo (8.532 candle): selisih median 0,02% tanpa geser,
                # 0,0% dengan geser +300 detik (BTC dan ETH). Konvensi repo: oi[t] = open interest di awal candle t.
                ts = (np.round(ts / 300) * 300).astype("int64") + 300
                mf.append(pd.DataFrame({"t": ts, "oi": pd.to_numeric(m["sum_open_interest"], errors="coerce")}))
    oi = pd.concat(mf, ignore_index=True).drop_duplicates("t", keep="last") if mf else pd.DataFrame(columns=["t", "oi"])
    df = px.merge(oi, on="t", how="left")
    df = df.sort_values("t").reset_index(drop=True)
    # Bersihkan nilai OI rusak di arsip publik: 0, atau menyimpang > OI_GLITCH dari median 1 jam di sekitarnya
    # (25 titik 5 menit). Ditemukan 29 Okt 2026: OI = 0 di beberapa titik (mis. BTC 2022-03-07, 2024-07-10), yang
    # membuat model mengira miliaran USD posisi baru. Perubahan nyata yang menetap tidak terhapus karena median ikut bergeser.
    med = df.oi.rolling(25, center=True, min_periods=5).median()
    bad = df.oi.notna() & ((df.oi <= 0) | ((df.oi / med - 1).abs() > OI_GLITCH))
    load.glitches = {"removed": int(bad.sum()),
                     "examples": [str(pd.to_datetime(x, unit="s")) for x in df.t[bad].head(10)]}
    df.loc[bad, "oi"] = np.nan
    for col in ("open", "high", "low", "close", "vol"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


if __name__ == "__main__":
    for s in sys.argv[1:] or PAIRS:
        t0 = time.time()
        r = download(s)
        print(f"{s}: baru {r['ok']}, sudah ada {r['have']}, tidak tersedia {len(r['missing'])} "
              f"({', '.join(r['missing'][:5])}{' ...' if len(r['missing']) > 5 else ''}), {time.time() - t0:.0f} detik")
