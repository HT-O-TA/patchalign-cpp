# PatchAlign-Cpp 执行记录

> 用途：持续记录第二项目已经真实完成、正在进行和仍被阻塞的事项。
> 记录原则：只写可由命令、文件、作业或用户确认支持的事实；不把计划写成完成。
> 首次建立：2026-08-30 18:28 CST（祝融 2026-08-30 10:28 UTC）

目录结构的独立台账见：`/home/lenovo/A/patchalign-cpp/docs/records/第二项目_PatchAlign-Cpp_目录结构.md`。发生较大目录更新时，应同步更新该台账及本文中的相关执行记录。

## 1. 已冻结的用户决策

| 事项 | 决策 |
|---|---|
| 本地仓库路径 | `/home/lenovo/A/patchalign-cpp` |
| 第一阶段范围 | 函数级 C++ 修复为主，Schema 兼容给定文件上下文 |
| GitHub 认证 | 仓库专属、无口令 Ed25519 Deploy Key |
| GitHub fetch / push | HTTPS fetch；SSH alias `github-patchalign-cpp` push |
| 祝融项目环境 | 显式 prefix `/mingli01/project/ht/.conda_envs/patchalign-cpp` |
| 主模型实际路径 | `/mingli01/models/Qwen2.5-Coder-7B` |
| 主模型 upstream revision | `0396a76181e127dfc13e5c5ec48a8cee09938b02`；官方 commit 与四个元数据哈希已匹配 |
| 环境与 smoke | 允许自主创建和验证，但不得修改其他环境或既有内容 |
| 本机—集群同步 | GitHub 作为同步中枢；代码和文档同步，运行产物保留在集群 |
| 仓库原创内容许可 | Apache-2.0；`Copyright 2026 PatchAlign-Cpp contributors` |
| 产物发布 | 正式 adapter 审计后可发布；中间状态和 G0 adapter 默认不公开；数据与完整预测须逐项审计 |
| 第一版数据组成 | ADR-0003：5,000 train、500 validation、400 function test、100 file-window test；主范围 100% C++ |

## 2. 本地与 GitHub

### 2.1 已完成

- 初次检查时 `/home/lenovo/A/patchalign-cpp` 不存在；2026-08-30 已创建本地 Git 仓库并使用 `main` 分支。
- 原 `/home/lenovo/A/new` 下三份 PatchAlign-Cpp 文档已移动到本仓库；初始交接说明后于2026-09-01完成内容合并并从当前树删除，历史由 Git 保留。
- 已建立 A0 Draft 文档、ADR、模型配置和三个机器可校验 JSON Schema。
- 已配置 `origin`：HTTPS fetch、`github-patchalign-cpp` SSH push。
- 已形成明确标注为 A0 Draft 的本地 Git 历史。
- GitHub 空仓库 `HT-O-TA/patchalign-cpp` 已存在。
- 已生成仓库专属 Ed25519 Deploy Key：
  - 私钥：`/home/lenovo/.ssh/id_ed25519_patchalign_cpp`
  - 公钥：`/home/lenovo/.ssh/id_ed25519_patchalign_cpp.pub`
  - 私钥权限：`600`
  - 指纹：`SHA256:JpsyLCyueK5SWlmheQop57y1E2Qp3qjaAwaFSGTC4JE`
- 用户已将公钥添加到 GitHub Deploy Keys，并启用所需权限。
- 已在 `/home/lenovo/.ssh/config` 配置独立 Host alias：`github-patchalign-cpp`。
- 2026-08-30 已执行身份验证，GitHub 返回：

  ```text
  Hi HT-O-TA/patchalign-cpp! You've successfully authenticated, but GitHub does not provide shell access.
  ```

  `ssh -T` 在成功认证后返回退出码 1 是 GitHub 不提供 shell 的正常行为；身份验证本身成功。

### 2.2 同步方式

- 本机是主要开发与提交工作区；
- GitHub 是代码和文档同步中枢；
- 祝融是同一仓库的计算工作副本；
- 产物、环境、模型、数据和权重不进入 Git；
- 具体流程见 `docs/development/git-sync.md`。

A0 当前为 Draft，尚未通过验收门禁。

