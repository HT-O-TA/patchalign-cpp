# 项目状态

最后核验：2026-09-08T18:31Z；A5 Defects4C 替换评分已有 96/176 个有效 checkpoint

项目状态：**简历交付版 DPO 已训练并完成独立开发集选型，正在一次性最终评测**。175 对经审计偏好已完成 beta=0.1/0.3 两组真实训练；64 条独立 executable dev 按冻结规则选择 beta=0.3。formal 500、confirmation 124、Defects4C 176 只评该胜者，随后自动执行评分、门禁、失败分析和交付整理。RLVR/GRPO 不属于本轮。

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
| Data-v2 来源准入 | metadata pilot 完成；当前查询容量失败 | v1/v1.1/v1.2 均 0 条准入；冻结查询仅 34 个仓库，小于 train 最低 100；未下载补丁 |
| Data-v2 exploratory replay | formal 500 评分完成；formal 门槛未通过 | Job `96780` 得到 13/500 Pass、1 timeout；Pass 低于预注册下限 14，新 adapter 的 confirmation/Defects4C 尚未运行 |
| Data-v2 研究扩张 | 结束并保留负结果 | 新来源和 2,000/200 容量探针均已关闭；ADR-0031 不再构建或训练 Data-v2 |
| A5 简历交付版 DPO | 推理与 C++ 评分完成；Defects4C 替换评分运行中 | beta=0.3 formal Pass 19/500、confirmation 0/124；array `97901` 已形成 96/176 个有效 checkpoint，仍按 `%8` 并发推进 |

## 当前执行点：A5 DPO 一次性最终评测

- 偏好审计 Job `97540`：182 对源偏好排除 7 对 timeout-only，冻结 175 对，其中 chosen full-success 75 对。
- DPO CPU 预检 `97557`、GPU smoke `97558` 和训练 array `97559` 均完成；beta=0.1/0.3 各训练 2 epochs、44 steps。
- 独立 dev 预检 `97566`、三路推理 `97567`、三路评分 `97570`、自动选择 `97571` 均完成。三者 Pass 均为 5/64；beta=0.3 的 apply/build 为 57/57，高于 baseline 53/52 且无 timeout/regression 退化，因此被选中。
- 最终预检 `97583` 以 `434 passed` 完成，三套固定数据、prompt、基线、adapter、环境和评分器哈希全部通过。
- 原推理 array `97586` 在 16m43s 时被共享账号 UID 1039 同秒主动取消，非代码、OOM 或时限失败；formal/confirmation/Defects4C 已原子保存 118/112/84 条预测，下游 `97589`～`97591` 同时被取消。
- 恢复 array `97608` 已完成三套固定分母；全部 generation status 为 `ok`，3/3 probe 稳定。C++ 评分 `97611` 也已完成：formal parse/apply/compile/Pass 为 500/437/424/19，function 17/400、file-window 2/100、regression 5、timeout 5；confirmation 为 0/124 Pass、regression 3、timeout 2。
- 原 Defects4C 评分 `97614` 暴露 rootfs runner 的 role 白名单只含 `m0/m1_r2`：8 个 parse/policy 终止案例保存有效 checkpoint，其余 168 个在执行前秒退。恢复提交 `fbe0717be11ca55648cd4d9d69c22c0fa707471c` 只加入 `dpo_beta03` 并以 `435 passed` 验收。替换评分 `97901` 截至 18:31Z 已形成 96/176 个有效 checkpoint，已列完成项均为 `ExitCode 0:0`，另有 8 个并发 task 运行、101～175 受 `%8` 上限排队；聚合 `97902` 正确等待全数组完成。详见 [恢复证据](evidence/a5_dpo_final_recovery.md)。
- 聚合 `97902` 成功后，CPU Job `97977` 将在严格核验恢复分支、commit、工作树和聚合产物后，把集群快进到固定 main 提交 `616c9d4a55dcd40b4818a9fb07c185291a6b3271`；单 GPU CLI smoke Job `97978` 已依赖其排队。两者不会启动新训练。
- Formal timeout 门禁已不可逆失败，交付推荐确定为 M1-R2；Defects4C 只补全外部画像与其他 gate reason。

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

