# Data-v2 泛化增强计划

> 当前状态：第一轮只读供给审计已完成；现有来源不足，尚未冻结训练集，尚未训练模型，未授权 A5/DPO。

## 目标

M1-R2 的六项诊断表明，模型已经显著改善 unified diff 协议、apply 和 build，但端到端修复语义没有在新 confirmation 和 Defects4C 上稳定迁移。Data-v2 的目标不是简单扩大条数，而是补足以下缺口：

1. 增加未被 v1 使用的 repository/problem family；
2. 提高代码不少于 100 行、prompt 不少于 1,024 tokens 的覆盖；
3. 增加 multi-line、add-helper、localized-refactor；
4. 增加 file-window，但仍以函数级为主；
5. 保持现有 formal、confirmation 和 external 评测身份不受污染；
6. 用多 seed 小规模消融证明数据变化有效后，才考虑正式重训。

## 第一阶段：供给审计

机器契约为 `configs/data/data_v2_supply_audit_v1.json`，实现为 `scripts/data/audit_data_v2_supply.py`。审计读取 CommitPackFT/RunBugRun 原始训练池和冻结 manifest，输出：

- v1 基座分布；
- 在“v1+增量每 family 最多 2 条”约束下的真实剩余容量；
- 长代码、长 prompt、复杂编辑、结构性编辑、file-window、新 family 和 CommitPackFT 的同步覆盖；
- 一个 2,000/200 增量草案是否能同时满足预设最低值；
- 所有拒绝原因、输入哈希和候选身份哈希。

这一阶段只输出元数据统计和候选哈希，不输出新训练 JSONL，不申请 GPU。

## 防泄漏边界

- Formal holdout 只读取 `problem_id` 用于排除；
- Confirmation 只读取 `problem_id` 用于排除；
- Defects4C 只读取 `project` 用于保守仓库别名排除；
- 不读取 confirmation/external 的源码、prompt、补丁、测试、得分或执行反馈；
- 不将六项诊断中的失败 case gold 用作训练；
- RunBugRun 保留 upstream train/validation，CommitPackFT 新 family 通过稳定哈希分配 split；
- v1 与增量合并后同一 family 最多 2 条，train/validation family 零交叉；
- 所有原始文件、冻结 manifest、tokenizer 和模型 revision 均需哈希匹配。

## 暂定规模与解释边界

供给审计暂用 2,000 train + 200 validation 的增量假设，它只是容量探针，不是最终冻结配额。目标同时要求新 family、长输入、复杂/结构修改、file-window 和 CommitPackFT 覆盖；任何不足都应调低方案或引入新来源，不能通过复制、合成或使用评测集补齐。

CommitPackFT 当前仍缺少仓库级可执行复现，因此可作为 SFT 监督数据，但不能被描述为经过 A2/Defects4C 同等级真实执行资格。RunBugRun 的 problem family 隔离也不能被描述为 repository-family 隔离。

## 第一轮真实结果

CPU-only Job `96256` 在 `gpu18` 用时 `00:06:14` 完成，5 项专项测试为 `5 passed`。同步结果文档后，CPU-only 全量回归 Job `96263` 为 `260 passed in 14.31s`。正式扫描看到 CommitPackFT 4,992 条、RunBugRun 237,516 条原始记录；所有原始 shard、v1 数据、formal holdout、confirmation、Defects4C manifest 和模型 config 哈希均匹配。

| 指标 | Train 可用增量 | Validation 可用增量 |
|---|---:|---:|
| 总数 | 260 | 131 |
| 新 family | 171 | 13 |
| 代码不少于 100 行 | 20 | 4 |
| Prompt 不少于 1,024 tokens | 14 | 4 |
| Complex edit | 189 | 92 |
| Add-helper + localized-refactor | 20 | 12 |
| File-window | 260 | 57 |
| CommitPackFT | 194 | 91 |

Train 剩余 260 条全部为 file-window，主要因为 v1 已占满大部分可用 function family 容量；validation 仍有 74 条 function。精确 token 化拒绝为 0，因此不能通过放宽 4,096-token 上限解决供给不足。

暂定 2,000/200 草案的两个 split 均未通过。即使把 391 条全部纳入，也无法达到新 family、长代码、长 prompt、结构性修改和“函数级为主”的共同目标。因此这些候选只保留为供给证据，不冻结为 Data-v2。

正式 artifact：

```text
artifacts/data-v2/supply-audit-v1/
├── candidate-audit.jsonl  cbe5f2fa910535be57458c5ca43483b21b3e92f17c3badaeef3847d308938e96
├── summary.json           a7f117a9d8a78c50d2dda17939ff80aeefbeff8bd889b993aece747dcfe6b753
└── run-manifest.json      cc34dec8b4ac4b21e4cae81a380d489bff57927f0700365e86cc7cb74b138cf9
```

结论：下一步必须接入新的 C++ 修复来源并重新做许可证、repository family、时间边界和 benchmark 污染审计；不能通过重复 v1、放宽 family 上限或使用 confirmation/external gold 补齐。

## 审计后的决策门

只有以下条件同时满足，才进入 Data-v2 构造：

1. 所有冻结输入和原始 shard 哈希一致；
2. confirmation/external gold 消费保持为 false；
3. 2,000/200 草案的同步覆盖门槛可实现，或先形成负责人认可的版本化修订；
4. 新训练集构造器能够拒绝覆盖、输出 Schema/隔离/token 报告并可重复得到相同哈希；
5. 训练方案预注册至少 3 个 seed 的小规模对照，评测继续使用冻结 greedy Pass@1 和真实执行评分。

如果供给不足，下一步应新增经过许可证与 family 治理的数据来源，而不是直接在 v1 上重复 SFT。
