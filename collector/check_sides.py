"""
Cek arti kolom l dan s dari Coinalyze (dokumentasi tidak menjelaskannya).
Logika: likuidasi LONG terjadi saat harga TURUN tajam, likuidasi SHORT saat harga NAIK tajam.
Jadi kolom yang menumpuk di menit harga turun = long, yang menumpuk di menit harga naik = short.
Hasil ditulis ke logs/sides_check.txt (tidak mengubah data).
"""
import csv, glob, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(pattern):
    rows = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", pattern))):
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                rows[int(r["t"])] = r
    return rows


def corr(a, b):
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5


lines = []
for pair in ("BTCUSDT", "ETHUSDT"):
    liq = read(f"liquidations/1min/{pair}_*.csv"); px = read(f"ohlcv/1min/{pair}_*.csv")
    ts = [t for t in liq if t in px]
    ret = [(float(px[t]["c"]) / float(px[t]["o"]) - 1) for t in ts]
    L = [float(liq[t]["l"] or 0) for t in ts]; S = [float(liq[t]["s"] or 0) for t in ts]
    down = [i for i, r in enumerate(ret) if r < 0]; up = [i for i, r in enumerate(ret) if r > 0]
    def share(col, idx):
        tot = sum(col)
        return sum(col[i] for i in idx) / tot if tot else float("nan")
    lines.append(f"{pair}: {len(ts)} menit | korelasi(l, return) = {corr(L, ret):+.2f}, korelasi(s, return) = {corr(S, ret):+.2f} | "
                 f"porsi l di menit turun = {share(L, down):.0%}, porsi s di menit naik = {share(S, up):.0%}")
verdict = ("Kesimpulan: jika korelasi l negatif dan s positif, maka l = likuidasi LONG dan s = likuidasi SHORT.")
os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
with open(os.path.join(ROOT, "logs", "sides_check.txt"), "w") as f:
    f.write("\n".join(lines + [verdict]) + "\n")
print("\n".join(lines + [verdict]))
