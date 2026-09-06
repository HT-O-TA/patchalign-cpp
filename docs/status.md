# 项目状态

最后核验：2026-09-06；Data-v2.1 契约已接受，metadata v1 零结果已诊断，v1.1 零结果已诊断，v1.2 分段续扫待运行

项目状态：**本轮按“完成 SFT 与探索性研究”收尾；A5/DPO 延后**。A3.4 readiness 仍未通过，124 条新确认集门禁失败使正式晋级保持阻断，账本为 `a4_ready=false`。负责人授权的 exploratory A4 已完成 264 条可执行数据、1,056 个候选、全量执行评分和 182 对偏好数据构造；run manifest 保持 `a5_started=false`，未提交任何 A5/DPO 作业。最终交付见 [`delivery/`](delivery/)，收尾决策见 [ADR-0009](decisions/0009-close-after-sft-and-exploratory-a4.md)。本轮交付口径保持不变；其后的 Data-v2 可行性研究已完成现有供给审计和新来源桌面准入审计，并已冻结分层 family 契约。GitHub metadata-only v1 Job `96406` 已完成但因 PR 级 `label:bug` 查询过窄得到 0 条；v1.1 已核验前 18 条并按治理规则全部拒绝；v1.2 将倒序按仓库去重续扫 12 条、待集群 CPU/网络实测。尚未下载补丁或源码、构造训练集或提交 GPU 训练。

本页是项目当前阶段和 Slurm 作业状态的唯一说明性入口。冻结配额、训练参数和质量阈值以[文档索引](README.md)列出的机器配置为准；单次运行的最终事实以集群 artifact manifest 为准。

## 阶段状态

| 阶段 | 状态 | 已形成的结果 |
|---|---|---|
| G0 | 完成 | Qwen2.5-Coder-7B 的 BF16 LoRA、NF4 QLoRA、adapter 保存和重载 smoke 通过 |
| A0 | 完成 | 任务契约、Schema、评分 fixture、质量门禁和治理边界冻结 |
| A1 | 完成 | 300/50 isolated-v2 数据 pilot，train/validation 多维零重叠 |
| A2 | 完成 | 50 function + 20 file-window 的 Bubblewrap 双资格回放和独立稳定重放通过 |
| A3.0 | 完成 | M0 Base 与 External 的 70 条 executable pilot 完成 |
| A3.1 | 完成 | `a3-scoring-v2` 冻结并完成不可变预测重评分 |
| A3.2 | 完成 | BF16 LoRA/NF4 QLoRA pilot 完成；按预注册资源平局规则选择 NF4 QLoRA |
| A3.3 | 内部门禁未通过 | 正式训练、500 条推理、评分和比较均完成；主提升通过，但 timeout 退化超过上限 0.1pp |
| A3.4 | 完成；最终 readiness 未通过 | Defects4C 176/176 评分完成，M0/M1-R2 均为 1/176；确认集失败使 `a4_ready=false` |
| A4 | 负责人授权 exploratory 完成 | 1,056 个候选全量评分；123 Pass、11 timeout；形成 182 对内部偏好数据 |
| 收尾后泛化诊断 | 完成 | Job `96197` 对 M1-R2 完成六项只读诊断；结论为尚未证明语义泛化 |
| Data-v2 供给审计 | 完成；现有来源不足 | CPU-only Job `96256` 仅找到 260 train + 131 validation 可用增量，不能冻结训练集 |
| Data-v2 来源准入 | 契约已接受；metadata v1.2 待运行 | v1 `96406` 查询为 0；v1.1 `96412` 检查 18 条后 0 条准入；v1.2 将续扫 12 个去重仓库；未下载补丁、未用 GPU |
| A5 | 延后、未启动 | 负责人决定本轮在 SFT + exploratory A4 收尾；`a5_started=false` |

## A3.3 当前有效链

