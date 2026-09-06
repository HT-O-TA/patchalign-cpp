# Data-v2 泛化增强计划

> 当前状态：现有供给审计与新来源桌面准入审计均已完成；等待 family 契约决策，尚未下载新来源内容、冻结训练集、训练模型或授权 A5/DPO。

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

## 第二阶段：新来源桌面准入

机器清单为 `configs/data/data_v2_source_admission_v1.json`，校验器为 `scripts/data/check_data_v2_source_admission.py`，详细证据见 [新来源准入与污染审计](evidence/data_v2_source_admission.md)。截至 2026-09-06 共审计 9 个方向：

- 元数据 pilot：自建 GitHub issue/PR 关联 C++ 修复池、Multi-SWE-RL、RunBugRun v2；
- 评测保留：Multi-SWE-bench C++、BugsCpp、LLVM APR Benchmark、DebugBench C++；
- 拒绝：FixEval、PatchEval-Verified，原因是当前发布没有 C++ 数据。

没有任何来源被直接准入训练。自建 GitHub 修复池是首选供给路线，因为它可以主动寻找新仓库、长输入和结构性修改；Multi-SWE-RL 只作仓库级复杂样本补充；RunBugRun v2 只先检查相对 legacy 的 C++ problem family 差量。

本轮同时发现 family 契约冲突：当前 `repo_family` 既是 split 隔离键，又受每 family 最多 2 条限制。train 最低 1,600 条 new-family 样本在 repository-family 解释下至少需要 800 个未见仓库，现有候选不可能直接满足。内容试采前必须通过新版本配置选择“保留规则并缩小目标”或“分离 repository split group 与 sampling family”；本轮未替负责人决定，也未修改第一轮冻结配置。

集群 CPU-only 专项 Job `96326` 完成 `5 passed in 0.03s`；替换全量回归 Job `96328` 完成 `265 passed in 13.50s`。首次 one-off 全量 Job `96327` 因 `/bin/sh` 不支持 Bash `pipefail`，在 pytest 前退出；失败被保留并由 POSIX 兼容的 `set -eu` 重提修正。

## 审计后的决策门

只有以下条件同时满足，才进入 Data-v2 构造：

1. 所有冻结输入和原始 shard 哈希一致；
2. confirmation/external gold 消费保持为 false；
3. 2,000/200 草案的同步覆盖门槛可实现，或先形成负责人认可的版本化修订；
4. 新训练集构造器能够拒绝覆盖、输出 Schema/隔离/token 报告并可重复得到相同哈希；
5. 训练方案预注册至少 3 个 seed 的小规模对照，评测继续使用冻结 greedy Pass@1 和真实执行评分。

如果供给不足，下一步应新增经过许可证与 family 治理的数据来源，而不是直接在 v1 上重复 SFT。
