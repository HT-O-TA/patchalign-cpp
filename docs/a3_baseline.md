# A3.0 冻结基线协议

状态：已完成（A3.0 executable pilot）

版本：`a3-baseline-v1`

## 1. 目标与边界

A3.0 在 A2 已冻结的 70 条可执行 C++ pilot 上运行两个 Pass@1 基线：

- M0：`Qwen/Qwen2.5-Coder-7B` Base；
- External：本地 `Qwen/Qwen3-8B` post-trained 强基线，不归因于本项目训练。

结果只用于建立 A3 pilot 的起点、验证模型生成到安全评分的闭环，并观察失败分布。它不是正式 400 function + 100 file-window 内部评测，也不形成 SFT/DPO 提升结论。

## 2. 冻结输入

- 数据：`/mingli01/data/patchalign-cpp/a2/holdout-v3`；
- 组成：50 function + 20 file-window；
- allowed path：`main.cpp`；
- 每条 prompt 只包含任务/格式约束、task level、一个 public 失败示例和 `buggy.cpp`；
- 不包含 fixed code、gold patch、hidden test 或 regression test；
- A2 artifact 没有自然语言 problem statement，因此 prompt 明确披露该字段不可用，不进行猜测或补写。

完整 canonical prompt 对两模型相同。M0 使用 raw completion；Qwen3-8B 使用其官方 chat template 且 `enable_thinking=false`。两者 tokenizer 渲染不同，但可见语义信息、样本顺序与生成预算相同。

## 3. 冻结生成参数

配置文件：`configs/evaluation/a3_baseline_v1.json`。

```text
do_sample=false
temperature=null
top_p=null
num_return_sequences=1
max_input_tokens=4096
max_new_tokens=512
seed=20260830
```

每个模型完成 70 条后，对稳定排序的前 3 条再次生成，raw completion 必须逐字节一致，否则作业 fail closed。

## 4. 模型身份

M0 固定 revision：

```text
0396a76181e127dfc13e5c5ec48a8cee09938b02
```

M0 `config.json` 必须匹配冻结 SHA256。Qwen3-8B 本地目录来自 ModelScope，`.msc` 显示文件 revision 不完全一致，因此当前 `model_revision=null` 并披露 `local_modelscope_snapshot_with_mixed_file_revisions`；不得将 `master` 写成精确、统一的 upstream commit。

## 5. 评分

模型原始 completion 不做围栏剥离、自然语言恢复、diff 修补或行号修复。评分顺序为：

```text
generation
→ strict unified diff parse
→ one-file path policy
→ git apply --recount --check
→ git apply --recount
→ C++17 build
→ public
→ hidden
→ regression
```

apply、编译和测试全部复用 A2 的 rootless、禁网 Bubblewrap 边界和 RunBugRun legacy 输出匹配器。固定分母保留 generation、parse、apply、build 和 timeout 失败。

## 6. Artifact

集群本地化目录：

```text
artifacts/a3/
├── logs/
├── baseline/
│   ├── m0_base/<inference-job-id>/
│   │   ├── prompts.jsonl
│   │   ├── predictions.jsonl
│   │   ├── determinism-probe.json
│   │   ├── generation-summary.json
│   │   ├── run-manifest.json
│   │   └── scoring/
│   └── external/<inference-job-id>/
│       └── ...
└── comparison/<comparison-job-id>/comparison.json
```

大型预测、逐测试结果和日志不进入 Git；文档只记录 Job ID、统计、路径和 SHA256。

## 7. 完成条件

A3.0 只有同时满足以下条件才关闭：

1. CPU 预检验证两个 tokenizer 的全部 prompt 不超过 4,096 tokens，且 gold patch 能通过真实沙箱评分；
2. M0 和 External 推理作业均完成 70 条且 generation failure/OOM 为 0；
3. 两模型的 3 条确定性 probe 全部稳定；
4. 两组预测均在 A2 沙箱中按固定 70 条分母完成评分；
5. 可比性检查确认 Git commit、配置、数据 manifest、seed、样本顺序和 canonical prompt hash 一致；
6. 保存比较结果、资源统计、完整失败分类及全部关键 SHA256；
7. 仓库测试通过，本机、GitHub 和集群同步到同一干净提交。

## 8. 最终运行与资源

2026-09-03 完成以下作业链。两个推理作业各申请 1 张 GPU，按队列先后在 `gpu14` 串行运行；预检、评分和比较均未申请 GPU。提交时课题组 GPU 配额为 20 张且已占满，因此作业最初因 `AssocGrpGRES` 排队；未取消或修改他人作业，仅将本项目推理时限从 6 小时收紧为 2 小时以利于 backfill。

