"""候选排序模型（numpy，稀疏特征，避免大矩阵）。

关键改动 vs 上一版：
  1. 文本特征只算一次（按样本缓存），候选特征叠加在上面；
  2. 全程用 (indices, values) 稀疏表示，只在矩阵乘法时按块稠密化；
  3. DIM 降到 2^13，内存从 11k×32768×4B=1.4GB 降到 350MB 以内。
"""
import json, re, sys, math, pickle
import numpy as np
sys.path.insert(0, '..')
import feat as F
from hasher import h32

DIM = 1 << 13
STRONG = {'n','N','len','length','size','m','M'}
WEAK = {'k','K','q','Q','cnt','tot','operations','op','ops','num','number','T','t','l','L'}

def text_feats(text, dim=DIM):
    idx, vs = F.featurize(text, dim=dim)
    return idx, vs

def cand_feats(text_idx, var, val, cands, dim=DIM):
    f = {}
    for i in text_idx:
        f[i] = f.get(i, 0.0) + 1.0
    def add(k, v=1.0):
        h = h32(k) & (dim - 1)
        f[h] = f.get(h, 0.0) + v
    add('var:' + var)
    add('cls:' + ('S' if var in STRONG else 'W' if var in WEAK else 'O'))
    add('mag:%d' % F.log10b(val))
    vals = [c[1] for c in cands]
    mn, mx = min(vals), max(vals)
    add('pos:' + ('min' if val == mn else 'max' if val == mx else 'mid'))
    add('gap:%d' % min(9, F.log10b(val) - F.log10b(mn)))
    add('nc:%d' % min(6, len(cands)))
    add('digits:%d' % min(9, len(str(int(val)))))
    return f

def convert(rows, dim=DIM):
    """-> list of (dict_feats_per_cand, labels)"""
    out = []
    for r in rows:
        cands = r['cands']
        if not cands: continue
        ti, _ = text_feats(r['text'], dim)
        per = []
        for var, val, kind, lab in cands:
            per.append((cand_feats(ti, var, val, cands, dim), float(lab)))
        out.append(per)
    return out

def to_matrix(sample_cands, dim=DIM):
    n = len(sample_cands)
    X = np.zeros((n, dim), dtype=np.float32)
    y = np.zeros(n, dtype=np.float32)
    for k, (f, lab) in enumerate(sample_cands):
        for i, v in f.items():
            X[k, i] = v
        y[k] = lab
    return X, y

def train(samples, dim=DIM, epochs=20, lr=0.5, l2=2e-3):
    w = np.zeros(dim, dtype=np.float32); b = np.float32(0)
    m = np.zeros(dim, dtype=np.float32); v = np.zeros(dim, dtype=np.float32)
    mb = np.float32(0); vb = np.float32(0)
    b1, b2, eps = 0.9, 0.999, 1e-8
    step = 0
    for ep in range(1, epochs + 1):
        loss = 0.0; correct = 0; total = 0
        for sc in samples:
            X, y = to_matrix(sc, dim)
            if X.shape[0] == 0: continue
            z = X @ w + b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            loss += float(-(y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9)).mean())
            dz = (p - y) / X.shape[0]
            gw = X.T @ dz + l2 * w
            gb = float(dz.sum())
            step += 1
            m = b1 * m + (1 - b1) * gw
            v = b2 * v + (1 - b2) * gw * gw
            mb = b1 * mb + (1 - b1) * gb
            vb = b2 * vb + (1 - b2) * gb * gb
            mh = m / (1 - b1 ** step); vh = v / (1 - b2 ** step)
            w -= lr * mh / (np.sqrt(vh) + eps)
            b -= lr * (mb / (1 - b1 ** step)) / (math.sqrt(vb / (1 - b2 ** step)) + eps)
            pred = int(np.argmax(p))
            correct += int(y[pred] > 0.5); total += 1
        print(f'  ep{ep:02d} loss {loss/max(1,len(samples)):.4f} top1 {correct}/{total} = {correct/max(1,total)*100:.2f}%', flush=True)
    return w, b

def eval_top1(w, b, samples, dim=DIM):
    hit = tot = 0
    for sc in samples:
        X, y = to_matrix(sc, dim)
        if X.shape[0] == 0: continue
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w + b, -30, 30)))
        tot += 1
        hit += int(y[int(np.argmax(p))] > 0.5)
    return hit, tot

def main():
    rows = [json.loads(l) for l in open('rank.jsonl')]
    rng = np.random.default_rng(42); rng.shuffle(rows)
    cut = int(len(rows) * 0.85)
    print(f'rows {len(rows)} -> train {cut} test {len(rows)-cut}', flush=True)
    tr = convert(rows[:cut]); te = convert(rows[cut:])
    print(f'train samples {len(tr)}  test samples {len(te)}', flush=True)
    w, b = train(tr)
    h, t = eval_top1(w, b, tr); print(f'TRAIN top1 {h}/{t} = {h/t*100:.2f}%', flush=True)
    h2, t2 = eval_top1(w, b, te); print(f'TEST  top1 {h2}/{t2} = {h2/t2*100:.2f}%', flush=True)
    np.savez('../model.npz', w=w, b=np.array([b]), dim=np.array([DIM]))
    print('saved model.npz', flush=True)

if __name__ == '__main__':
    main()
