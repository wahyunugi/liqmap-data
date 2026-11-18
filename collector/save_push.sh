#!/usr/bin/env bash
# Simpan hasil pengumpulan ke repo dengan aman bila ada jalan lain yang menyimpan lebih dulu.
#   bash collector/save_push.sh "<pesan commit>" <path> [<path> ...]
#
# Urutan: commit -> git pull --rebase -> push. Bila rebase bentrok (dua jalan menulis file yang sama, misalnya snapshot
# data/hyperliquid/profile/*.json), rebase dibatalkan lalu diulang dengan -X theirs: untuk bagian yang bentrok, versi
# jalan INI (yang lebih baru) dipakai; bagian lain tetap digabung. Bila push ditolak karena ada commit baru di antara
# pull dan push, seluruhnya diulang (maksimal 4 kali). Keluar dengan kode 1 bila tetap gagal, supaya terlihat di Actions.
set -u
msg="$1"; shift
git config user.name "liqmap-bot"
git config user.email "liqmap-bot@users.noreply.github.com"
for p in "$@"; do [ -e "$p" ] && git add -- "$p"; done
if git diff --cached --quiet; then
  echo "tidak ada data baru"; exit 0
fi
git commit -q -m "$msg"
for attempt in 1 2 3 4; do
  if ! git pull -q --rebase; then
    git rebase --abort 2>/dev/null || true
    echo "::warning::bentrok saat menggabung (percobaan $attempt); bagian yang bentrok memakai versi jalan ini"
    if ! git pull -q --rebase -X theirs; then
      git rebase --abort 2>/dev/null || true
      echo "penggabungan gagal, coba lagi"; sleep $((attempt * 5)); continue
    fi
  fi
  if git push -q; then
    echo "tersimpan (percobaan $attempt)"; exit 0
  fi
  echo "push ditolak, coba lagi"; sleep $((attempt * 5))
done
echo "::error::gagal menyimpan setelah 4 percobaan"
exit 1