| 阶段 | Job | 状态 | 说明 |
|---|---:|---|---|
| M0 正式推理 | 94338 | COMPLETED 0:0 | 500/500 生成成功，3/3 确定性 probe 稳定 |
| M0 scoring v2 | 94339 | COMPLETED 0:0 | 500 条均为 `parse_failed`；这是模型输出协议结果，不是流水线失败 |
| 正式 NF4 QLoRA SFT | 94340 | COMPLETED 0:0 | 3 epochs，最佳 checkpoint 为 epoch 2 / step 1,250 |
| M1 正式推理 | 94341 | COMPLETED 0:0 | 500/500 生成成功，499/500 为 strict diff，3/3 probe 稳定 |
| M1 scoring v2 | 94342 | COMPLETED 0:0 | Pass 15/500；function 12/400，file_window 3/100 |
| M1 对 M0 比较 | 94343 | COMPLETED 0:0 | 比较器正常完成；`internal_gate_passed=false` |

### A3.3 正式结果

- 94340 用时 `02:21:23`；1,875 optimizer steps，最佳 validation loss 为 `0.1280414615`（epoch 2 / step 1,250）。
- M1 parse/apply/compile 为 499/391/373，最终 Pass 为 15/500；function Pass 从 M0 的 0/400 提升为 12/400（+3pp），paired bootstrap 95% 区间为 +1.5pp～+4.75pp，主提升门通过。
- regression failure 为 5/500（+1.0pp，等于上限）；timeout 为 3/500（+0.6pp），超过冻结的 +0.5pp 上限，因此内部门禁未通过。
- 三个 timeout 均由 M1 补丁引入。CPU-only 诊断 Job 94493 在同一 Bubblewrap 边界下复现：buggy/fixed 均在 0.04 秒内结束，M1 均在 3.00 秒被杀死。逐例分析见 [A3.3 论文材料](evidence/a3_3_pipeline_findings.md)。

## 已冻结的正式数据身份

- preflight Job：94337，Git commit `b9aa00248d4264eca0f75c378b004f462ddea9a6`。
- train/validation：5,000/500；holdout：400 function + 100 file-window。
- formal data lock SHA256：`f37eef03ce0a96ad1fa14622b8b7ef6f30c3f6bcc8dad85addbb1e4c53d12a12`。
- 正式配置 SHA256：`358894a6e8e3b54a1b71ea1884848296c8af6381063cb44fb1a0f70483f4abb4`。
- 完整数据分布、路径和训练参数不在本页重复维护，分别见 [`a3_formal_v1.json`](../configs/data/a3_formal_v1.json) 和 [`a3_sft_formal_v1.json`](../configs/training/a3_sft_formal_v1.json)。

## 当前边界与收尾决策

- A3.3 的 M1 主修复率提升成立，但 timeout 超限，历史门禁结论保持未通过。
- A3.4 的旧 500 条内部门禁通过，但未见确认集门禁失败；M1-R2 没有取得正式 A4 晋级资格。
- Defects4C 已按原协议完成 176 条固定分母成对评测；M0/M1-R2 均为 1/176 Pass、0 timeout，外部门禁通过，但没有最终 Pass 提升。
- pre-A4 readiness 已绑定内部、确认和外部三项 artifact；确认集是唯一 blocker，因此该账本保持 `a4_ready=false`、`a4_started=false`。
- ADR-0006 允许在该失败账本之后以 `owner_authorized_exploratory` 模式进入 A4；该授权不改变 A3.4 门禁结论。
- ADR-0009 记录负责人在 A4 质量结果完成后决定本轮不启动 A5/DPO，并以最终报告、模型卡和集群 artifact 索引交付。

## 收尾后泛化失败诊断

CPU-only Job `96197` 在提交 `6f1b453` 上完成 6 个专项测试和六项只读诊断。正式结果见 [M1-R2 泛化失败诊断](evidence/generalization_failure_diagnostic.md)。

