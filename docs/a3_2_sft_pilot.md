# A3.2 LoRA/QLoRA SFT 小规模训练 Pilot

状态：已完成（2026-09-03）

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

A3.2 已关闭；正式 SFT 尚未启动。

## 7. 实际执行与预检

最终预检 Job `93946` 为 CPU-only，在 `gpu16` 用时 `00:01:05`、MaxRSS `359212K`，完成 `129 passed`、九项 Bubblewrap 自检、gold patch 真实评分、350 条训练/验证 Schema 与 diff/policy 校验、A2 prompt identity 校验及 token 上限校验。训练最大 1,677 tokens，验证最大 1,768 tokens，均未达到 2,048 上限；A2 最大 prompt 为 1,984 tokens。

预检先暴露并关闭了旧 A1 split 泄漏：

- Job `93921` 因 8 GiB 预检内存请求触发 `QOSMaxMemoryPerUser`，未分配节点即取消；
- Job `93927` 发现新单元测试错误复用了 `gold_patch=null` fixture，修复测试后继续；
- Job `93929` 在全部测试通过后 fail-closed 检出旧 pilot 的 26 个跨 split repository family 重叠，其中 20 条 CommitPackFT validation payload 与 train 重复，另有 6 个 RunBugRun problem family 重叠；
- 构建器改为全局隔离 family 并拒绝覆盖旧目录；CPU-only Job `93938` 生成 `pilot-v2-isolated`，train/validation 在 family、sample、base commit、repo_id 和 provenance 五个维度均为零重叠；
- 旧 `pilot-v1-stratified` 保留用于审计，但不得训练。

## 8. 作业与资源

| 阶段 | Job | 资源 | 节点 | Elapsed | MaxRSS |
|---|---:|---|---|---:|---:|
| A1 isolated-v2 rebuild | 93938 | 2 CPU / 4 GiB / 0 GPU | gpu16 | 00:00:44 | 401928K |
| A3.2 final preflight | 93946 | 2 CPU / 2 GiB / 0 GPU | gpu16 | 00:01:05 | 359212K |
| BF16 train + reload + generate | 93951 | 8 CPU / 48 GiB / 1 GPU | gpu19 | 00:13:43 | 17147436K |
| NF4 train + reload + generate | 93952 | 8 CPU / 48 GiB / 1 GPU | gpu19 | 00:12:13 | 2216040K |
| BF16 scoring v2 | 93953 | 4 CPU / 4 GiB / 0 GPU | gpu16 | 00:01:00 | 29956K |
| NF4 scoring v2 | 93954 | 4 CPU / 4 GiB / 0 GPU | gpu16 | 00:00:53 | 163484K |
| comparison | 93955 | 2 CPU / 4 GiB / 0 GPU | gpu16 | 00:00:02 | 620K |

两个 GPU 作业在同一 `gpu19` 串行执行，从未同时占用 GPU。评分作业原请求 16 GiB，`93953` 曾被用户内存配额阻塞；在保持 Job ID 和依赖链不变的前提下降为 4 GiB 后立即运行，实际 MaxRSS 证明 4 GiB 充足，后续 sbatch 默认值同步改为 4 GiB。

## 9. 训练、生成与评分结果

| 模式 | train loss | validation loss | 训练进程秒数 | 生成秒数 | pipeline 秒数 | 峰值 GPU | parse/apply/compile/Pass |
|---|---:|---:|---:|---:|---:|---:|---:|
| BF16 LoRA | 0.189773 | 0.158027 | 449.603 | 313.734 | 808.020 | 18.17 GiB | 70/42/38/1 |
| NF4 QLoRA | 0.190269 | 0.159412 | 162.789 | 515.781 | 725.275 | 11.97 GiB | 70/39/36/1 |
| M0 Base scoring v2 | — | — | — | — | — | — | 2/2/2/0 |

两种模式都完成 300 个 micro-step、38 个 optimizer step、50 条 validation，训练 loss 和 grad norm 均有限。adapter 保存后由独立进程从磁盘重载；两组均 70/70 生成成功、70/70 strict diff、无 OOM/timeout/generation failure，且前 3 条逐字节重复生成全部稳定。BF16 有一条输出达到 512-token 上限，但仍形成可解析 diff；scoring v2 仅给 BF16 一条输出追加终止 LF，NF4 为零条。

BF16 的 1 条 Pass 与 NF4 的 1 条 Pass 都来自 file-window 子集。相对 M0 scoring v2，两者都显著增加 parse/apply/compile 并首次取得 1 条完整 Pass；但 70 条 pilot 不应用正式 400 条 SFT 门禁，也不能给出正式质量提升结论。

## 10. 选择结论与限制

两种模式 Pass 数相同，差值小于 2，触发 `quality_difference_below_two_samples_resource_tiebreak`。NF4 的完整 pipeline 峰值显存更低，因此按 ADR-0004 选择 `nf4_qlora`；本次 pipeline wall time 也更短。BF16 首次模型读取耗时约 301 秒而 NF4 命中共享文件缓存，wall time 不宜单独解释为固有速度差；显存指标已在 wall time 之前决定选择。

已知限制：

- BF16 反向传播触发 Flash Attention 非严格确定性警告；代码固定 seed 与样本顺序，但本 pilot 不声称训练权重逐 bit 可复现；
- 推理使用 greedy decoding，BF16/NF4 各自的 3 条重复生成均逐字节一致；
- bitsandbytes 与 PyTorch 分别报告未来 API 兼容性警告，不影响本次作业完成；
- 该选择只确定正式 SFT 的候选加载方式，不冻结正式训练规模、epoch 或 checkpoint 选择策略。

## 11. 关键 artifact

```text
BF16: artifacts/a3/sft-pilot/bf16_lora/93951
  adapter       5eb7b3d939c02fbe7cacc7090dba9c7cc564eccd21ca8df622d7c127a713d8cd
  predictions   fc82d84191aab8a05134a7ad05ec88b4adae7b1c9a0e24526725c1f064a14cf0
  scores        7252e410c73b6a24b1ceaa03dc42f04291afa8b814e7a3e91b012489aa288654
  score summary 858f3fdcaf172ea251179f74edbf3dcaa0b373cbcba30f9a766419420fc0c3ad
NF4: artifacts/a3/sft-pilot/nf4_qlora/93952
  adapter       0187f53a7c4238e998ca875e38eae81aad0eea2356099a6d8b47ea937d5a7cee
  predictions   59086945de1d9f02fbdb1510ec79da057b18122e127218ea5f35173ad1129943
  scores        efbc99217df54e037d9ff97fced18f27ead079c727992ddd4dab458013581e9e
  score summary 352694d6cc45b897c48400779e7b79fe074a1e6c9779be598570c3d0245589ad
Comparison: artifacts/a3/comparison-a32/93955/comparison.json
  sha256        4e9a436893984bebeb180641e34ee5882854ab527262f52c006f06c948105e56
  decision      c2f103c6250848ff3cfa96a901a73df11ca7efa2c327a95afa0e699c8aea358b
```
