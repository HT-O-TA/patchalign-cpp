# 项目状态

最后核验：2026-09-04 19:18:53 CST（2026-09-04T11:18:53Z）

项目状态：**已暂停**。暂停期间不提交训练、推理、评分或数据构建作业；当前正式结果和冻结协议保持不变。

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

## 当前边界与下一门禁

- M1 的主修复率提升成立，但冻结的内部门禁整体未通过；不得把主指标通过写成 promotion gate 通过。
- Defects4C 不少于 150 条的外部门禁尚未完成；即使内部 M1 门禁通过，也不能宣称完整 SFT promotion gate 已通过。
- 下一步先把三例真实运行时退化作为训练/解码改进目标；不得删除样本、改写正式评分或事后放宽 timeout 阈值。

## 暂停点与恢复清单

恢复时按以下顺序推进；这些项目目前是待办，不代表已冻结的新实验设计：

1. 核验本地、GitHub 和集群均从暂停提交恢复，确认现有正式 artifact 哈希未变，并确认没有遗留 PatchAlign Slurm 作业。
2. 为 A3 修正轮次建立版本化名称和契约；建议暂称 `SFT-R2`，正式编号需在恢复时冻结。A4 executable preference data 暂不启动。
3. 只从原训练候选中构造循环安全、边界更新和复杂度约束相关样本；禁止使用三条已调查 holdout 的参考补丁、隐藏测试或执行反馈进行训练。
4. 若增加静态危险补丁检查、候选拒绝或多候选重排，必须先版本化推理/评分语义，并明确被拒绝候选如何计入固定分母；不得事后修改 A3.3 结果。
5. 原 500 条 holdout 保留作可比性/开发分析。由于三个失败样本已被逐例检查，最终晋级还需新建一组未查看的确认集，重新执行 family 隔离、Schema、token 和 Bubblewrap 双重回放门禁。
6. 建立并冻结不少于 150 条的 Defects4C 外部评测集；在此之前不得宣称完整 promotion gate 通过。
7. 运行顺序为：CPU 数据审计与 preflight → GPU SFT-R2 → GPU 固定推理 → CPU scoring v2 → 新确认集与外部评测 → 冻结比较。GPU 作业继续串行，默认先申请 1 张。
8. 晋级 A4 前，新的 M1 候选必须在预注册比较中同时满足 function 主提升、bootstrap、parse/apply/compile、regression、timeout、file-window、validity 和外部门禁；现有阈值不得因本轮结果放宽。
