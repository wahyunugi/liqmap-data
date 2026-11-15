"""Uji titik balik (low/high 10 hari) di 8 koin: rasio akun dan top trader Binance vs hasil entri 24 jam setelah low/high bertahan.
Menang = bergerak 2,25 ayunan mingguan normal searah posisi sebelum 1,5 melawan, dalam 60 hari. Butuh research/data/hourly (workflow research-data).
    python research/turning_points.py
"""
import glob,warnings,pickle; warnings.filterwarnings('ignore')
import pandas as pd,numpy as np
from sklearn.metrics import roc_auc_score
import os
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+'/'
def load(sym):
    if sym in ('BTCUSDT','ETHUSDT'):
        h=pd.concat([pd.read_csv(f) for f in sorted(glob.glob(R+f'data/derived/hourly/{sym}_20*.csv'))])
    else: h=pd.read_csv(R+f'research/data/hourly/{sym}.csv.gz')
    return h.drop_duplicates('t').sort_values('t').reset_index(drop=True)
def race(H,L,k,e,up,dn,hz=1440,long=True):
    for m in range(k+1,min(len(H),k+1+hz)):
        u=H[m]>=e*(1+up); d=L[m]<=e*(1-dn)
        if u and d: return 0.0,m
        if u: return (1.0 if long else 0.0),m
        if d: return (0.0 if long else 1.0),m
    return np.nan,None
def events(sym,side='bottom',hold=24):
    h=load(sym); t=h.t.values;H=h.high.values;L=h.low.values;C=h.close.values;N=len(h);acc=h.acc_lsr.values;top=h.top_lsr.values;oi=h.oi.values
    sig=pd.Series(C).pct_change().rolling(720).std().values*np.sqrt(24*7)      # one normal week's swing
    accp=pd.Series(acc).rolling(8760,min_periods=2000).rank(pct=True).values*100
    rl=pd.Series(L).rolling(240).min().values; rh=pd.Series(H).rolling(240).max().values; h60=pd.Series(H).rolling(1440).max().values; l60=pd.Series(L).rolling(1440).min().values
    rows=[];last=-10**9
    for j in range(1440,N-hold):
        s=sig[j]
        if not s==s: continue
        if side=='bottom':
            if L[j]>rl[j] or L[j]/h60[j]-1>-3*s or L[j+1:j+hold+1].min()<=L[j]: continue
        else:
            if H[j]<rh[j] or H[j]/l60[j]-1<3*s or H[j+1:j+hold+1].max()>=H[j]: continue
        k=j+hold
        if k-last<72: continue
        last=k; e=C[k]; long=side=='bottom'
        y,m=race(H,L,k,e,2.25*s if long else 1.5*s,1.5*s if long else 2.25*s,1440,long)
        yf,_=race(H,L,k,e,0.15 if long else 0.10,0.10 if long else 0.15,1440,long)
        ext=L[j] if long else H[j]
        rows.append(dict(sym=sym[:-4],t=t[k],date=str(pd.Timestamp(t[k],unit='s'))[:10],yr=pd.Timestamp(t[k],unit='s').year,k=k,entry=e,sig=s*100,y=y,yfix=yf,
            acc=acc[k],accp=accp[k],acc_at_ext=acc[j],acc_chg_since=acc[k]-acc[j],acc_chg72=acc[k]-acc[k-72],acc_pk=acc[k]-np.nanmax(acc[k-168:k+1]) if long else acc[k]-np.nanmin(acc[k-168:k+1]),
            top=top[k],move=abs(100*(e/ext-1)),move_sig=abs(e/ext-1)/s,oi24=100*(oi[j]/oi[j-24]-1)))
    return pd.DataFrame(rows)
def auc(x,y):
    m=x.notna()&y.notna()
    if m.sum()<20 or y[m].nunique()<2 or min((y[m]==1).sum(),(y[m]==0).sum())<5: return np.nan
    return roc_auc_score(y[m],x[m])
