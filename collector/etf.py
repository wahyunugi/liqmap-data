"""
Arus harian ETF spot Bitcoin dan Ether di AS (juta USD per ETF per hari), dari rekap Farside Investors (farside.co.uk).

Apa ini: ETF spot (IBIT BlackRock, FBTC Fidelity, dll.) wajib memegang koin sungguhan. Arus masuk = investor membeli
saham ETF lebih banyak dari yang menjual, sehingga ETF membeli koin sebanyak itu; arus keluar = ETF menjual koin.
Angka negatif ditulis Farside dalam kurung, mis. "(65.4)". "-" = belum ada / belum dilaporkan.

Penyimpanan: data/etf/<BTC|ETH>.csv, satu baris per hari bursa AS: date, kolom per ETF, total.
Tiap jalan diambil halaman ringkas (±2–3 minggu terakhir); halaman "all data" (seluruh riwayat sejak Jan 2024 untuk
BTC, Jul 2024 untuk ETH) diambil bila file belum ada atau sekali sehari (jam 00 UTC) untuk menangkap revisi.
Baris dengan tanggal yang sama ditimpa angka terbaru (Farside merevisi angka beberapa penerbit sehari kemudian).
Hari libur bursa (semua ETF "-") dilewati.

    python collector/etf.py
"""
import csv, os, re, sys, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "etf")
PAGES = {
    "BTC": ("https://farside.co.uk/btc/", "https://farside.co.uk/bitcoin-etf-flow-all-data/"),
    "ETH": ("https://farside.co.uk/eth/", "https://farside.co.uk/ethereum-etf-flow-all-data/"),
}
UA = "liqmap-data collector (https://github.com/wahyunugi/liqmap-data)"
DATE_RE = re.compile(r"^\d{1,2} [A-Z][a-z]{2} \d{4}$")
TICKER_RE = re.compile(r"^[A-Z]{2,6}$")


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell, self.depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1; self.tables.append([])
        elif tag == "tr" and self.depth:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split())); self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.tables:
                self.tables[-1].append(self.row)
            self.row = None
        elif tag == "table":
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def num(s):
    s = s.strip().replace(",", "")
    if s in ("", "-", "–"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    v = float(s.strip("()"))
    return -v if neg else v


def parse(html):
    p = Tables(); p.feed(html)
    t = max(p.tables, key=len)
    hdr = next(r for r in t if sum(bool(TICKER_RE.match(c)) for c in r) >= 3)
    tickers = [c for c in hdr[1:] if TICKER_RE.match(c)]
    out = {}
    for r in t:
        if not r or not DATE_RE.match(r[0]):
            continue
        vals = [num(c) for c in r[1:1 + len(tickers)]]
        if all(v is None for v in vals):              # hari libur
            continue
        d = datetime.strptime(r[0], "%d %b %Y").strftime("%Y-%m-%d")
        tot = num(r[1 + len(tickers)]) if len(r) > 1 + len(tickers) else None
        row = dict(zip(tickers, vals)); row["total"] = tot
        out[d] = row
    if not out:
        raise ValueError("tabel tidak berisi baris tanggal")
    return tickers, out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def load(path):
    if not os.path.exists(path):
        return [], {}
    with open(path) as f:
        rd = csv.DictReader(f)
        cols = [c for c in rd.fieldnames if c not in ("date", "total")]
        rows = {r["date"]: {k: (float(v) if v != "" else None) for k, v in r.items() if k != "date"} for r in rd}
    return cols, rows


def save(path, cols, rows):
    text = ["date," + ",".join(cols) + ",total"]
    for d in sorted(rows):
        r = rows[d]
        text.append(d + "," + ",".join("" if r.get(c) is None else f"{r[c]:g}" for c in cols + ["total"]))
    text = "\n".join(text) + "\n"
    old = open(path).read() if os.path.exists(path) else ""
    if text != old:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)
        return True
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    hour = datetime.now(timezone.utc).hour
    bad = 0
    for coin, (recent, full) in PAGES.items():
        path = os.path.join(OUT, f"{coin}.csv")
        cols, rows = load(path)
        urls = ([full] if (not rows or hour == 0) else []) + [recent]
        try:
            for url in urls:
                tickers, new = parse(fetch(url))
                for c in tickers:
                    if c not in cols:
                        cols.append(c)
                for d, r in new.items():
                    rows[d] = r
            changed = save(path, cols, rows)
            last = max(rows)
            msg = f"{len(rows)} hari, terakhir {last} total {rows[last].get('total')} juta USD" + (" (diperbarui)" if changed else "")
            print(f"ETF {coin}: {msg}")
            status.record(f"etf_{coin}", True, msg)
        except Exception as e:
            bad += 1
            print(f"ETF {coin}: GAGAL {e}", file=sys.stderr)
            status.record(f"etf_{coin}", False, repr(e))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
