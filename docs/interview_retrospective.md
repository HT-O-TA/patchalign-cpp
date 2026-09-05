# PatchAlign-Cpp 项目复盘与面试复述

状态：持续更新。本文用于面试叙事和项目复盘，不作为实时作业、冻结配置或最终指标的事实源。当前进度以 [`status.md`](status.md) 为准，运行身份以集群 artifact manifest 为准。

## 一句话介绍

PatchAlign-Cpp 是一个面向真实代码修复的可复现实验系统：以 Qwen2.5-Coder-7B Base 为基础，用受控的 SFT/QLoRA 学习输出 unified diff，并在隔离、禁网、限时的真实构建与测试环境中判断补丁能否应用、编译和通过测试，而不是只比较文本相似度。

## 我解决的核心问题

项目的难点不只是“把模型训起来”，而是让训练数据、模型输出和真实执行评测形成一条可审计闭环：

1. 数据不能跨 train、validation、holdout 泄漏，并且要满足函数级为主、兼容文件窗口上下文的统一 Schema。
2. 模型必须只输出一个可解析的 unified diff，补丁还要能真实应用、编译和执行。
3. 失败必须保留在固定分母中，不能因为格式错误、超时或难样本而被排除。
4. 每次运行要绑定代码提交、模型 revision、配置与输入输出哈希，失败作业也要可追溯。
5. 训练后的提升必须同时满足修复率和安全退化上限，不能只看一个变好的主指标。

## 阶段经历

### G0：先证明模型和集群环境可用

- 冻结 Qwen2.5-Coder-7B Base upstream revision `0396a76181e127dfc13e5c5ec48a8cee09938b02`，不把 Base 与 Instruct 混用。
- 在 A800 上分别验证 BF16 LoRA 与 NF4 QLoRA 的训练、adapter 保存和独立重载，先排除 CUDA、量化、PEFT 和模型路径问题。
- 将代码放在 `/mingli01/project/ht/patchalign-cpp`，环境放在并列的 `/mingli01/project/ht/.conda_envs/patchalign-cpp`；Git 同步源码，集群 artifact 本地化，不用软链接把两台机器耦合在一起。

面试要点：先用最小真实模型闭环降低后续实验风险，同时把模型 revision、环境与目录职责冻结下来。

### A0：把任务定义成可执行契约

- 设计 Sample Schema v0.2，统一 function 和 file-window 两种输入层级；主任务以函数级为主。
- 冻结 strict unified diff 解析、`git apply --recount --check`、编译、测试和终态分类。`--recount` 只忽略错误的 hunk 行号，不放宽删除行或上下文内容。
- 建立确定性 fixture 和评分闭环；固定总分母并记录 parse/apply/build/test/timeout 等失败。
- 冻结 SFT/DPO 的提升阈值和退化上限；sanitizer 仅在样本明确适用时执行。

面试要点：先定义“什么算成功”，再训练模型，避免看到结果后改评分口径。

### A1：构造隔离的数据 pilot

- 从 CommitPackFT 和 RunBugRun 构造 300/50 的 train/validation pilot。
- 对 exact payload、problem/repository family 等维度做隔离，防止相同修复或同一问题族跨 split 泄漏。
- 用 Schema、token 长度和哈希 manifest 固定数据身份。

面试要点：数据规模不是唯一目标，更重要的是可训练、可验证、无泄漏且能被后续流水线真实消费。

### A2：建立真实执行沙箱

- 对 50 条 function 和 20 条 file-window 样本完成 buggy/fixed 双资格回放和独立稳定重放。
- 使用 rootless、禁网 Bubblewrap，限制资源和执行时间，保存 stdout/stderr、退出码、信号与 timeout。
- 用 `git apply --recount --check` 连接模型 diff 与真实仓库，随后执行构建和 public/regression/hidden 测试。

面试要点：代码修复不能只评 BLEU 或 diff 相似度；真实 apply、compile、test 才能揭示语法正确但行为错误的补丁。

### A3.0–A3.2：基线、评分升级与训练方案选择

- A3.0 用 70 条 executable pilot 比较 Base 与外部模型，发现“能生成文本”不等于“能输出严格补丁”。
- A3.1 冻结 scoring v2，并对不可变 predictions 重评分，保证模型生成和评分器演进彼此解耦。
- A3.2 比较 BF16 LoRA 与 NF4 QLoRA。两者 pilot 成功数持平，按预注册资源 tie-break 选择显存占用更低的 NF4 QLoRA，而不是事后挑选偏好的方案。

面试要点：先用小规模 pilot 验证假设和资源策略，再投入正式训练；平局规则提前注册可以降低选择偏差。

### A3.3：正式 SFT、有效提升与安全门禁失败

