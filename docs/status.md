# 项目状态

最后核验：2026-09-06 00:34 CST（2026-09-05T16:34Z）

项目状态：**A3.4 全部 pre-A4 评测与 readiness 已完成；A4 仅以负责人授权的 exploratory 模式运行**。内部与 Defects4C 外部门禁通过，但 124 条新确认集门禁失败，因此正式晋级仍被阻断，账本保持 `a4_ready=false`。A4 修正后的 CPU 数据 Job `95586` 正在双重资格筛选，依赖式单 GPU 生成 Job `95587` 已排队；不得表述为晋级或门禁通过。

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
| A4 | 负责人授权 exploratory 进行中 | 修正后 CPU 数据 Job `95586` 运行中；单 GPU Job `95587` 以 `afterok:95586` 依赖排队 |

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

- A3.3 的 M1 主修复率提升成立，但 timeout 超限，历史门禁结论保持未通过。
- A3.4 的旧 500 条内部门禁通过，但未见确认集门禁已经失败；无论 Defects4C 最终结果如何，M1-R2 都不能晋级 A4。
- Defects4C 已按原协议完成 176 条固定分母成对评测；M0/M1-R2 均为 1/176 Pass、0 timeout，外部门禁通过，但没有最终 Pass 提升。
- pre-A4 readiness 已绑定内部、确认和外部三项 artifact；确认集是唯一 blocker，因此 `a4_ready=false`、`a4_started=false`。
- ADR-0006 允许在该失败账本之后以 `owner_authorized_exploratory` 模式进入 A4；该授权不改变 A3.4 门禁结论。

## A3.4 当前状态

- A3.4 恢复起点审计曾确认三端位于 `cbfb752d85aa2ad3c14f8cfde760b6c21494f31b`，并核对 A3.3 数据锁、M0 预测与评分、正式比较和 timeout 复现哈希；该提交仅是恢复基线，不是当前 HEAD。
- 恢复起点当时没有 PatchAlign 排队或运行作业；管理节点直接 `squeue` 的权限限制不影响后续通过 `sacct` 和 artifact 核验 Job `94521`～`94538`。
- 修正轮次正式命名为 `A3.4 / SFT-R2`，候选为 `M1-R2`；机器配置和方法见 [A3.4 协议](a3_4_sft_r2.md)。
- 静态选择器只消费冻结 A3.3 SFT train/validation；CPU-only Job `94521` 以 `COMPLETED 0:0` 在 2 秒内完成 5 项测试和 1,200/117 集群重建。train/validation SHA256 为 `6eeab690...678cc`、`878abb76...4b73`，selection manifest 为 `7492a373...30ac`。
- preflight Job `94523` 以 `COMPLETED 0:0` 在 28 秒内完成 `145 passed`、数据/adapter/token/holdout 身份校验；报告 SHA256 为 `9da6ed41...ce3b`。
- 单 GPU 训练 Job `94524` 以 `COMPLETED 0:0` 结束，用时 15 分 15 秒；完成 150 optimizer steps，最佳 checkpoint 为 epoch 1/step 150，adapter SHA256 为 `8437acca...425a`。原 500 条 reference validation loss 从 `0.12804146` 变为 `0.13105401`（+`0.00301254`）；该轻微上升只作为遗忘风险信号，最终判断必须等待固定 500 条真实推理与评分。运行代码提交为 `8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c`，A4 仍未启动。
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
11. **执行中**：首次 CPU Job `95574` 因 27 个 `file_window` 备用候选与至少 5 条测试门槛不可同时满足而失败，失效 GPU Job `95575` 已取消；ADR-0007 保留测试门槛并将备用池修正为 26。新 CPU Job `95586` 已生成 600 function + 26 file_window 候选并开始双重资格筛选，单 GPU Job `95587` 依赖排队。A5 未授权。