本轮没有下载 JSONL、SQLite、仓库源码或容器，`content_downloaded=false`、`training_data_frozen=false`、`gpu_job_authorized=false`。负责人已接受 [ADR-0010](decisions/0010-data-v2-hierarchical-family-contract.md)：仓库级 `repository_split_group` 负责隔离，细粒度 `sampling_family` 仍维持最多 2 条，并新增 train/validation 每仓库 40/20 条上限以及 100/20 个新仓库、1,000/100 个新 sampling family 最低目标。当前只授权 GitHub metadata-only pilot。v1 Job `96406` 为 0/15 仓库，诊断确认 PR 级 `label:bug` 是零结果条件；v1.1 保留 15 仓库目标、检查 18 个 PR 后仍为 0；拒绝由 6 个文件数越界、3 个行数越界、7 个无显式同仓库 issue、1 个 stars 不足和 1 个许可证不在 allowlist 组成。48 条搜索结果实际覆盖 34 个仓库；v1.2 Job `96417` 倒序、详情前按仓库去重检查 12 个仓库后仍为 0，拒绝为文件数 4、行数 1、fork 1、stars 2、无显式 issue 3、许可证 1。由于查询全集的 34 个仓库已小于 train 的 100 个新仓库下限，当前查询容量门直接失败，未继续消耗 API 扫描中段。内容下载、测试重放、Data-v2 冻结和 GPU 仍关闭。完整证据见 [GitHub metadata pilot 结果](evidence/data_v2_github_metadata_pilot.md)。

CPU-only 专项 Job `96326` 在提交 `b93084c` 上以 `5 passed in 0.03s` 完成；来源审计全量回归 Job `96328` 为 `265 passed in 13.50s`。Data-v2.1 最终全仓回归 Job `96419` 为 `276 passed in 13.27s`。首次 one-off 回归 Job `96327` 因 `sbatch --wrap` 的 `/bin/sh` 不支持 Bash `pipefail` 而在进入 pytest 前失败，已由 POSIX 兼容命令替代，不计为测试失败。

RunBugRun v2 的来源边界由 ADR-0015 进一步关闭：官方数据/代码仓库许可证不能替代逐条竞赛提交授权；在逐记录 provenance、训练/再分发授权与 opt-out 排除无法证明前，只允许不含程序/测试正文的 schema 和规模元数据研究，不允许完整 release 下载、Data-v2/SFT/DPO 训练或再分发。该工程决定不是法律意见，也不回写既有实验事实。

## Data-v2 exploratory replay

CPU-only Job `96423` 在提交 `080b82f` 上以 `COMPLETED 0:0` 用时 57 秒完成 9 项专项测试和确定性数据构建。输出固定为 train 780（416 function + 364 file-window；520 replay + 260 safe increment）与 focused validation 131（74 function + 57 file-window）；sample、payload、repo-family 三类交叉均为 0，未读取评测 gold。train/validation/selection-manifest SHA256 分别为 `009abf88...25ae1`、`fb0cf553...44d4`、`5852bf9b...83c`。

该数据只服务 ADR-0011 的单 seed、98-step、M1-R2 adapter continuation 消融，不满足 Data-v2.1 正式容量门，也不启动 A5。CPU preflight Job `96426` 在提交 `53329624` 上用时 23 秒，以 `287 passed` 完成全仓测试，并验证数据、token、模型、adapter、环境和 Git 身份；报告 SHA256 为 `4a6f4416...79f3`。

单 GPU Job `96427` 随后在 `gpu06` 以 `COMPLETED 0:0` 用时 `00:11:41` 完成 780 micro-steps / 98 optimizer steps，无 OOM、NaN 或超时，峰值 allocated 显存为 14,453,680,640 bytes（约 13.46 GiB）。最佳 checkpoint 为 epoch 1 / step 98，adapter SHA256 为 `d01dc411...21323`。formal SFT validation 的 report-only loss 从 M1-R2 的 `0.1310540061` 降到 `0.1293390337`（`-0.0017149724`），focused validation loss 为 `0.2120499949`。这只说明监督损失与遗忘风险信号没有恶化，不能替代 formal 500、confirmation 124 和 Defects4C 176 的真实执行评分。training summary/manifest SHA256 为 `23df309c...ac5a`、`3feb8f6c...60a8b`。