- Formal 500 与 confirmation 124 使用同一 prompt 版本，任务层级与测试覆盖近似；确认集主要在全新 problem family、source shard 集中度、代码/prompt 长度和 multi-line 比例上发生偏移。
- Confirmation 的 M1-R2 漏斗为 parse/apply/build/public/hidden/final = `123/104/103/6/3/0`；97 条在 public 阶段终止，主瓶颈是修复语义而非 diff 格式。
- 3 个 regression 和 4 个 timeout case 已全部逐例审计；即使乐观移除 4 个 timeout case，也不能解释 `0/124`。
- Formal 的 14 个成功中 13 个代码少于 100 行、7 个与参考 fixed source 完全一致；成功偏向短输入和 single-line，但不集中于单一任务层级或 source shard。
- Defects4C 唯一成功来自 LLVM，且 LLVM 占外部集 `139/176`；它证明一次端到端成功，不能证明跨项目代表性。
- 综合结论为 `protocol_learning_without_demonstrated_semantic_generalization`：协议、apply 和 build 能力跨集合改善，但最终正确性未稳定迁移。

正式产物位于 `artifacts/a3/diagnostics/generalization-v1/`；summary/case-audit/run-manifest SHA256 分别为 `bbca0502...5eba`、`c7e61a4e...f721`、`1587a8b5...7243`。本诊断不改变既有 readiness 和收尾决策。

## Data-v2 供给审计

CPU-only Job `96256` 在提交 `3b1fa42` 上完成，5 项专项测试通过；结果文档同步后，全量回归 Job `96263` 为 `260 passed in 14.31s`；扫描 CommitPackFT 4,992 条和 RunBugRun 237,516 条原始记录，并完成所有 shard、冻结评测 manifest 和模型 tokenizer 身份校验。

- 在 v1+增量每 family 最多 2 条、formal/confirmation family 排除和 Defects4C 项目别名排除后，只剩 `260 train + 131 validation`。
- Train 可用增量中仅 20 条代码不少于 100 行、14 条 prompt 不少于 1,024 tokens、20 条结构性修改；validation 对应为 4、4、12。
- 精确 tokenizer 拒绝为 0，短缺不是 4,096-token 门槛造成，而是现有 family 容量、评测隔离和原始来源组成共同决定。
- Train 剩余 260 条全部为 file-window，不能在保持“函数级为主”的同时直接并入；validation 仍有 74 function + 57 file-window。
- 暂定 2,000/200 增量的同步门槛在两个 split 均失败，因此没有生成训练 JSONL、没有启动 SFT，也没有改写现有评测集。

正式结果位于 `artifacts/data-v2/supply-audit-v1/`；candidate-audit/summary/run-manifest SHA256 分别为 `cbe5f2fa...8e96`、`a7f117a9...b753`、`cc34dec8...8cf9`。下一步是引入经过许可证、family 和评测污染审计的新 C++ 修复来源，见 [Data-v2 泛化增强计划](data_v2_plan.md)。

## Data-v2 新来源准入

2026-09-06 已完成只读官方资料审计，并用 `configs/data/data_v2_source_admission_v1.json` 固化 9 个候选：自建 GitHub issue/PR 关联 C++ 修复池、Multi-SWE-RL、RunBugRun v2 进入元数据 pilot；Multi-SWE-bench C++、BugsCpp、LLVM APR Benchmark、DebugBench C++ 作为评测保留；FixEval 与 PatchEval-Verified 因当前发布无 C++ 而拒绝。

