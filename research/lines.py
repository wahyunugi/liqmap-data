"""
Iterasi 3: baca langsung garis-garis di heatmap CoinGlass.
Untuk tiap garis: kapan mulai, di harga berapa, kapan hilang.
Dari harga candle saat garis mulai, hitung leverage yang tersirat.
"""
import numpy as np, pandas as pd
from evaluate import PRICES, VAL, VALID, DF_WIN

BG = 0.06            # nilai viridis latar (ungu) ~0; di atas ini dianggap ada garis
MIN_LEN = 4          # minimal 4 candle (20 menit) agar dihitung garis


def extract():
    on = (VAL > BG) & VALID
    segs = []
    for r in range(on.shape[0]):
        row = on[r]; i = 0
        while i < len(row):
            if row[i]:
                j = i
                while j + 1 < len(row) and (row[j + 1] or (not VALID[r, j + 1])):
                    j += 1
                if j - i + 1 >= MIN_LEN:
                    segs.append((r, i, j, float(np.nanmean(np.where(VALID[r, i:j+1], VAL[r, i:j+1], np.nan)))))
                i = j + 1
            else:
                i += 1
    # gabungkan baris piksel bertetangga yang mulai di candle sama (satu garis tebal)
    segs.sort(key=lambda s: (s[1], s[0]))
    merged = []
    for s in segs:
        if merged and s[1] == merged[-1]["start"] and s[0] - merged[-1]["r1"] <= 1:
            m = merged[-1]; m["r1"] = s[0]; m["end"] = max(m["end"], s[2]); m["v"] = max(m["v"], s[3])
        else:
            merged.append(dict(r0=s[0], r1=s[0], start=s[1], end=s[2], v=s[3]))
    out = []
    for m in merged:
        price = PRICES[[m["r0"], m["r1"]]].mean()
        out.append(dict(price=price, start=m["start"], end=m["end"], v=m["v"], thick=m["r1"] - m["r0"] + 1))
    return pd.DataFrame(out)


if __name__ == "__main__":
    L = extract()
    print("jumlah garis:", len(L))
    print(L.sort_values("start").head(60).round(1).to_string())
