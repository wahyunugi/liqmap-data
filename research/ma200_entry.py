"""Uji: apakah menunggu harga di atas rata-rata 200 hari (MA200 harian) membuat entri lebih baik, dan berapa harganya?
Harga harian BTC Bitstamp sejak 2014, ETH Bitstamp 2018-2019 + Binance sejak 2020 (research/data/daily_bitstamp.csv,
data/derived/<SIMBOL>_1d.csv). Hasil: perubahan harga 30 dan 90 hari, hari di atas vs di bawah MA200; dan untuk tiap
penutupan pertama di atas MA200 setelah >= 60 hari di bawahnya: sudah berapa persen di atas low, dan hasil sesudahnya.
    python research/ma200_entry.py
"""
import os
import pandas as pd
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
b = pd.read_csv(R + "research/data/daily_bitstamp.csv")


def series(coin):
    s = b[b.pair == coin.lower() + "usd"][["date", "close"]]
    n = pd.read_csv(R + f"data/derived/{coin}USDT_1d.csv")[["date", "close"]]
    return pd.concat([s[s.date < "2020-01-01"], n[n.date >= "2020-01-01"]]).drop_duplicates("date").set_index("date").close.sort_index()


for coin, start in (("BTC", "2014-01-01"), ("ETH", "2018-03-01")):
    c = series(coin); d = pd.DataFrame(dict(c=c, ma=c.rolling(200).mean())).dropna(); d = d[d.index >= start]
    d["f30"] = d.c.shift(-30) / d.c - 1; d["f90"] = d.c.shift(-90) / d.c - 1; d["above"] = d.c > d.ma; x = d.dropna(subset=["f90"])
    for lab, m in (("di atas MA200", x.above), ("di bawah MA200", ~x.above)):
        q = x[m]; print(f"{coin} {lab}: {len(q)} hari, 30 hari naik {100 * (q.f30 > 0).mean():.0f}%, median 90 hari {100 * q.f90.median():+.1f}%")
    run = 0
    for i in range(1, len(d)):
        if not d.above.iat[i - 1]:
            run += 1
        if d.above.iat[i] and not d.above.iat[i - 1]:
            if run >= 60:
                w = d.iloc[max(0, i - 400):i + 1]; f = lambda k: f"{100 * (d.c.iat[i + k] / d.c.iat[i] - 1):+.0f}%" if i + k < len(d) else "-"
                print(f"   {d.index[i]}: {100 * (d.c.iat[i] / w.c.min() - 1):+.0f}% di atas low {w.c.idxmin()}; 90 hari {f(90)}, 180 hari {f(180)}")
            run = 0
