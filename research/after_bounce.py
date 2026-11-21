"""Setelah pantulan: sesudah puncak pantulan (peta pantulan, research/bounce_map.py), apa yang datang lebih dulu dalam
30 hari: terendah lebih rendah (di bawah titik terendah sebelum pantulan) atau harga di atas puncak pantulan?

Kejadian sama persis dengan bounce_map.py: jam pertama harga menembus terendah 20 hari dengan volume 24 jam >= 2x median
30 hari, jarak >= 7 hari, 8 koin Binance futures per jam sejak 2020. Terendah = terendah dalam 10 hari sesudah kejadian;
puncak pantulan = tertinggi sesudah terendah itu dalam jendela 10 hari yang sama. Puncak yang jatuh dalam 48 jam terakhir
jendela dipisah ("masih naik di hari ke-10", bukan puncak nyata). Dipisah juga menurut fase (harga di bawah/di atas MA200).
    python research/after_bounce.py
"""
import sys, numpy as np, pandas as pd
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from turning_points import load
COINS=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","LINKUSDT"]
rows=[]
for sym in COINS:
    h=load(sym); H=h.high.values; L=h.low.values; C=h.close.values; t=h.t.values; n=len(h)
    sw=pd.Series(C).pct_change().rolling(720).std().values*np.sqrt(168)
    v24=h.vol.rolling(24).sum(); volr=(v24/v24.rolling(720,min_periods=360).median()).values
    pl=pd.Series(L).rolling(480).min().shift(1).values
    ma=pd.Series(C).rolling(24*200,min_periods=24*150).mean().values
    last=-10**9
    for i in range(720+480,n-240-720):
        if not (L[i]<pl[i] and volr[i]>=2 and sw[i]==sw[i]) or i-last<168: continue
        last=i
        w=L[i+1:i+241]; new=w.min()<L[i]; jlo=i+1+int(np.argmin(w)) if new else i; lo=min(L[i],w.min())
        a=H[jlo+1:i+241]; jpk=jlo+1+int(np.argmax(a)); pk=a.max()
        # after the bounce peak, 30 days: which comes first, break below lo, or break above pk
        first='neither'; k_end=min(n,jpk+1+720)
        for k in range(jpk+1,k_end):
            if L[k]<lo: first='lower low'; break
            if H[k]>pk: first='above bounce peak'; break
        # where the next pullback low sits (min in 30 days after peak) relative to lo
        mn=L[jpk+1:k_end].min(); end=C[k_end-1]
        anylow=bool(L[jpk+1:k_end].min()<lo); edge=jpk>i+240-48
        rows.append(dict(anylow=anylow,edge=edge,sym=sym[:-4],yr=pd.to_datetime(t[i],unit='s').year,bear=C[i]<ma[i],first=first,
             trough_vs_lo=mn/lo-1, end_vs_lo=end/lo-1, end_vs_pk=end/pk-1, bounce=pk/lo-1))
E_=pd.DataFrame(rows)
for nm,q in (("falling market, 8 coins",E_[E_.bear==True]),("falling market, BTC+ETH",E_[(E_.bear==True)&E_.sym.isin(['BTC','ETH'])]),
             ("falling, 2024-2026",E_[(E_.bear==True)&(E_.yr>=2024)]),("rising market, 8 coins",E_[E_.bear==False])):
    vc=q['first'].value_counts(); print(f"{nm}: {len(q)} events, weeks {q.shape[0]}")
    print("   first after bounce peak (30d):",{k:f"{v} ({100*v/len(q):.0f}%)" for k,v in vc.items()})
    hl=q[q['first']!='lower low']
    print(f"   lowest point in 30d after peak vs bounce low: median {100*q.trough_vs_lo.median():+.1f}% ; price 30d after peak vs bounce low median {100*q.end_vs_lo.median():+.1f}%, vs bounce peak median {100*q.end_vs_pk.median():+.1f}%")
print("\n--- peaks at least 48h before the 10-day window ends (a real top, not just 'still rising at day 10') ---")
for nm,q in (("falling market, 8 coins",E_[(E_.bear==True)]),("falling market, BTC+ETH",E_[(E_.bear==True)&E_.sym.isin(['BTC','ETH'])])):
    print(nm,"edge peaks:",int(q.edge.sum()),"of",len(q))
    q=q[~q.edge]; vc=q['first'].value_counts()
    print(f"  {len(q)} events:",{k:f"{v} ({100*v/len(q):.0f}%)" for k,v in vc.items()}, f"| any lower low within 30d after peak: {100*q.anylow.mean():.0f}%")
    print(f"  pullback low after peak vs bounce low: median {100*q.trough_vs_lo.median():+.1f}%, quartiles {100*q.trough_vs_lo.quantile(.25):+.1f}% / {100*q.trough_vs_lo.quantile(.75):+.1f}% | 30d later vs peak median {100*q.end_vs_pk.median():+.1f}%, bounce median {100*q.bounce.median():.1f}%")
