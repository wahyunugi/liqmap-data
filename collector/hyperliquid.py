"""
Posisi terbuka BTC dan ETH di Hyperliquid (bursa futures on-chain): sisi (long/short), harga masuk, harga likuidasi.

Kenapa Hyperliquid: di Binance posisi tiap akun tidak terlihat, jadi harga masuk long dan short tidak bisa dipisahkan.
Di Hyperliquid posisi setiap akun publik (API info, tipe "clearinghouseState"), jadi long dan short bisa dibaca
langsung. INI DATA HYPERLIQUID SAJA, bukan Binance. Uji 14 Nov 2026 (satu snapshot): akun kecil sama-sama condong long,
tetapi akun besar berlawanan arah dengan "top trader" Binance, dan funding kedua bursa lemah korelasinya. Data per jam
ini dikumpulkan untuk menguji ulang setelah 2 sampai 4 minggu apakah perubahan posisi Hyperliquid mengikuti Binance.

Cara kerja (tiap jalan, batas waktu BUDGET detik):
  1. Semesta akun (dibangun ulang sekali per hari UTC dari leaderboard publik stats-data.hyperliquid.xyz):
     4.000 akun dengan nilai akun terbesar + 3.000 akun lain dengan volume 30 hari terbesar. Sisanya = akun kecil.
  2. Permintaan (urutan a, c, b): (a) semua "holder" = akun semesta yang pada pengecekan terakhir punya posisi BTC/ETH;
     (b) 1.000 akun semesta berikutnya secara bergiliran (seluruh semesta terputar kira-kira tiap 6 jam, untuk
     menemukan pemegang posisi baru); (c) 300 akun kecil acak (pembanding "akun kecil", dirata-rata harian).
  3. Hanya jawaban jam ini yang dihitung (tidak ada posisi lama yang dibawa).

Keluaran:
  data/hyperliquid/summary/<YYYY-MM>.csv  satu baris per koin per jam (lihat COLS)
  data/hyperliquid/profile/<KOIN>.json    snapshot terakhir: ukuran long/short per kotak harga masuk dan harga likuidasi
Status (holder, giliran, semesta) disimpan di .cache/hyperliquid (cache GitHub Actions, tidak masuk repo).

    python collector/hyperliquid.py
"""
import csv, json, os, random, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "hyperliquid")
STATE = os.path.join(ROOT, ".cache", "hyperliquid", "state.json")
API = "https://api.hyperliquid.xyz/info"
LB = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
UA = "liqmap-data collector (https://github.com/wahyunugi/liqmap-data)"
COINS = {"BTC": ("BTCUSDT", 1000.0), "ETH": ("ETHUSDT", 50.0)}   # kotak harga: BTC $1.000, ETH $50
TOP_VALUE, TOP_VOLUME, ROTATE, SMALL = 4000, 3000, 1000, 300
BIG = 1_000_000.0          # akun bernilai >= $1 juta = "akun besar"
BUDGET = float(os.environ.get("HL_BUDGET", "420"))
WORKERS, RATE = 6, 8.0     # batas API: 1.200 bobot/menit per IP, clearinghouseState berbobot 2 -> maks 10/detik
PROFILE_RANGE = 0.5        # profil hanya kotak harga dalam +-50% dari harga sekarang
COLS = ["t", "coin", "mark", "oi", "queried", "holders",
        "nL", "nS", "szL", "szS", "avgL", "avgS", "lossL", "lossS",
        "big_nL", "big_nS", "big_szL", "big_szS",
        "sm_queried", "sm_nL", "sm_nS", "sm_szL", "sm_szS"]


def post(body, timeout=30):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"))
    os.replace(tmp, STATE)


def build_universe(rows):
    """rows = leaderboardRows. Kembalikan (semesta, akun_kecil)."""
    def month_vlm(r):
        for k, v in r.get("windowPerformances") or []:
            if k == "month":
                return float(v.get("vlm") or 0)
        return 0.0
    by_val = sorted(rows, key=lambda r: float(r.get("accountValue") or 0), reverse=True)
    uni = [r["ethAddress"] for r in by_val[:TOP_VALUE]]
    seen = set(uni)
    rest = [r for r in rows if r["ethAddress"] not in seen]
    for r in sorted(rest, key=month_vlm, reverse=True)[:TOP_VOLUME]:
        uni.append(r["ethAddress"]); seen.add(r["ethAddress"])
    small = [r["ethAddress"] for r in rows if r["ethAddress"] not in seen]
    return uni, small


