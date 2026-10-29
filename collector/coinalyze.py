"""
Pengumpul data gratis dari Coinalyze (berjalan di GitHub Actions, tidak butuh laptop).

Yang dikumpulkan, untuk Binance BTCUSDT & ETHUSDT perpetual, per 1 menit dan 5 menit:
  liquidations  : nilai likuidasi per interval (USD), kolom l dan s dari Coinalyze
  ohlcv         : harga open/high/low/close + volume (untuk tahu di harga berapa likuidasi terjadi)
  open_interest : open interest (satuan koin) open/high/low/close per interval

Kenapa harus rutin: Coinalyze hanya menyimpan 1.500–2.000 titik data terakhir per interval
(1 menit ≈ 1 hari, 5 menit ≈ 5–7 hari). Data yang sudah lewat tidak bisa diambil lagi.

Sifat penyimpanan:
- HANYA MENAMBAH: baris lama tidak pernah dihapus/diubah; baris dengan waktu sama tidak dobel.
- Interval yang belum selesai tidak disimpan.
- Ditulis ke file sementara lalu diganti sekaligus (aman bila terputus).
- File dipecah per bulan: data/<dataset>/<interval>/<SIMBOL>_<YYYY-MM>.csv
- Setiap jalan dicatat di logs/runs.csv
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

API = "https://api.coinalyze.net/v1"
PAIRS = ["BTCUSDT", "ETHUSDT"]                      # simbol di Binance (USDT-margined perpetual)
INTERVALS = {"1min": 60, "5min": 300}
LOOKBACK = {"1min": 36 * 3600, "5min": 8 * 86400}   # sedikit melebihi retensi Coinalyze
DATASETS = {
    # nama        : (endpoint, parameter tambahan, kolom dari Coinalyze)
    "liquidations": ("liquidation-history", {"convert_to_usd": "true"}, ["l", "s"]),
    "ohlcv": ("ohlcv-history", {}, ["o", "h", "l", "c", "v", "bv", "tx", "btx"]),
    "open_interest": ("open-interest-history", {"convert_to_usd": "false"}, ["o", "h", "l", "c"]),
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LOGF = os.path.join(ROOT, "logs", "runs.csv")
MAX_CALLS_PER_MIN = 35                              # batas Coinalyze 40/menit, sisakan ruang
STALE_HOURS = 3                                     # data 5 menit lebih tua dari ini = dianggap macet


class Client:
    def __init__(self, key, opener=None):
        self.key, self.calls, self.window = key, 0, []
        self.opener = opener or self._http

    def _http(self, url, headers):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read()

    def get(self, path, params, cost=1):
        # jaga batas panggilan per menit
        now = time.time()
        self.window = [t for t in self.window if now - t < 60]
        if len(self.window) + cost > MAX_CALLS_PER_MIN:
            time.sleep(60 - (now - self.window[0]) + 1)
        url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(5):
            status, headers, body = self.opener(url, {"api_key": self.key, "Accept": "application/json"})
            self.window += [time.time()] * cost
            self.calls += cost
            if status == 200:
                return json.loads(body)
            if status == 429:
                time.sleep(float(headers.get("Retry-After", 10)) + 1)
                continue
            if status >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {status} untuk {path}: {body[:200]!r}")
        raise RuntimeError(f"gagal setelah 5 percobaan: {path}")


def resolve_symbols(client):
    """Cari kode simbol Coinalyze untuk pasangan Binance perpetual (bukan ditebak)."""
    ex = client.get("exchanges", {})
    codes = {e["code"] for e in ex if e["name"].strip().lower() == "binance"}
    if not codes:
        raise RuntimeError(f"kode bursa Binance tidak ditemukan: {[e['name'] for e in ex][:20]}")
    mk = client.get("future-markets", {})
    out = {}
    for m in mk:
        if m["exchange"] in codes and m.get("is_perpetual") and m["symbol_on_exchange"] in PAIRS:
            if m["symbol_on_exchange"] in out:
                raise RuntimeError(f"lebih dari satu pasar untuk {m['symbol_on_exchange']}: "
                                   f"{out[m['symbol_on_exchange']]['symbol']} dan {m['symbol']}")
            out[m["symbol_on_exchange"]] = m
    missing = [p for p in PAIRS if p not in out]
    if missing:
        cand = [(m["symbol"], m["symbol_on_exchange"], m.get("margined")) for m in mk
                if m["exchange"] in codes and m["symbol_on_exchange"] in PAIRS]
        raise RuntimeError(f"simbol tidak ditemukan untuk {missing}; kandidat: {cand}")
    return {p: out[p] for p in PAIRS}


def month_path(dataset, interval, pair, t):
    ym = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m")
    return os.path.join(DATA, dataset, interval, f"{pair}_{ym}.csv")


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {int(r["t"]): r for r in csv.DictReader(f)}


def save(path, rows, cols):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["t"] + cols)
        w.writeheader()
        for t in sorted(rows):
            w.writerow({"t": t, **{c: rows[t].get(c, "") for c in cols}})
    os.replace(tmp, path)


def last_stored(dataset, interval, pair):
    d = os.path.join(DATA, dataset, interval)
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.startswith(pair + "_") and f.endswith(".csv"))
    for f in reversed(files):
        rows = load(os.path.join(d, f))
        if rows:
            return max(rows)
    return None


def merge_append(dataset, interval, pair, history, cols, now):
    """Tambah baris baru (tanpa menghapus/ubah yang lama). Hasil: jumlah baris ditambah."""
    step = INTERVALS[interval]
    by_file = {}
    for h in history:
        t = int(h["t"])
        if t + step > now:                          # interval belum selesai -> lewati
            continue
        by_file.setdefault(month_path(dataset, interval, pair, t), {})[t] = {c: h.get(c, "") for c in cols}
    added = 0
    for path, new in by_file.items():
        old = load(path)
        fresh = {t: r for t, r in new.items() if t not in old}
        if not fresh:
            continue
        merged = dict(old); merged.update(fresh)
        if len(merged) < len(old):
            raise RuntimeError(f"{path}: akan menyusut, dibatalkan")
        save(path, merged, cols)
        added += len(fresh)
    return added


def log_run(rec):
    os.makedirs(os.path.dirname(LOGF), exist_ok=True)
    new = not os.path.exists(LOGF)
    with open(LOGF, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rec))
        if new:
            w.writeheader()
        w.writerow(rec)


def run(client, now=None):
    now = int(now or time.time())
    syms = resolve_symbols(client)
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "symbols.json"), "w") as f:
        json.dump({p: {k: m.get(k) for k in ("symbol", "exchange", "symbol_on_exchange", "margined",
                                                 "oi_lq_vol_denominated_in")} for p, m in syms.items()}, f, indent=1)
    summary, errors = {}, []
    for ds, (endpoint, extra, cols) in DATASETS.items():
        for iv, step in INTERVALS.items():
            # satu panggilan untuk semua pasangan (maks 20 simbol); dari titik tersimpan paling awal
            starts = []
            for p in PAIRS:
                last = last_stored(ds, iv, p)
                starts.append(max(now - LOOKBACK[iv], (last + step) if last else 0))
            frm = min(starts)
            if frm >= now - step:
                continue
            params = {"symbols": ",".join(syms[p]["symbol"] for p in PAIRS), "interval": iv,
                      "from": frm, "to": now, **extra}
            try:
                resp = client.get(endpoint, params, cost=len(PAIRS))
            except Exception as e:                  # satu kegagalan tidak menghentikan yang lain
                errors.append(f"{ds}/{iv}: {e}")
                continue
            back = {r["symbol"]: r.get("history", []) for r in resp}
            for p in PAIRS:
                hist = back.get(syms[p]["symbol"], [])
                summary[f"{ds}/{iv}/{p}"] = merge_append(ds, iv, p, hist, cols, now)
    # cek kesegaran: data 5 menit terbaru harus berumur < STALE_HOURS. Jika tidak, tandai gagal
    # (mencegah jalan "sukses" padahal Coinalyze diam-diam tidak mengirim data baru).
    for p in PAIRS:
        for ds in ("ohlcv", "open_interest"):
            last = last_stored(ds, "5min", p)
            if last is None or now - last > STALE_HOURS * 3600:
                age = "tidak ada data" if last is None else f"{(now - last) / 3600:.1f} jam"
                errors.append(f"DATA BASI {ds}/5min/{p}: data terbaru {age} lalu")
    rec = {"run_utc": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d %H:%M"),
           "api_calls": client.calls, "rows_added": sum(summary.values()),
           "detail": json.dumps(summary), "errors": " | ".join(errors)}
    log_run(rec)
    print(json.dumps(rec, indent=1))
    if errors:
        sys.exit(1)                                 # tandai gagal agar GitHub mengirim email
    return summary


if __name__ == "__main__":
    key = os.environ.get("COINALYZE_API_KEY", "").strip()
    if not key:
        sys.exit("COINALYZE_API_KEY belum diisi (Settings > Secrets and variables > Actions)")
    os.makedirs(DATA, exist_ok=True)
    run(Client(key))
