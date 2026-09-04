# A3.4：SFT-R2 安全修正轮次

阶段状态：数据冻结、CPU preflight 和单 GPU SFT-R2 训练已完成；固定 500 条推理的独立 artifact 绑定与作业入口已实现，等待集群 preflight。

## 目标

A3.3 的 M1 在冻结 500 条 holdout 上取得 15/500 Pass，function 相对 M0 提升 3 个百分点，但模型补丁引入 3/500 timeout，使 timeout 退化 0.6 个百分点并超过 0.5 个百分点上限。A3.4 的目标是在不修改 A3.3 历史结果、不查看更多 holdout 答案的前提下，训练一个降低循环与复杂度危险修改倾向的 SFT 候选。

本轮正式名称为 `A3.4 / SFT-R2`，候选简称 `M1-R2`。A4 executable preference data 不在本轮范围内。

## 数据契约

机器事实源为 [`a3_sft_r2_v1.json`](../configs/data/a3_sft_r2_v1.json)，构造器为 [`build_a3_sft_r2_data.py`](../scripts/data/build_a3_sft_r2_data.py)。

- 唯一输入是 A3.3 已冻结的 5,000/500 SFT train/validation；输入数据锁 SHA256 为 `f37eef...12a12`。
- 只保留 `RunBugRun/function`，再根据 gold diff 的通用静态语法信号选择循环控制/推进、边界/索引更新、规模/分配复杂度相关修复。
- 选择器不读取 problem statement、正式 holdout、测试内容或执行反馈；不会读取三条已调查 timeout 样本的参考补丁、hidden test 或 fixed 代码。
- 输出保持原 Sample Schema v0.2 记录不变，安全标签只写入 selection manifest。
- 冻结输出为 1,200 train、117 validation；train 标签计数为 938/637/19，validation 为 89/55/1。标签可重叠，不能相加作为样本数。
- train/validation 样本交集必须为 0；来源文件、输出文件、选择规则和计数全部哈希绑定。

## 训练契约

机器事实源为 [`a3_sft_r2_v1.json`](../configs/training/a3_sft_r2_v1.json)。

- 从 A3.3 M1 的最佳 epoch 2 / step 1,250 adapter 继续训练；adapter SHA256 为 `807fa6...350f`。
- Base 模型、revision、NF4 QLoRA、LoRA 结构、seed、4,096 token 上限和确定性设置保持不变。
- 重置 optimizer/scheduler，不恢复 A3.3 optimizer state；学习率 `2e-5`、warmup 20 steps、gradient accumulation 8，在 1,200 条安全聚焦 train 上训练 1 epoch，共应为 150 optimizer steps。
- 每 50 optimizer steps 保存 checkpoint；聚焦 validation loss 用于 fail-closed 检查。原 500 条 validation 在训练前后只报告 loss，不参与 checkpoint 选择，防止看到正式 holdout 后选择模型。
- 单轮、较低学习率和固定起始 adapter 用于限制对 A3.3 已学补丁协议的破坏；是否真的保住能力只能由冻结 executable 评测判断。

## 推理、评分与门禁

- 不增加候选过滤、静态拒绝、多候选生成或重排。
- 继续使用原 500 条 holdout、`a3-cpp-repair-v1`、raw completion、greedy Pass@1、512 输出 token 和 `a3-scoring-v2`。
- generation、parse、apply、build、test 和 timeout 失败全部保留在固定 500 分母内。
- `M1-R2` 对 M0 运行原 SFT promotion gate；同时对 M1 做诊断比较，明确报告 Pass 和三个 timeout 样本的逐例变化，但不据此修改门禁。
- timeout 相对 M0 最多增加 0.5 个百分点，因此 500 条中最多允许 2 个 timeout；function 主提升仍至少为 2 个百分点且 paired-bootstrap 95% 下界不小于 0。其余 parse/apply/compile、regression 和 file-window 上限保持 ADR-0004 不变。
- 原 500 条 holdout 已用于开发分析，只能用于可比性结果。晋级 A4 前仍必须建立未查看的新确认集，并完成不少于 150 条 Defects4C 外部门禁。

## 推理 artifact 绑定

训练 Job `94524` 必须保留其原始提交 `8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c`，不得为了运行后续代码而改写 training manifest。固定推理使用独立配置 `configs/evaluation/a3_sft_r2_inference_v1.json`，同时绑定训练 commit、training manifest/summary、best-checkpoint、adapter、模型 revision 和 holdout manifest 的 SHA256；推理 preflight 与推理本身再绑定新的实现提交。由此允许经过审计的跨提交 artifact 消费，同时拒绝未声明的训练权重或数据变化。

