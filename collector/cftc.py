"""
Ambil laporan mingguan CFTC (Commitments of Traders, versi "Traders in Financial Futures", futures saja)
untuk futures Bitcoin dan Ether di CME, lalu simpan ke data/cftc/cme_tff.csv.

Apa ini: CFTC (regulator futures Amerika) mewajibkan bursa melaporkan posisi pemain besar setiap minggu.
Laporan terbit tiap Jumat untuk posisi hari Selasa. Posisi dipecah per kelompok:
  dealer        = bank / pembuat pasar
  asset manager = dana pensiun, asuransi, reksa dana
  leveraged     = hedge fund ("leveraged funds")
  other         = pemain besar lain yang wajib lapor
  nonreportable = pemain kecil di bawah batas wajib lapor
Sumber: CFTC Public Reporting Environment, dataset gpe5-46if (publicreporting.cftc.gov), gratis tanpa kunci.

Kontrak yang dipakai dan satuannya (spesifikasi kontrak CME; teks contract_units dari CFTC tidak seragam, misalnya
"(50 Index Points)" untuk Ether, jadi satuannya ditulis tetap di CONTRACTS):
  133741 Bitcoin futures 5 BTC, 133742 Micro Bitcoin 0,1 BTC, 146021 Ether futures 50 ETH, 146022 Micro Ether 0,1 ETH.
Pasar lain yang ditemukan (mis. kontrak baru) dilewati dan dicatat di data/cftc/markets.json. Seluruh riwayat diambil ulang tiap jalan (kecil, ±2.000 baris),
sehingga revisi CFTC atas data lama ikut terbawa. File hanya ditulis bila isinya berubah.

    python collector/cftc.py
"""
import csv, io, json, os, sys, urllib.parse, urllib.request

URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "cftc", "cme_tff.csv")

# kolom CFTC -> nama pendek di file
FIELDS = {
    "report_date_as_yyyy_mm_dd": "date",
    "cftc_contract_market_code": "code",
    "market_and_exchange_names": "market",
    "contract_units": "units_text",
    "open_interest_all": "oi",
    "dealer_positions_long_all": "dealer_l", "dealer_positions_short_all": "dealer_s",
    "dealer_positions_spread_all": "dealer_sp",
    "asset_mgr_positions_long": "am_l", "asset_mgr_positions_short": "am_s", "asset_mgr_positions_spread": "am_sp",
    "lev_money_positions_long": "lev_l", "lev_money_positions_short": "lev_s", "lev_money_positions_spread": "lev_sp",
    "other_rept_positions_long": "oth_l", "other_rept_positions_short": "oth_s",
    "other_rept_positions_spread": "oth_sp",
    "nonrept_positions_long_all": "nr_l", "nonrept_positions_short_all": "nr_s",
}
NUM = [v for v in FIELDS.values() if v not in ("date", "code", "market", "units_text")]
COLS = ["date", "coin", "code", "market", "units"] + NUM
CONTRACTS = {"133741": ("BTC", 5.0), "133742": ("BTC", 0.1), "146021": ("ETH", 50.0), "146022": ("ETH", 0.1)}


def fetch():
    where = ("upper(market_and_exchange_names) like '%CHICAGO MERCANTILE EXCHANGE%' AND "
             "(upper(market_and_exchange_names) like '%BITCOIN%' OR upper(market_and_exchange_names) like '%ETHER%')")
    q = {"$select": ",".join(FIELDS), "$where": where, "$order": "report_date_as_yyyy_mm_dd", "$limit": "50000"}
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(q),
                                 headers={"Accept": "application/json", "User-Agent": "liqmap-data collector"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def rows_from(raw):
    out, skipped = [], {}
    for rec in raw:
        r = {FIELDS[k]: rec.get(k) for k in FIELDS}
        if r["code"] not in CONTRACTS:
            skipped[r["market"]] = r["units_text"]
            continue
        coin, units = CONTRACTS[r["code"]]
        row = {"date": (r["date"] or "")[:10], "coin": coin, "code": r["code"], "market": " ".join(r["market"].split()),
               "units": units}
        for k in NUM:
            v = r[k]
            row[k] = int(float(v)) if v not in (None, "") else ""
        out.append(row)
    out.sort(key=lambda x: (x["date"], x["coin"], x["code"]))
    return out, skipped


def main():
    raw = fetch()
    rows, skipped = rows_from(raw)
    if not rows:
        print("CFTC: tidak ada baris yang cocok; file tidak diubah", file=sys.stderr)
        sys.exit(1)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    text = buf.getvalue()
    old = open(OUT).read() if os.path.exists(OUT) else ""
    markets = sorted({(r["coin"], r["code"], r["market"], r["units"]) for r in rows})
    print(f"CFTC: {len(raw)} baris diterima, {len(rows)} dipakai, laporan terakhir {rows[-1]['date']}")
    for m in markets:
        print("  pakai:", m)
    for k, v in skipped.items():
        print("  lewati:", k, v)
    # daftar semua pasar yang ditemukan (dipakai / dilewati), supaya bisa dicek tanpa membuka log GitHub
    info = {}
    for rec in raw:
        k = (rec.get("cftc_contract_market_code"), (rec.get("market_and_exchange_names") or "").strip())
        d = (rec.get("report_date_as_yyyy_mm_dd") or "")[:10]
        e = info.setdefault(k, {"code": k[0], "market": k[1], "units_text": rec.get("contract_units"),
                                "rows": 0, "first": d, "last": d})
        e["rows"] += 1; e["first"] = min(e["first"], d); e["last"] = max(e["last"], d)
        e["units_text"] = rec.get("contract_units") or e["units_text"]
    mk = [dict(e, used=e["code"] in CONTRACTS, units=CONTRACTS.get(e["code"], (None, None))[1]) for e in sorted(info.values(), key=lambda e: e["market"])]
    mtext = json.dumps(mk, indent=1)
    mpath = os.path.join(os.path.dirname(OUT), "markets.json")
    if not os.path.exists(mpath) or open(mpath).read() != mtext:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(mpath, "w") as f:
            f.write(mtext)
    if text != old:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        tmp = OUT + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, OUT)
        print("CFTC: file diperbarui")
    else:
        print("CFTC: tidak ada perubahan")


if __name__ == "__main__":
    main()