| 阶段 | Job | 状态 | 节点 | 耗时 | GPU | MaxRSS |
|---|---:|---|---|---:|---:|---:|
| CPU 预检 | 93715 | COMPLETED 0:0 | gpu16 | 00:03:30 | 0 | 1,179,520K |
| M0 推理 | 93717 | COMPLETED 0:0 | gpu14 | 00:16:29 | 1 | 16,578,320K |
| External 推理 | 93718 | COMPLETED 0:0 | gpu14 | 00:14:54 | 1 | 16,504,228K |
| M0 评分 | 93719 | COMPLETED 0:0 | gpu16 | 00:00:02 | 0 | 3,056K |
| External 评分 | 93720 | COMPLETED 0:0 | gpu16 | 00:00:05 | 0 | 7,984K |
| 比较 | 93721 | COMPLETED 0:0 | gpu16 | 00:00:01 | 0 | 716K |

预检在提交 `c548c154381eb64389b35eadd1273ab839f9ea30` 上完成 `111 passed`、九项 Bubblewrap 自检和 gold patch 全链路评分。70 条 prompt 的最大长度为 M0 1,984 tokens、External 1,996 tokens，均低于 4,096；冻结配置 SHA256 为 `d1747f8ad4ddaa904a2ab618e6648cf0a40a4da05e51e2543c6609b6ec9730dc`。

## 9. 基线结果

| 指标 | M0 Base | External |
|---|---:|---:|
| generation failure / OOM / timeout | 0 / 0 / 0 | 0 / 0 / 0 |
| 确定性 probe | 3/3 稳定 | 3/3 稳定 |
| strict diff parse | 2/70 | 54/70 |
| apply / compile / success | 0/70 | 0/70 |
| 终态分类 | 68 parse_failed, 2 apply_failed | 16 parse_failed, 4 policy_violation, 50 apply_failed |
| 输入 / 输出 tokens | 45,256 / 28,982 | 46,096 / 23,499 |
| 模型加载 / 生成 | 297.905s / 615.975s | 92.631s / 757.835s |
| 峰值 GPU tensor bytes | 15,638,064,128 | 16,898,003,456 |

M0 的 function/file-window 成功数为 `0/50`、`0/20`；External 同为 `0/50`、`0/20`，External-M0 差值为 0。比较器确认 Git commit、配置、A2 manifest、seed、案例顺序和 canonical prompt 均一致。该结果只证明 A3.0 生成—安全评分闭环和当前提示/输出协议下的 pilot 起点，不支持模型质量优劣或 SFT/DPO 效果结论。

Artifact：

```text
M0:        /mingli01/project/ht/patchalign-cpp/artifacts/a3/baseline/m0_base/93717
External:  /mingli01/project/ht/patchalign-cpp/artifacts/a3/baseline/external/93718
Comparison:/mingli01/project/ht/patchalign-cpp/artifacts/a3/comparison/93721/comparison.json
Logs:      /mingli01/project/ht/patchalign-cpp/artifacts/a3/logs
```

关键 SHA256：

```text
M0 predictions:       681ba6bdb080dcef5992698fbb7ecf9973035bcd70c70c61d30ca71402c71f49
M0 scores:            d7f82d80810d83323f5c9a79ab53742a0309eb6f9b2c3bd46f4d40bbf11b81e9
External predictions: 4dd51b4ad0c42f59eabdf5520482f777dfdccefe3304f1f80a9ed987deb279da
External scores:      ada1ad925c6f0d077c9ab8ce585525fdfe64a940ece00d36395374d9ab39420e
Comparison:           87ef35d9cf8c860d72c9de0e4ddb36dd5ce19565cb0ddb2451d0a546b48211dc
```

## 10. 行尾诊断与 A3.1 边界

本次所有通过 strict diff parser 的 56 个 raw completion 都没有以 LF 结尾。只用于诊断地给 raw completion 追加一个 `\n` 后，M0 的 2/2 和 External 的 13/50 apply failure 可通过 `git apply --recount --check`；External 其余 37 条仍因内容或上下文不匹配失败。该探针不属于冻结评分，没有覆盖 artifact，也没有重计 Pass；A3.0 的正式结果仍是两组 0/70。

A3.1 在训练前必须显式选择并版本化以下一种语义：要求模型输出终止 LF，或在评分入口做固定、可审计的单个终止 LF 规范化。决定前不得静默改变 `a3-baseline-v1`、回填本次结果或据此启动正式质量比较。
