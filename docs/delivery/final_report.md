# PatchAlign-Cpp 最终技术报告

报告日期：2026-09-09

交付口径：面向简历展示的可验证 AI 应用与后训练闭环；RLVR/GRPO 不属于本轮

## 1. 执行摘要

PatchAlign-Cpp 是一个面向局部 C++ 缺陷修复的可验证 AI 系统。输入是结构化的 buggy code、任务级别和公开失败示例，模型只输出一个 unified diff；系统对输出执行严格格式与路径策略校验，再在 rootless、禁网、限时的 Bubblewrap 中依次完成 `git apply --recount`、编译、公开测试、隐藏测试、回归测试和明确适用时的 sanitizer。最终质量由真实执行决定，而不是由 loss、文本相似度或“能编译”替代。

项目完成了 Qwen2.5-Coder-7B Base 的环境验证、Schema 与评分闭环、隔离数据构建、NF4 QLoRA SFT、独立确认与 Defects4C 外部评测、泛化失败诊断、可执行偏好构造、两组 beta 的真实 DPO、独立开发集选型和一次性正式评测。应用侧提供结构化 CLI、严格 diff 校验、模型与补丁 provenance metadata、Slurm 编排、原子恢复和 hash-complete 交付索引。

最终默认模型为 **M1-R2**。DPO-beta03 在 formal 500 上将 Pass 从 14 提升到 19，并明显改善 apply/compile；但 timeout 从 2 增加到 5，`+0.6pp` 超过预注册的 `+0.5pp` 上限，触发不可被其他指标抵消的安全否决。Defects4C 上候选将 apply/compile 从 72/55 提高到 84/65，但双方仍同为 1/176 Pass。该决策保留 DPO 的真实正收益，也不隐藏无限循环、递归和外部泛化不足。

## 2. 项目目标与范围

核心问题分成两层：

1. 工程层：能否把开放权重代码模型接入一个可约束、可隔离执行、可恢复、可追溯的补丁生成服务；
2. 后训练层：在固定数据、prompt、生成预算和评分协议下，SFT 与真实执行偏好优化能否提高端到端修复成功率，同时不突破预注册安全退化上限。

本轮以 function-level 为主，并兼容固定 file-window 上下文。只允许修改 `main.cpp`，不包含仓库自主探索、联网搜索、长程 Agent、多文件修改、生产自动合并或自动部署。项目定位优先服务 AI 应用开发求职，同时保留完整后训练证据作为能力补充。

## 3. 系统架构

```text
raw defect/test data
  → Schema normalization
  → family/split isolation + immutable manifests
  → NF4 QLoRA SFT (M1/M1-R2)
  → train-only multi-candidate generation
  → Bubblewrap execution ranking
  → audited chosen/rejected pairs
  → DPO beta ablation + independent dev selection
  → one selected candidate on frozen formal/confirmation/Defects4C
  → paired gates + failure analysis
  → model cards + CLI smoke + delivery manifest
```

模型生成与不可信代码执行被有意拆开。CLI 只负责请求校验、冻结 prompt、Base + adapter 推理和 strict diff/path validation；真实应用、编译和测试进入最小权限沙箱。run manifest 绑定 Git commit、Base revision、配置、数据、环境、预测和评分 SHA256。

## 4. 阶段与结果