## 3. 祝融目录与基础设施

### 3.1 已确认

- SSH alias `a800` 可登录祝融管理节点。
- `/mingli01/project/ht` 存在，检查时为空。
- `/mingli01/project/ht/patchalign-cpp` 已创建并作为 Git 计算工作副本；原有 G0 artifact 保留在被忽略的 `artifacts/`。
- 系统模块可用：
  - `conda/3`
  - `cuda/13.0`
- 集群关联上限：`gres/gpu=20`。
- `professors` QOS 上限包括：`cpu=256, gres/gpu=80, mem=1T`。
- `/mingli01` 检查时总容量约 30 TB、剩余约 4.1 TB、使用率约 86%。
- 登录节点具有 GCC/G++ 11.4、Make、Git、patch、timeout 和 prlimit。
- CMake 与 Ninja 已安装到项目专属环境，不修改系统工具。
- 常见 rootless 隔离工具 Bubblewrap、Podman、Apptainer 和 Singularity 未在登录节点发现。
- Slurm 暴露 `srun --container`，但 OCI 隔离能力尚未通过计算节点安全测试。

### 3.2 祝融本地作业模板参考

经用户授权，2026-08-30 对 `/mingli01/project` 中可读的少量 Slurm 模板做了只读抽样，仅检查 Shell、`#SBATCH`、模块和 Conda 初始化行，没有修改文件或读取无关业务内容。

代表性模板包括：

```text
/mingli01/project/hyh/.claude/skills/zhurong-job-submission/template.sbatch
/mingli01/project/hyh/zhurong/template.sbatch
/mingli01/project/hyh/install_deps.sbatch
/mingli01/project/hyh/infer_alpamayo.sbatch
```

共同模式：

```bash
#!/bin/bash
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --gres=gpu:1

module load conda/3
module load cuda/13.0
source /persist_data/apps/miniconda3/etc/profile.d/conda.sh
conda activate <named-environment>
```

PatchAlign-Cpp 的环境是自定义显式 prefix，而非普通逻辑名称。实测该集群可能出现 `CONDA_PREFIX` 正确但 `python` 仍指向系统 Miniconda 的异常，因此本项目作业规范增加强制验证：

```bash
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
export PATH="${ENV_PREFIX}/bin:${PATH}"
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
```

后续 Slurm 脚本必须：

1. 使用真实 `#!/bin/bash` 文件，不用包含 Bash 语法的裸 `sbatch --wrap`；
2. 提交前执行 `bash -n`；
3. Python 入口提交前执行 `python -m py_compile` 或项目测试；
4. 运行时断言专属 Python 路径和 `sys.prefix`；
5. 设置 `PYTHONNOUSERSITE=1`；
6. 不执行 `conda init`，不修改共享 Shell 初始化；
7. 不在计算作业内安装依赖。

## 4. PatchAlign-Cpp 专属 Conda 环境

### 4.1 环境标识

该环境使用显式 prefix 创建：

```text
/mingli01/project/ht/.conda_envs/patchalign-cpp
```

因为它不在 Conda 默认 `envs_dirs` 中，`conda env list` 的名称栏为空，只显示完整路径。因此：

- 项目简称可以写作 `patchalign-cpp`；
- 它没有可依赖的 Conda 逻辑名称；
- 文档和 Slurm 脚本必须按完整 prefix 激活：

  ```bash
  conda activate /mingli01/project/ht/.conda_envs/patchalign-cpp
  ```

### 4.2 已安装并验证的核心版本

| 软件 | 版本 |
|---|---|
| Python | 3.10.20 |
| PyTorch | 2.11.0+cu130 |
| PyTorch CUDA runtime | 13.0 |
| Transformers | 4.57.6 |
| Datasets | 3.6.0 |
| Accelerate | 1.13.0 |
| PEFT | 0.18.1 |
| TRL | 0.28.0 |
| bitsandbytes | 0.49.2 |
| CMake | 3.31.6 |
| Ninja | 1.11.1.4 |
| pytest | 8.4.2 |
| Pydantic | 2.12.5 |