本轮没有下载 JSONL、SQLite、仓库源码或容器，`content_downloaded=false`、`training_data_frozen=false`、`gpu_job_authorized=false`。负责人已接受 [ADR-0010](decisions/0010-data-v2-hierarchical-family-contract.md)：仓库级 `repository_split_group` 负责隔离，细粒度 `sampling_family` 仍维持最多 2 条，并新增 train/validation 每仓库 40/20 条上限以及 100/20 个新仓库、1,000/100 个新 sampling family 最低目标。当前只授权 GitHub metadata-only pilot。v1 Job `96406` 为 0/15 仓库，诊断确认 PR 级 `label:bug` 是零结果条件；v1.1 保留 15 仓库目标、检查 18 个 PR 后仍为 0；拒绝由 6 个文件数越界、3 个行数越界、7 个无显式同仓库 issue、1 个 stars 不足和 1 个许可证不在 allowlist 组成。48 条搜索结果实际覆盖 34 个仓库，故 v1.2 改为倒序、详情前按仓库去重、最多续扫 12 个仓库，最坏 36 次 core 请求。内容下载、测试重放、Data-v2 冻结和 GPU 仍关闭。完整证据见 [Data-v2 新来源准入与污染审计](evidence/data_v2_source_admission.md)。

CPU-only 专项 Job `96326` 在提交 `b93084c` 上以 `5 passed in 0.03s` 完成；全量回归 Job `96328` 为 `265 passed in 13.50s`。首次 one-off 回归 Job `96327` 因 `sbatch --wrap` 的 `/bin/sh` 不支持 Bash `pipefail` 而在进入 pytest 前失败，已由 POSIX 兼容命令替代，不计为测试失败。

## A4 最终状态

- 数据 Job `95586` 以 `COMPLETED 0:0` 用时 `01:28:41`，评估 480 个候选、273 个双资格通过，冻结 256 function + 8 file-window；source manifest SHA256 为 `8cba1ec5...5095495`。
- 单 GPU 生成 Job `95587` 以 `COMPLETED 0:0` 用时 `02:58:19`，完成 1,056/1,056 候选；候选、summary、manifest SHA256 为 `ca497dbd...f0c67`、`95631a06...07b2`、`b0a001c3...def7`。峰值显存约 6.56 GB。
- ADR-0008 冻结执行阶段排序：同一 case 内按 generation→parse→policy→apply→build→public→hidden→regression→sanitizer→success 从差到好；同终态仅以非 timeout 优于 timeout。每例最多一对，最高/最低档相同则不配对。
- 偏好训练文件只含 prompt 与 chosen/rejected 原始 completion；执行终态和排序理由进入独立 audit，不向训练输入泄漏 gold、fixed、测试或执行反馈。
- CPU-only preflight `95651`、替换评分数组 `95670`、聚合 `95671` 均完成：1,056 个候选 parse/apply/compile/Pass 为 1,055/805/780/123，regression failure 4、timeout 11。
- 77/264 个 case 至少有一个 success；形成 182 对偏好数据（function 175、file-window 7），其中 75 对 chosen 为 success、7 对只由 timeout tiebreak 区分；82 个 case 无严格差异而不配对。
- 原数组 `95652` 与未运行聚合 `95653` 因 `gpu16` 零日志/零 checkpoint 被停止；排除该节点后替换链正常完成，未删除案例或改变评分协议。
- scores/preferences/summary/manifest SHA256 为 `c218cd58...cee2`、`5e6b56e4...78bf`、`302e7a9a...fc8`、`03c61f0e...7cbe`。负责人已审阅并决定本轮延后 A5；这些文件作为内部探索产物交付。

## A3.4 当前状态

