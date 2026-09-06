# PatchAlign-Cpp 最终技术报告

报告日期：2026-09-06
交付口径：完成 SFT 与探索性研究；A5/DPO 延后
决策依据：[ADR-0009](../decisions/0009-close-after-sft-and-exploratory-a4.md)

## 1. 执行摘要

PatchAlign-Cpp 建立了一套面向局部 C++ 缺陷修复的可验证后训练系统：模型只接收缺陷描述、已定位代码上下文和公开失败证据，只输出一个 unified diff；后端在 rootless Bubblewrap 中依次验证解析、路径策略、`git apply --recount`、编译、公开测试、隐藏测试、回归测试和明确适用时的 sanitizer。

本轮完成了真实 Base 模型 smoke、任务与 Schema 冻结、数据隔离、沙箱执行、基线、SFT pilot、正式 NF4 QLoRA SFT、安全修正轮次、独立确认集、Defects4C 外部评测，以及一次负责人授权的 exploratory A4 偏好数据研究。最终模型候选 M1-R2 在旧 500 条 holdout 上相对 Base 的 function Pass@1 提升 `+2.75pp`，但在新 124 条确认集上 M0 与 M1-R2 均为 `0/124`，且 R2 新增 regression failure 与 timeout；在 Defects4C 176 条上双方均为 `1/176`。因此完整 promotion gate 未通过，`a4_ready=false` 保持不变。

探索性 A4 对 264 个 train-only 可执行案例各采样 4 次，完成 1,056 个候选的真实执行评分，得到 123 个完整 Pass 和 182 对保守偏好数据。该结果证明执行反馈能够产生可复现的同题偏好信号，但不能证明未见分布泛化，也没有启动 DPO。本轮按负责人决定在 SFT 与探索性研究处收尾。

## 2. 研究问题与范围

核心问题是：在固定数据、提示、生成预算和评分协议下，局部 C++ 修复 SFT 能否提高开放权重 Base 模型生成可应用、可编译并通过隐藏与回归测试补丁的能力；当正式晋级失败时，真实执行反馈能否仍形成可审计的探索性偏好信号。

本轮范围以 function-level 为主，并兼容固定 file-window 上下文。只允许修改 `main.cpp`，不包含仓库自主探索、联网搜索、长程 Agent、多文件修改或生产环境自动合并。

## 3. 已完成阶段

| 阶段 | 结果 | 证据等级 |
|---|---|---|
| G0 | Qwen2.5-Coder-7B 的 BF16 LoRA、NF4 QLoRA、adapter 保存和重载通过 | Smoke |
| A0 | 任务契约、Schema、评分 fixture、质量门禁和治理边界冻结 | Synthetic test / contract |
| A1 | 300/50 isolated pilot，跨 split 多维零重叠 | Pilot |
| A2 | 50 function + 20 file-window 的 rootless 双资格与三次稳定回放通过 | Pilot |
| A3.0～A3.2 | Base/外部基线、scoring v2、BF16/NF4 公平 pilot 完成 | Pilot |
| A3.3 | 正式 NF4 QLoRA SFT、500 条固定推理和评分完成；timeout 上限失败 | Frozen evaluation |
| A3.4 | SFT-R2、旧 holdout、独立确认集和 Defects4C 完成；最终 readiness 失败 | Frozen evaluation |
| exploratory A4 | 1,056 候选全量执行评分和 182 对偏好数据完成 | Exploratory, train-only |
| A5 | 未启动，`a5_started=false` | Deferred |

## 4. 数据与隔离

| 用途 | 规模与组成 | 关键边界 |
|---|---|---|
| A3.3 SFT | 5,000 train + 500 validation；CommitPackFT/RunBugRun | 与正式 holdout problem family 零重叠；hidden/gold 不进 prompt |
| A3.3 internal holdout | 400 function + 100 file-window | 不参与 checkpoint 选择；固定 greedy Pass@1 |
| A3.4 R2 continuation | 1,200 train + 117 validation | 只从既有 train/validation 静态选择风险模式，不读取 holdout 修复答案 |
| 独立 confirmation | 100 function + 24 file-window | 不参与 R2 checkpoint 选择 |
| Defects4C external | 176 function | 排除与训练来源 family 重叠；139/176 来自 LLVM，分布偏斜 |
| exploratory A4 | 256 function + 8 file-window | 只来自冻结 train 的 RunBugRun；每例 4 候选 |

基础模型预训练语料不可完全审计，因此项目只声称控制了本人后训练数据的隔离，不声称“完全无污染”。原始数据和重打包样本没有进入 Git。

## 5. 训练设置

基础模型固定为 `Qwen/Qwen2.5-Coder-7B` revision `0396a76181e127dfc13e5c5ec48a8cee09938b02`。正式 M1 使用 NF4 QLoRA，在 5,000 条 train 上训练 3 epochs、1,875 optimizer steps；最佳 checkpoint 为 epoch 2 / step 1,250。

M1-R2 从 M1 最佳 adapter 继续，以 NF4 QLoRA、learning rate `2e-5`、micro batch 1、gradient accumulation 8、LoRA rank 8 / alpha 16 训练 1 epoch、150 optimizer steps。训练 Job `94524` 用时 `00:15:15`，峰值 GPU 显存 `17,933,322,752` bytes。M1-R2 adapter SHA256 为 `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a`。