- `pip check`：通过，无损坏依赖。
- 环境占用：约 8.2 GB。
- 未安装 DeepSpeed。
- 未修改 `base`、`dirl_grpo`、`llamafactory_env` 或其他已有环境。
- 登录节点没有 GPU，故登录节点上的 `torch.cuda.is_available()` 为 `False`；这不代表计算节点失败。

### 4.3 环境污染防护

实测发现祝融用户级目录 `~/.local/lib/python3.10/site-packages` 默认可能进入新环境的 Python 搜索路径。所有项目命令和 Slurm 作业必须设置：

```bash
export PYTHONNOUSERSITE=1
```

否则可能误用历史环境之外的用户级包，使复现结论失真。

### 4.4 复现证据

环境内已保存：

```text
/mingli01/project/ht/.conda_envs/patchalign-cpp/repro/conda-explicit.txt
/mingli01/project/ht/.conda_envs/patchalign-cpp/repro/pip-freeze.txt
```

首次生成时的 SHA256：

```text
691ce1aa4ecab68bf309ddd1006ff6824fd325a511a10490f67de179451c8d0a  conda-explicit.txt
d50b7ea34e48542f50348fa560c0b70d3d24b12f220b82dd6365fc0d1e59e655  pip-freeze.txt
```

## 5. 模型权重

### 5.1 已完成的检查

- 已确认现有外部基线 `/mingli01/models/Qwen3-8B` 存在。
- 已确认其 `config.json` 为 `model_type: qwen3`、`torch_dtype: bfloat16`。
- 未修改任何已有模型。
- 已从祝融尝试访问 Hugging Face 官方地址。

### 5.2 集群直接下载结果

祝融连接 `huggingface.co:443` 超时，Hugging Face dry-run 也无法取得模型文件清单，因此集群直接下载失败。

首次尝试时，用户原计划路径：

```text
/mingli01/models/Qwen2.5-Coder-7B Base
```

该带空格目录没有被创建，也没有残缺模型文件。

### 5.3 模型已到位后的核验

2026-08-30 后续检查确认，模型实际放在：

```text
/mingli01/models/Qwen2.5-Coder-7B
```

CPU 侧静态核验结果：

- 目录大小约 15 GB；
- `architectures`：`Qwen2ForCausalLM`；
- `model_type`：`qwen2`；
- `torch_dtype`：`bfloat16`；
- hidden size：3584；
- 层数：28；
- attention heads：28；
- key/value heads：4；
- vocabulary size：152064；
- 权重索引声明总大小：15,231,233,024 字节；
- 权重索引包含 339 个 tensor；
- 4 个 safetensors 分片全部存在；
- README 标题为 `Qwen2.5-Coder-7B`，不是 Instruct 模型卡；
- 许可证文件和模型卡声明 Apache-2.0。

下载目录没有保留 Hugging Face snapshot 元数据。2026-09-01 已通过用户提供的官方 commit 和四个元数据文件哈希恢复精确 revision；真实 tokenizer/config 加载及计算节点 BF16/NF4 链路也已由 Job `90719` 验证。当前仅剩四个权重分片与上游 LFS OID 的逐片对照作为供应链证据补强项。

## 6. GPU 环境 smoke

### 6.1 已提交

| 项目 | 值 |
|---|---|
| Slurm Job ID | `90574` |
| Job name | `patchalign-env-smoke` |
| GPU | 1 |
| CPU | 2 |
| 主机内存 | 4 GB |
| 时间上限 | 20 分钟 |

smoke 计划验证：

1. A800 与 CUDA 可见性；
2. BF16 矩阵计算；
3. bitsandbytes NF4 前向与反向；
4. 小型模型 LoRA 注入和 optimizer step；
5. adapter 保存与重载；
6. 峰值 GPU 显存。

脚本位置：

```text
/mingli01/project/ht/patchalign-cpp/artifacts/smoke/history/90574/env_smoke.py
```

脚本 SHA256：

```text
56d8c85cecc4c1f64526da3201558d0ca4f86ec91afc48c122ef76583c0a721e
```

### 6.2 实际结果

Job `90574` 后来获得过 1 张 GPU，但在进入 Python 和 CUDA 测试前 1 秒失败：

