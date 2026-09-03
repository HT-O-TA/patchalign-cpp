# A3.1 评分协议修订与基线重评分

状态：已完成

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

## 6. 实际执行

所有 A3.1 作业均为 CPU-only，未申请或占用 GPU：

- M0 重评分 Job `93822`：`COMPLETED 0:0`，4 CPU、16 GiB，耗时 `00:00:06`，MaxRSS `10080K`；
- External 重评分 Job `93823`：`COMPLETED 0:0`，4 CPU、16 GiB，耗时 `00:00:20`，MaxRSS `6768K`；
- 首次比较 Job `93824`：因比较脚本把 JSON 展示字段 `run_dir` 当作 `Path` 使用而失败，未修改两组评分 artifact；
- 修复后的比较 Job `93828`：`COMPLETED 0:0`，2 CPU、2 GiB，耗时 `00:00:01`，MaxRSS `504K`。

集群专属环境最终全量测试为 `121 passed in 10.24s`。

## 7. 重评分结果

| 基线 | parse v1→v2 | apply v1→v2 | compile v1→v2 | Pass v1→v2 |
|---|---:|---:|---:|---:|
| M0 Base | 2→2 | 0→2 | 0→2 | 0→0 |
| External | 54→54 | 0→13 | 0→13 | 0→0 |

M0 有 67/70 条、External 有 69/70 条原始输出被追加恰好一个终止 LF。该计数覆盖全部 raw output，不等于可解析补丁数。所有因该修订恢复 apply/compile 的补丁最终均未通过 public tests，hidden 与 regression 因而没有进入执行。

关键输出：

```text
M0 scoring-v2:
  artifacts/a3/baseline/m0_base/93717/scoring-v2/93822
  scores.jsonl sha256 ef309d81db6c695cfa457c8b628e7e1562e2cb9e5843290036697fb9d93f8936
  score-summary.json  sha256 e4d2d82af00c965db5bacdc944600f716adbf9022bebd1f6bb7ef7529944db44
  score-manifest.json sha256 60626dc8c34e81d1912eb4c9cf5cf80ee02709fad72c078940a4c091ddf4f345

External scoring-v2:
  artifacts/a3/baseline/external/93718/scoring-v2/93823
  scores.jsonl sha256 3be9eb8ba53d00f2a7940bd64678e6598e87dc2ff6eba1611f066ecc7739f854
  score-summary.json  sha256 00544a9fab8ec0ee316bce647dc93890403fe52f22855138fc76d0b1833560de
  score-manifest.json sha256 ae65e4f5f5814a44a92570c35b3ceaf647630240a3cda09cc393301291e093e5

Comparison:
  artifacts/a3/comparison-a31/93828/comparison.json
  sha256 75d4c5561f6eafef25027f8753240bdaf509885342b9db608fb36b63cdc87112
```

比较器确认：原始 prediction SHA256 未变，70 条顺序、canonical prompt、数据 manifest、seed、source inference 配置与 commit、evaluator commit 和 scoring config 均可比。结论仅是评分传输协议修正，不能表述为模型质量或训练收益；后续 Base/SFT/DPO/External 必须统一使用 `a3-scoring-v2`。
