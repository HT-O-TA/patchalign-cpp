# M1-R2 模型卡

模型名称：PatchAlign-Cpp M1-R2
模型类型：Qwen2.5-Coder-7B Base 上的 LoRA adapter
版本状态：内部研究交付；未公开发布
日期：2026-09-06

## 模型摘要

M1-R2 是用于局部 C++ 缺陷修复研究的 LoRA adapter。它接收固定模板中的缺陷描述、已定位代码上下文和公开失败证据，并生成一个只修改 `main.cpp` 的 unified diff。它不是完整独立模型，使用时必须与精确匹配的 Qwen2.5-Coder-7B Base 一起加载。

本模型显著改善了 Base 的 diff 协议遵循、补丁应用和编译能力，但没有通过全部正式 promotion gate：旧 500 条 holdout 的内部门禁通过，独立 124 条确认集失败，Defects4C 176 条最终 Pass 与 Base 持平。因此它应被视为可复核的研究 checkpoint，而不是已验证可部署的自动修复模型。

## 身份与谱系

| 字段 | 值 |
|---|---|
| Base | `Qwen/Qwen2.5-Coder-7B` |
| Base revision | `0396a76181e127dfc13e5c5ec48a8cee09938b02` |
| Base config SHA256 | `4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605` |
| 起始 adapter（M1）SHA256 | `807fa6de2d07bf9fd5e3ebbba9879e8aab77769d3d4ed1b31d184f234297350f` |
| M1-R2 adapter SHA256 | `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a` |
| Adapter 大小 | 80,792,096 bytes |
| 训练 run | `a34_sft_r2_nf4_s20260830` / Slurm Job `94524` |
| 训练代码 commit | `8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c` |
| Seed | `20260830` |
| 训练 manifest SHA256 | `b85f43a5edf194b2edfc57cb456459ce1b149b015d5392ee66f1ec97c2ebd884` |

集群内部 adapter 路径：

```text
/mingli01/project/ht/patchalign-cpp/artifacts/a3/sft-r2/training/checkpoints/checkpoint-step-000150-epoch-1/adapter/adapter_model.safetensors
```

该路径是内部交付位置，不是稳定公共下载地址。

## 训练数据

M1-R2 从 A3.3 正式 M1 adapter 继续训练。M1 使用 5,000 条 train 和 500 条 validation，来源为 CommitPackFT C++ 与 RunBugRun C++。R2 continuation 使用 1,200 条 train 和 117 条 focused validation，只从冻结 A3.3 train/validation 静态选择循环、边界和复杂度风险模式。

R2 数据 selection manifest SHA256 为 `7492a3732e3b0a6546e6b733a7fbb0314a63abd1f9069220b605e96061f630ac`。正式 internal holdout、独立 confirmation、Defects4C、gold patch、fixed source、hidden tests 和执行反馈均未用于 R2 checkpoint 选择。

数据的逐来源再分发许可尚未完成审计，因此模型卡不授予训练数据或 adapter 的再分发许可。

## 训练方法

| 参数 | 值 |
|---|---|
| 模式 | NF4 QLoRA adapter continuation |
| Epochs | 1 |
| Optimizer steps | 150 |
| Micro batch / gradient accumulation | 1 / 8 |
| Learning rate | `2e-5` |
| Max sequence length | 4,096 tokens |
| LoRA rank / alpha / dropout | 8 / 16 / 0.0 |
| Target modules | q/k/v/o projection 与 gate/up/down projection |
| Focused validation loss | `0.0771820154` |
| Reference validation loss | `0.1280414615` → `0.1310540061` |
| Peak GPU memory | 17,933,322,752 bytes |
| 训练时长 | 15 分 15 秒 |

环境快照 SHA256 为 `bef5b08f129a08a1f720e8698c99606832192d1f77b0f9cce1adc98e3baa43a4`。关键版本为 Python 3.10 环境、PyTorch 2.11.0、Transformers 4.57.6、PEFT 0.18.1、Accelerate 1.13.0、bitsandbytes 0.49.2、Datasets 3.6.0 和 TRL 0.28.0。

## 评测协议与结果

正式生成使用 greedy Pass@1、`max_new_tokens=512` 和固定 prompt。评分器只允许一个 unified diff，执行 `git apply --recount`，再在 rootless Bubblewrap 中按 build、public、hidden、regression 顺序验证；sanitizer 只在样本明确适用时运行。

| 数据 | 结果 | 解释 |
|---|---|---|
| 旧 internal holdout 500 | parse/apply/compile/Pass = 499/412/392/14；function 11/400；regression 3；timeout 2 | 相对 M0 function `+2.75pp`，旧 holdout 内部门禁通过 |
| 独立 confirmation 124 | 0/124 Pass；相对 M0 新增 3 regression failure、4 timeout | 确认门禁失败，不能声称泛化 |
| Defects4C 176 | parse/apply/build/Pass = 174/72/55/1；0 timeout | Base 同为 1/176；前置阶段改善但最终 Pass 无提升 |

固定推理 predictions SHA256 为 `c5fe4e6d90d59c24f749949c8df4f074e2b26f6af625e960ce95013367e7bb6a`；scoring scores SHA256 为 `f05b54a107850591c0cfc16564ef477488cacfe50cb6b703ace41fb093c650b8`。完整 promotion 状态为 internal=true、confirmation=false、external=true，`a4_ready=false`。

## 预期用途

- 在隔离环境中研究局部 C++ 补丁生成、输出协议和执行式评测；
- 复现本项目固定 holdout、确认集与外部评测；
- 在人工审阅下生成候选补丁，研究失败类型或偏好数据构造。

## 非预期用途

- 不应直接对生产仓库自动提交、合并或部署补丁；
- 不适用于多文件修改、仓库自主探索、依赖升级或安全关键系统；
- 不应把可解析、可应用、可编译或通过公开测试单独当作正确性证明；
- 不应基于本模型宣称 C++ 修复能力已经在未见分布上泛化；
- 不应在未完成许可和安全审计时公开分发 adapter、训练数据或完整预测。

## 风险与限制

- 独立 confirmation 上最终 Pass 为零，并出现新的 regression 和 timeout；
- Defects4C 中 139/176 来自 LLVM，外部分布不均衡；
- 模型只在单 seed 主链上训练和评测，未达到 replicated result；
- 任务限于单文件和局部上下文，无法处理许多真实仓库级依赖；
- Base 预训练污染未知；
- 模型生成代码可能包含逻辑错误、无限循环、资源消耗或不安全行为，必须在最小权限沙箱内执行。

## 使用与复现入口

在集群内应从固定 Base、上述 adapter 和版本化推理配置共同恢复，不直接依赖 `latest`：

- 训练配置：`configs/training/a3_sft_r2_v1.json`
- 推理配置：`configs/evaluation/a3_sft_r2_inference_v1.json`
- 推理入口：`scripts/training/run_a3_sft_r2_inference.py`
- Slurm 入口：`slurm/a3_4_infer_preflight.sbatch`、`slurm/a3_4_infer.sbatch`
- 评分配置：`configs/evaluation/a3_sft_r2_scoring_v1.json`

加载前必须先核验 Base revision、adapter SHA256、training manifest 和环境快照。模型输出不得在宿主机直接执行。

## 许可与发布状态

仓库原创代码和文档采用 Apache-2.0，但该许可证不会自动覆盖 Base 权重、训练数据、adapter、生成补丁或第三方依赖。M1-R2 当前只作内部研究交付；公开发布尚未获准，逐来源许可、敏感信息、漏洞披露和 NOTICE 审计仍是前置条件。
