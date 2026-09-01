# A0 实验与复现协议

状态：Draft
版本：`0.1.0`

## 1. 模型角色

| 角色 | 模型 | 归因规则 |
|---|---|---|
| M0 | Qwen2.5-Coder-7B Base | 本项目 SFT 起点和 Base 基线 |
| External | 现有 Qwen3-8B | Prompt/Few-shot 强基线，不归因于本人训练 |
| M1 | M0 + SFT adapter | 本项目 SFT 结果 |
| M2 | M1 + DPO adapter | 本项目 DPO 结果 |

Qwen2.5-Coder-7B 固定 revision 为 `0396a76181e127dfc13e5c5ec48a8cee09938b02`。集群的 config、权重索引、tokenizer 和 tokenizer config 哈希已与该官方 revision 匹配；在四个权重分片逐片对照上游 LFS OID 前，报告必须披露“revision 与元数据已验证，完整权重供应链证明待补强”。

## 2. 当前 G0 证据

Job `90719` 已证明当前 A800、Torch 2.11.0+cu130、PEFT 0.18.1、TRL 0.28.0 和 bitsandbytes 0.49.2 支持：

- BF16 Base 加载；
- BF16 LoRA 单 optimizer step；
- NF4 + BF16 compute + double quant；
- QLoRA 单 optimizer step；
- adapter 保存与重载。

G0 不使用正式数据，不能作为 SFT、DPO 或修复能力结论。

## 3. 生成协议

Pass@1 的初始冻结候选配置：

```yaml
do_sample: false
temperature: null
top_p: null
num_return_sequences: 1
max_input_tokens: 4096
max_new_tokens: 512
```

Pass@k 或偏好候选使用单独配置和 seed 集合，不得覆盖 Pass@1 原始预测。正式基线前需通过 tokenizer 长度和停止条件测试。

## 4. Seed

默认根 seed：`20260830`。每个 run manifest 必须保存 Python、NumPy、PyTorch、CUDA 和 sampler seed。多 seed 实验从冻结列表派生，不临时挑选有利 seed。

完全确定性可能降低性能或不被部分 CUDA kernel 支持。若不能严格确定，必须记录 deterministic 设置、库警告和重复运行差异。

## 5. Run ID

推荐格式：

```text
YYYYMMDD-HHMMSSZ_<stage>_<model>_<config8>_<data8>_s<seed>
```

示例：

```text
20260830-130351Z_g0_qwen25coder7b_a62195d6_998a0781_s20260830
```

run ID 不能替代内容哈希。

## 6. 配置冻结

每个可报告 run 保存：

- 解析后的完整配置；
- 原始配置文件；
- 配置 SHA256；
- Git commit 和 dirty 状态；
- 模型和 tokenizer 标识；
- 数据 manifest hash；
- 环境清单 hash；
- Slurm 脚本 hash；
- seed 和生成参数。

命令行覆盖必须进入解析后配置，不能只存在 shell history。

## 7. Artifact 规则

Git 保存：

- 源码；
- 配置；
- Schema；
- 小型 fixture；
- 小型公开摘要和哈希。

祝融持久化目录保存：

- 原始/处理数据；
- 模型和 adapter；
- checkpoint；
- 完整预测；
- 执行日志；
- 大型统计中间产物。

报告引用 artifact URI/路径与 SHA256。不得只引用“latest”。

## 8. Slurm 规则

- 使用真实 `#!/bin/bash` sbatch 文件；
- 提交前 `bash -n`；
- 设置 `PYTHONNOUSERSITE=1`；
- 显式 prefix 并断言 `command -v python`、`sys.prefix`；
- 不在计算作业安装依赖；
- 第一版单 GPU 串行；
- 正式训练每 100～200 optimizer step checkpoint；
- 每段建议 4～8 小时，并支持 resume；
- 只取消本项目且 Job ID 精确确认的作业。

## 9. 阶段门禁

```text
G0 compatibility smoke
→ A0 contract accepted
→ A1 manifests frozen
→ A2 sandbox and baseline frozen
→ A3 LoRA/QLoRA pilot
→ formal SFT
→ A4 executable preference data
→ A5 DPO
→ A7/A8 evaluation and delivery
```

任何后续阶段不得用计划或 mock 结果反向填充上游验收证据。
