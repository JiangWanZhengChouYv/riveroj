"""题面「数据范围」特征提取（中文 + English）。

设计约束（对应用户要求「只用吐范围好识别」）：
  1. 只吃「提示 / 数据范围 / 说明 / Hints / Constraints」这一段，不碰题面正文；
  2. 输出的是「哪个变量的上界是多少」，不是整段文本的分类；
  3. 特征只用句式骨架 + 变量名 + 数值量级，避免记住具体题目。
"""
import re, math
from hasher import h32

# ---------- 归一化 ----------
_MACROS = [
    (r'\\times(?![a-zA-Z])', ' * '), (r'\\cdot(?![a-zA-Z])', ' * '),
    (r'\\le(q|qslant)?(?![a-zA-Z])', ' <= '), (r'\\ge(q|qslant)?(?![a-zA-Z])', ' >= '),
    (r'\\(?:dfrac|frac)(?![a-zA-Z])', ' / '),
    (r'\\lvert|\\rvert|\\vert', ' '),
    (r'\\[a-zA-Z]+\*?', ' '),
    (r'[{}\\]', ' '),
]
_CN = [('不超过',' <= '),('不大于',' <= '),('至多',' <= '),('最多',' <= '),
       ('不小于',' >= '),('至少',' >= '),('最少',' >= '),('小于等于',' <= '),
       ('大于等于',' >= ')]
_EN = [(r'\bat\s+most\b',' <= '),(r'\bno\s+more\s+than\b',' <= '),(r'\bup\s+to\b',' <= '),
       (r'\bless\s+than\s+or\s+equal\s+to\b',' <= '),(r'\bnot\s+greater\s+than\b',' <= '),
       (r'\bat\s+least\b',' >= '),(r'\bno\s+less\s+than\b',' >= ')
      ]
_SYM = [('≤',' <= '),('≥',' >= '),('×',' * '),('·',' * '),('＜',' < '),('＞',' > '),('≦',' <= '),('≧',' >= ')]

