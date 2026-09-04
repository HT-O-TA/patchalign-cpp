# 项目状态

最后核验：2026-09-04 16:02:09 CST（2026-09-04T08:02:09Z）

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
| A3.3 | 进行中 | 5,000/500 SFT 数据、400/100 holdout 和 preflight 已冻结；正式 SFT 正在训练 |

## A3.3 当前有效链

| 阶段 | Job | 状态 | 说明 |
|---|---:|---|---|
| M0 正式推理 | 94338 | COMPLETED 0:0 | 500/500 生成成功，3/3 确定性 probe 稳定 |
| M0 scoring v2 | 94339 | COMPLETED 0:0 | 500 条均为 `parse_failed`；这是模型输出协议结果，不是流水线失败 |
| 正式 NF4 QLoRA SFT | 94340 | RUNNING | `gpu10`，1 GPU；见下方训练快照 |
| M1 正式推理 | 94341 | PENDING (Dependency) | 仅在 94340 成功后加载最佳 adapter |
| M1 scoring v2 | 94342 | PENDING (Dependency) | 仅在 94341 成功后运行 |
| M1 对 M0 比较 | 94343 | PENDING (Dependency) | 仅在两组正式评分可用后运行 |

### 94340 训练快照

- Slurm 已运行 `01:40:25`；训练日志为 `1320 / 1875` optimizer steps，约 `70.40%`。
- 当前处于 epoch 3；最新 `mean_loss=0.0664719981`，`grad_norm=0.3044596314`，没有观察到 NaN、OOM 或 traceback。
- 已落盘 `checkpoint-step-001250-epoch-2`；此前周期 checkpoint 也已成功保存。
- 本快照只说明训练健康度，不构成 M1 修复质量结论。M1 必须完成 500 条独立生成、scoring v2 和冻结门禁比较后才能评价。

## 已冻结的正式数据身份

- preflight Job：94337，Git commit `b9aa00248d4264eca0f75c378b004f462ddea9a6`。
- train/validation：5,000/500；holdout：400 function + 100 file-window。
- formal data lock SHA256：`f37eef03ce0a96ad1fa14622b8b7ef6f30c3f6bcc8dad85addbb1e4c53d12a12`。
- 正式配置 SHA256：`358894a6e8e3b54a1b71ea1884848296c8af6381063cb44fb1a0f70483f4abb4`。
- 完整数据分布、路径和训练参数不在本页重复维护，分别见 [`a3_formal_v1.json`](../configs/data/a3_formal_v1.json) 和 [`a3_sft_formal_v1.json`](../configs/training/a3_sft_formal_v1.json)。

## 当前边界与下一门禁

- 当前尚无 M1 正式评测结果，不能声称 SFT 提升或通过 promotion gate。
- Defects4C 不少于 150 条的外部门禁尚未完成；即使内部 M1 门禁通过，也不能宣称完整 SFT promotion gate 已通过。
- 94340 完成后，依赖链应自动进入 94341、94342 和 94343；任一 `afterok` 前置失败都会阻止后续运行。