- 正式数据为 5,000 train、500 validation；正式 holdout 为 400 function + 100 file-window。
- 正式 NF4 QLoRA 训练 3 epochs、1,875 optimizer steps，最佳 checkpoint 为 epoch 2 / step 1,250。
- Base 在冻结 raw-completion 协议下 500/500 生成成功，但 strict diff 为 0；SFT 后 499/500 成为 strict diff，说明模型首先学会了输出协议。
- SFT 候选取得 15/500 Pass，其中 function 12/400；相对 Base 提升 3 个百分点，paired bootstrap 95% 区间为 +1.5pp～+4.75pp。
- 但候选引入 3/500 timeout，退化 0.6 个百分点，超过预注册上限 0.5 个百分点，因此即使主提升通过，整体内部门禁仍判失败。

面试要点：这是项目中最重要的取舍——没有为了得到“成功结论”而删除超时样本或修改阈值，而是保留失败并继续做根因分析。

### 三个超时样本的定位

- 一个补丁把 Fenwick 更新入口改成 0，导致 `x += x & -x` 永远无法推进。
- 一个补丁改变循环保护条件，在 `i=1` 时乘法更新使变量永远停在 1。
- 一个补丁把外层界限从较小的 `N` 改成数百万量级的 `M`，造成复杂度爆炸。
- 在相同 Bubblewrap、2 GiB 和 3 秒限时下，CPU-only 对照证明 buggy/fixed 都能快速退出，而三个模型补丁均稳定超时，因此排除了集群抖动。

调查本身也暴露了两个工程问题：`sbatch --wrap` 默认 `/bin/sh` 不支持 `set -o pipefail`；登录节点 `/tmp` 不与计算节点共享。最终将诊断脚本放到共享项目目录，并用明确的 Bash 作业入口完成复现。

面试要点：我用对照实验把“可能是环境噪声”变成“模型引入的确定性退化”，并把无效诊断作业和有效模型证据严格分开。

### A3.4：针对风险模式的 SFT-R2

- 不进入 A4，也不查看三个 holdout 样本的参考答案；只从冻结的 A3.3 train/validation gold diff 中，用静态规则选择循环推进、边界/索引和规模/分配相关修复。
- 最终得到 1,200 train / 117 validation 的 RunBugRun function 安全子集，选择结果由输入锁、标签计数和输出哈希约束。
- 从 A3.3 最佳 adapter 继续训练，重置 optimizer/scheduler，以更低学习率训练 1 epoch、150 optimizer steps。
- 推理仍使用原 500 条 holdout、raw completion、greedy Pass@1、512 token 和 scoring v2；不增加候选过滤、拒绝或重排，确保与 M0/M1 可比。
- 单 GPU 训练 Job `94524` 完成 150/150 optimizer steps，用时 15 分 15 秒；最佳 adapter 位于 epoch 1 / step 150。聚焦 validation loss 为 `0.07718202`，原 500 条 reference validation loss 相对起点增加 `0.00301254`。这只是潜在遗忘信号，不能替代真实可执行评测，因此暂不宣称风险修正有效。
- 训练与推理代码处于不同提交，因此不伪造“同一 commit”；使用独立 inference binding，以 training manifest、summary、checkpoint、adapter 和 holdout/prompt 的 SHA256 显式桥接，并让 CPU preflight 与正式推理绑定新的实现 commit。
- CPU-only preflight Job `94537` 用 21 秒完成 `154 passed`，并证明新渲染的 500 条 prompt 与 A3.3 M0/M1 prompt artifact 逐字节一致；正式推理因此只改变 adapter，不改变输入和解码协议。
- 正式推理 Job `94538` 完成 500/500 生成，499 条为 strict diff，3/3 确定性重放稳定且无 OOM；这只能证明生成与格式闭环，修复正确率和超时风险仍由真实执行评分决定。
- 生成与评分彻底解耦：评分只读取已哈希冻结的 predictions，并在创建输出前验证推理 manifest、holdout、scoring v2 配置和 Bubblewrap 身份，因此可以复评而不重新消耗 GPU。
- A3.4 scoring preflight 在真实集群 artifact 上再次通过：500 条顺序、预测哈希、499 条 strict diff、3 条稳定 probe、固定 holdout 与沙箱身份全部一致，随后才允许执行评分。
- CPU-only 真实执行评分得到 14/500 Pass：相对 M1，apply/compile 从 391/373 提升到 412/392，regression failure 从 5 降到 3，timeout 从 3 降到 2，但总 Pass 从 15 降到 14。该结果说明工程可执行性和安全性改善不必然带来端到端正确率提升，必须按多目标冻结门禁判断。
- 超时变化不是简单的“修好一个”：三个旧超时中两个消失、一个保留，同时出现一个新超时。逐例身份对照避免了用汇总数掩盖风险迁移；正式比较 Job `94580` 已确认旧 500 条内部门禁通过，但这一结论随后被新确认集门禁失败所阻断，不能用于晋级 A4。

面试要点：修正策略针对一般风险模式而非记忆失败样本答案，同时保持评测协议不变，避免 holdout 泄漏和事后优化。旧 holdout 内部门禁通过而新确认集失败，是“可比性提升不等于分布外泛化”的直接证据。

