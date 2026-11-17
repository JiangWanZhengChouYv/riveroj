"""端到端评估：模型能否为每题给出可用的 targetN。"""
import json, re, sys
import numpy as np
sys.path.insert(0, '..')
import feat as F
from train2 import cand_feats, text_feats, DIM

m = np.load('../model.npz')
w, b, dim = m['w'], float(m['b'][0]), int(m['dim'][0])

def predict_targetN(text):
    """返回 (targetN, conf) 或 (None, 0)。"""
    cands = []
    seen = set()
    for name, sign, val, kind in F.bounds(text):
        if sign != '<=' or not (1 <= val <= 5_000_000): continue
        k = (name, val)
        if k in seen: continue
        seen.add(k)
        cands.append((name, val, kind, 0))
    if not cands: return None, 0.0
    ti, _ = text_feats(text, dim)
    X = np.zeros((len(cands), dim), dtype=np.float32)
    for i, (var, val, kind, _) in enumerate(cands):
        for j, v in cand_feats(ti, var, val, cands, dim).items():
            X[i, j] = v
    p = 1.0 / (1.0 + np.exp(-np.clip(X @ w + b, -30, 30)))
    best = int(np.argmax(p))
    return int(cands[best][1]), float(p[best])

def main():
    rows = [json.loads(l) for l in open('statements_zh.jsonl')]
    cov = 0; conf_ok = 0
    by_conf = {'high':0,'mid':0,'low':0}
    examples = []
    for r in rows:
        t, c = predict_targetN(r.get('hint',''))
        if t is None: continue
        cov += 1
        if c >= 0.5: conf_ok += 1
        by_conf['high' if c>=0.8 else 'mid' if c>=0.5 else 'low'] += 1
        if len(examples) < 8 and t > 1:
            examples.append((r['docId'], t, round(c,3), ' '.join((r.get('hint') or '')[:110].split())))
    print(f'zh 题数 {len(rows)}')
    print(f'能给出 targetN: {cov}  {cov/len(rows)*100:.1f}%')
    print(f'  其中置信度>=0.5: {conf_ok}  {conf_ok/len(rows)*100:.1f}%')
    print(f'  置信度分布: {by_conf}')
    print('\n样例:')
    for d,t,c,h in examples:
        print(f'  doc{d} targetN={t} conf={c}  {h[:90]}')

if __name__ == '__main__':
    main()