```text
90574 | FAILED | elapsed 00:00:01 | ExitCode 2:0
```

失败原因：`sbatch --wrap` 使用 `/bin/sh` 解释包装脚本，而包装命令使用了 Bash 专属的 `source` 和 `set -o pipefail`。日志为：

```text
source: not found
set: Illegal option -o pipefail
```

这是提交封装错误，不是 Python、CUDA、bitsandbytes、LoRA 或 GPU 失败。作业已经结束，不再排队或占用资源，因此没有可终止的 Job。后续正式 smoke 必须使用具有 `#!/bin/bash` 的 sbatch 文件或显式 `/bin/bash -lc`。

GPU smoke 在作业实际完成并检查日志前，不得写成“通过”。

### 6.3 真实模型综合 G0 smoke

2026-08-30 已使用明确的 Bash sbatch 文件提交新作业：

| 项目 | 值 |
|---|---|
| Slurm Job ID | `90699` |
| Job name | `patchalign-g0-smoke` |
| 模型 | `/mingli01/models/Qwen2.5-Coder-7B` |
| GPU | 1 |
| CPU | 8 |
| 主机内存 | 32 GB |
| 时间上限 | 1 小时 |
| 初始状态 | `PENDING (AssocGrpGRES)` |

脚本：

```text
/mingli01/project/ht/patchalign-cpp/scripts/smoke/patchalign_g0_smoke.py
/mingli01/project/ht/patchalign-cpp/slurm/g0_smoke.sbatch
```

最初失败和成功作业实际使用的原始 sbatch 已归档：

```text
/mingli01/project/ht/patchalign-cpp/artifacts/smoke/history/90699/patchalign_g0_smoke.sbatch
/mingli01/project/ht/patchalign-cpp/artifacts/smoke/history/90719/patchalign_g0_smoke_v2.sbatch
```

SHA256：

```text
480c828891063f1238ce2be580b6e393bad900d56051fadc868bd176ed21d72e  patchalign_g0_smoke.py
d0d5e73f3921f44950d48fc100309cd9c1a88076eec0722d1cabe61190940c9c  patchalign_g0_smoke.sbatch
```

该作业按独立进程依次验证：

1. A800、CUDA 和 BF16 运算；
2. tokenizer/config 离线加载；
3. BF16 Base 加载、LoRA 单步、adapter 保存/重载；
4. NF4 Base 加载、QLoRA 单步、adapter 保存/重载；
5. 版本、loss、梯度、显存、生成文本和 artifact 哈希。

作业结束且原始日志、JSON artifact、Slurm 资源记录均通过检查前，不得标记 G0 完成。

### 6.4 G0 修正与最终结果

Job `90699` 后来启动，但在 2 秒内失败：非交互 Slurm Shell 中 `conda activate` 报 `Run 'conda init' before 'conda activate'`，尚未进入 Python。进一步检查发现，即使显式加载 `conda.sh`，集群 Shell 仍可能设置正确的 `CONDA_PREFIX`、但保留错误的系统 Python PATH。为避免修改全局 Shell 配置，最终脚本改为把专属 prefix 的 `bin` 显式放在 PATH 首位，并强制检查：

```text
command -v python == /mingli01/project/ht/.conda_envs/patchalign-cpp/bin/python
sys.prefix == /mingli01/project/ht/.conda_envs/patchalign-cpp
```

修正版 Job：

| 项目 | 结果 |
|---|---|
| Slurm Job ID | `90719` |
| Job name | `patchalign-g0-smoke-v2` |
| State / ExitCode | `COMPLETED / 0:0` |
| 节点 | `gpu10` |
| GPU | NVIDIA A800-SXM4-80GB，compute capability 8.0 |
| Driver / CUDA | 580.65.06 / 13.0 |
| 总耗时 | 3 分 48 秒 |
| 主机 MaxRSS | 17,764,536 KiB，约 16.9 GiB |

BF16 LoRA 结果：

- 模型 footprint：15,231,233,280 bytes；
- trainable parameters：20,185,088；
- trainable fraction：约 0.2643%；
- 单步 loss：0.4554518163；
- adapter gradient norm：0.6343216168；
- 峰值 allocated GPU memory：16,501,191,680 bytes，约 15.37 GiB；
- 峰值 reserved GPU memory：16,703,815,680 bytes，约 15.56 GiB；
- adapter 保存、重载、forward 和短生成通过。