| 阶段 | 主要结果 | 证据等级 |
|---|---|---|
| G0 | 7B Base 的 BF16 LoRA、NF4 QLoRA、adapter 保存与重载 smoke 通过 | GPU smoke |
| A0 | 任务契约、Schema v0.2、评分 fixture、质量门禁和治理边界冻结 | Contract/unit test |
| A1 | 300/50 isolated-v2 pilot，跨 split 多维零重叠 | Data pilot |
| A2 | 50 function + 20 file-window 的 rootless 双资格与三次稳定回放 | Execution pilot |
| A3.0～A3.2 | Base/外部基线、scoring v2、BF16/NF4 公平 pilot | Controlled pilot |
| A3.3 | 5,000/500 正式 SFT、500 条固定推理和评分；主提升通过但 timeout 退化 | Frozen evaluation |
| A3.4 | SFT-R2、旧 holdout、124 条独立确认、176 条 Defects4C | Frozen evaluation |
| 泛化诊断与 Data-v2 | 六项失败诊断；来源扩张和单轮 replay 均保留负结果并早停 | Diagnostic/exploratory |
| A4 | 1,056 个候选全量执行评分，182 对源偏好 | Train-only exploratory |
| A5 | 175 对审计偏好、两组 DPO、64 条 dev、一次性正式评测 | Frozen DPO evaluation |
| 交付 | CLI、模型卡、复现指南、面试材料、最终 manifest | Application delivery |

## 5. 数据与隔离

| 用途 | 规模与组成 | 隔离边界 |
|---|---|---|
| A3.3 SFT | 5,000 train + 500 validation；CommitPackFT/RunBugRun C++ | 与 formal family 零重叠；hidden/gold 不进 prompt |
| Formal holdout | 400 function + 100 file-window | 不参与 checkpoint 选择；greedy Pass@1 |
| A3.4 R2 | 1,200 train + 117 validation | 只从既有 train/validation 静态选择风险模式 |
| Confirmation | 100 function + 24 file-window | 不参与 R2 或 DPO checkpoint 选择 |
| Defects4C | 176 function | 排除训练 family；LLVM 139/176，披露分布偏斜 |
| A4 执行候选 | 256 function + 8 file-window，各 4 候选 | 只来自冻结 train；执行结果不写入 prompt |
| DPO dev | 64 executable cases | 与 175 对 preference case/family 零重叠 |

基础模型预训练语料无法完全审计，因此项目只声称控制本人后训练数据的 split/family 隔离，不声称“完全无污染”。原始数据、重打包样本和完整运行产物不进入 Git。

## 6. SFT 主链

Base 固定为 `Qwen/Qwen2.5-Coder-7B` revision `0396a76181e127dfc13e5c5ec48a8cee09938b02`。正式 M1 使用 NF4 QLoRA，在 5,000 条 train 上训练 3 epochs、1,875 optimizer steps；M1-R2 从最佳 M1 adapter 继续，以 learning rate `2e-5`、micro batch 1、gradient accumulation 8、LoRA rank 8 / alpha 16 训练 1 epoch、150 steps。

| 模型 | Parse | Apply | Compile | Pass | Function Pass | Regression | Timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 Base | 0 | 0 | 0 | 0/500 | 0/400 | 0 | 0 |
| M1 SFT | 499 | 391 | 373 | 15/500 | 12/400 | 5 | 3 |
| M1-R2 | 499 | 412 | 392 | 14/500 | 11/400 | 3 | 2 |

M1-R2 的 function Pass 相对 Base 为 `+2.75pp`，paired bootstrap 95% CI 为 `+1.25pp～+4.5pp`，旧 holdout 内部门禁通过。但 confirmation 上 M0/M1-R2 均为 0/124，M1-R2 新增 regression 和 timeout；Defects4C 上 M1-R2 虽将 parse/apply/build 提高到 174/72/55，最终仍与 Base 同为 1/176。结论是协议学习成立，语义泛化未被证明。

## 7. 泛化诊断与停止无效扩张

六项诊断检查了数据身份、prompt 长度、语言/任务切片、终止阶段、成功与输入长度关系、confirmation 和 Defects4C 分布。主要瓶颈是 public/hidden 语义测试，而不是 diff 解析；旧集成功偏向较短输入，外部唯一成功也不具跨项目代表性。

