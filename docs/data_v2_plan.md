# Data-v2 泛化增强计划

> 文档范围：保留 Data-v2 的问题定义、来源演进和晋级理由；实时作业状态只见 [项目状态](status.md)。旧单查询容量失败已由 repository→PR v2.1 的有效容量结果取代，当前执行受 ADR-0012～ADR-0019 的分阶段硬门约束。

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

混合 train 固定为 416 function + 364 file-window，避免 260 条全 file-window 增量单独 continuation；训练从 M1-R2 adapter 以 NF4、单轮、低学习率继续。CPU Job `96423` 已冻结 780/131；preflight Job `96426` 以 `287 passed` 核验 Schema、隔离、token、adapter、模型、环境和提交身份；单 GPU Job `96427` 已完成 98-step continuation，adapter SHA256 为 `d01dc411...21323`。

该路线不把旧来源包装成正式 Data-v2，不改变 A3.4/A5 状态。训练 loss 结果只允许作为优化与遗忘风险信号。`data-v2-exploratory-formal-inference-v0.1` 已冻结新 adapter 与原 formal 500 prompt 身份；preflight Job `96658` 与单 GPU Job `96662` 已完成，得到 500/500 成功生成、498 strict diff 和 3/3 稳定 probe。formal 500 的 CPU 真实评分由 Job `96780` 完成：parse/apply/compile/Pass 为 `498/412/389/13`，regression failure 8、timeout 1。相对 M1-R2 的 `14/500`，新增 3 个成功、丢失 4 个成功，净退化 1；虽满足 timeout≤2，但未达到 Pass≥14 的预注册下限。该单 seed replay continuation 因此不具备晋级条件。配置没有冻结自动 early-stop；继续运行 confirmation 124 和 Defects4C 176 只能补充诊断证据，不能挽回本轮 formal 门槛，提交额外 GPU 前应单独权衡研究价值。


## 第五阶段：多来源 discovery 与 Data-v2→DPO 硬门

负责人在旧 replay formal 失败后授予从 Data-v2 到正式 DPO 和最终交付的持续决策权。新路线由 [ADR-0012](decisions/0012-data-v2-to-dpo-staged-governance.md) 管理：旧 780 条混合分支封存，不运行其 confirmation/Defects4C，也不重复调参。

`data-v2-multisource-discovery-v1` 原计划按 2018～2025 的 32 个季度窗口执行 64 次 Issue Search，但 Job `96894`/`96902` 暴露出端点语义错误：`language`、`stars` 和 `archived` 是 Repository Search 条件，不是 Issue/PR Search 条件。Job `96894` 在 11 个 checkpoint 后遇到 HTTP 504；同提交续跑 `96902` 到 19/64 时主动取消。两者没有终态 manifest，不能支持容量结论；checkpoint 和日志只作为负面工程证据保留。

[ADR-0013](decisions/0013-correct-github-discovery-endpoint-semantics.md) 用版本化 v2 修正，不覆盖 v1：先通过合法的 Repository Search 固定 10×100 个 C++ 仓库候选，再按 Data-v2.1 哈希 split 与固定哈希排序选取 200 train + 40 validation 仓库，最后对每个仓库执行 `repo:… is:pr is:merged linked:issue` 的 repo-local PR Search。共 250 个 metadata-only 请求，间隔至少 7 秒并逐请求原子 checkpoint；输出仍只保留必要身份、时间、star 快照和响应哈希。容量门仍是有候选的实际 split 仓库 100/20、候选 PR 上界 1,000/100、cap 后样本上界 2,000/200，不因修正端点而降低。

Multi-SWE-RL revision `97776489...6f32` 的 9 个 C++ 仓库全部属于保留评测仓库，训练路线关闭。RunBugRun v2 固定 tag/revision `v2`/`bbac70b7...c938`，官方压缩 SQL 为 120,501,798 bytes，只作为不计仓库多样性的次级 problem-family 差量来源；本 discovery 配置不授权下载，必须在 GitHub 容量门后新增契约。所有 Data-v2 内容、GPU、训练和 DPO 在容量与污染门通过前保持关闭。

