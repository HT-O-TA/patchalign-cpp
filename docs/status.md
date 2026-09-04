# 项目状态

最后核验：2026-09-04 22:46:23 CST（2026-09-04T14:46:23Z）

项目状态：**A3.4 M1-R2 推理已完成，待 scoring v2**。Job `94538` 已完成 500 条生成与确定性重放；GPU 已释放。

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
| A3.4 | 推理完成，待评分 | 500/500 生成成功，499/500 strict diff，3/3 确定性重放稳定 |

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

## A3.4 当前状态

- A3.4 恢复起点审计曾确认三端位于 `cbfb752d85aa2ad3c14f8cfde760b6c21494f31b`，并核对 A3.3 数据锁、M0 预测与评分、正式比较和 timeout 复现哈希；该提交仅是恢复基线，不是当前 HEAD。
- 恢复起点当时没有 PatchAlign 排队或运行作业；管理节点直接 `squeue` 的权限限制不影响后续通过 `sacct` 和 artifact 核验 Job `94521`～`94538`。
- 修正轮次正式命名为 `A3.4 / SFT-R2`，候选为 `M1-R2`；机器配置和方法见 [A3.4 协议](a3_4_sft_r2.md)。
- 静态选择器只消费冻结 A3.3 SFT train/validation；CPU-only Job `94521` 以 `COMPLETED 0:0` 在 2 秒内完成 5 项测试和 1,200/117 集群重建。train/validation SHA256 为 `6eeab690...678cc`、`878abb76...4b73`，selection manifest 为 `7492a373...30ac`。
- preflight Job `94523` 以 `COMPLETED 0:0` 在 28 秒内完成 `145 passed`、数据/adapter/token/holdout 身份校验；报告 SHA256 为 `9da6ed41...ce3b`。
- 单 GPU 训练 Job `94524` 以 `COMPLETED 0:0` 结束，用时 15 分 15 秒；完成 150 optimizer steps，最佳 checkpoint 为 epoch 1/step 150，adapter SHA256 为 `8437acca...425a`。原 500 条 reference validation loss 从 `0.12804146` 变为 `0.13105401`（+`0.00301254`）；该轻微上升只作为遗忘风险信号，最终判断必须等待固定 500 条真实推理与评分。运行代码提交为 `8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c`，A4 仍未启动。
- 固定推理 preflight Job `94537` 完成 `154 passed` 和 prompt 逐字节身份核验。单 GPU Job `94538` 以 `COMPLETED 0:0` 结束，用时 `01:13:49`；500/500 状态为 `ok`，499/500 为 strict diff，3/3 确定性 probe 稳定。predictions/run manifest SHA256 分别为 `c5fe4e6d...7bb6a`、`88abe605...3878`。

## 后续执行清单

1. **已完成**：集群 CPU-only 重建 R2 数据并核对计数、标签分布、输出 SHA256 和 selection manifest（Job `94521`）。
2. **已完成**：实现版本化 R2 训练/恢复入口与 fail-closed preflight；集群全量测试 `145 passed`，preflight Job `94523` 通过。
3. **已完成**：单 GPU SFT-R2 Job `94524` 完成 150/150 optimizer steps并固化最佳 adapter。
4. **已完成**：CPU preflight Job `94537` 和单 GPU 固定推理 Job `94538` 均完成。
5. **下一步**：CPU-only 运行 scoring v2，并分别对 M0 promotion baseline 和 M1 diagnostic baseline 比较；不得修改固定分母或阈值。
6. 若内部指标通过，建立未查看的新确认集并执行 family 隔离、Schema、token 和 Bubblewrap 双重回放。
7. 建立并冻结不少于 150 条的 Defects4C 外部评测集。
8. 只有新候选同时通过 function、bootstrap、parse/apply/compile、regression、timeout、file-window、validity 和外部门禁后，才讨论进入 A4。
