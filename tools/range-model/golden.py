"""生成 TS/Python 对照样本，验证特征与打分一致。"""
import json, sys
sys.path.insert(0,'..')
import feat as F
from hasher import h32
from train2 import cand_feats, text_feats, DIM
import numpy as np

m=np.load('../model.npz'); w=m['w']; b=float(m['b'][0]); dim=int(m['dim'][0])

cases=[
 r'$100\%$ 的数据满足：$1\le n\le3\times10^4$，$80\le w\le200$',
 '对于全部的数据，M ≤ 100。',
 r'$1 \le N \le 9$，$1 \le x,y \le N$，$1 \le v \le 30$',
 'For $40\%$ of the testdata, $2 \le b \le 1{,}000$.',
 'and $0 \\le a_i, k \\le 5 \\times 10^8$',
]
out=[]
for c in cases:
    raw=F.bounds(c)
    by={}
    for n,sg,v,k in raw:
        if sg!='<=' or not (1<=v<=5_000_000): continue
        by[n]=max(by.get(n,0),v)
    cands=[(n,v,'merged',0) for n,v in by.items()]
    ti,_=text_feats(c,dim)
    res=[]
    for var,val,kind,_ in cands:
        f=cand_feats(ti,var,val,cands,dim)
        z=b
        for i,v in f.items(): z+=w[i]*v
        p=1/(1+np.exp(-max(-30,min(30,z))))
        res.append({'var':var,'val':val,'score':round(float(p),6)})
    out.append({'text':c,'norm':F.normalize(c),'bounds':[(n,sg,v,k) for n,sg,v,k in raw],
                'byVar':by,'cands':res})
json.dump(out,open('../golden.json','w'),ensure_ascii=False,indent=1)
print(json.dumps(out,ensure_ascii=False,indent=1)[:1200])