项目随后审计 GitHub、CommitPack、RunBugRun v2、BeetleBox、BugsCpp 等来源。固定许可、provenance、family 隔离和可执行资格后，新增供给不足以达到正式 Data-v2 容量门；单轮 780 条安全 replay 消融在 formal 仅 13/500 Pass，低于 M1-R2 的 14/500。按预注册停止线终止宽泛来源搜索和追加训练，避免用更多低质量数据或结果驱动补考制造虚假进步。

## 8. 可执行偏好与 DPO

A4 对 264 个 train-only 案例各生成 4 个候选，共 1,056 个。所有候选进入真实执行漏斗，得到 123 个完整 Pass、11 个 timeout 和 182 对保守偏好；75 对 chosen 为完整 success，107 对只提供更后终止阶段信号。

A5 重新审计 182 个 source group，排除 7 对 timeout-only，冻结 175 对 DPO 输入。偏好与 DPO dev、formal、confirmation 和 Defects4C 均无重叠。M1-R2 起点 adapter SHA256 为 `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a`。

| 变体 | Beta | Epochs / steps | Train loss | Dev Pass | Dev apply/build | 结果 |
|---|---:|---:|---:|---:|---:|---|
| DPO-beta01 | 0.1 | 2 / 44 | 0.67567 | 5/64 | 55/55 | 合格但未入选 |
| DPO-beta03 | 0.3 | 2 / 44 | 0.64335 | 5/64 | 57/57 | 按冻结次级规则入选正式评测 |

两组训练只改变 beta，不在看见 dev 后重训或补充超参数搜索。beta=0.3 adapter SHA256 为 `2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a`。

## 9. DPO 一次性正式评测

### Formal 500

| 指标 | M1-R2 | DPO-beta03 | 变化 |
|---|---:|---:|---:|
| Parse | 499 | 500 | +1 |
| Apply | 412 | 437 | +25 |
| Compile | 392 | 424 | +32 |
| Public success | 22 | 28 | +6 |
| Pass | 14 | 19 | +5 |
| Function Pass | 11/400 | 17/400 | +1.5pp |
| File-window Pass | 3/100 | 2/100 | -1.0pp |
| Regression failure | 3 | 5 | +0.4pp |
| Timeout | 2 | 5 | +0.6pp |

Function Pass 的 paired bootstrap 为 observed `+1.5pp`、95% CI `[0,+3.0pp]`。主提升、parse/apply/compile、regression 和 file-window 限制均通过，但 timeout 超过冻结上限，因此 `formal_timeout_increase_exceeded` 已足以否决候选。

成功迁移为 8 gained、3 lost、11 retained，500 个 completion 中 363 个变化。四个 DPO 新增 timeout 分别来自队列不收缩、循环变量不增长、链表边界翻转和递归入口替换；它们均可 apply/compile，却在 public tests 稳定超时。

### Confirmation 124

| 指标 | M1-R2 | DPO-beta03 |
|---|---:|---:|
| Parse / Apply / Compile | 123/104/103 | 124/110/109 |
| Public success | 6 | 5 |
| Pass | 0 | 0 |
| Regression / Timeout | 3/4 | 3/2 |

DPO 改变 86/124 个 completion，并改善格式、应用、编译和 timeout，但没有产生端到端成功。这界定了 formal 内收益与独立分布泛化之间的差距。

### Defects4C 176

替换评分 array `97901` 与聚合 `97902` 已完成固定 176 条。DPO-beta03 的 parse/apply/compile/Pass 为 `176/84/65/1`，M1-R2 为 `174/72/55/1`，双方 timeout 均为 0。paired Pass 差值及 95% 区间均为 0；唯一成功案例为 retained success，没有 gained 或 lost。候选改善了前置漏斗，但没有外部端到端收益。scores、summary、comparison、failure-analysis SHA256 分别为 `ee105851...e1`、`58b9e918...8b0`、`28b9806f...fc4`、`502a7c20...3e0`。

## 10. 工程故障与恢复

项目保留了会改变复现设计的失败，而不是只展示成功 Job：