class Limiter:
    def __init__(self, rate):
        self.gap = 1.0 / rate; self.next = time.monotonic(); self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic(); t = max(now, self.next); self.next = t + self.gap
        time.sleep(max(0.0, t - now))


def query_many(addrs, deadline, lim, fetch=None):
    """clearinghouseState untuk tiap alamat sampai deadline. Kembalikan {alamat: (nilai_akun, [posisi])}."""
    fetch = fetch or (lambda a: post({"type": "clearinghouseState", "user": a}))
    out = {}

    def one(a):
        for attempt in range(4):
            if time.monotonic() > deadline:
                return
            lim.wait()
            try:
                j = fetch(a)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(5 * (attempt + 1)); continue
                return
            except Exception:
                time.sleep(1); continue
            av = float((j.get("marginSummary") or {}).get("accountValue") or 0)
            pos = []
            for p in j.get("assetPositions") or []:
                q = p.get("position") or {}
                if q.get("coin") in COINS and float(q.get("szi") or 0) != 0:
                    lq = q.get("liquidationPx")
                    pos.append((q["coin"], float(q["szi"]), float(q["entryPx"]), None if lq in (None, "") else float(lq)))
            out[a] = (av, pos)
            return

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, addrs))
    return out


def aggregate(coin, mark, res):
    """Ringkasan satu koin dari jawaban {alamat: (nilai_akun, posisi)}."""
    L = []; S = []
    for a, (av, pos) in res.items():
        for c, sz, e, lq in pos:
            if c == coin:
                (L if sz > 0 else S).append((abs(sz), e, lq, av))
    szL = sum(x[0] for x in L); szS = sum(x[0] for x in S)
    avg = lambda X, tot: sum(x[0] * x[1] for x in X) / tot if tot else None
    return dict(nL=len(L), nS=len(S), szL=szL, szS=szS, avgL=avg(L, szL), avgS=avg(S, szS),
                lossL=(sum(x[0] for x in L if x[1] > mark) / szL) if szL else None,
                lossS=(sum(x[0] for x in S if x[1] < mark) / szS) if szS else None,
                big_nL=sum(1 for x in L if x[3] >= BIG), big_nS=sum(1 for x in S if x[3] >= BIG),
                big_szL=sum(x[0] for x in L if x[3] >= BIG), big_szS=sum(x[0] for x in S if x[3] >= BIG),
                _L=L, _S=S)