## 评分 artifact 绑定

scoring v2 只消费 Job `94538` 已固化的不可变预测。`configs/evaluation/a3_sft_r2_scoring_v1.json` 精确绑定 predictions、run manifest、generation summary、determinism probe、adapter、推理提交、holdout manifest、scoring v2 配置和 Bubblewrap 身份。评分 preflight 在创建输出目录前校验全部身份；正式评分继续复用 A3.1 冻结评分器，不修改固定分母、终止 LF 规范化、`git apply --recount` 或测试语义。

## 执行顺序

1. 集群 CPU-only 构造 R2 数据并核对选择 manifest。
2. 实现训练/恢复入口和独立 fail-closed preflight；本地与集群测试通过。
3. 单张 GPU 运行 SFT-R2，再以单张 GPU 对原 500 条固定推理。
4. CPU-only scoring v2 和与 M0/M1 的冻结比较。
5. 只有内部指标通过后，才构造新确认集和 Defects4C 外部集；这些数据不得反向用于选择本轮 checkpoint。

CPU-only 数据 Job `94521` 以 `COMPLETED 0:0` 结束，耗时 2 秒并通过 5 项定向测试。Preflight Job `94523` 以 `COMPLETED 0:0` 结束，耗时 28 秒并通过全量 `145 passed`；报告 SHA256 为 `9da6ed4148026d2f0b472ce97577da60f746444b84cde491951fb7b1d885ce3b`。单 GPU 训练 Job `94524` 在 `gpu10` 以 `COMPLETED 0:0` 结束，用时 15 分 15 秒并完成 150 optimizer steps。最佳 checkpoint 为 epoch 1/step 150，focused validation loss 为 `0.07718202`；原 500 条 reference validation loss 从 `0.12804146` 上升至 `0.13105401`。最佳 adapter SHA256 为 `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a`，training summary/manifest SHA256 分别为 `4cab1f118ebddc90e69e5f3d202b96906c5ab399d00906adc842c6f378cf2f4d` 和 `b85f43a5edf194b2edfc57cb456459ce1b149b015d5392ee66f1ec97c2ebd884`。绑定实现提交仍为 `8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c`；训练作业结束时尚未预提交推理。


CPU-only 固定推理 preflight Job `94537` 在实现提交 `84fb9dfe06c4530b8fab32d03ef3e15d803a94e7` 上以 `COMPLETED 0:0` 结束，用时 21 秒并通过全量 `154 passed`。报告确认 500 条组成 400/100、输入 token 范围 170～3,589，重建 prompt artifact SHA256 `1a1c8cb2c827c6c6325db798991bb3c9b66241520ae70520cdbdd18e6188ba1f` 与 A3.3 M0/M1 完全一致；报告 SHA256 为 `8eb0350779242ee62dd5c734a0e8f44cdcf70fb00a15c70131cdde84f120f88c`。单 GPU 正式推理 Job `94538` 随后在 `gpu10` 启动，并以 `COMPLETED 0:0` 结束，用时 1 小时 13 分 49 秒。500/500 生成状态为 `ok`，499/500 为 strict diff，3/3 确定性 probe 稳定；generation failure、OOM 均为 0。predictions、run manifest、generation summary、determinism probe SHA256 分别为 `c5fe4e6d90d59c24f749949c8df4f074e2b26f6af625e960ce95013367e7bb6a`、`88abe6053202e8b81e0332166c3e6b66fefca3e50a0f36b39cdffae086983878`、`eb82f96cef4c103a4944f888f0d171307f1a25d3b35b15d780d5c18b1d26c09a`、`3176c6a73d397561b75a3215a74380626dc290e4c41fc67111999202d790a38a`。scoring v2 尚未提交。


A3.4 scoring 实现提交 `22efebfa27afdaad09d4f08e7c8bdebafb1e0e27` 在集群通过全量 `163 passed`。CPU-only Job `94558` 随后启动，申请 4 CPU、4 GiB、0 GPU；artifact preflight 已确认 500 条预测、499 条 strict diff、3 条稳定 probe 及全部冻结哈希，正在执行 scoring v2。preflight config SHA256 为 `2e44189ed400fdd497a4508d488be702c61c71ff7d6663192fc142f6a9cb3e4a`。
