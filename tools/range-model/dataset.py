"""构造「候选上界排序」训练集。

任务定义：
  给定范围文本，抽出一串候选上界 (变量名, 数值)，
  模型要判断【哪一个是数据规模参数】→ 用它当 targetN。

监督信号（训练时可用，推理时不可用）：
  样例第一行/token 里的实际计数 cnt。若某候选上界 >= cnt 且量级与 cnt 相近，
  它才可能是规模参数；若上界远大于 cnt 且明显是值域（如 a<=1e9），则不是。
  这样标签就不是「规则的复读」，而是来自样例的结构证据。
"""
import json, re, sys
sys.path.insert(0, '..')
import feat as F

COUNT_STRONG = {'n', 'N', 'len', 'length', 'size', 'm', 'M'}
COUNT_WEAK = {'k', 'K', 'q', 'Q', 'cnt', 'tot', 'operations', 'op', 'ops', 'num', 'number', 'T', 't', 'l', 'L'}

def seed_count(seed):
    """从样例推断「计数」大概是多少：优先第 1 个 token，其次第 2 个。"""
    toks = [t for t in re.split(r'\s+', (seed or '').strip()) if t]
    ints = [int(t) for t in toks if re.fullmatch(r'-?\d+', t)]
    return ints

def candidates(text):
    """合并同名同值的候选，保留最可信的 kind。"""
    seen = {}
    for name, sign, val, kind in F.bounds(text):
        if sign != '<=': continue
        if not (1 <= val <= 5_000_000): continue
        key = (name, val)
        if key not in seen:
            seen[key] = kind
    return [(n, v, k) for (n, v), k in seen.items()]

def label_candidates(text, seed):
    """给每个候选打 0/1 标签，返回 [(var, val, kind, label)]。"""
    cands = candidates(text)
    if not cands:
        return []
    ints = seed_count(seed)
    seed_n = ints[0] if ints else 0
    out = []
    for name, val, kind in cands:
        lab = 0
        if name in COUNT_STRONG:
            # 规模参数名的直接候选：只要不小于样例规模就成立
            if val >= max(1, seed_n): lab = 1
        elif name in COUNT_WEAK:
            if val >= max(1, seed_n) and val <= 2_000_000: lab = 1
        else:
            # 其它变量：只有当它是「所有上界里最小的那个量级」时才可能是规模
            mags = [F.log10b(v) for _, v, _ in cands]
            if val <= 1_000_000 and F.log10b(val) <= min(mags) + 1:
                lab = 1
        out.append((name, val, kind, lab))
    return out

def build(zh_path, en_path, out_path):
    rows = []
    # 中文带样例
    for line in open(zh_path):
        d = json.loads(line)
        lab = label_candidates(d.get('hint', ''), d.get('seed', ''))
        if not lab: continue
        rows.append({'lang': 'zh', 'text': d['hint'][:1400], 'cands': lab,
                     'seed_n': (seed_count(d.get('seed','')) or [0])[0]})
    # 英文无样例：用中文同 docId 的样例补
    seed_by_doc = {}
    for line in open(zh_path):
        d = json.loads(line)
        seed_by_doc[d['docId']] = d.get('seed', '')
    for line in open(en_path):
        d = json.loads(line)
        seed = seed_by_doc.get(d['docId'], '')
        lab = label_candidates(d.get('hint', ''), seed)
        if not lab: continue
        rows.append({'lang': 'en', 'text': d['hint'][:1400], 'cands': lab,
                     'seed_n': (seed_count(seed) or [0])[0]})
    with open(out_path, 'w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    npos = sum(1 for r in rows if any(c[3] for c in r['cands']))
    print(f'rows {len(rows)}  with-positive {npos} ({npos/len(rows)*100:.1f}%)')
    print(f'  zh {sum(1 for r in rows if r["lang"]=="zh")}  en {sum(1 for r in rows if r["lang"]=="en")}')
    return rows

if __name__ == '__main__':
    build('statements_zh.jsonl', 'statements_en.jsonl', 'rank.jsonl')
