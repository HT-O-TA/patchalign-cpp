# Data-v2 泛化增强计划

> 当前状态：现有供给审计与新来源桌面准入审计均已完成；负责人已接受 ADR-0010 的分层 family 契约，GitHub C++ 修复元数据 pilot 已实现、待集群 CPU/网络实测。尚未下载补丁或源码内容、冻结训练集、训练模型或授权 A5/DPO。

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

桌面审计发现的 family 契约冲突已由负责人接受 ADR-0010 解决：`repository_split_group` 只负责仓库级 train/validation/benchmark 隔离，`sampling_family` 负责 issue/function 级重复控制，仍保持 v1+增量每 sampling family 最多 2 条，并新增 train/validation 每仓库最多 40/20 条。2,000/200 仍是容量探针，不是训练配额；新的多样性最低目标为 train 100 个新仓库、1,000 个新 sampling family，validation 20 个新仓库、100 个新 sampling family。第一轮冻结配置不被回写。

集群 CPU-only 专项 Job `96326` 完成 `5 passed in 0.03s`；替换全量回归 Job `96328` 完成 `265 passed in 13.50s`。首次 one-off 全量 Job `96327` 因 `/bin/sh` 不支持 Bash `pipefail`，在 pytest 前退出；失败被保留并由 POSIX 兼容的 `set -eu` 重提修正。

## 第三阶段：分层契约与 GitHub 元数据 pilot

版本化机器契约为 `configs/data/data_v2_contract_v2_1.json`，决策依据为 [ADR-0010](decisions/0010-data-v2-hierarchical-family-contract.md)。`scripts/data/check_data_v2_contract.py` 以 fail-closed 方式检查 split、sampling、仓库上限、容量目标和防泄漏边界。

首轮 GitHub pilot v1 由 `configs/data/data_v2_metadata_pilot_v1.json` 固定，但 Job `96406` 的真实查询为 0 条：诊断证明 `label:bug` 挂在 PR 上的搜索条件过窄，去掉该条件后同一冻结时间窗有 48 条。v1 的空 artifact 和日志按原样保留。

修正版 `configs/data/data_v2_metadata_pilot_v1_1.json` 不把质量门槛降成关键词猜测，而是要求 PR 显式关闭同仓库 issue，并读取该 issue 的元数据核验 `bug/defect` 标签。为适配无令牌 GitHub 核心 API 配额，最多检查 18 个候选 PR，目标仍为最多 15 个不同仓库。它只允许保存仓库/PR/issue/commit 身份、公开统计、许可证标识与哈希、查询响应哈希和拒绝原因；禁止保存 patch、源码 blob、标题正文、用户身份和 LICENSE 原文。评测仓库 denylist 在内容准入前仍标记为不完整，因此本阶段只能判断供给与治理可行性，不能产生训练样本。

v1.1 Job `96412` 实查前 18 条后仍为 0：6 条文件数越界、3 条行数越界、7 条无同仓库显式 issue、1 条 stars 回落、1 条许可证不在 allowlist。v1.2 Job `96417` 按创建时间倒序、在详情请求前按仓库去重，再查 12 个仓库后仍为 0。全部 48 条搜索结果只覆盖 34 个仓库，低于 train 至少 100 个新仓库的门槛；即使未检查项全部通过也无法改变容量结论，所以当前单查询路线判定失败并停止，详见 [GitHub metadata pilot 结果](evidence/data_v2_github_metadata_pilot.md)。

该 pilot 使用 CPU 和网络，不申请 GPU。即使达到 15 仓库目标，也只说明发现链和筛选链可运行；父提交核验、变更文件类型、测试重放、许可证原文审计、时间边界和完整 benchmark 去污染仍必须在受控内容阶段另行闭环。

## 审计后的决策门

只有以下条件同时满足，才进入 Data-v2 构造：

1. 所有冻结输入和原始 shard 哈希一致；
2. confirmation/external gold 消费保持为 false；
3. ADR-0010 的 2,000/200 容量探针及 train/validation 多样性最低目标得到真实元数据与后续内容资格结果支持；
4. 新训练集构造器能够拒绝覆盖、输出 Schema/隔离/token 报告并可重复得到相同哈希；
5. 训练方案预注册至少 3 个 seed 的小规模对照，评测继续使用冻结 greedy Pass@1 和真实执行评分。

当前 GitHub 单查询已证明容量不足。下一步应先设计多查询/多时间窗的仓库发现层，并并行完成 Multi-SWE-RL C++ 与 RunBugRun v2 legacy 差量元数据审计；在任一路线满足仓库和 sampling-family 容量前，不下载补丁、不冻结 Data-v2，也不直接在 v1 上重复 SFT。

## 第四阶段：容量失败后的 exploratory replay 消融

当前 GitHub 查询容量失败后，负责人授权由执行方选择后续方案直至合理 GPU 作业排队。项目据此接受 [ADR-0011](decisions/0011-data-v2-exploratory-replay-mix.md)，建立明确不满足 Data-v2.1 正式容量门的 `data-v2-exploratory-replay-v0.1`：train 使用 260 条已审计安全增量和 520 条冻结 formal-train replay，focused validation 使用 131 条安全增量。

混合 train 固定为 416 function + 364 file-window，避免 260 条全 file-window 增量单独 continuation；训练从 M1-R2 adapter 以 NF4、单轮、低学习率继续。数据构建器必须重新生成候选并与冻结 candidate-audit 精确一致，同时验证 Schema、formal lock、sample/payload/family 隔离和输入哈希。只有 CPU 数据构建、全仓回归和 token/adapter/environment preflight 全部通过，才提交单 GPU 的 98-step exploratory 消融。

该路线不把旧来源包装成正式 Data-v2，不改变 A3.4/A5 状态；GPU 结果之后仍须在 formal、confirmation 和 Defects4C 上按原协议评测才能讨论泛化。