## 6. 正式评测结果

### 6.1 旧 500 条 internal holdout

| 模型 | Parse | Apply | Compile | Pass | Function Pass | Regression failure | Timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 Base | 0 | 0 | 0 | 0/500 | 0/400 | 0 | 0 |
| M1 SFT | 499 | 391 | 373 | 15/500 | 12/400 | 5 | 3 |
| M1-R2 | 499 | 412 | 392 | 14/500 | 11/400 | 3 | 2 |

M1 相对 M0 的 function 提升为 `+3.0pp`，paired bootstrap 95% 区间 `+1.5pp～+4.75pp`，但 timeout 增加 `+0.6pp`，超过冻结的 `+0.5pp` 上限。M1-R2 相对 M0 的 function 提升为 `+2.75pp`，95% 区间 `+1.25pp～+4.5pp`，旧 holdout 内部门禁通过；相对 M1，它改善 apply/compile 和汇总风险数，却少了一个最终 Pass，且 timeout 样本发生迁移。

### 6.2 独立确认与外部评测

| 数据 | M0 | M1-R2 | 结论 |
|---|---:|---:|---|
| Confirmation 124 | 0/124 Pass | 0/124 Pass；新增 3 regression failure、4 timeout | 确认门禁失败 |
| Defects4C 176 | parse/apply/build/Pass = 94/24/17/1 | 174/72/55/1 | 前置阶段改善，最终 Pass 无提升；无退化门禁通过 |

pre-A4 合取门禁为 internal=true、confirmation=false、external=true，唯一 blocker 为 `supplementary_confirmation_passed`；最终 ledger 保持 `a4_ready=false`。这项负结果不能被 exploratory A4 覆盖。

## 7. Exploratory A4 结果

M1-R2 以 temperature 0.7、top-p 0.95 对 264 个已筛选 train-only 案例各生成 4 个候选。执行排序在看见结果前冻结，只按终止阶段和同阶段 timeout 区分；同题最高档与最低档相同则不配对。

| 指标 | 结果 |
|---|---:|
| 候选总数 | 1,056 |
| Parse / Apply / Compile | 1,055 / 805 / 780 |
| 完整 Pass | 123（11.65%） |
| Regression failure / Timeout | 4 / 11 |
| 至少一次成功的案例 | 77/264（经验 Pass@4 29.17%） |
| 偏好对 | 182；另有 82 个案例无严格差异 |
| Chosen 为完整 success | 75 |
| 非 success 阶段信号 | 107 |

file-window 候选 Pass 为 11/32，但只来自 8 个案例，不能宣称其优于 function。训练文件只含 prompt、chosen/rejected 原始 completion、身份与内容哈希；终态和排序理由保存在独立 audit，未向训练输入泄漏 gold、fixed、测试内容或执行反馈。

## 8. 核心结论

1. SFT 最显著的收益是协议遵循：M0 在正式 500 条上全部 parse failed，M1/M1-R2 达到 499/500 可解析；但前置阶段改善远大于最终正确率改善。
2. Apply、compile 和 public success 都不是补丁正确性的替代指标，hidden 与 regression 才暴露行为错误。
3. 旧 holdout 上的正结果没有在新确认集上复现；独立确认是本项目最重要的反过拟合证据。
4. R2 的风险修正存在权衡：汇总 regression/timeout 下降，但最终 Pass 下降且风险样本迁移，不能称为“已修复”。
5. 多候选真实执行能产生有信息量的选择信号，但 A4 来自筛选后的 train-only 分布，经验 Pass@4 不能与未见集 greedy Pass@1 直接比较。
6. 固定分母、预注册门禁、不可变预测、原子 checkpoint、哈希绑定和失败保留，使负结果仍可复核并具有研究价值。

## 9. 已知限制

- 任务只覆盖局部、单文件 C++ 修复，不能外推到多文件仓库级修复。
- confirmation 为 124 条且最终 Pass 全零，现有实验没有证明未见分布上的端到端提升。
- Defects4C 样本明显偏向 LLVM，不能代表均衡的 C++ 项目生态。
- A4 只有 8 个 file-window 案例，且 107/182 偏好对不包含完整 success，信号强度有限。
- 只完成单 seed 主链，没有多 seed replicated result。
- 基础模型预训练污染未知；训练数据和 adapter 的公开再分发许可尚未完成逐来源审计。

## 10. 工程与故障经验

项目中有效的非模型发现包括：Slurm 脚本解释器与依赖关系必须显式；长资格任务应按候选保存原子 checkpoint；推理与训练跨提交消费必须通过 manifest 桥接；rootfs 内路径必须使用沙箱可见路径；同一代码在 `gpu16` 零日志而在 `gpu25` 正常，证明节点故障应通过跨节点对照归因；timeout 长尾必须保留，不能为缩短作业事后删除困难样本。

## 11. 交付与复现

Git 交付包含代码、配置、Schema、测试、Slurm 入口、决策和报告；大型 artifact 继续留在集群并由路径和 SHA256 索引。模型身份、用途和限制见 [M1-R2 模型卡](model_card_m1_r2.md)，文件位置、校验命令和接收清单见[交付说明](README.md)。

本报告不等同于 adapter 或数据的公开发布批准，也不宣称 A5/DPO 已完成。