- A3.4 恢复起点审计曾确认三端位于 `cbfb752d85aa2ad3c14f8cfde760b6c21494f31b`，并核对 A3.3 数据锁、M0 预测与评分、正式比较和 timeout 复现哈希；该提交仅是恢复基线，不是当前 HEAD。
- 恢复起点当时没有 PatchAlign 排队或运行作业；管理节点直接 `squeue` 的权限限制不影响后续通过 `sacct` 和 artifact 核验 Job `94521`～`94538`。
- 修正轮次正式命名为 `A3.4 / SFT-R2`，候选为 `M1-R2`；机器配置和方法见 [A3.4 协议](a3_4_sft_r2.md)。
- 静态选择器只消费冻结 A3.3 SFT train/validation；CPU-only Job `94521` 以 `COMPLETED 0:0` 在 2 秒内完成 5 项测试和 1,200/117 集群重建。train/validation SHA256 为 `6eeab690...678cc`、`878abb76...4b73`，selection manifest 为 `7492a373...30ac`。
- preflight Job `94523` 以 `COMPLETED 0:0` 在 28 秒内完成 `145 passed`、数据/adapter/token/holdout 身份校验；报告 SHA256 为 `9da6ed41...ce3b`。
- 单 GPU 训练 Job `94524` 以 `COMPLETED 0:0` 结束，用时 15 分 15 秒；完成 150 optimizer steps，最佳 checkpoint 为 epoch 1/step 150，adapter SHA256 为 `8437acca...425a`。原 500 条 reference validation loss 从 `0.12804146` 变为 `0.13105401`（+`0.00301254`）；该轻微上升只作为遗忘风险信号，最终判断必须等待固定 500 条真实推理与评分。运行代码提交为 `8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c`；该次运行时 A4 尚未启动。
- 固定推理 preflight Job `94537` 完成 `154 passed` 和 prompt 逐字节身份核验。单 GPU Job `94538` 以 `COMPLETED 0:0` 结束，用时 `01:13:49`；500/500 状态为 `ok`，499/500 为 strict diff，3/3 确定性 probe 稳定。predictions/run manifest SHA256 分别为 `c5fe4e6d...7bb6a`、`88abe605...3878`。
- CPU-only scoring v2 Job `94558` 以 `COMPLETED 0:0` 结束，用时 `00:41:02`。M1-R2 parse/apply/compile 为 499/412/392，最终 Pass 为 14/500；function 为 11/400，file_window 为 3/100，regression failure 为 3/500，timeout 为 2/500。
- 相对 A3.3 M1，apply/compile 分别增加 21/19，regression failure 从 5 降到 3，timeout 从 3 降到 2，但总 Pass 从 15 降到 14、function Pass 从 12 降到 11。原 3 个 timeout 中 2 个消失、1 个保留，同时新增 1 个 timeout；因此不能把总数下降表述为三个风险样本均已修复。
- scores、summary、manifest SHA256 分别为 `f05b54a...50b8`、`23ee63ff...1c07`、`b6d72c85...bf2`，均已与 manifest 交叉核验。
- CPU-only 正式比较 Job `94580` 完成。M0→M1-R2 的 function 提升为 `+2.75pp`，paired bootstrap 95% 区间为 `+1.25pp～+4.5pp`；parse/apply/compile、regression、timeout、file-window 和 validity 均满足冻结上限，因此 `internal_gate_passed=true`。promotion artifact SHA256 为 `5425feb2...1027`；完整门禁当时只因 Defects4C 分母为 0 而保持关闭。
- 新确认集冻结为 124 条（100 function + 24 file-window），manifest/prompts SHA256 分别为 `7adf...917`、`cf141...58f`。M0 与 M1-R2 均为 0/124 Pass；R2 相对 M0 的 parse/apply/compile 分别增加 `+99.19pp/+83.87pp/+83.06pp`，但 regression 增加 `+2.42pp`、timeout 增加 `+3.23pp`，确认集门禁失败。比较 Job `94605` 的 artifact SHA256 为 `faca13cc...e6094`。
- Defects4C 外部管线使用官方源提交 `aecc2cf...`，排除与训练来源 family 重叠的 `bblanchon___ArduinoJson` 和 `znc___znc` 后得到 203 个 C++ function 候选。源码准备 Job `94642` 完成 203/203；资格数组 `94643` 完成 203/203，176 条合格、27 条因 fixed 官方测试未通过而拒绝，0 timeout、0 infrastructure error。旧聚合 Job `94644` 暴露官方 prompt 双模板兼容问题后失败；提交 `3ea8a5f` 增加精确双后缀白名单并通过 234 项测试和 176 条真实 prompt 遍历，重提 Job `94925` 成功冻结 176 条。manifest/prompts SHA256 为 `0728c602...28631`、`b23663fc...5484f`；最终 LLVM 占 139/176，分布偏斜必须披露。正式 preflight Job `94927` 以 `COMPLETED 0:0` 通过 241 项测试和冻结身份核验；M0 Job `94928`、M1-R2 Job `94929` 分别用时 `00:40:40`、`00:38:08`，均以 `COMPLETED 0:0` 结束并冻结 176/176 预测。CPU 评分数组 `94930` 释放后，所有进入 rootfs runner 的样本均在约 1 秒内因未返回结果 JSON 而失败；仅 4 条在 parse/policy 阶段提前终止的样本写出有效检查点。为避免继续消耗资源，原数组及聚合 `94931`、readiness `94932` 已停止；预测和 4 个有效检查点保留。诊断 Job `95140` 证明 rootfs 内部缺少可见的 `/patchalign` Python 导入路径；提交 `bff21bc` 显式设置 `/patchalign/src:/patchalign` 并通过专项 11 项、全量 243 项测试。单样本 Job `95141` 用时 `00:05:17` 完成真实 apply/build 链；替换评分数组 `95144` 完成 176/176，聚合 `95150` 以 `COMPLETED 0:0` 结束。M0 parse/apply/build/Pass 为 94/24/17/1，M1-R2 为 174/72/55/1，双方 timeout 均为 0；paired bootstrap 95% 区间为 `-1.7045pp～+1.7045pp`，外部门禁通过。comparison SHA256 为 `d8a1c14e...75f67e`。readiness Job `95151` 以 `COMPLETED 0:0` 结束，账本 SHA256 为 `c2a920bc...6c0fd0`，观测门禁为 internal=true、confirmation=false、external=true，最终 `a4_ready=false`，唯一 blocker 为 `supplementary_confirmation_passed`。

