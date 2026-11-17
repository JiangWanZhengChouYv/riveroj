# 数据范围识别模型

训练与导出脚本。产出 `addons/luogu-import/src/range-weights.json`，由
`addons/luogu-import/src/rangeModel.ts` 在运行时加载。

## 为什么不是普通的文本分类

要回答的问题不是「这段文字有没有范围」，而是「**哪个变量的上界是数据规模**」。
所以做成候选排序：抽出所有 `var <= 数值`，给每个候选打分，取最高分。

## 流程

```bash
# 0. 从 Hydro 导出题面（需 MongoDB 可访问）
#    statements_zh.jsonl / statements_en.jsonl，每行 {docId, hint, seed}
mongo hydro dump_final.js > statements_zh.jsonl
mongo hydro dump_en.js   > statements_en.jsonl

# 1. 构造候选排序训练集
python3 dataset.py

# 2. 训练（纯 numpy，无 sklearn 依赖）
python3 train2.py          # 输出 test top-1 准确率

# 3. 导出权重
python3 export.py          # 生成 range-weights.json
cp range-weights.json ../../addons/luogu-import/src/
```

## 关键约束

- **哈希必须与 TypeScript 完全一致**：用 FNV-1a 32bit（`hasher.py` / `rangeModel.ts`）。
  Python 内置 `hash()` 对 str 默认加盐，跨进程不可复现，绝不能用。
- **文件名不能撞**：权重文件叫 `range-weights.json`，不能叫 `rangemodel.json`——
  与 `rangeModel.ts` 只差大小写，在 macOS/部分 Linux 上会被解析成同一路径，
  `import ... from './rangeModel'` 会拿到 JSON 内容而不是模块（实测踩过）。
- **只喂范围段**：训练与推理都只看「提示 / 数据范围 / Constraints」这一段，
  喂整篇题面会让正文里的坐标、示例数字混进特征，准确率下降。
- **同名变量取最大上界**：题面常分 30%/100% 两档，要满档；让模型直接选会选到部分分档。

## 实测

| 指标 | 值 |
| --- | --- |
| 训练集 | 13003 条（zh 10984 / en 2019） |
| 测试集 top-1 | **96.0%** |
| 中文覆盖（能给出 targetN） | 16753 题中 64.4% |
| 其中小于样例规模（错） | 1.2% |
| 英文覆盖 | 14.3%（洛谷英文题面 80% 没有 Constraints 段） |

英文覆盖率低不是模型问题：14070 份英文题面里 11295 份根本没有 Constraints 段。
中文题面 98.7% 都有，且同一道题的中英文共用 docId，实际使用走中文即可。

## 端到端

`oracle.ts` 里的优先级：手工指定 > **模型** > 规则解析的 n > 默认值。
模型输出必须 ≥ 样例里的实际计数，否则退回规则（挡住那 1.2% 错例）。
