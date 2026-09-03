# A3.2 LoRA/QLoRA SFT 小规模训练 Pilot

状态：执行中

协议：`a3-sft-pilot-v1`

## 1. 目标

使用已冻结的 A1 `300 train + 50 validation` 数据，在同一 Qwen2.5-Coder-7B Base、同一 seed、同一 LoRA 结构和优化参数下，串行比较 BF16 LoRA 与 NF4 QLoRA。该阶段只选择正式 SFT 的可运行方案，不把 70 条 executable pilot 的比例包装成正式模型提升。

## 2. 冻结输入

- Base：`/mingli01/models/Qwen2.5-Coder-7B`；
- upstream revision：`0396a76181e127dfc13e5c5ec48a8cee09938b02`；
- A1 train：300 条，255 function + 45 file-window；
- A1 validation：50 条，43 function + 7 file-window；
- A2 evaluation：70 条，50 function + 20 file-window；
- 根 seed：`20260830`；
- 训练配置：`configs/training/a3_sft_pilot_v1.json`；
- 评分配置：`configs/evaluation/a3_scoring_v2.json`。

A1 train/validation 仅用于监督训练和 validation loss；A2 holdout 仅用于训练结束后的生成与 executable 评分，不参与梯度、checkpoint 选择或超参数调整。

## 3. 公平比较

两种模式共同使用：

- 1 epoch；
- micro-batch 1，gradient accumulation 8；
- 最大序列 2,048 tokens，CPU 预检必须证明不截断；
- learning rate `1e-4`，linear warmup 4 optimizer steps；
- LoRA `r=8`、`alpha=16`、dropout 0；
- q/k/v/o 与 gate/up/down projection；
- gradient checkpointing；
- 同一确定性样本顺序、prompt/target 和验证数据；
- 保存 adapter 后从磁盘重新加载，再进行 70 条 greedy Pass@1 生成；
- 统一使用 A3.0 canonical evaluation prompt 和 `a3-scoring-v2`。

唯一允许差异是 Base 权重加载方式：

- `bf16_lora`：BF16；
- `nf4_qlora`：NF4、BF16 compute、double quant。

## 4. 作业与资源

GPU 训练/生成作业均为单节点、单 GPU。BF16 先提交，NF4 使用 `afterany` 串行依赖；CPU 评分分别使用 `afterok`，最终比较依赖两个评分成功。这样最多同时占用本项目一张 GPU。

产物：

```text
artifacts/a3/sft-pilot/<mode>/<train-job-id>/
├── adapter/
├── training-manifest.json
├── training-summary.json
├── token-stats.json
└── inference/
    ├── predictions.jsonl
    ├── prompts.jsonl
    ├── generation-summary.json
    ├── determinism-probe.json
    ├── run-manifest.json
    └── scoring-v2/<score-job-id>/
```

## 5. 选择规则

只有训练完成、loss 有限、adapter 成功重载、70/70 生成完成且确定性 probe 稳定的模式可以进入比较。按 ADR-0004：

1. 两种模式成功数相差至少 2 条时，选择成功数更高者；
2. 否则不声称质量差异，依次按完整 pipeline 峰值显存更低、wall time 更短、名称字典序选择；
3. 同时报告两者相对 A3.1 M0 Base 的 parse/apply/compile/Pass 变化，但不应用正式 400 条 SFT 门禁。

## 6. 完成条件

1. 配置、训练入口、生成入口、评分链与比较器进入 Git；
2. CPU preflight 验证数据哈希、Schema、gold patch、token 上限、A2 identity、Bubblewrap 和全量测试；
3. 两种模式均完成训练、adapter 重载、70 条生成和 scoring v2；
4. 比较器验证相同数据、模型、prompt、seed、训练超参数和评分协议；
5. 记录 Job ID、资源、wall time、峰值显存、loss、结果与 artifact SHA256；
6. 本机、GitHub、集群同步到同一干净提交。

A3.2 关闭前不启动正式 SFT。
