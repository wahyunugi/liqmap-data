"""Eksperimen 8 (literatur: Liu dan Tsyvinski, "Risks and Returns of Cryptocurrency", Review of Financial Studies 2021:
lonjakan pencarian Google memprediksi imbal hasil 1-6 minggu ke depan): apakah lonjakan PEMBACA WIKIPEDIA (pengganti
gratis Google Trends) memprediksi harga atau gejolak?

Aturan ditetapkan sebelum melihat hasil.
  Data: data/attention/wikipedia.csv (pembaca harian artikel "Bitcoin" dan "Ethereum", sejak Juli 2015).
  Harga harian: BTC Bitstamp (research/data/daily_bitstamp.csv) seluruhnya; ETH Bitstamp sampai 2019, Binance sejak 2020.
  Angka hari d dianggap diketahui pada akhir hari d+1; masuk pada harga penutupan d+1.
  Bacaan:
    kejut  = log(rata-rata pembaca 7 hari / rata-rata 28 hari sebelumnya)  (versi mingguan dari ukuran makalah)
    tingkat = log(rata-rata 7 hari / median harian 365 hari sebelumnya)
  Hasil: perubahan harga 7 dan 30 hari; gejolak 7 hari ke depan (simpangan baku perubahan harian) dibanding 30 hari
  sebelumnya. Lima kelompok sama besar; periode 2015-2019, 2020-2022, 2023-2026. Korelasi memakai satu titik per
  minggu (Senin) supaya hari yang tumpang tindih tidak dihitung berkali-kali.
    python research/exp8_attention.py
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
PER = (("2015-2019", "2015-01-01", "2019-12-31"), ("2020-2022", "2020-01-01", "2022-12-31"), ("2023-2026", "2023-01-01", "2026-12-31"))


def prices(coin):
    b = pd.read_csv(R + "research/data/daily_bitstamp.csv"); b = b[b.pair == coin.lower() + "usd"][["date", "close"]]
    if coin == "ETH":
        n = pd.read_csv(R + "data/derived/ETHUSDT_1d.csv")[["date", "close"]]
        b = pd.concat([b[b.date < "2020-01-01"], n[n.date >= "2020-01-01"]])
    return b.drop_duplicates("date").set_index("date").close.sort_index()


def frame(coin, article):
    a = pd.read_csv(R + "data/attention/wikipedia.csv").set_index("date")[article].astype(float)
    p = prices(coin); d = pd.DataFrame(dict(views=a)).join(p.rename("close"), how="inner")
    v7 = d.views.rolling(7).mean()
    d["shock"] = np.log(v7 / d.views.shift(7).rolling(28).mean())
    d["level"] = np.log(v7 / d.views.shift(7).rolling(365, min_periods=180).median())
    c = d.close; entry = c.shift(-1)                                   # masuk pada penutupan d+1
    d["p7"] = c / c.shift(7) - 1
    d["r7"] = c.shift(-8) / entry - 1; d["r30"] = c.shift(-31) / entry - 1
    lr = np.log(c).diff()
    d["volx"] = lr[::-1].rolling(7).std()[::-1].shift(-2) / lr.rolling(30).std()      # 7 hari setelah masuk vs 30 hari terakhir
    return d.dropna(subset=["shock", "level"])


def report(coin, article):
    d = frame(coin, article); print(f"\n===== {coin} (artikel {article}): {d.index[0]} s.d. {d.index[-1]}, {len(d)} hari =====")
    for col, nm in (("shock", "KEJUT (7 hari vs 4 minggu sebelumnya)"), ("level", "TINGKAT (7 hari vs median setahun)")):
        q = d.dropna(subset=["r7"]).copy(); q["b"] = pd.qcut(q[col], 5, labels=["terendah", "2", "3", "4", "tertinggi"])
        print(f" {nm}:")
        for k, g in q.groupby("b", observed=False):
            print(f"   {k} ({g[col].min():+.2f} s.d. {g[col].max():+.2f}): 7 hari median {100 * g.r7.median():+.1f}%, naik {100 * (g.r7 > 0).mean():.0f}% | "
                  f"30 hari median {100 * g.r30.median():+.1f}%, naik {100 * (g.r30 > 0).mean():.0f}% | gejolak 7 hari ke depan {g.volx.median():.2f}x")
        w = d[pd.to_datetime(d.index).dayofweek == 0].dropna(subset=["r7", "p7"])
        print(f"   korelasi mingguan: dengan harga 7 hari SEBELUM {w[col].corr(w.p7):+.2f}, SESUDAH {w[col].corr(w.r7):+.2f}, 30 hari sesudah {w[col].corr(w.r30):+.2f}, gejolak sesudah {w[col].corr(np.log(w.volx)):+.2f} ({len(w)} minggu)")
        for nm2, a, b in PER:
            z = w[(w.index >= a) & (w.index <= b)]
            if len(z) > 30:
                hi = d[(d.index >= a) & (d.index <= b) & (d[col] >= q[col].quantile(.8))].dropna(subset=["r30"])
                print(f"     {nm2}: SESUDAH 7 hari {z[col].corr(z.r7):+.2f}, 30 hari {z[col].corr(z.r30):+.2f}, gejolak {z[col].corr(np.log(z.volx)):+.2f} | "
                      f"kelompok tertinggi: 30 hari naik {100 * (hi.r30 > 0).mean():.0f}% ({len(hi)} hari) ({len(z)} minggu)")
    last = d.iloc[-1]; print(f" terakhir {d.index[-1]}: kejut {last.shock:+.2f}, tingkat {last.level:+.2f}, pembaca 7 hari {d.views.tail(7).mean():.0f}/hari")


if __name__ == "__main__":
    report("BTC", "Bitcoin"); report("ETH", "Ethereum")