NF4 QLoRA 结果：

- 发现 196 个 bitsandbytes `Linear4bit` 模块；
- 量化模型 footprint：5,443,300,608 bytes；
- trainable parameters：20,185,088；
- 单步 loss：0.4569952786；
- adapter gradient norm：0.7460884016；
- 峰值 allocated GPU memory：9,253,692,928 bytes，约 8.62 GiB；
- 峰值 reserved GPU memory：10,645,143,552 bytes，约 9.91 GiB；
- adapter 保存、重载、forward 和短生成通过。

结果与 adapter：

```text
/mingli01/project/ht/patchalign-cpp/artifacts/smoke/g0/90719
```

结果 JSON SHA256：

```text
67ed4a7e580d121bdbbb12f108eb2b19d8fc2a23dfd4d815ebb66ef720f7b06f  bf16-result.json
c264097d18417cb9b2575cbc670d4dd28197bae66bdd3775c1fc5cbfcb3d79a5  nf4-result.json
```

adapter SHA256：

```text
ba334293a988d9ebf08fd44214742bab7edb171f328e4f5219ca67c5fc890e0e  bf16-adapter/adapter_model.safetensors
2e6b0495f4c32c9aaf8ea87396bf4dd7f3db96ff8925bcbdf20d399c8c78257b  nf4-adapter/adapter_model.safetensors
```

日志中的 `torch_dtype` 弃用提示和 bitsandbytes FutureWarning 不影响本次结果，后续代码应把 `torch_dtype` 更新为 `dtype`。短生成只验证数值与加载链路，不用于判断补丁质量。

结论：G0 真实模型综合 smoke 已通过。该结论仅证明当前环境、模型、BF16 LoRA、NF4 QLoRA 和 adapter 生命周期兼容，不代表正式 SFT 或修复质量结果。

### 6.5 smoke 目录结构迁移

根据用户决定，2026-08-30 将项目代码和 Conda 环境调整为并列结构：

```text
/mingli01/project/ht/
├── patchalign-cpp/
│   ├── scripts/smoke/
│   ├── slurm/
│   └── artifacts/smoke/
└── .conda_envs/
    └── patchalign-cpp/
```

迁移结果：

- 成功 G0 Python 脚本进入 `scripts/smoke`；
- 新的可复用 sbatch 进入 `slurm/g0_smoke.sbatch`，所有路径已改为新项目根目录；
- Job 90719 的 JSON、adapter 和日志进入 `artifacts/smoke`；
- Job 90574、90699、90719 的旧脚本和失败证据保留在 `artifacts/smoke/history`；
- Conda prefix 下原临时 `smoke` 目录已清空并移除；
- 模型目录和 Conda 包未移动、未修改；
- 迁移后关键 Python 脚本、结果 JSON 和 adapter 权重 SHA256 与迁移前一致。

新的可复用 sbatch SHA256：

```text
a62195d62e27a646e11408ffa4d1bf9fb210a9440a715938098577f2434d8656  slurm/g0_smoke.sbatch
```

## 7. 本地仓库与 A0 Draft 建立

2026-08-30 完成：

- 在 `/home/lenovo/A/patchalign-cpp` 初始化 Git `main` 分支；
- 配置 `origin`：HTTPS fetch、Deploy Key SSH push；
- 将原 `/home/lenovo/A/new` 下三份项目文档迁入仓库；
- 建立 README、pyproject、最小 Python package；
- 建立任务契约、Schema 说明、评测协议、实验协议和真实性声明；
- 建立两个 ADR、模型配置和三个 JSON Schema；
- 建立三个正例 fixture 和关键负例 pytest；
- 完成本地 JSON/TOML 解析、Python 编译、Markdown 相对链接、Git ignore、敏感模式和大文件检查；
- 初始提交：`aaecacf chore: bootstrap A0 draft contracts`；
- 空白规范化提交：`2de6363 style: normalize repository whitespace`。
- A0 引导证据提交：`c5a1f4c docs: record local A0 bootstrap evidence`。