[ADR-0014](decisions/0014-evaluation-denylist-completeness-boundary.md) 进一步冻结当前评测身份：formal/confirmation 共 624 个互斥 CodeNet problem family、Defects4C 的 6 个仓库、Multi-SWE-bench C++ 的 9 个仓库、BugsCpp 24 个项目标识、LLVM APR 与 DebugBench/LeetCode-derived 域。只有 manifest/revision/集合哈希全部通过才允许取得候选内容；这不等于训练准入，取得内容后仍须 exact commit/content 去重、许可证和 buggy-fail/fixed-pass 重放。


### v2.1 容量终态与固定详情门

ADR-0016 的 casefold 修正由 Job `96939` 完成独立重跑：7,721 条 metadata 候选覆盖 train/validation 143/29 个仓库，容量门通过。该结果不能直接转成训练数据。ADR-0017 进一步固定 200 条 PR detail 分母，只验证小改动、显式同仓库 bug issue、仓库身份和 allowlist LICENSE；详情门至少 50 条通过后才允许取得固定 50 条的 commit/source/test 内容，并要求至少 10 条稳定 buggy-fail/fixed-pass。

Data-v2 单一新来源仍最多占 70%。GitHub evidence v2 的固定内容 Job `97292` 在静态执行门后为 0/20，当前 broad GitHub 路线关闭且不换样本。ADR-0022 因此激活 CommitPack revision `5eee2c84...e575` 的唯一固定分片 `c++-0001.jsonl`：先做 CPU 流式供给审计，禁止追加其余 364 个分片。CommitPack 最多贡献 `1,400/140`；与 legacy 安全增量 `260/131` 合并后 train 仍至少缺 340 条独立来源数据，所以单分片通过只会授权固定仓库执行 pilot，同时必须继续寻找另一条独立可执行来源。v1 Job `97473` 的 0/0 已确认为 `lang` 值大小写映射错误，不是容量结果；ADR-0023 的 v1.1 只接受实际精确值 `C++`，保持同一分片和全部硬门。RunBugRun v2 继续受 ADR-0015 限制，不作为本轮训练来源。

v1.1 Job `97486` 已在 25 秒内完成 `412 passed`。它读取 6,291 条，cap 前 253 条、cap 后 train 236 / validation 17；train 只满足新仓库数量，样本与 family 不足，validation 三项均不足。legacy 与该分片合计为 496/148，相对 2,000/200 容量探针仍缺 1,504/52。ADR-0024 因此关闭 CommitPack 路线：禁止第二分片、执行 pilot、Data-v2 构造和 GPU。下一步先对独立、已发布 buggy-fail/fixed-pass 证据的来源做有界桌面审计；只有来源身份、历史许可证、执行可复现性、评测污染和真实容量同时可行，才下载内容。若严格全量可执行的 2,000/200 被证明确实不可实现，必须以新 ADR 显式建立“静态监督层 + 可执行资格层”，再冻结新的训练配额和三 seed 方案。

## 第六阶段：detail v1 早停与 executable-evidence v2

固定 detail Job `96959` 在连续完成 144 个 train 候选后只有 8 条合格；train 剩余 16 条，因此记录和仓库乐观上限分别为 24/40、23/30。CPU-only Job `97150` 以 `391 passed` 独立重建这一反证，v1 正式关闭，未取得 patch/source，也未激活 ADR-0019。

136 个拒绝中有 58 条来自 58 个不同仓库，唯一失败条件是关联关闭 issue 没有 bug 标签。ADR-0021 因此建立新版本：保持同一 200 条固定分母和显式 closing issue/关闭状态，小改动与评测 denylist 不变；标签只用于分层，最终缺陷资格仍要求历史许可证和断网双资格稳定重放。先补完缺失的 PR/issue metadata；只有至少 50 条、train/validation 40/10 且仓库 30/8 通过，才固定 20 条（16/4）执行可行性分母。至少 4/20 通过后再运行不重叠的正式 50 条 pilot，避免直接在异构仓库上开展无效大规模构建。

## 第七阶段：独立来源可实现性裁决与 BeetleBox 固定元数据门

