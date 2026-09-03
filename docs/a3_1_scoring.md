# A3.1 评分协议修订与基线重评分

状态：执行中

协议：`a3-scoring-v2`

## 1. 目标

先关闭 A3.0 暴露的终止 LF 传输歧义，再进入 LoRA/QLoRA 训练 pilot。A3.1 不重新运行模型推理，而是对 Job `93717` 和 `93718` 的不可变预测执行 CPU-only 重评分。

## 2. 唯一规范化

评分器读取 prediction 的原始 `raw_text`。仅当它非空且末字符不是 LF 时追加一个 LF；除此之外逐字节保持不变。strict parser、路径策略、`git apply --recount`、C++17 build、public、hidden、regression 和 Bubblewrap 边界均沿用 A3.0。

权威决策见 [ADR-0005](decisions/0005-terminal-lf-normalization.md)，机器配置见 [a3_scoring_v2.json](../configs/evaluation/a3_scoring_v2.json)。

## 3. 输入与不可变性

```text
M0 source:
  artifacts/a3/baseline/m0_base/93717/predictions.jsonl
  sha256:681ba6bdb080dcef5992698fbb7ecf9973035bcd70c70c61d30ca71402c71f49

External source:
  artifacts/a3/baseline/external/93718/predictions.jsonl
  sha256:4dd51b4ad0c42f59eabdf5520482f777dfdccefe3304f1f80a9ed987deb279da
```

两者 source inference commit 均为 `c548c154381eb64389b35eadd1273ab839f9ea30`，A2 manifest SHA256 均为 `10930b2dc915606b8ad17e15bb61c34919d8fc74f755d55e4c0b885899b28305`。重评分不得修改 source 目录中的任何文件。

## 4. 作业链

```text
CPU rescore M0 ─────┐
                    ├─> CPU compare
CPU rescore External┘
```

入口：

- `slurm/a3_1_rescore.sbatch`：4 CPU、16 GiB、0 GPU；
- `slurm/a3_1_compare.sbatch`：2 CPU、2 GiB、0 GPU；
- `scripts/baseline/compare_a3_1_rescores.py`：逐条完整性和可比性审计。

输出：

```text
artifacts/a3/baseline/<role>/<inference-job-id>/scoring-v2/<score-job-id>/
artifacts/a3/comparison-a31/<comparison-job-id>/comparison.json
```

## 5. 完成条件

1. scoring v2 配置、代码、Schema 和测试冻结；
2. 集群全量 pytest 与 Bubblewrap 自检通过；
3. 两组重评分均保持 70 条固定分母；
4. 每条 raw/evaluated SHA256 和规范化标记可重算；
5. comparison 验证 source predictions、prompt、数据、seed、evaluator 和 scoring config 可比；
6. 保存 Job ID、资源、结果与 SHA256；
7. 本机、GitHub、集群同步到同一干净提交。

在上述条件关闭前，不提交 LoRA/QLoRA 训练作业。
