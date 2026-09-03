# A1 数据 Pilot：边界与来源登记

## A1-0 冻结边界

本阶段只验证数据生产链，不进行正式训练。目标规模为 `300 train + 50 validation`，第一版只纳入 C++，function/file-window 目标比例为 85%/15%。外部测试数据、合成 fixture 和 hidden test 内容不得进入 pilot 训练或验证数据。

所有最终样本必须符合 `schemas/sample-v0.2.schema.json`，并能重放 base revision、gold patch 和测试命令。数据、原始下载文件和完整 JSONL 保留在集群；Git 只保存脚本、配置、manifest 摘要和报告。

当前冻结配置：`configs/data/a1_pilot_v2.json`。集群权威目录为 `/mingli01/data/patchalign-cpp/a1/processed/pilot-v2-isolated`。

旧 `pilot-v1-stratified` 在 A3.2 fail-closed 预检中发现跨 split 隔离实现错误：20 条 CommitPackFT validation 与 train payload 重复，另有 6 个 RunBugRun problem family 重叠。旧目录保留作审计但不得训练。Job `93938` 生成的 isolated-v2 保持 300/50 配额和来源比例，train/validation 在 repository family、sample、base commit、repo_id 和 provenance 五个维度均为零重叠。

isolated-v2 的 train SHA256 仍为 `af549373d147ff294e138d8aeaa01a6d512cc3cc61b031f10be10781bd1c5d98`；validation SHA256 为 `8b1f168befe506c221380b02b1263ea006917fddbe10fb15a2e8c988236bd0bd`；manifest SHA256 为 `e078753bbfe69044641ef8e71c935340a7785886627993b8042956a72ba6b9a4`。

`configs/data/a1_pilot_v1.json` 仅用于重放旧 artifact，不再是训练输入。

## A1-1 数据源登记

| 数据源 | 用途 | 本地下载内容 | 必须登记 |
|---|---|---|---|
| CommitPackFT | train/validation 候选 | 官方 C++ 数据文件及其 metadata | dataset revision、下载文件 SHA256、许可证字段、原始数量 |
| RunBugRun | train/validation 候选、buggy/fixed 重放 | 官方数据索引、C++ buggy/fixed pair、测试元数据；代码仓库按需下载 | release/commit、索引 SHA256、problem_id、许可证、原始数量 |

本阶段不下载 Defects4C 或 SWE-bench Multilingual；它们属于后续 external test，不得混入 A1 train/validation。Qwen 模型也不属于 A1 数据下载任务，继续使用集群已有模型路径。

## 传输目录建议

本地先按来源分目录保存并计算 SHA256，再传到集群：

```text
/mingli01/data/patchalign-cpp/a1/raw/commitpackft/
/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data/
```

不要覆盖已有文件；文件名应保留上游名称，另附 `source-record.json` 记录 URL、revision、下载时间、许可证和 SHA256。传输完成后先在集群校验 SHA256，再开始解析和过滤。

## A1 责任

项目由用户独立完成。用户同时负责数据下载与许可审查、处理脚本、评测复验、集群作业、模型实验、artifact 管理和最终论文记录。
