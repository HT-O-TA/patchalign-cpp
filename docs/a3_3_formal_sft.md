# A3.3 正式 SFT 准备与冻结

状态：静态契约与实现已冻结；首次 CPU 数据 Job 94111 超时，未生成正式 holdout/SFT；可恢复替代实现已通过集群 135 项测试，等待重新提交依赖链。

## 冻结契约

- 基座：`Qwen/Qwen2.5-Coder-7B`，revision `0396a76181e127dfc13e5c5ec48a8cee09938b02`。
- 训练集/验证集：5,000/500；CommitPackFT 为 2,000/200，RunBugRun 为 3,000/300。
- 任务级别：训练 4,250 function + 750 file_window；验证 425 + 75。
- 正式内部留出集：400 function + 100 file_window；与 SFT 数据按 problem/repository family 隔离。
- A1 pilot-v2 的 300/50 原样嵌入；单个 repository/problem family 在单一 split 中最多 2 条。
- 修改类型 35%/50%/10%/5% 是分布目标。受真实来源稀缺约束时记录实际值和偏差，不合成样本、不降低过滤条件。
- Schema、精确配额、payload 去重、family 隔离、最长 4,096 token 和产物 SHA-256 均为 fail-closed 检查。

## 训练冻结

- A3.2 资源平局按显存占用选择 `NF4 QLoRA`。
- 3 epochs；micro batch 1；gradient accumulation 8；学习率 `1e-4`；linear warmup 50 optimizer steps；weight decay 0；max grad norm 1。
- LoRA：r=8、alpha=16、dropout=0，作用于 q/k/v/o、gate/up/down projection。
- 每 200 optimizer steps 以及每个 epoch 末保存可恢复 checkpoint。
- 每个 epoch 末对完整 500 条 validation 计算 loss；最低有限 validation loss 胜出，相同时选择更早 optimizer step。
- 正式 500 条测试集不参与 checkpoint 选择。
- 单次 Slurm 时限 8 小时，训练器在 7 小时 40 分主动落 checkpoint。按 A3.2 吞吐估算，本轮应在一个 segment 内完成；若未完成，使用同一脚本和输出目录恢复，不改变超参数。

## 正式评测与门槛

- M0 基座和 M1 SFT 使用同一个冻结 400/100 内部留出集、同一 NF4 加载方式、同一 prompt、贪心解码和 `a3-scoring-v2`。
- SFT 在 400 function 上需绝对提升至少 2 个百分点，paired bootstrap 10,000 次、seed 20260830，置信区间下界需不小于 0。
- parse/apply/compile 最大退化 1pp；regression 最大增加 1pp；timeout 最大增加 0.5pp；file_window Pass 最大退化 3pp。
- sanitizer 仅对 manifest 中明确适用的样本执行。
- Defects4C 外部集尚未落地；内部正式训练和比较可以执行，但在外部不少于 150 条的门槛完成前，不宣称完整 SFT promotion gate 通过。

## 资格筛选恢复策略

- Job 94111 在 6 小时时限到达后以 TIMEOUT 结束；它已完成 133 项测试、Bubblewrap 自检和 900/250 候选池构建，但没有写出正式 holdout、SFT、哈希锁或 preflight。
- 原实现先对全部 1,150 个候选、合计 109,024 个测试实例执行 buggy/fixed 回放，全部结束后才选择 400/100 并写盘；这使任何超时都会丢失本轮筛选进度。
- 替代实现按固定 function、file_window 顺序，每批 16 个并行筛选；每个候选完成后立即以原子 JSON 检查点写入独立 progress 目录。
- 恢复时必须精确匹配候选 manifest SHA-256、候选版本、所需任务配额、沙箱策略和输出匹配器；不匹配即 fail closed。
- 每个任务层达到冻结配额即停止。作业超时时，重新提交同一脚本会跳过已经持久化的候选，仅损失当时尚未完成的进程。
- 资格筛选与 SFT 构建/冻结/preflight 拆为两个 CPU 作业；后者只能在前者成功后运行。冻结锁先生成，preflight 再校验该锁。

## 作业链

1. CPU 双重 replay qualification，可恢复地冻结 400/100 holdout。
2. CPU 构建 SFT 数据、生成哈希锁并执行正式 preflight。
3. GPU M0 正式推理。
4. GPU NF4 QLoRA 正式训练。
5. GPU 加载最佳 adapter 正式推理。
6. CPU 分别评分并执行冻结质量门比较。

GPU 作业通过 `afterok` 串行依赖；前置失败时不得继续运行。CPU 的 M0 评分可与 GPU 训练并行，不增加 GPU 占用。

## 2026-09-04 作业编号

| 阶段 | Job | 资源 | 结果 |
|---|---:|---|---|
| 候选构建与旧资格回放 | 94111 | CPU | 6:00:29 后 TIMEOUT；候选池保留 |
| M0 推理 / M0 评分 | 94118 / 94119 | GPU / CPU | 未执行，已取消 |
| 正式 SFT | 94120 | GPU | 未执行，已取消 |
| M1 推理 / M1 评分 | 94121 / 94122 | GPU / CPU | 未执行，已取消 |
| 质量门比较 | 94123 | CPU | 未执行，已取消 |