建立 A0 Draft 时，本机与当时检查到的祝融项目环境尚未隔离验证 `jsonschema`，因此该阶段 pytest 未实际验收。此历史状态已由第 11 节的 Schema v0.2 隔离验收取代。

## 8. Git 同步与当前边界

已完成：

- 本机仓库、GitHub 和祝融计算工作副本使用 Git 同步；
- 祝融 G0 Python 与 sbatch 纳入版本控制；
- G0 小型证据摘要纳入文档；
- 原始 JSON、adapter、日志、模型和 Conda 环境继续保留在集群，不进入 Git。

仍未推进：

- 没有下载数据；
- 没有运行正式基线或质量评测；
- 没有正式训练；
- 没有修改 MeetingMind；
- 没有提交新的 GPU 作业。

## 9. 许可证与发布边界

2026-09-01 经用户确认，已完成 A0 许可证与发布策略决策：

- 新增标准 Apache License 2.0 `LICENSE`；
- 新增 `NOTICE`，当前使用中性版权标识 `PatchAlign-Cpp contributors`；
- 新增 `THIRD_PARTY_NOTICES.md` 初始清单；
- 新增发布策略并标记为 `Accepted for A0`；该内容后合并至 `docs/a0/governance.md`；
- 仓库原创代码、文档、Schema、配置和脚本采用 Apache-2.0；
- 仓库许可证不重新许可模型、数据集、benchmark、生成补丁或依赖；
- 正式 SFT/DPO adapter 可在逐项审计后发布；中间 checkpoint、optimizer state 和 G0 smoke adapter 默认不公开；
- 原始或重打包数据在逐来源许可审计前不公开；
- 完整预测必须通过来源许可、敏感信息和漏洞披露检查；
- 原始日志和内部路径不公开，但失败结果不能从统计分母中删除。

该决策关闭 A0 的“项目代码许可证”和“产物公开范围”两个未决项，但不代表 A0 已完成。当时 Schema 自动测试、确定性评分 fixture、输出协议用户验收、评测集阈值与沙箱等门禁仍待完成；其中前三项随后分别在第 11、12 节关闭。

## 10. 模型 revision 与第一版数据组成冻结

2026-09-01 完成两项 A0 决策记录。

模型身份：

- 用户确认 `Qwen/Qwen2.5-Coder-7B` upstream revision 为 `0396a76181e127dfc13e5c5ec48a8cee09938b02`；
- 官方 Hugging Face commit 已确认存在；
- 集群模型的 `config.json`、`model.safetensors.index.json`、`tokenizer.json` 和 `tokenizer_config.json` SHA256 与该 revision 官方文件一致；
- 四个权重分片尚未逐片对照上游 LFS OID，记录为 provenance 证据补强项；
- `configs/model/qwen2_5_coder_7b_base.yaml` 和 ADR-0001 已更新。

数据组成：

- 新增 `docs/decisions/0003-dataset-composition-v1.md`，状态为 `Accepted for A0`；
- 目标配额：5,000 train、500 validation、400 internal function test、100 internal file-window test；
- train 来源目标为 2,000 CommitPackFT C++ + 3,000 RunBugRun C++；validation 为 200 + 300；
- 主训练、验证和主指标为 100% C++，Python/Java 为 0%；C 如使用只做独立外部切片；
- train/validation 的 function/file-window 目标比例为 85%/15%；
- 修改类型目标比例为单行 35%、函数内多行 50%、新增辅助函数 10%、局部重构 5%；
- file-window 最多 256 行、目标前后各最多 96 行、完整输入最多 4,096 tokens，禁止截断目标函数；
- 同一批 500 条内部评测样本必须同时具备 public、hidden 和 regression 阶段；
- external function 使用所有可重放且符合契约的 Defects4C C++ 样本，目标至少 150；SWE-bench Multilingual 当前 12 条 C++ 任务只做仓库级扩展；
- 当前冻结的是配额、筛选规则和报告分层；正式数据尚未下载或构建，最终来源 revision、可重放数量和 manifest SHA256 必须在 A1 实测后冻结；
- 本节冻结数据组成时，`sample-v0.1` 尚未编码修改类型和窗口统计字段；该前置项随后已按第 11 节升级为 v0.2 并完成正反例测试。