- 早期 A2 作业因 Slurm 入口和环境假设秒退，后续显式验证解释器、prefix 和工作目录；
- 长资格与评分任务改为逐案例原子 checkpoint，支持固定身份的断点恢复；
- Defects4C rootfs 曾缺少 `/patchalign` Python 路径，通过沙箱内外路径对照定位；
- GPU 节点零日志通过跨节点对照归因，固定排除 `gpu12/gpu16`，不把节点故障算作模型失败；
- A5 原推理 Job `97586` 被共享 UID 主动取消，恢复 Job `97608` 只续跑缺失 segment；
- A5 Defects4C 原评分 Job `97614` 暴露沙箱内 role 白名单断层，恢复提交 `fbe0717…` 只加入显式 `dpo_beta03`，以 435 项测试验收后由 Job `97901/97902` 重做缺失评分。

所有恢复均保持数据、prompt、模型、生成参数、评分协议、timeout 和固定分母不变。基础设施失败不伪装成模型 failure，也不通过删样本获得更好指标。

## 11. 最终模型与应用交付

M1-R2 是当前默认交付 adapter。它已从集群本地化到本机 `artifacts/delivery/model/m1_r2/`，权重为 80,792,096 bytes，SHA256 为 `8437acca…3425a`；配置 SHA256 为 `acd214f4…2c69`，本地 `PROVENANCE.json` 已与实际字节核验。大型权重继续由 Git 忽略。

应用 CLI 提供 `prompt` 和 `infer` 两个入口。Job `97978` 已读取最终 comparison 并自动选择 M1-R2，完成真实 GPU smoke：推理延迟 7.03 秒、峰值显存 5,810,547,712 bytes，adapter SHA256 与推荐权重一致，固定 prompt 和 patch 的 SHA256 均写入 metadata。CLI 只生成并结构校验候选，不自动执行或合并。

## 12. 核心结论

1. SFT 最确定的收益是输出协议学习：Base 在 formal 500 上 0 parse，M1/M1-R2 达到 499；但协议遵循不等于语义正确。
2. DPO 的正收益真实：formal Pass 14→19、apply 412→437、compile 392→424；不能因最终否决而抹去。
3. DPO 的安全退化也真实：timeout 2→5，且逐例存在明确非终止控制流；不能用总 Pass 提升覆盖。
4. 独立 confirmation 的 0 Pass 和 Defects4C 的低成功率说明当前模型没有证明广泛语义泛化。
5. 多阶段漏斗、固定分母、预注册 gate、不可变预测、原子恢复和 SHA256 绑定，使正负结果都可审计。
6. 对简历级 AI 应用交付，遵守安全门禁并回退 M1-R2，比继续调 beta、扩大低质量数据或提前做 RLVR/GRPO 更合理。

## 13. 限制与发布边界

- 任务只覆盖局部、单文件 C++ 修复，不能外推到多文件仓库级 Agent；
- confirmation 最终 Pass 为零，Defects4C 又明显偏向 LLVM；
- DPO 只有单 seed 与两组 beta，不等价于 replicated research；
- Base 预训练污染未知；训练数据、adapter 和生成补丁的公开再分发许可尚未逐项完成；
- 模型可能生成逻辑错误、无限循环、资源消耗或不安全代码，必须在最小权限沙箱和人工复核下使用。

仓库原创代码和文档采用 Apache-2.0，但该许可证不会自动覆盖 Base 权重、数据、adapter、生成补丁或第三方依赖。本报告不是公开模型 release 或生产部署批准。

## 14. 交付状态

正式 SFT、探索性 A4、真实 DPO、三套固定分母评测、失败分析、最终模型回退、adapter 本地化和 CLI GPU smoke 均已完成。剩余动作只有生成 hash-complete delivery manifest，并完成本机、GitHub、集群三端 commit、工作树和 artifact 哈希审计；不再启动训练、调参或结果驱动补考。