if __name__=='__main__':
    pd.set_option('display.width',230)
    COINS=['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','LINKUSDT']
    out={}
    for side in ('bottom','top'):
        E=pd.concat([events(s,side) for s in COINS],ignore_index=True); out[side]=E; Q=E.dropna(subset=['y'])
        print(f'\n################ {side.upper()}S: events {len(Q)} wins {Q.y.mean():.2f} (with ratio data {Q.acc.notna().sum()})')
        rows=[]
        for s in ['BTC','ETH','SOL','BNB','XRP','DOGE','ADA','LINK','ALL','ALTS(6)']:
            q=Q if s=='ALL' else Q[~Q.sym.isin(['BTC','ETH'])] if s.startswith('ALTS') else Q[Q.sym==s]; qa=q.dropna(subset=['acc'])
            r=dict(coin=s,n=len(qa),win=round(qa.y.mean(),2))
            for v in ('acc','accp','acc_chg_since','acc_chg72','acc_pk','top','move_sig','oi24'): r[v]=auc(q[v],q.y)
            lo=qa[qa.accp<=33]; hi=qa[qa.accp>=67]; r['win_lowP']=f'{lo.y.mean():.2f} ({len(lo)})'; r['win_highP']=f'{hi.y.mean():.2f} ({len(hi)})'
            rows.append(r)
        print(pd.DataFrame(rows).round(2).to_string(index=False))
        for lab,q in (('ALL',Q),('ALTS only',Q[~Q.sym.isin(['BTC','ETH'])])):
            print(f'-- {lab} by period: '+' | '.join(f'{a}-{b}: acc {auc(q[(q.yr>=a)&(q.yr<=b)].acc,q[(q.yr>=a)&(q.yr<=b)].y):.2f} accp {auc(q[(q.yr>=a)&(q.yr<=b)].accp,q[(q.yr>=a)&(q.yr<=b)].y):.2f} move {auc(q[(q.yr>=a)&(q.yr<=b)].move_sig,q[(q.yr>=a)&(q.yr<=b)].y):.2f} n={((q.yr>=a)&(q.yr<=b)&q.acc.notna()).sum()}' for a,b in ((2020,2021),(2022,2023),(2024,2026))))
        qa=Q.dropna(subset=['accp']); print('-- win by own-1-year percentile of ratio (all coins):',{str(k):(int(v['size']),round(v['mean'],2)) for k,v in qa.groupby(pd.cut(qa.accp,[0,20,40,60,80,100])).y.agg(['size','mean']).iterrows()})
        qa=Q.dropna(subset=['acc']); print('-- win by absolute ratio (all coins):',{str(k):(int(v['size']),round(v['mean'],2)) for k,v in qa.groupby(pd.cut(qa.acc,[0,1.5,2,2.5,3,4,99])).y.agg(['size','mean']).iterrows()})
        print('-- win by move already made at entry, in normal-week units (all coins):',{str(k):(int(v['size']),round(v['mean'],2)) for k,v in Q.groupby(pd.cut(Q.move_sig,[0,0.25,0.5,0.75,1,9])).y.agg(['size','mean']).iterrows()})
        # date-cluster robustness: one row per (week) = mean
        qa=Q.dropna(subset=['accp']).copy(); qa['wk']=qa.t//(7*86400); g=qa.groupby('wk').agg(y=('y','mean'),accp=('accp','mean'),n=('y','size'))
        print(f'-- independent weeks {len(g)}: correlation of week avg percentile with week win rate {g.accp.corr(g.y):.2f}; weeks low-third win {g[g.accp<=33].y.mean():.2f} ({(g.accp<=33).sum()}), high-third {g[g.accp>=67].y.mean():.2f} ({(g.accp>=67).sum()})')
    pickle.dump(out,open(R+'research/results/turning_points.pkl','wb'))