## 11. Schema v0.2 与自动测试闭环

2026-09-01 完成 canonical sample Schema 的兼容升级和隔离测试验收：

- 保留 `schemas/sample-v0.1.schema.json` 用于历史重放；
- 新增 `schemas/sample-v0.2.schema.json`，新建 A1 样本必须使用 `0.2.0`；
- 新增 edit type、逻辑修改行数、file-window 统计、输入 token 数和三阶段测试计数字段；
- 编码单文件、修改类型行数、256/96/96/4096 上限和 internal test 最低测试数量联动；
- 新增 3 个 v0.2 正例 fixture，并将测试扩展至路径逃逸、多文件、未知/缺失字段、版本错配及各类边界反例；
- 实现提交：`ec9039646696fde16dfaf512350acf50ef877da2`。

环境核验发现：未设置 `PYTHONNOUSERSITE` 的首次测试虽然为 `30 passed`，但 `jsonschema` 实际来自用户级 `~/.local`，不能作为项目环境验收。随后：

1. 设置 `PYTHONNOUSERSITE=1` 复现 `ModuleNotFoundError`，确认环境污染；
2. 仅在 `/mingli01/project/ht/.conda_envs/patchalign-cpp` 安装项目已声明范围 `jsonschema>=4.23,<5`；
3. 确认版本为 `4.26.0`，模块路径位于该 Conda prefix 的 `site-packages`；
4. 在 `PYTHONNOUSERSITE=1` 下连续运行两次全量 pytest，结果分别为 `30 passed in 0.29s` 和 `30 passed in 0.27s`；
5. 刷新环境复现清单 `repro/pip-freeze.txt`，SHA256 为 `bef5b08f129a08a1f720e8698c99606832192d1f77b0f9cce1adc98e3baa43a4`；
6. 全程未使用 GPU、未提交 Slurm 作业、未修改模型或数据目录。

结论：Schema 自动校验与正反例测试门禁已关闭，A0 仍为 Draft。本节记录时仍待完成的确定性评分 fixture 和输出协议验收已随后在第 12 节关闭；提升/退化阈值和沙箱验证仍待完成。

## 12. 严格输出协议与确定性评分闭环

2026-09-01 用户接受 ADR-0002 的严格 unified diff 输出协议，并接受标准应用模式：

- 唯一纯 unified diff，不允许围栏、解释或多个候选；
- 多文件、路径逃逸、绝对路径和二进制 patch 严格拒绝；
- 应用前后分别使用 `git apply --recount --check` 和 `git apply --recount`；
- `--recount` 只放宽 hunk header 行数计数，不忽略删除行、上下文或空白差异；
- parse、policy 和 apply 失败保持独立分类，apply 通过不等于最终 Pass。

实现提交 `c000f775071f7632f81edc5103455dfe93d271c2` 新增：

- `src/patchalign/evaluation/patches.py`：严格 parser 和单文件路径策略；
- `src/patchalign/evaluation/scorer.py`：临时 clone、固定顺序评分、超时进程组清理、规范化哈希和固定分母汇总；
- `tests/fixtures/scoring`：固定 base commit 的微型 C++ 仓库、v0.2 sample、prediction 和各阶段失败 patch；
- parser、策略和端到端确定性 pytest。

集群项目环境设置 `PYTHONNOUSERSITE=1`，使用 Python 3.10.20、Git 2.34.1 和 g++ 11.4.0 验收：

```text
全量首轮：53 passed in 5.51s
全量复跑：53 passed in 5.23s
评分专项：12 passed in 4.92s
```

固定证据：

```text
fixture base commit: d68a0718b4a066cb319e89efc21e5c2af9d1d093
success score SHA256: sha256:199e2f57b505a9dd148bf9c57c219c8bd952ee90a2c7a74d44ed96b3a6a98dc0
```

结论：A0 的输出协议验收、极小确定性评分 fixture 和重复评分门禁已关闭。该受控 fixture 不等于 A2 沙箱或真实数据评分闭环；A0 继续保持 Draft。本次未使用 GPU、未提交 Slurm 作业、未修改模型或数据。

