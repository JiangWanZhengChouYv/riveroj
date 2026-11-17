"""确定性字符串哈希（FNV-1a 32bit），与 TypeScript 侧逐位一致。

Python 内置 hash() 对 str 默认加随机盐（PYTHONHASHSEED），
跨进程/跨语言不可复现，因此训练与推理都必须用这个。
"""

def h32(s: str) -> int:
    # FNV-1a over UTF-8 bytes
    x = 0x811C9DC5
    for b in s.encode('utf-8'):
        x ^= b
        x = (x * 0x01000193) & 0xFFFFFFFF
    return x
