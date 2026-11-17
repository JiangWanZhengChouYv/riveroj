"""严格校验：模型的 targetN 是否可用。

两条硬性检查（违反即判错）：
  1. targetN >= 样例里的实际计数（否则生成的数据比样例还小，无意义）
  2. targetN <= 5e6（judge 预算上限）
"""
import json, re, sys
import numpy as np
sys.path.insert(0,'..')
import feat as F
from train2 import cand_feats, text_feats, DIM
from evaluate import predict_targetN

def seed_n(seed):
    toks=[t for t in re.split(r'\s+',(seed or '').strip()) if t]
    ints=[int(t) for t in toks if re.fullmatch(r'-?\d+',t)]
    return ints[0] if ints else 0

def check(path, label):
    rows=[json.loads(l) for l in open(path)]
    ok=bad_small=bad_big=none=0
    bad_examples=[]
    for r in rows:
        t,c=predict_targetN(r.get('hint',''))
        if t is None: none+=1; continue
        sn=seed_n(r.get('seed','')) if 'seed' in r else 0
        if t>5_000_000: bad_big+=1; continue
        if sn and t<sn:
            bad_small+=1
            if len(bad_examples)<6: bad_examples.append((r['docId'],t,sn))
            continue
        ok+=1
    n=len(rows)
    print(f'== {label}  ({n} 题)')
    print(f'   可用 targetN      : {ok:6d}  {ok/n*100:5.1f}%')
    print(f'   无候选(题面没写范围): {none:6d}  {none/n*100:5.1f}%')
    print(f'   小于样例规模(错)   : {bad_small:6d}  {bad_small/n*100:5.1f}%')
    print(f'   超过上限(错)       : {bad_big:6d}')
    if bad_examples: print('   错例 docId/targetN/seedN:', bad_examples)
    return ok,n

check('statements_zh.jsonl','中文')
check('statements_en.jsonl','英文')
