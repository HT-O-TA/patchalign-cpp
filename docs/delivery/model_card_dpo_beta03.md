# DPO beta=0.3 候选模型卡

模型名称：PatchAlign-Cpp DPO-beta03

模型类型：Qwen2.5-Coder-7B Base 上的 LoRA adapter，接续 M1-R2 进行 DPO

版本状态：实验候选；因正式安全门禁失败，不作为推荐交付模型

日期：2026-09-08

## 模型摘要

DPO-beta03 是 PatchAlign-Cpp 在 M1-R2 监督微调 adapter 上继续进行直接偏好优化得到的候选模型。它接收冻结模板中的缺陷描述、已定位代码上下文和公开失败证据，输出一个仅修改 `main.cpp` 的 unified diff。模型的目标是利用真实执行结果构造的偏好对，改善局部 C++ 补丁的协议遵循和端到端成功率。

独立开发集在 beta=0.1 与 beta=0.3 之间选择了 beta=0.3，但一次性正式评测发现：相对 M1-R2，500 条 formal 上 Pass 从 14 提升到 19，同时 timeout 从 2 增加到 5，超过冻结的 `+0.5pp` 退化上限；124 条 confirmation 仍为 0 Pass。Defects4C 上候选虽将 parse/apply/compile 从 `174/72/55` 提高到 `176/84/65`，双方仍同为 1/176 Pass。因此该候选不能晋级，推荐交付模型仍为 M1-R2。

## 身份与谱系

| 字段 | 值 |
|---|---|
| Base | `Qwen/Qwen2.5-Coder-7B` |
| Base revision | `0396a76181e127dfc13e5c5ec48a8cee09938b02` |
| 起始 adapter | PatchAlign-Cpp M1-R2 |
| 起始 adapter SHA256 | `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a` |
| DPO adapter SHA256 | `2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a` |
| Adapter config SHA256 | `8b271b67e9afd124a3f3ff36cd22f22ea6cda2d00b2ed55dbca9e37072c5ee0` |
| Adapter 大小 | 80,792,096 bytes |
| 训练 run | `a5_dpo_v1_1` / Slurm Job `97559_1` |
| 训练代码 commit | `80cf19d1bd23a49118dc5fc4bfdda9b6d65f102d` |
| Seed | `20260830` |

集群内部 adapter 路径：

```text
/mingli01/project/ht/patchalign-cpp/artifacts/a5/dpo-training-v1.1/beta03/final-adapter
```

该路径是内部实验位置，不是稳定公共下载地址。

## 偏好数据

偏好数据来自 A4 真实执行结果。审计从 182 个 source group 中排除 7 个仅有 timeout 差异、无法证明语义优劣的 group，最终冻结 175 对偏好样本；其中 75 对的 chosen 补丁通过完整执行闭环。数据与 64 条 DPO dev、500 条 formal、124 条 confirmation 和 176 条 Defects4C 均无重叠。

| 字段 | 值 |
|---|---|
| Preference pairs | 175 |
| Chosen full-success pairs | 75 |
| Excluded timeout-only groups | 7 |
| Preference JSONL SHA256 | `892812ae43f551aeff06486963e75806ce6da185f8f41d3df3cff64a6f6ba43c` |
| Dev / formal / confirmation overlap | 0 |

本卡不授予偏好数据、上游训练数据或 adapter 的再分发许可。

## 训练方法

| 参数 | 值 |
|---|---|
| 模式 | NF4 QLoRA DPO continuation |
| Beta | `0.3` |
| Loss | sigmoid；非 reference-free |
| Epochs / optimizer steps | 2 / 44 |
| Micro batch / gradient accumulation | 1 / 8 |
| Learning rate / warmup steps | `5e-6` / 4 |
| Max prompt / completion / sequence | 3,072 / 640 / 4,096 tokens |
| Trainable / total parameters | 20,185,088 / 4,373,157,376 |
| Train loss | `0.6433538442` |
| Peak GPU memory | 29,723,163,136 bytes |
| 训练时长 | 5 分 57 秒 |

关键软件版本为 Accelerate 1.13.0、bitsandbytes 0.49.2、Datasets 3.6.0、PEFT 0.18.1、Transformers 4.57.6 和 TRL 0.28.0。完整机器契约见 `configs/training/a5_dpo_v1_1.json` 及训练 artifact manifest。

## 选择与评测

正式生成统一使用 greedy Pass@1 和冻结 prompt；评分器仅接受一个 unified diff，执行 `git apply --recount --check`，随后在 rootless Bubblewrap 中依次运行 build、public、hidden 与 regression 测试。`--recount` 只忽略 diff 头中的行号数字，不放宽上下文或删除行内容。sanitizer 仅在样本明确适用时运行。

| 数据 | DPO-beta03 | M1-R2 | 结论 |
|---|---:|---:|---|
| DPO dev 64 | Pass 5；apply/build 57/57 | Pass 5；apply/build 53/52 | beta=0.3 按冻结次级规则入选 |
| Formal 500 | parse/apply/compile/Pass = 500/437/424/19；timeout 5 | 499/412/392/14；timeout 2 | Pass `+1.0pp`，但 timeout `+0.6pp`，触发安全否决 |
| Confirmation 124 | parse/apply/compile/Pass = 124/110/109/0；timeout 2 | 123/104/103/0；timeout 4 | 前置阶段改善，最终 Pass 无提升 |
| Defects4C 176 | parse/apply/compile/Pass = 176/84/65/1；timeout 0 | 174/72/55/1；timeout 0 | 前置漏斗改善，最终 Pass 无提升 |

Formal 的配对 bootstrap Pass 差值为 `+1.5pp`，95% 区间 `[0.0pp, 3.0pp]`；共有 8 个成功获得、3 个成功丢失、11 个共同成功。虽然总体补丁可应用和可编译数量提升，但新增的 4 个 timeout 分别表现为队列不收缩、循环变量不增长、链表边界翻转和递归入口替换。这说明执行偏好可以把错误推进到更深的执行阶段，却不自动保证终止性和语义安全。

## 预期用途

- 复现 DPO 训练、开发集选择和一次性正式评测；
- 研究“格式/可执行性提升但安全性退化”的后训练失败模式；
- 在隔离环境和人工复核下生成候选补丁，用于比较或失败分析。

## 非预期用途

- 不作为本项目推荐模型，也不应替换 M1-R2 进入默认推理入口；
- 不应自动提交、合并或部署到生产仓库；
- 不应用于多文件自主修改、安全关键系统或未经隔离的代码执行；
- 不应把 parse、apply、compile 或 public-test 改善解释为语义正确；
- 不应基于单 seed、单任务族结果宣称普适代码修复能力。

## 风险与发布状态

该候选已观察到可复现的非终止风险，且 confirmation 最终 Pass 为零；它只完成单 seed 比较，没有多 seed 稳健性证明。Base 预训练污染未知，外部分布以 LLVM 为主，任务范围也只覆盖局部单文件修改。

仓库原创代码和文档采用 Apache-2.0，但该许可证不自动覆盖 Base 权重、训练数据、adapter、生成补丁或第三方依赖。DPO-beta03 作为失败门禁的研究 checkpoint 保留，不作为公开发布或生产交付模型。
