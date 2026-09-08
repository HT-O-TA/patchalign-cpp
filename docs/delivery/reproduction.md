# PatchAlign-Cpp 复现指南

本文给出内部集群上的最小复现路径。代码仓库可公开审阅，但 Base、adapter、数据与完整预测当前
只保留在集群；没有这些受限 artifact 时只能运行静态测试、prompt demo 和合成评分 fixture。

## 1. 身份检查

```bash
cd /mingli01/project/ht/patchalign-cpp
git status --short --branch
git rev-parse HEAD

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
PYTHONNOUSERSITE=1 "$ENV_PREFIX/bin/python" -m pytest -q
sha256sum /mingli01/models/Qwen2.5-Coder-7B/config.json
sha256sum "$ENV_PREFIX/repro/pip-freeze.txt"
```

正式运行要求工作树干净；Base config SHA256 应为
`4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605`，环境锁 SHA256 应为
`bef5b08f129a08a1f720e8698c99606832192d1f77b0f9cce1adc98e3baa43a4`。

## 2. 无 GPU 的 CLI 检查

```bash
cd /mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
export PYTHONPATH="$PWD/src:$PWD"
export PYTHONNOUSERSITE=1

"$ENV_PREFIX/bin/python" -m patchalign.cli prompt \
  --request examples/repair_request.json
```

该命令只验证结构化请求和冻结 prompt，不加载模型。

## 3. 单卡推理 demo

```bash
cd /mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
export PYTHONPATH="$PWD/src:$PWD"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=0

"$ENV_PREFIX/bin/python" -m patchalign.cli infer \
  --request examples/repair_request.json \
  --model-path /mingli01/models/Qwen2.5-Coder-7B \
  --adapter-path /mingli01/project/ht/patchalign-cpp/artifacts/a5/dpo-training-v1.1/beta03/final-adapter \
  --output /tmp/patchalign-demo.patch \
  --metadata /tmp/patchalign-demo.json
```

CLI 固定使用 NF4、greedy decoding 和一个可见 GPU；输出必须通过 strict diff 和路径策略校验。
这只是候选生成，不会自动执行、提交或合并补丁。正式执行必须进入 Bubblewrap 评分链。

## 4. DPO 训练复现

输入身份：

- 175 对偏好数据 SHA256：`892812ae43f551aeff06486963e75806ce6da185f8f41d3df3cff64a6f6ba43c`；
- M1-R2 起点 adapter SHA256：`8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a`；
- 配置：`configs/training/a5_dpo_v1_1.json`。

顺序提交：

```bash
preflight=$(sbatch --parsable slurm/a5_dpo_preflight.sbatch)
smoke=$(sbatch --parsable --dependency="afterok:$preflight" slurm/a5_dpo_gpu_smoke.sbatch)
sbatch --dependency="afterok:$smoke" slurm/a5_dpo_train_array.sbatch
```

正式 array 只包含 beta=0.1 和 beta=0.3 两组。不得在看到开发集结果后修改 seed、数据、epoch、
learning rate 或 beta 再补考。

## 5. 开发集选择复现

```bash
preflight=$(sbatch --parsable slurm/a5_dpo_dev_preflight.sbatch)
infer=$(sbatch --parsable --dependency="afterok:$preflight" slurm/a5_dpo_dev_inference_array.sbatch)
score=$(sbatch --parsable --dependency="afterok:$infer" slurm/a5_dpo_dev_scoring_array.sbatch)
sbatch --dependency="afterok:$score" slurm/a5_dpo_dev_select.sbatch
```

64 条开发集与 A4 训练 case/family 零重叠。选择产物必须匹配 SHA256
`248ad6dcb6783fd2e8c971b05191a87c5b5bd02b696e26f7076262631de665f4`，胜者为 `beta03`。

## 6. 一次性最终评测复现

```bash
preflight=$(sbatch --parsable slurm/a5_dpo_final_preflight.sbatch)
infer=$(sbatch --parsable --dependency="afterok:$preflight" slurm/a5_dpo_final_inference_array.sbatch)
cpp_score=$(sbatch --parsable --dependency="afterok:$infer" slurm/a5_dpo_final_cpp_scoring_array.sbatch)
d4c_score=$(sbatch --parsable --dependency="afterok:$infer" slurm/a5_dpo_final_defects4c_scoring_array.sbatch)
sbatch --dependency="afterok:$cpp_score:$d4c_score" slurm/a5_dpo_final_aggregate.sbatch
```

这条链只生成胜出 DPO 的预测，M1-R2 基线使用已冻结 artifact，不重复消耗 GPU。最终聚合验证
prompt 同一性、配对顺序、固定分母、生成稳定性与全部 artifact 哈希，然后输出：

```text
artifacts/a5/final-evaluation-v1/comparison.json
artifacts/a5/final-evaluation-v1/failure-analysis.json
```

## 7. 不能省略的复现边界

- 所有 Slurm 脚本必须设置 `PYTHONNOUSERSITE=1` 并验证 Conda prefix；
- 不在登录节点直接占用 GPU；
- 不跳过 CPU preflight，不覆盖已存在的正式输出；
- 不删除 generation failure、timeout 或失败样本来改变分母；
- `git apply --recount` 只放宽行号，绝不改写 diff 内容；
- sanitizer 只在样本显式标记适用时执行；
- PyTorch 对部分注意力内核只提供 warn-only 确定性，因此契约可复现不等于权重逐 bit 可复现；
- 数据和 adapter 的公开再分发仍需单独许可与安全审计。