## 后续执行清单

1. **已完成**：集群 CPU-only 重建 R2 数据并核对计数、标签分布、输出 SHA256 和 selection manifest（Job `94521`）。
2. **已完成**：实现版本化 R2 训练/恢复入口与 fail-closed preflight；集群全量测试 `145 passed`，preflight Job `94523` 通过。
3. **已完成**：单 GPU SFT-R2 Job `94524` 完成 150/150 optimizer steps并固化最佳 adapter。
4. **已完成**：CPU preflight Job `94537` 和单 GPU 固定推理 Job `94538` 均完成。
5. **已完成**：CPU-only scoring v2 Job `94558` 完成固定 500 条真实执行评分，产物哈希已核验。
6. **已完成**：Job `94580` 执行 M0→M1-R2 promotion comparison 与 M1→M1-R2 diagnostic comparison；内部门禁通过。
7. **已完成**：冻结并评测未查看的 124 条新确认集；Job `94605` 判定确认集门禁失败。
8. **已完成**：203 个 Defects4C 候选完成可恢复源码准备和离线双资格筛选，冻结 176 条外部成对评测集。
9. **已完成**：替换 CPU 评分数组 `95144` 完成 176/176，聚合 `95150` 固化外部 M0/M1-R2 均为 1/176，外部门禁通过。
10. **已完成**：readiness Job `95151` 忠实记录确认集失败、`a4_ready=false` 和唯一 blocker，三项输入哈希已交叉核验。
11. **已完成**：Job `95586` 冻结 264 条可执行 train-only 数据；Job `95587` 完成 1,056/1,056 候选生成，1,055 条为 strict diff，seed replay 稳定。
12. **已完成**：提交 `d296833` 冻结 ADR-0008、偏好对 Schema 和 A4 scoring v1；preflight `95651`、替换评分数组 `95670` 和聚合 `95671` 完成 1,056 条评分与 182 对偏好数据。
13. **已决策**：负责人审阅 A4 的规模、信号强度、timeout 风险和 train-only 泛化边界后，决定本轮在 SFT + exploratory A4 收尾，A5/DPO 延后。
14. **已完成**：建立最终技术报告、M1-R2 模型卡和交付说明；大型 artifact 保持集群本地化，不作公开发布。