### A3.4：独立确认与 Defects4C 外部闭环

- 正式比较 Job `94580` 在旧 500 条上给出 function `+2.75pp`、paired-bootstrap 95% 区间 `+1.25pp～+4.5pp`，因此内部冻结门通过；与 M1 的诊断则显示成功样本新增 5 条、丢失 6 条。
- 新确认集固定 124 条且不参与 checkpoint 选择。M0/M1-R2 都是 0/124 Pass；R2 虽改善 parse/apply/compile，却新增 3 条 regression failure 和 4 条 timeout，确认集门禁明确失败。
- 外部 Defects4C 从官方源筛出 203 个 C++ function 候选，并排除两个训练 family 重叠项目；其中 LLVM 占 141/203，必须披露外部集明显偏向单一大型项目。目标是以离线 Bubblewrap 双资格冻结至少 150 条，再对 M0/R2 做成对推理与执行。
- 大仓库准备阶段先后遇到 DNS 抖动、LLVM checkout 120 秒误超时和取消作业遗留 Git lock。通过有限退避、900 秒 checkout、原子检查点和精确锁清理恢复，且不删除样本、不放宽质量阈值。

面试要点：晋级条件是合取而非择优展示。即便旧测试集通过，只要独立确认集失败，就必须停止；外部评测仍应跑完以形成完整证据，而不是用失败结果反向调参。

## 代表性的工程故障与改进

1. 全量资格回放在单次时限内无法完成：改为候选级原子 checkpoint 和可恢复执行。
2. 目标配额超过真实合格容量：保持总量和硬约束，仅做最小、可审计的联合配额调整。
3. 后置 Schema 校验导致无效样本占配额：改为流式“校验后接纳”。
4. holdout 的真实 prompt 超过 4,096 tokens：用正式 tokenizer、模板和测试输入在 GPU 前做全量 token preflight。
5. 配置与独立验证器常量漂移：让测试直接调用 fail-closed 验证器，跨组件核对冻结值。
6. prompt 输入模式曾是隐式常量：将 `raw_completion` 写入可哈希配置，由 preflight 和推理共同读取。
7. Slurm 任务出现秒退或空日志：区分调度/入口错误与模型实验失败，保留 Job 证据但不把无效运行计入模型结论。

详细证据见 [`evidence/a3_3_pipeline_findings.md`](evidence/a3_3_pipeline_findings.md)。

## 面试表达模板

### 60 秒版本

“我做了一个面向真实代码修复的训练与评测系统。模型是 Qwen2.5-Coder-7B Base，目标是让它根据 buggy code 和上下文输出统一 diff。我的重点不是单纯训练，而是建立从无泄漏数据、Schema、补丁解析，到隔离编译测试和固定质量门禁的闭环。正式 QLoRA SFT 后，模型从 500 条全部无法解析提升到 499 条可解析，function Pass 提升 3 个百分点；但它引入了 3 个真实运行时超时，超过预注册安全上限，所以我没有宣布整体通过。我进一步用 CPU 对照复现，定位到死循环和复杂度爆炸，再设计不接触 holdout 答案的风险模式 SFT-R2。R2 将 timeout 从 3 降到 2、regression failure 从 5 降到 3，并提高 apply/compile 成功数，但端到端 Pass 从 15 降到 14，说明局部安全改善不等于综合质量提升。这个项目让我最有价值的经验是：模型主指标提升不等于系统可靠，评测协议、可恢复数据管线和失败归因同样重要。”

### 深挖时的回答顺序

1. 先解释为什么文本相似度不足以评价代码修复。
2. 说明如何防止数据泄漏，以及为什么用固定分母。
3. 给出 Base→SFT 的 parse 和 Pass 变化。
4. 主动说明门禁未通过及三个 timeout，不回避负结果。
5. 讲清 CPU 对照如何排除集群噪声。
6. 说明 SFT-R2 如何避免利用 holdout 答案。
7. 最后说明新确认集已经失败、Defects4C 外部门禁正在闭环，因此 A4 不可进入，避免过度宣称。

## 可以诚实声称与不能声称的内容

可以声称：已完成可复现的数据、训练、生成、沙箱评分和比较流水线；SFT 显著改善格式遵循，并在冻结 function holdout 上达到预注册的主提升要求；超时退化得到独立复现和逐例根因。

目前不能声称：完整 SFT promotion gate 已通过；模型已在新的未查看确认集上泛化；Defects4C 外部门禁已经得到最终结果；A4 preference optimization 已启动。已有证据反而表明确认集门禁失败，因此本轮模型不能晋级 A4。

## 维护规则

- 每个正式阶段结束后，补充“问题—证据—判断—修正—结果—局限”六项。
- 只引用冻结结果，不把 `RUNNING`、预计时间或临时 checkpoint 写成本文件事实。
- 数字变更先核对配置、manifest 和 `status.md`；本文只做稳定叙事。
- 失败作业只有在能说明工程判断或实验方法时才进入复述，并明确其不构成模型结果。