## 13. 完整任务契约与训练质量门禁冻结

2026-09-01 用户接受完整第一版任务契约，并明确 sanitizer 只在显式适用样本上执行。落地规则：

- 任务契约状态改为 `Accepted for A0`；该内容后合并至 `docs/a0/core_protocol.md`；
- A2 执行配置/结果 Schema 必须显式记录 `sanitizer_applicable`；
- `true` 必须绑定命令、工具版本、环境和 timeout，`false` 记为 `not_applicable`；
- 缺少标记不能进入正式 sanitizer 指标，且不静默修改已验收的 `sample-v0.2`；
- 该字段由 A2 版本化执行 Schema 承接。

新增 `docs/decisions/0004-training-quality-gates-v1.md` 和 `configs/evaluation/quality_gates_v1.json`，冻结：

- A3 pilot 成功数相差至少2条才按质量选择，否则按稳定性、峰值显存、wall time 和名称选择；
- M1 对 M0 的 function Hidden-test Pass@1 至少 `+2.0 pp`；
- M2 对 M1 至少 `+1.0 pp`；
- 95% paired bootstrap，10,000次，seed `20260830`，差值区间下界必须 `>=0`；
- parse/apply/compile 最大下降1.0 pp，regression 最大增加1.0 pp，timeout 最大增加0.5 pp；
- file-window 最大下降3.0 pp，Defects4C C++ 外部切片最大下降2.0 pp；
- 分母变化、数据泄漏、hidden test 暴露、修改测试或 artifact/manifest 不匹配一票否决。

初始实现提交 `db758373ce0f0a3152613a6475f64dfbe648d2ef` 新增确定性门禁判定器、paired bootstrap、pilot 选择和专项测试。集群首轮结果：

```text
全量 pytest：73 passed in 9.19s
质量门禁专项：20 passed in 3.94s
```

补齐有效 bootstrap 参数审计、零次 bootstrap 拒绝和双候选 pilot 限制后，对提交 `b236fcafe0d22b4612e5d64c3e4b7c8aa20e1101` 最终复验：

```text
全量 pytest：75 passed in 9.06s
质量门禁专项：22 passed in 4.04s
```

配置规范化 SHA256：

```text
sha256:a21772dbddf07b7c7d42f3813569515b23db1413f33c19f8dc062e7bd5bc7138
```

结论：完整任务契约、指标分母/跳过规则/失败优先级和正式训练质量阈值门禁已关闭。A0 仍为 Draft，剩余事项包括实验复现协议与真实性声明的最终审阅、未决事项 owner/进入条件，以及 A2 沙箱验证。本次未使用 GPU、未提交 Slurm 作业、未修改模型或数据。

## 14. 文档结构整理与合并

2026-09-01 对现有文档进行去重，保持 ADR、执行记录、目录台账和 G0 作业证据独立：

- `task_contract.md` 与 `evaluation_protocol.md` 合并为 `docs/a0/core_protocol.md`；
- `authenticity_and_leakage.md` 与 `publication_policy.md` 合并为 `docs/a0/governance.md`，分别保留 Draft 与 Accepted 状态；
- 两份 A0 合成验收证据合并为 `docs/evidence/a0-validation.md`；
- 初始 Codex 交接说明已被当前 A0、ADR、执行记录和目录台账完全取代，从当前工作树删除；
- 根 README 与 A0 索引改为只指向当前权威文档；
- 被删除文件仍可通过 Git 历史恢复，没有删除运行 artifact、模型、数据或环境内容。

整理原则：当前规范只保留一个入口；历史执行事实留在本文；不可变决策继续留在独立 ADR；用户要求的目录台账继续独立维护。

## 15. 下一次应更新的事件

发生以下任一事件时更新本文：

1. 对 Qwen2.5-Coder-7B 四个权重分片补充上游 LFS OID 对照；
2. A0 验收；
3. A1 固定数据源 revision、完成过滤统计并冻结 manifest；
4. A2 评测协议冻结后安排 Base 与外部强基线 GPU 推理；
5. 新增重要目录、模型、环境、作业或 artifact 迁移。
