# A3.0 冻结基线协议

状态：执行中

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
