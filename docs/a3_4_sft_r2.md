# A3.4：SFT-R2 安全修正轮次

阶段状态：契约与数据选择规则已冻结；集群数据构建、CPU preflight、GPU 训练和评测尚未执行。

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

## 执行顺序

1. 集群 CPU-only 构造 R2 数据并核对选择 manifest。
2. 实现训练/恢复入口和独立 fail-closed preflight；本地与集群测试通过。
3. 单张 GPU 运行 SFT-R2，再以单张 GPU 对原 500 条固定推理。
4. CPU-only scoring v2 和与 M0/M1 的冻结比较。
5. 只有内部指标通过后，才构造新确认集和 Defects4C 外部集；这些数据不得反向用于选择本轮 checkpoint。

当前尚未提交任何 A3.4 Slurm 作业。