def profile(coin, mark, agg, step):
    lo, hi = mark * (1 - PROFILE_RANGE), mark * (1 + PROFILE_RANGE)
    def bucket(X, idx):
        d = {}
        for x in X:
            p = x[idx]
            if p is None or not (lo <= p <= hi):
                continue
            k = int(p // step * step)
            d[k] = d.get(k, 0.0) + x[0]
        return {str(k): round(v, 4) for k, v in sorted(d.items())}
    return dict(coin=coin, step=step, mark=mark,
                entryL=bucket(agg["_L"], 1), entryS=bucket(agg["_S"], 1),
                liqL=bucket(agg["_L"], 2), liqS=bucket(agg["_S"], 2))


def write_summary(rows, now):
    d = os.path.join(OUT, "summary"); os.makedirs(d, exist_ok=True)
    path = os.path.join(d, now.strftime("%Y-%m") + ".csv")
    keep = []
    if os.path.exists(path):
        with open(path) as f:
            keep = [r for r in csv.DictReader(f) if not any(int(r["t"]) == x["t"] and r["coin"] == x["coin"] for x in rows)]
    def fmt(v):
        if v is None:
            return ""
        return ("%.6g" % v) if isinstance(v, float) else str(v)
    with open(path + ".tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in sorted(keep + [{k: fmt(x.get(k)) for k in COLS} for x in rows], key=lambda r: (int(r["t"]), r["coin"])):
            w.writerow(r)
    os.replace(path + ".tmp", path)


def run(now=None, fetch=None, lb_rows=None, ctx=None):
    now = now or datetime.now(timezone.utc)
    t0 = time.monotonic(); deadline = t0 + BUDGET
    st = load_state()
    day = now.strftime("%Y-%m-%d")
    if st.get("universe_day") != day or not st.get("universe"):
        rows = lb_rows if lb_rows is not None else get(LB)["leaderboardRows"]
        uni, small = build_universe(rows)
        st.update(universe=uni, small=small, universe_day=day, cursor=st.get("cursor", 0) % max(len(uni), 1))
    uni, small = st["universe"], st["small"]
    us = set(uni)
    holders = [a for a in st.get("holders", []) if a in us]
    ctx = ctx if ctx is not None else post({"type": "metaAndAssetCtxs"})
    names = [u["name"] for u in ctx[0]["universe"]]
    mk = {c: (float(ctx[1][names.index(c)]["markPx"]), float(ctx[1][names.index(c)]["openInterest"])) for c in COINS}

    hs = set(holders)
    others = [a for a in uni if a not in hs]
    cur = st.get("cursor", 0) % max(len(others), 1)
    room = int(BUDGET * RATE * 0.85) - len(holders) - SMALL       # isi sisa kapasitas jam ini (jalan pertama: lebih banyak)
    rot = (others[cur:] + others[:cur])[:max(ROTATE, room)]
    lim = Limiter(RATE)
    res = query_many(holders, deadline, lim, fetch)                                    # (a) holder dulu
    sm = query_many(random.sample(small, min(SMALL, len(small))), deadline, lim, fetch)  # (c) sampel akun kecil
    res.update(query_many(rot, deadline, lim, fetch))                                  # (b) giliran mengisi sisa waktu
    st["cursor"] = (cur + sum(1 for a in rot if a in res)) % max(len(others), 1)

    new_holders = set(a for a in holders if a not in res)          # belum sempat ditanya: tetap holder
    new_holders |= {a for a, (_, pos) in res.items() if pos}
    st["holders"] = sorted(new_holders)
    save_state(st)

    t = int(now.timestamp()) // 3600 * 3600
    rows = []
    os.makedirs(os.path.join(OUT, "profile"), exist_ok=True)
    for coin, (sym, step) in COINS.items():
        mark, oi = mk[coin]
        a = aggregate(coin, mark, res); s = aggregate(coin, mark, sm)
        row = {k: v for k, v in a.items() if not k.startswith("_")}
        row.update(t=t, coin=coin, mark=mark, oi=oi, queried=len(res), holders=len(st["holders"]),
                   sm_queried=len(sm), sm_nL=s["nL"], sm_nS=s["nS"], sm_szL=s["szL"], sm_szS=s["szS"])
        rows.append(row)
        pr = profile(coin, mark, a, step)
        pr.update(t=t, oi=oi, queried=len(res), nL=a["nL"], nS=a["nS"], szL=a["szL"], szS=a["szS"])
        with open(os.path.join(OUT, "profile", coin + ".json.tmp"), "w") as f:
            json.dump(pr, f, separators=(",", ":"))
        os.replace(os.path.join(OUT, "profile", coin + ".json.tmp"), os.path.join(OUT, "profile", coin + ".json"))
    write_summary(rows, now)
    took = time.monotonic() - t0
    msg = (f"{len(res)} akun semesta ({len(holders)} holder, {len(rot)} giliran) + {len(sm)} akun kecil, {took:.0f} s; "
           + "; ".join(f"{r['coin']} long {r['szL']:.0f}/short {r['szS']:.0f} dari OI {r['oi']:.0f}" for r in rows))
    return msg


def main():
    try:
        msg = run()
        print("hyperliquid:", msg)
        status.record("hyperliquid", True, msg)
    except Exception as e:
        print("hyperliquid GAGAL:", repr(e))
        status.record("hyperliquid", False, repr(e)[:200])


if __name__ == "__main__":
    main()
