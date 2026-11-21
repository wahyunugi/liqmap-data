"""Sudah jauh di bawah terendah kejadian, apakah terendahnya sudah selesai? Dari jam pertama harga sudah 5%, 10%, 15% di
bawah terendah kejadian (kejadian = sama dengan research/bounce_map.py, hanya fase turun: harga di bawah MA200 harian),
apakah dalam 10 hari berikutnya ada terendah lagi yang > 1% lebih dalam dari terendah jam itu, seberapa dalam, kapan, dan
berapa pantulan dari terendah akhirnya (10 hari). Dasar: di waktu nyata kita tidak tahu terendah mana yang terakhir.
    python research/already_down.py
"""
import os,sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from turning_points import load
COINS=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","LINKUSDT"]
R=[]
for sym in COINS:
    h=load(sym); H=h.high.values; L=h.low.values; C=h.close.values; t=h.t.values; n=len(h)
    sw=pd.Series(C).pct_change().rolling(720).std().values*np.sqrt(168)
    v24=h.vol.rolling(24).sum(); volr=(v24/v24.rolling(720,min_periods=360).median()).values
    pl=pd.Series(L).rolling(480).min().shift(1).values
    ma=pd.Series(C).rolling(24*200,min_periods=24*150).mean().values
    last=-10**9
    for i in range(720+480,n-480):
        if not (L[i]<pl[i] and volr[i]>=2 and sw[i]==sw[i]) or i-last<168: continue
        last=i
        if not C[i]<ma[i]: continue
        for d in (0.05,0.10,0.15):
            hit=np.nonzero(L[i+1:i+241]<=L[i]*(1-d))[0]
            if not len(hit): R.append(dict(sym=sym[:-4],d=d,reached=False)); continue
            j=i+1+hit[0]; ref=L[j]
            w=L[j+1:j+241]; lo=min(ref,w.min()); jl=(j+1+int(np.argmin(w))) if w.min()<ref else j
            pk=H[jl:jl+241].max()
            R.append(dict(sym=sym[:-4],d=d,reached=True,further=lo/ref-1,lower=(lo<ref*0.99),bounce=pk/lo-1,bounce_sw=(pk/lo-1)/sw[i],
                          hrs=jl-j))
D=pd.DataFrame(R)
for d in (0.05,0.10,0.15):
  for nm,q in (("8 coins",D[D.d==d]),("BTC+ETH",D[(D.d==d)&D.sym.isin(['BTC','ETH'])])):
    r=q[q.reached]
    print(f"already {int(d*100)}% below the event low | {nm}: reached in {len(r)} of {len(q)} events | from there, another low >1% deeper within 10 days: {100*(r.further.astype(float)<-0.01).mean():.0f}% | further drop median {100*r.further.median():.1f}% (quartiles {100*r.further.quantile(.25):.1f} / {100*r.further.quantile(.75):.1f}) | final low median {r.hrs.astype(float).median():.0f} h later, mean {r.hrs.astype(float).mean():.0f} | bounce from final low median {100*r.bounce.median():.0f}% ({r.bounce_sw.median():.1f} swings)")
