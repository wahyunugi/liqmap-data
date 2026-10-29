import sys, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from score_w import image
from tune import ctx
from model import PARAMS_V5 as P
WL={(L,s):L/175 for L in (25,50,100) for s in ("long","short")}
ref,dfa,dfw,prices,val,valid=ctx("C")
g=np.clip(image("C",dict(P,entry="ohlc4",mmr=0.0001),WL,20)/ref.cbar_max,0,1)
boxes=[(77700,78500,0,140),(82500,83200,0,140),(78600,79300,100,288),(81300,82000,150,288)]
fig,ax=plt.subplots(len(boxes),2,figsize=(14,4*len(boxes)))
for r,(p0,p1,i0,i1) in enumerate(boxes):
    rows=(prices>=p0)&(prices<=p1)
    for c,(im,t) in enumerate([(np.where(valid,val,np.nan),"CoinGlass C"),(g,"model")]):
        ax[r,c].imshow(im[rows][:,i0:i1],aspect="auto",cmap="viridis",vmin=0,vmax=1,extent=[i0,i1,p0,p1])
        ax[r,c].set_title(f"{t} {p0}-{p1}"); ax[r,c].grid(alpha=.3)
fig.tight_layout(); fig.savefig("zoom.png",dpi=65); print("ok")