ADR-0024 关闭 CommitPack 后，项目对 BugsCpp、CppPerf、TrickyBugs 与 BeetleBox 做一次
官方 revision 和集群能力桌面审计。BugsCpp 保持为未来外部评测，CppPerf 因性能优化
目标错位只作未来消融，TrickyBugs 因竞赛提交逐条权利与单仓库域问题拒绝当前训练。
BeetleBox 以 `ac12f9cd...b4ef` 固定：数据卡声明 C++ native train/test 为
3,868/4,783，记录含 repo、issue/PR 和 before/after SHA，但没有源码、测试或许可。

ADR-0025 只授权下载两个固定 Parquet（合计 19,375,255 bytes），且读取列显式排除
title/body。CPU 审计检查 schema、C++ 数量、SHA/URL/文件有效性、重复、评测 denylist、
native split 仓库重叠和 repository 重分后的 40/20 cap。门槛 400/50 样本、15/4
仓库只决定是否进入历史许可证 pilot；通过不授权内容、训练或 GPU。真实结果出来前不
冻结新的 Data-v2 配额。

## 第八阶段：BeetleBox 终态与宽泛来源搜索停止线

最终 v1.2 Job `97508` 在 `417 passed` 后确认固定文件实际 `c++` 为 3,317/3,865；
过滤后有 3,534 条，但只来自 4 个非评测仓库。按 repository resplit 和 40/20 cap
得到 train 160 / validation 0，400/50 与 15/4 门全部失败。该结果关闭 BeetleBox，
不通过换 seed、native split 或提高 cap 补考。

ADR-0028 同时结束其他宽泛来源的同类搜索。2,000/200 容量探针保留为失败证据；
ADR-0012 的 SFT、三套评测、DPO 与交付门继续有效。下一步只对尚未读取 patch gold 的
BugsCpp 24 个项目做预注册 split、现有评测重叠和历史许可证审计，再以真实上界建立
“开发者修复监督层 + 本地执行层”的 Data-v2 新契约。新契约冻结前无 GPU。

## 第九阶段：BugsCpp 项目 split 与许可证上界

ADR-0029 在读取任何 patch blob 前，用 seed `20260908`、project ID 和公开 defect count
冻结 train 12/104、validation 3/41、held-out 7/39；cppcheck 30 因当前 Defects4C
重叠排除，example 1 因非真实项目排除。split 之后不因许可或 C++ 产量重分。

第一道作业只 partial clone/no checkout BugsCpp，并用 `git show` 读取 24 个 meta.json；
对 train/validation 最多请求 12 个 GitHub repository metadata endpoint，非 GitHub host
fail-closed，held-out 不请求许可证。当前 SPDX 只计算上界：train 至少 40 defects/4
projects、validation 至少 20/2 才允许下一道 patch-header + 历史许可证审计。它不读取
patch、源码、测试或许可证正文，也不申请 GPU。

## 第十阶段：停止来源搜索并构建分层 Data-v2

Job 97515 的 train 许可证上界通过、validation 仅 5 defects/1 project，低于冻结的
20/2，BugsCpp 路线按 ADR-0029 关闭。由此 GitHub、CommitPack、BeetleBox、BugsCpp
四条最后候选路线都已经得到终态，项目不再用换查询、分片或 split 搜索数据。

ADR-0030 用真实可得证据替换 2,000/200 容量探针：监督候选池固定为旧 formal
5,000/500 加安全增量 260/131；另从未进入 A4 偏好集的 train-only A4 候选中取得
64 个双资格 function family 作为独立开发执行集，并从所有监督 split 移除整个 family。
先完成 CPU 资格扩展和精确数据构建；Schema、token、sample/payload/family 隔离全部通过后，
才预注册三个从 Base 重训的 SFT seed。

## 第十一阶段：简历交付范围收敛

+项目负责人明确当前以 AI 应用开发投递为主，PatchAlign-Cpp 作为第二项目展示后训练、
+真实执行评测和工程治理能力。ADR-0031 因此停止分层 Data-v2 构建和三 seed SFT/DPO；
+上述研究门的失败事实不删除，也不包装为通过。

+当前只保留对简历叙事有直接价值的闭环：完成与 A4 偏好零交叉的独立执行开发集，审计
+现有 182 对，基于 M1-R2 训练单 seed DPO 主配置与一个 beta 对照，再对选中模型运行
+formal 500、confirmation 124 和 Defects4C 176 各一次。最后统一交付模型、模型卡、
+指标、失败分析、CLI demo 和复现入口。