独立的 `data-v2-exploratory-formal-inference-v0.1` 精确锁定新 adapter 及训练 artifact，继续使用原 formal 500、原 prompt 字节、greedy Pass@1 和 4,096/512 token 上限，不覆盖 M1-R2 推理目录。CPU preflight Job `96658` 以 `298 passed` 完成；单 GPU Job `96662` 在一次无预测节点重排后于 `gpu04` 以 `COMPLETED 0:0` 用时 `01:15:27` 完成 500/500。全部 generation status 为 ok，498/500 为 strict diff，3/3 deterministic probe 稳定；predictions/summary/run-manifest SHA256 为 `4adcb5b7...4eabe`、`2141632b...e22dc`、`0d5bd0d1...2546b`。CPU-only scoring v2 Job `96780` 在 `gpu10` 以 `COMPLETED 0:0` 用时 `00:27:42` 完成；全仓 `310 passed`，artifact preflight 通过。parse/apply/compile/Pass 为 `498/412/389/13`，function `10/400`、file-window `3/100`，regression failure `8/500`、timeout `1/500`。相对 M1-R2，apply 不变、compile -3、public-test success +5、Pass -1，成功样本新增 3 条、丢失 4 条、保持 10 条；timeout 从 2 降到 1，但 regression failure 从 3 增到 8。formal 预注册要求 Pass 至少 14、timeout 至多 2，因此只满足 timeout，不满足 Pass。scores/summary/manifest SHA256 分别为 `9150c6fb...0bfb`、`1a8bc423...ddd3`、`9cfd0160...7cf`。该结果不能晋级；配置未定义自动 early-stop，新 adapter 的 confirmation/Defects4C 若继续只具有诊断价值，并需单独权衡 GPU 成本。

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

## GitHub detail v1 早停终态

Job `96959` 在固定顺序的前 144 个 train 候选中仅得到 8 条合格记录。剩余 16 条即使全部成功，train 也最多 24 条；可覆盖仓库最多 23 个，分别低于 40 条和 30 仓库门。作业在 `2026-09-07T17:31:47Z` 主动取消，检查点保留。

CPU-only Job `97150` 在提交 `a169fdf` 上用时 35 秒，完成 `391 passed`，并精确核对源 Job 的 Slurm 终态、源配置/脚本/选择哈希和 145/81/20 个 pull/issue/license checkpoint。最终连续完成前缀为 144：8 合格、136 拒绝、1 中断、55 未开始；第 145 条因只有 pull 而无 issue checkpoint 记为中断。拒绝主项为 issue 无 bug 标签 58、无显式 closing issue 34、文件数越界 20、许可证不在 allowlist 12、行数越界 9。

该结果关闭 ADR-0017 v1，不激活 ADR-0019，也不授权内容或训练。ADR-0021 的新路线保持固定 200 条和全部执行硬门，只把 bug 标签改为分层字段；先完成缺失 metadata，过 40/10、30/8 门后才固定 20 条执行可行性分母。完整证据见 [GitHub detail v1 早停审计](evidence/data_v2_github_detail_early_stop.md)。

## GitHub executable-evidence metadata v2 终态

CPU/网络 Job `97210` 在提交 `76161d5` 上以 `COMPLETED 0:0` 用时 `01:24:08`，完整回归 `395 passed in 84.39s`。它逐哈希复用 v1 的 pull/issue checkpoint，只新增 81 次无 token API 请求，无重试；没有读取或保存 patch/source、LICENSE 内容、raw response、文本或用户身份。

固定 200 条中得到 104 个 metadata 候选：train/validation 为 86/18，仓库为 81/14；有 bug 标签 31、无标签 73。总数 50、split 40/10 和仓库 30/8 的全部门槛通过。candidate/summary/run manifest SHA256 分别为 `a7f67ef2...f0eb`、`9ef07936...e484`、`4e457e99...a0df`。

本结果只授权 ADR-0021 的固定 20 条执行可行性 pilot。选择固定为 train 8 有标签 + 8 无标签、validation 2 + 2，20 个仓库互异；clone、许可证、构建或测试失败后不得替换。至少 4/20 严格通过才扩大正式 50 条。

## 固定 20 条执行可行性分母

CPU-only Job `97278` 在提交 `b4383db` 上以 `COMPLETED 0:0` 用时 26 秒，完整回归 `398 passed`。固定分母为 train 16、validation 4；两个 split 内有/无 bug 标签分别为 8/8 和 2/2，20 条来自 20 个不同仓库且不允许失败替换。selected/summary/run manifest SHA256 分别为 `92925952...c7227`、`f8806391...ea7e`、`a9708124...0def`。

内容阶段先顺序取得固定 PR commit 列表、files 投影、merge commit、parent/fixed 历史许可证及两个 Git 对象，只保存 API response 哈希，仓库内容留在 `/mingli01/data`。静态门要求本地 parent→fixed diff 与 PR files 完全一致、无 rename/copy/binary/mode 变化、恰好一个既有 UTF-8 生产 C++ 目标、至少一个测试路径、根 CMake 存在且无不安全的测试目录外 build-manifest 改动。若静态执行候选少于 4 条，直接在编译前关闭路线。
