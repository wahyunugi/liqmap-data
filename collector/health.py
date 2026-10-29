"""
Cek kesehatan pengumpulan data (dijalankan GitHub Actions setelah tiap collect).
Gagal (kode keluar 1) -> GitHub mengirim email, supaya masalah diam-diam tidak luput:
  1. candle atau open interest 5 menit terbaru lebih tua dari MAX_AGE_HOURS
     (misalnya Coinalyze berhenti mengirim data, kunci API dicabut, atau format berubah);
  2. ukuran repo (env REPO_SIZE_KB, dari GitHub API) melewati SIZE_LIMIT_MB — hanya dicek pada jalan jam 00 UTC,
     jadi paling banyak satu email per hari. Langkah bila ini terjadi: lihat README, bagian "Bila repo mendekati 1 GB".
"""
import csv, glob, os, sys, time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = ["BTCUSDT", "ETHUSDT"]
MAX_AGE_HOURS = 3
SIZE_LIMIT_MB = 900


def newest(pattern):
    files = sorted(glob.glob(os.path.join(ROOT, "data", pattern)))
    if not files:
        return None
    with open(files[-1], newline="") as f:
        ts = [int(r["t"]) for r in csv.DictReader(f)]
    return max(ts) if ts else None


def main():
    now, problems = time.time(), []
    for p in PAIRS:
        for ds in ("ohlcv/5min", "open_interest/5min"):
            t = newest(f"{ds}/{p}_*.csv")
            age = None if t is None else (now - t) / 3600
            print(f"{p} {ds}: data terbaru "
                  f"{'-' if t is None else datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                  f" ({'-' if age is None else f'{age:.1f} jam lalu'})")
            if age is None or age > MAX_AGE_HOURS:
                problems.append(f"{p} {ds}: tidak ada data baru selama lebih dari {MAX_AGE_HOURS} jam")
    size_kb = os.environ.get("REPO_SIZE_KB", "")
    if size_kb.isdigit():
        mb = int(size_kb) / 1024
        print(f"ukuran repo menurut GitHub: {mb:.0f} MB (batas peringatan {SIZE_LIMIT_MB} MB)")
        if mb > SIZE_LIMIT_MB and datetime.now(timezone.utc).hour == 0:
            problems.append(f"ukuran repo {mb:.0f} MB > {SIZE_LIMIT_MB} MB: lihat README 'Bila repo mendekati 1 GB'")
    for pr in problems:
        print("MASALAH:", pr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
