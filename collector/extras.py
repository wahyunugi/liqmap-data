"""
Data harian tambahan (pengganti gratis untuk data berbayar), sekali sehari:

  data/exchanges/reserves.csv        saldo dompet bursa per hari (DefiLlama, kategori CEX): date, exchange, usdt, usdc,
                                     stable_other, btc, eth (jumlah token). Perubahan harian = arus bersih masuk/keluar
                                     bursa. Hanya bursa yang membuka alamat dompetnya; daftar dompet bisa bertambah,
                                     sehingga lonjakan satu hari tidak selalu berarti arus nyata.
  data/attention/wikipedia.csv       pembaca harian artikel Wikipedia bahasa Inggris (API resmi Wikimedia, sejak
                                     Juli 2015): date, Bitcoin, Ethereum, Cryptocurrency. Pengganti Google Trends.
  data/liquidations/daily/<SIMBOL>.csv  likuidasi Binance per hari dari Coinalyze: t, l (long, USD), s (short, USD).
                                     Coinalyze menyimpan kira-kira 1.500 hari terakhir; yang lebih lama tetap di file.

Jalan penuh hanya pada jam 01 UTC, bila ada file yang belum ada, atau bila EXTRAS_FORCE=1. Hari UTC yang sedang berjalan
tidak disimpan (belum lengkap). Tiap bagian berdiri sendiri: satu gagal tidak menghentikan yang lain.

    python collector/extras.py
"""
import csv, json, os, sys, time, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "liqmap-data collector (https://github.com/wahyunugi/liqmap-data) wahyunugi"
EXCHANGES = ["binance-cex", "okx", "bybit", "bitfinex", "robinhood", "bitget", "gate", "gemini", "bitstamp", "mexc", "htx",
             "deribit", "kucoin", "crypto-com"]                 # 14 terbesar di DefiLlama pada 16 Nov 2026
STABLE_OTHER = {"FDUSD", "DAI", "TUSD", "BUSD", "USDE", "PYUSD", "USDP", "USDD", "USD1", "RLUSD"}
BTC_LIKE, ETH_LIKE = {"BTC", "WBTC", "BTCB"}, {"ETH", "WETH", "BETH", "WBETH"}
RES_COLS = ["date", "exchange", "usdt", "usdc", "stable_other", "btc", "eth"]
ARTICLES = ["Bitcoin", "Ethereum", "Cryptocurrency"]
PATHS = dict(res=os.path.join(DATA, "exchanges", "reserves.csv"), wiki=os.path.join(DATA, "attention", "wikipedia.csv"),
             liq=os.path.join(DATA, "liquidations", "daily"))


def get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def day(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")


def write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    os.replace(path + ".tmp", path)


def parse_reserves(slug, j, today):
    """Jawaban /protocol/<slug> -> {date: {usdt, usdc, stable_other, btc, eth}}; satu titik per hari per rantai."""
    out = {}
    for chain, cv in (j.get("chainTvls") or {}).items():
        if "-" in chain or chain in ("borrowed", "staking", "pool2"):
            continue
        perday = {}
        for e in cv.get("tokens") or []:
            perday[day(e["date"])] = e                         # hari yang sama muncul dua kali -> yang terakhir menang
        for d, e in perday.items():
            if d >= today:
                continue
            r = out.setdefault(d, dict(usdt=0.0, usdc=0.0, stable_other=0.0, btc=0.0, eth=0.0))
            for tok, amt in (e.get("tokens") or {}).items():
                u = tok.upper()
                k = ("usdt" if u == "USDT" else "usdc" if u == "USDC" else "stable_other" if u in STABLE_OTHER
                     else "btc" if u in BTC_LIKE else "eth" if u in ETH_LIKE else None)
                if k and amt:
                    r[k] += float(amt)
    return out


def reserves(today, fetch=get):
    old = {}
    if os.path.exists(PATHS["res"]):
        with open(PATHS["res"]) as f:
            old = {(r["date"], r["exchange"]): r for r in csv.DictReader(f)}
    ok = 0
    for slug in EXCHANGES:
        try:
            for d, v in parse_reserves(slug, fetch(f"https://api.llama.fi/protocol/{slug}"), today).items():
                old[(d, slug)] = dict(date=d, exchange=slug, **{k: "%.6g" % x for k, x in v.items()})
            ok += 1
        except Exception as e:
            print(f"  saldo bursa {slug} gagal: {e!r}"[:200])
        time.sleep(1)
    if not ok:
        raise RuntimeError("tidak ada bursa yang terambil")
    rows = [old[k] for k in sorted(old, key=lambda k: (k[1], k[0]))]
    write_csv(PATHS["res"], RES_COLS, rows)
    return f"{ok}/{len(EXCHANGES)} bursa, {len(rows)} baris, sampai {max(k[0] for k in old)}"


def wikipedia(today, fetch=get):
    end = today.replace("-", ""); table = {}
    for a in ARTICLES:
        j = fetch(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{a}/daily/20150701/{end}")
        for i in j["items"]:
            ts = i["timestamp"]; d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            if d < today:
                table.setdefault(d, {})[a] = i["views"]
    rows = [dict(date=d, **{a: table[d].get(a, "") for a in ARTICLES}) for d in sorted(table)]
    write_csv(PATHS["wiki"], ["date"] + ARTICLES, rows)
    return f"{len(rows)} hari, sampai {rows[-1]['date']}"


def liquidations(now):
    import coinalyze as cz
    key = os.environ.get("COINALYZE_API_KEY")
    if not key:
        raise RuntimeError("COINALYZE_API_KEY kosong")
    c = cz.Client(key); syms = cz.resolve_symbols(c); t_day = now // 86400 * 86400; msg = []
    for p, m in syms.items():
        path = os.path.join(PATHS["liq"], p + ".csv"); old = {}
        if os.path.exists(path):
            with open(path) as f:
                old = {int(r["t"]): r for r in csv.DictReader(f)}
        r = c.get("liquidation-history", {"symbols": m["symbol"], "interval": "daily", "from": 1577836800, "to": now, "convert_to_usd": "true"})
        for h in (r[0]["history"] if r else []):
            if h["t"] < t_day:
                old[int(h["t"])] = dict(t=int(h["t"]), l="%.0f" % (h.get("l") or 0), s="%.0f" % (h.get("s") or 0))
        write_csv(path, ["t", "l", "s"], [old[k] for k in sorted(old)])
        msg.append(f"{p} {len(old)} hari")
    return ", ".join(msg)


def main():
    now = int(time.time()); today = day(now)
    missing = not (os.path.exists(PATHS["res"]) and os.path.exists(PATHS["wiki"]) and os.path.isdir(PATHS["liq"]))
    if not (datetime.now(timezone.utc).hour == 1 or missing or os.environ.get("EXTRAS_FORCE") == "1"):
        print("extras: bukan jam 01 UTC, dilewati"); return
    for name, fn in (("extras_exchange_reserves", lambda: reserves(today)), ("extras_wikipedia", lambda: wikipedia(today)),
                     ("extras_liquidations_daily", lambda: liquidations(now))):
        try:
            msg = fn(); print(name + ":", msg); status.record(name, True, msg)
        except Exception as e:
            print(name, "GAGAL:", repr(e)[:300]); status.record(name, False, repr(e)[:200])


if __name__ == "__main__":
    main()
