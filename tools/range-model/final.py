"""最终推理：模型选变量 + 同名变量取最大上界 = 满档规模。"""
import json, re, sys
import numpy as np
sys.path.insert(0,'..')
import feat as F
from train2 import cand_feats, text_feats, DIM

_m = np.load('../model.npz')
_w, _b, _dim = _m['w'], float(_m['b'][0]), int(_m['dim'][0])

def predict(text):
    """返回 (targetN, confidence, var) 或 (None, 0, None)。"""
    raw = F.bounds(text or '')
    # 同名变量合并，取最大上界（题面常分 30%/100% 两档，要的是满档）
    by_var = {}
    for name, sign, val, kind in raw:
        if sign != '<=' or not (1 <= val <= 5_000_000): continue
        by_var[name] = max(by_var.get(name, 0), val)
    if not by_var: return None, 0.0, None
    cands = [(n, v, 'merged', 0) for n, v in by_var.items()]
    ti, _ = text_feats(text or '', _dim)
    X = np.zeros((len(cands), _dim), dtype=np.float32)
    for i, (var, val, kind, _) in enumerate(cands):
        for j, v in cand_feats(ti, var, val, cands, _dim).items():
            X[i, j] = v
    p = 1.0 / (1.0 + np.exp(-np.clip(X @ _w + _b, -30, 30)))
    best = int(np.argmax(p))
    return int(cands[best][1]), float(p[best]), cands[best][0]

def seed_n(seed):
    toks=[t for t in re.split(r'\s+',(seed or '').strip()) if t]
    ints=[int(t) for t in toks if re.fullmatch(r'-?\d+',t)]
    return ints[0] if ints else 0

def report(path, label, has_seed=True):
    rows=[json.loads(l) for l in open(path)]
    ok=small=big=none=0; ex=[]
    for r in rows:
        t,c,v = predict(r.get('hint',''))
        if t is None: none+=1; continue
        if t > 5_000_000: big+=1; continue
        sn = seed_n(r.get('seed','')) if has_seed else 0
        if sn and t < sn:
            small+=1
            if len(ex)<5: ex.append((r['docId'],t,sn,v))
            continue
        ok+=1
    n=len(rows)
    print(f'== {label} ({n})')
    print(f'   可用 targetN : {ok:6d}  {ok/n*100:5.1f}%')
    print(f'   无范围       : {none:6d}  {none/n*100:5.1f}%')
    print(f'   小于样例(错) : {small:6d}  {small/n*100:5.1f}%')
    print(f'   超上限(错)   : {big:6d}')
    if ex: print('   剩余错例:', ex)
    return ok, n

if __name__ == '__main__':
    a,b = report('statements_zh.jsonl','中文')
    report('statements_en.jsonl','英文', has_seed=False)