def normalize(text):
    s = text or ''
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', s)
    s = re.sub(r'```[\s\S]*?```', ' ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r' \1 ', s)
    s = s.replace('$', ' ')
    # 千分位必须在 _MACROS 之前去掉：_MACROS 会把 { } 变成空格，
    # 之后 1{,}000 就变成 "1 , 000"，再也合不回去了。
    s = re.sub(r'\{\s*,\s*\}', '', s)          # 1{,}000 -> 1000
    for _ in range(3):
        s = re.sub(r'(\d)\s*,\s*(\d{3})(?!\d)', r'\1\2', s)
    for p, r in _MACROS:
        s = re.sub(p, r, s)
    for a, b in _CN + _SYM:
        s = s.replace(a, b)
    for p, r in _EN:
        s = re.sub(p, r, s, flags=re.I)
    s = re.sub(r'[ \t]+', ' ', s)
    return s

# ---------- 数值与变量 ----------
NUM = (r'(?:\d+(?:\.\d+)?\s*(?:\*\s*)?10\s*\^\s*\{?\s*\d+\s*\}?'
       r'|\d+\s*\^\s*\{?\s*\d+\s*\}?'
       r'|\d+(?:\.\d+)?)')
VAR = r'([A-Za-z][A-Za-z0-9_]{0,15})'

def magnitude(tok):
    t = re.sub(r'[\s{}]', '', tok)
    m = re.match(r'^(\d+(?:\.\d+)?)\*?10\^(\d+)$', t)
    if m: return float(m.group(1)) * 10 ** int(m.group(2))
    m = re.match(r'^10\^(\d+)$', t)
    if m: return 10 ** int(m.group(1))
    m = re.match(r'^(\d+(?:\.\d+)?)$', t)
    if m: return float(m.group(1))
    return None

def log10b(v):
    if not v or v <= 0: return -1
    return int(min(12, math.floor(math.log10(v))))

# 常见「计数变量」名；模型会在此基础上自己学权重
COUNT_NAMES = {'n','N','m','M','k','K','q','Q','len','length','size','cnt','tot',
               'T','t','operation','operations','op','ops','num','number','l','L'}

def bounds(text):
    """返回 [(var, sign, value, kind)]；sign 为 '<=' 表示这是上界。"""
    s = normalize(text)
    out = []
    def add(m, vg, ng, kind):
        v = magnitude(m.group(vg))
        name = m.group(ng)
        if v: out.append((name, '<=', v, kind))
    # 链式 lo <= var <= hi（取 hi）
    for m in re.finditer(NUM + r'\s*(?:<=|<)\s*' + VAR + r'\s*(?:<=|<)\s*(' + NUM + ')', s):
        v = magnitude(m.group(2))
        if v: out.append((m.group(1), '<=', v, 'chain'))
    # var <= num
    for m in re.finditer(VAR + r'\s*(?:<=|<)\s*(' + NUM + ')', s):
        v = magnitude(m.group(2))
        if v: out.append((m.group(1), '<=', v, 'direct'))
    # num <= var  → var 有下界
    for m in re.finditer('(' + NUM + r')\s*(?:<=|<)\s*' + VAR, s):
        v = magnitude(m.group(1))
        if v: out.append((m.group(2), '>=', v, 'reverse'))
    # var >= num / num >= var
    for m in re.finditer(VAR + r'\s*(?:>=|>)\s*(' + NUM + ')', s):
        v = magnitude(m.group(2))
        if v: out.append((m.group(1), '>=', v, 'ge'))
    for m in re.finditer('(' + NUM + r')\s*(?:>=|>)\s*' + VAR, s):
        v = magnitude(m.group(1))
        if v: out.append((m.group(2), '<=', v, 'rev_ge'))
    # 逗号列表 a, b, c <= 1e5
    for m in re.finditer(r'((?:[A-Za-z][A-Za-z0-9_]{0,15}\s*[,，、]\s*)+[A-Za-z][A-Za-z0-9_]{0,15})\s*(?:<=|<)\s*(' + NUM + ')', s):
        v = magnitude(m.group(2))
        if not v: continue
        for nm in re.split(r'[,，、]', m.group(1)):
            nm = nm.strip()
            if nm: out.append((nm, '<=', v, 'list'))
    # 表格：| 1 <= n <= | 10^5 | 形式（洛谷常见）
    for m in re.finditer(r'\|\s*1\s*<=\s*' + VAR + r'\s*<=\s*\|?\s*(' + NUM + ')', s):
        v = magnitude(m.group(2))
        if v: out.append((m.group(1), '<=', v, 'table'))
    return out

def featurize(text, dim=1 << 14):
    """返回 (indices, values)；稀疏特征。"""
    s = normalize(text or '')
    f = {}
    def add(k, v=1.0):
        h = h32(k) & (dim - 1)
        f[h] = f.get(h, 0.0) + v

    bs = bounds(text or '')
    ups = [(n, v, k) for n, sg, v, k in bs if sg == '<=']

    # 句式骨架（数字替换成 #），让模型学「怎么读」而不是「读到几」
    skel = re.sub(r'\d+', '#', s)
    for tok in re.findall(r'[A-Za-z]{2,}|[\u4e00-\u9fff]{1,4}|<=|>=', skel):
        add('w:' + tok.lower())

    add('n_up:%d' % min(len(ups), 8))
    add('n_all:%d' % min(len(bs), 10))
    if not bs: add('no_bounds')

    # 是否有「计数名」上界，以及它的量级
    cnt = [(n, v) for n, v, k in ups if n in COUNT_NAMES]
    add('has_count:%d' % (1 if cnt else 0))
    if cnt:
        add('cnt_min_mag:%d' % log10b(min(v for _, v in cnt)))
        add('cnt_max_mag:%d' % log10b(max(v for _, v in cnt)))
        add('cnt_cnt:%d' % min(len(cnt), 5))
    # 全部上界的最小/最大值级：计数上界通常显著小于值域上界
    if ups:
        mags = sorted(log10b(v) for _, v, _ in ups)
        add('up_min_mag:%d' % mags[0])
        add('up_max_mag:%d' % mags[-1])
        add('up_spread:%d' % min(9, mags[-1] - mags[0]))
    for n, v, k in ups:
        add('var:' + n)
        add('kind:' + k)
        add('varmag:%s:%d' % (n, log10b(v)))
        if n in COUNT_NAMES:
            add('countvar:%s:%d' % (n, log10b(v)))

    # 中文/英文兜底句式
    if re.search(r'(?:不超过|不大于|至多|最多)\s*\d', s): add('cn_phrase')
    if re.search(r'\bat\s+most\s+\d', s, re.I): add('en_phrase')
    if re.search(r'题目来源|source\b', s, re.I): add('source_note')
    # 表格标记
    if s.count('|') >= 4: add('table_form')

    idx = sorted(f)
    return idx, [f[i] for i in idx]
