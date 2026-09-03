# ADR-0005：评分入口终止 LF 规范化

状态：Accepted for A3.1

日期：2026-09-03

## 背景

A3.0 在冻结的 70 条 A2 holdout 上完成两组真实模型生成。M0 有 2 条、External 有 54 条输出通过 strict unified diff parser，但 56 条中有 55 条缺少终止 LF。在不改变其他字节的诊断中，仅追加一个 LF 后，M0 2/2 和 External 13/50 个原 apply failure 可通过 `git apply --recount --check`。

缺少终止 LF 可能来自 tokenizer decode 的传输边界，不等价于模型生成了错误的删除行、上下文、路径或 hunk。若把它与内容错误混为 apply failure，会使评分过度依赖字符串封装细节。

## 决策

自 `a3-scoring-v2` 起，在 strict parser 和 `git apply` 之前执行唯一允许的传输规范化：

```text
if raw_text is non-empty and does not end with LF:
    evaluated_text = raw_text + one LF
else:
    evaluated_text = raw_text unchanged
```

规范化最多新增 1 byte，绝不删除或改写原字节。以下操作继续禁止：

- 剥离 Markdown 围栏或自然语言；
- trim 任意空白；
- 修复 hunk header、路径或上下文；
- 恢复截断/部分 diff；
- 多候选选择或失败后重试。

parser、单文件 `main.cpp` 路径策略、`git apply --recount`、Bubblewrap、编译和测试语义保持不变。

## 审计与版本边界

- prediction artifact 与其中的 `raw_text` 保持不可变；
- 每条 v2 score 同时保存 raw SHA256、evaluated SHA256、是否追加 LF 和新增字节数；
- score manifest 同时记录 source inference commit/config 与 evaluator commit/scoring config；
- A3.0 strict-v1 artifact、哈希和 0/70 结果不覆盖、不改名、不回填；
- A3.1 v2 重评分写入独立 `scoring-v2/<job-id>`，只能称为协议修订后的基线；
- 后续 Base、SFT、DPO 和 External 比较必须统一使用 v2，禁止跨 scoring protocol 直接比较。

机器配置为 `configs/evaluation/a3_scoring_v2.json`，manifest 使用 `schemas/run-manifest-v0.2.schema.json`。

## 解释边界

该决定只消除终止换行的传输差异，不放宽补丁内容。v2 分数高于 v1 时，只能归因于评分协议修订，不能称为模型质量提升或训练收益。

## 验收

- 单元测试覆盖缺失 LF、已有 LF、CRLF、空输出和不允许的其他恢复；
- 配置语义漂移 fail closed；
- v2 manifest 通过 Draft 2020-12 Schema；
- 两组不可变 A3.0 prediction 完成 CPU-only v2 重评分；
- 比较器重算 summary 并核对逐案例 raw/evaluated 哈希、固定 70 条分母、案例顺序和 canonical prompt。
