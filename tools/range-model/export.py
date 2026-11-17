import json, numpy as np
m=np.load('../model.npz')
w=m['w']; b=float(m['b'][0]); dim=int(m['dim'][0])
nz=np.nonzero(np.abs(w)>1e-6)[0]
print(f'dim {dim}  nonzero {len(nz)} ({len(nz)/dim*100:.1f}%)')
out={'version':1,'dim':dim,'bias':round(b,6),
     'w':{str(int(i)):round(float(w[i]),6) for i in nz}}
s=json.dumps(out,separators=(',',':'))
open('../rangemodel.json','w').write(s)
print('json bytes', len(s))
