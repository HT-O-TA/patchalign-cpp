# 第二项目 PatchAlign-Cpp：Codex 新对话交接说明

> 更新时间：2026-08-30
> 用途：把第二项目完整交给一个全新的 Codex 对话。新对话应先完整阅读本文，再阅读原始立项文档，然后从 A0 开始建设。
> 优先级：本文记录了最新用户决策、祝融集群实测和执行约束；若与旧规划冲突，以本文为准。

## 0. 给新 Codex 的直接指令

你正在接手一个全新的独立项目：`PatchAlign-Cpp`。

请先完成以下动作，再修改文件或提交作业：

1. 完整阅读本文；
2. 完整阅读：
   `/home/lenovo/A/meetingmind-agent/docs/项目规划/第二项目_PatchAlign-Cpp立项与实施路线.md`；
3. 确认本地仓库、远端运行目录、模型权重和 GitHub 远端的实际状态；
4. 从 A0 问题契约、评测协议和执行沙箱开始，不要直接训练；
5. 使用系统 `conda/3` 和 `cuda/13.0` 模块，在用户目录创建 PatchAlign-Cpp 专属 Conda 环境；
6. 依赖只允许安装到该专属环境，不得修改系统环境、`base` 或任何已有共享/历史环境；未经用户明确授权，不下载新模型、不取消已有作业、不修改 `/mingli01/models` 中现有模型；
7. 第二项目不得修改 MeetingMind 仓库。MeetingMind 只是规划资料来源，不是第二项目工作区。

默认本地仓库建议为：

```text
/home/lenovo/A/patchalign-cpp
```

默认祝融运行目录建议为：

```text
/mingli01/project/ht/patchalign-cpp
```

这两个目录在首次创建前仍应进行只读检查。如果用户指定其他名称或路径，以用户决定为准。

---

## 1. 用户目标与协作方式

### 1.1 核心目标

建设一个以 C++ 缺陷修复为任务、以可执行验证为核心的微调对齐项目：

```text
PatchAlign-Cpp：C++ 缺陷修复可验证后训练
```

项目要证明的不是“调用一次训练框架”，而是完整能力链：

```text
数据溯源与隔离
→ 冻结基线
→ LoRA/QLoRA SFT
→ 可执行验证
→ 偏好数据
→ DPO
→ 失败分析、消融和部署证据
```

### 1.2 用户偏好

- 用户掌握技术是第一目标，项目改进和简历产出是第二目标；
- 每个阶段都要解释关键原理、选择依据、失败原因和验证方法；
- 不要把复杂实现完全隐藏在黑盒配置里；
- 在安全和权限范围内应主动推进，但遇到模型下载、平台规则、账号权限等外部闸门时暂停并询问；
- 需要真实运行证据，不能把 mock、合成日志或“代码看起来可行”写成训练成功；
- 可以使用合成数据做早期单元测试，但最终核心结论必须来自公开可追溯数据和可执行评测。

### 1.3 三项目组合中的位置

用户未来简历预计包含：

1. MeetingMind Agent：AI 应用、RAG、Agent 工程；
2. PatchAlign-Cpp：数据、微调、偏好对齐、可执行评测；
3. C++ 游戏服务器：C++、网络、并发、系统工程。

第二项目必须与 MeetingMind 保持边界清晰，不把 MeetingMind 的小模型教学实验包装成第二项目成果。

---

## 2. 项目边界与完成定义

### 2.1 第一阶段任务层次

按难度递进，而不是一开始做完整 SWE Agent：

1. 函数级 C++ 修复；
2. 给定文件上下文的补丁生成；
3. 已定位仓库范围内的补丁；
4. 真实仓库 issue/PR 修复作为外部评测或后续扩展。

第一版重点是“给定缺陷上下文，生成可以应用、编译并通过测试的补丁”。

### 2.2 第一版明确不做

- 不训练基础模型；
- 不宣称完整 RLHF 生产经验；
- 不把联网搜索、仓库自主探索和长程 Agent 作为第一版必做；
- 不在评测闭环完成前进入大规模 SFT；
- 不在可靠奖励和防 reward hacking 证据不足时强做 GRPO/RLVR；
- 不把基础模型可能见过公开基准的问题写成“完全无污染”；
- 不为了模型规模牺牲可复现性和实验解释性。

### 2.3 最终完成定义

至少交付：

- 冻结的任务契约和样本 Schema；
- 数据来源、许可证、revision、哈希和仓库隔离清单；
- 可重放的数据准备管线；
- patch 解析、应用、编译、测试、回归和资源限制沙箱；
- Base / Prompt 基线、SFT、DPO 的同协议结果；
- LoRA/QLoRA 至少一组公平对照；
- 每条预测、执行日志、失败分类和资源指标；
- 数据卡、模型卡、实验报告、Bad Case；
- 从空工作区可执行的命令、测试和固定 Demo；
- 只基于真实证据填写的简历 bullet。

---

## 3. 当前目录与外部状态

### 3.1 祝融目录

用户远端项目根目录：

```text
/mingli01/project/ht
```

2026-08-30 初次清理后确认：

- 目录存在；
- 目录所有内容已经用户明确授权后删除；
- 清理完成时为空；后续已创建 `patchalign-cpp` 和 `.conda_envs/patchalign-cpp`；
- 旧测试脚本和旧 Slurm 输出已经删除；
- Slurm 历史记账仍由平台保存，不属于普通用户可删除范围。

模型统一存放目录：

```text
/mingli01/models
```

不要把模型权重复制进 Git 仓库，也不要修改或删除共享模型。

### 3.2 本地目录

本文当前放在：

```text
/home/lenovo/A/patchalign-cpp/docs/handoff/第二项目_PatchAlign-Cpp_Codex交接说明.md
```

完整规划原文放在：

```text
/home/lenovo/A/meetingmind-agent/docs/项目规划/第二项目_PatchAlign-Cpp立项与实施路线.md
```

本地仓库已于 2026-08-30 创建：

```text
/home/lenovo/A/patchalign-cpp
```

### 3.3 GitHub

- 用户已决定第二项目使用仓库专属 Deploy Key 推送，不使用 Collaborator 邀请或 Personal Access Token；
- 继续保留 MeetingMind 的双 URL 思路：fetch 使用公开 HTTPS，push 使用 SSH；
- Deploy Key 只授权 `HT-O-TA/patchalign-cpp`，并在 GitHub 仓库设置中启用 `Allow write access`；
- 当前状态：GitHub 空仓库、专属无口令密钥、Deploy Key 写权限和 SSH Host alias 已完成，`ssh -T github-patchalign-cpp` 身份验证成功；本地 remote、首次 commit 和首次 push 仍待完成；
- 建议在 A0/A2/A3/A5/A8 等重大里程碑形成可验证提交后推送；
- 不要把数据、模型权重、token、集群地址、作业日志中的敏感内容提交到 GitHub。

目标配置：

```text
origin fetch: https://github.com/HT-O-TA/patchalign-cpp.git
origin push:  git@github-patchalign-cpp:HT-O-TA/patchalign-cpp.git
branch:       main -> origin/main
SSH alias:    github-patchalign-cpp
private key:  /home/lenovo/.ssh/id_ed25519_patchalign_cpp
```

Deploy Key 配置流程：

1. 在 GitHub 创建空仓库 `HT-O-TA/patchalign-cpp`；
2. 删除操作禁止：生成密钥前先确认 `/home/lenovo/.ssh/id_ed25519_patchalign_cpp` 不存在，若存在则停止并核对，不得覆盖；
3. 在本机生成专属 Ed25519 密钥对，私钥只保存在本机，不上传祝融；
4. 将 `.pub` 公钥添加到 GitHub：`Repository Settings → Deploy keys → Add deploy key`；
5. 勾选 `Allow write access`；
6. 在本机 `~/.ssh/config` 添加独立 Host alias；
7. 验证 SSH 身份，再配置 Git remote 和首次推送。

密钥生成骨架：

```bash
test ! -e /home/lenovo/.ssh/id_ed25519_patchalign_cpp
test ! -e /home/lenovo/.ssh/id_ed25519_patchalign_cpp.pub

ssh-keygen -t ed25519 \
  -f /home/lenovo/.ssh/id_ed25519_patchalign_cpp \
  -C "patchalign-cpp deploy key"
```

优先使用 passphrase + `ssh-agent`。如果必须无人值守推送，是否使用无口令密钥由用户明确决定，Codex 不得自行降低保护。

`~/.ssh/config` 目标片段：

```sshconfig
Host github-patchalign-cpp
    HostName github.com
    User git
    IdentityFile /home/lenovo/.ssh/id_ed25519_patchalign_cpp
    IdentitiesOnly yes
```

不得把私钥复制到祝融、Git 仓库、文档、聊天或日志。只有 `.pub` 公钥可以粘贴到 GitHub Deploy Key 页面。

验证：

```bash
ssh -T github-patchalign-cpp
```

本地 Git 仓库首次配置：

```bash
git remote add origin https://github.com/HT-O-TA/patchalign-cpp.git
git remote set-url --push origin \
  git@github-patchalign-cpp:HT-O-TA/patchalign-cpp.git
git push -u origin main
```

如果 `origin` 已存在，则使用：

```bash
git remote set-url origin https://github.com/HT-O-TA/patchalign-cpp.git
git remote set-url --push origin \
  git@github-patchalign-cpp:HT-O-TA/patchalign-cpp.git
```

完成后必须用 `git remote -v` 确认 fetch/push 分离，并用一个不含敏感信息的初始提交验证写权限。不得回退为在 URL 中嵌入 token。

---

## 4. 祝融集群硬约束

### 4.1 专属 Conda 环境原则

用户最新决定：第二项目必须创建并维护一个属于 PatchAlign-Cpp 的独立 Conda 环境。原因是其他已有环境不可修改，依赖缺失时无法保证项目可复现。

推荐使用显式 prefix，避免和账户中的历史环境同名：

```text
/mingli01/project/ht/.conda_envs/patchalign-cpp
```

原则：

1. 使用系统提供的 `conda/3` 创建一次专属环境；
2. Conda/Python 依赖只安装到这个 prefix；
3. `base`、`dirl_grpo`、`llamafactory_env` 和其他已有环境全部只读；
4. 不执行 `conda init`，不修改共享 shell 初始化文件；
5. 不使用 `sudo`、系统包管理器，也不安装或替换系统 CUDA、驱动和系统 Python；
6. 不在每个 Slurm 作业中重复安装依赖；环境准备与训练作业分离；
7. 首先维护可审查的 `environment.yml`/requirements，再创建环境；
8. 安装完成后导出 Conda 显式清单、`pip freeze` 和核心库版本，纳入复现证据；
9. 整个环境目录、wheel 缓存和包缓存不得提交 Git。

推荐的一次性创建流程骨架：

```bash
module load conda/3
module load cuda/13.0

conda env create \
  --prefix /mingli01/project/ht/.conda_envs/patchalign-cpp \
  --file environment.yml

conda activate /mingli01/project/ht/.conda_envs/patchalign-cpp
python --version
python -m pip --version
```

`environment.yml` 中的 Python、PyTorch、Transformers、PEFT、TRL 和 bitsandbytes 版本必须经过目标模型 smoke 后冻结。不要盲目复制已有环境的全部包。

如果依赖缺失：

1. 先确认当前激活的确实是专属 prefix；
2. 更新项目的环境声明和锁定记录；
3. 只在专属环境中安装或升级；
4. 重新执行导入、CUDA、量化和最小训练 smoke；
5. 禁止通过修改其他现有环境解决。

### 4.2 软件查看和加载

使用：

```bash
module avail
module spider <name>
```

当前已验证的模块：

```bash
module load conda/3
module load cuda/13.0
```

正式项目激活专属环境：

```bash
conda activate /mingli01/project/ht/.conda_envs/patchalign-cpp
```

### 4.3 已实测参考软件栈

以下版本来自既有 `dirl_grpo` 环境中的 A800 80GB 真实探测，仅作为创建专属环境的兼容性参考，不代表新环境已经验收：

| 项目 | 已验证结果 |
|---|---|
| GPU | NVIDIA A800-SXM4-80GB |
| Driver | 580.65.06 |
| CUDA module / nvcc | 13.0 / V13.0.48 |
| Python | 3.10.20 |
| PyTorch | 2.11.0+cu130 |
| Transformers | 4.57.6 |
| Datasets | 3.6.0 |
| Accelerate | 1.13.0 |
| PEFT | 0.18.1 |
| TRL | 0.28.0 |
| bitsandbytes | 0.49.2，计算节点导入成功 |
| DeepSpeed | 当前环境缺失 |
| CUDA 运算 | 单 GPU FP16 矩阵计算通过 |

重要结论：

- `dirl_grpo` 可见 CUDA 13 和分配的 A800，但正式项目不修改、不依赖它长期保持不变；
- `llamafactory_env` 实际导入 CPU 版 PyTorch，不得用于正式 GPU 训练；
- bitsandbytes 只完成了导入验证，尚未针对目标模型完成 NF4 加载、反向传播和 adapter 保存验证；
- 需要在新专属环境中重新完成整套探测；
- 第一版仍优先走单 GPU LoRA/QLoRA，不要仅因能够安装 DeepSpeed 就默认引入 ZeRO。

### 4.4 登录节点规则

- 登录节点只做文件检查、配置生成、轻量元数据查询和 `sbatch`；
- 专属环境只做一次受控创建/更新，不在计算作业中执行 `conda install` 或 `pip install`；
- 模型加载、PyTorch GPU 探测、训练和重评测全部提交计算节点；
- 不在登录节点长时间导入多个大环境或运行数据重放；
- 不输出完整环境变量，避免泄漏 token 或内部信息。

---

## 5. Slurm、QOS 与分段作业

### 5.1 已查询到的限制

2026-08-30 只读查询结果：

| 层次 | 限制 |
|---|---|
| 用户关联 GrpTRES / MaxTRES | `gres/gpu=20` |
| professors QOS MaxTRESPU | `cpu=256, gres/gpu=80, mem=1T` |
| QOS MaxWall | 未配置/未显示 |
| 分区详情 | `sinfo` 被 ACL 拒绝，无法查看 |

实际 GPU 上限先受更严格的 20 张关联限制约束。

查询时账户已有任务约占 17 GPU、884G 主机内存，所以：

- 4 GPU 作业因 `AssocGrpGRES` 等待；
- 16G 测试曾因 `QOSMaxMemoryPerUser` 等待；
- 4G、1 GPU 测试可以启动。

这些使用量只是当时快照。每次提交前重新查询，不要硬编码“总有 3 张卡空闲”。

### 5.2 常见等待原因

| Reason | 含义 | 处理 |
|---|---|---|
| `AssocGrpGRES` | 关联 GPU 总额已满 | 降低 GPU 数或等待已有任务结束 |
| `QOSMaxMemoryPerUser` | 用户请求内存总和接近/超过 1T | 降低 `--mem`、串行运行 |
| `JobArrayTaskLimit` | 数组并发上限生效 | 若使用 `%1`，这是预期行为 |
| `Dependency` | 等待上游 | 检查上游状态 |
| `DependencyNeverSatisfied` | 上游失败或条件不可能满足 | 不能继续等，应取消/重建本项目依赖任务 |

不要取消账户中的其他作业。只可在确认精确 Job ID、且该作业由当前 Codex 为本项目提交时，取消本项目作业。

### 5.3 推荐资源起点

| 阶段 | GPU | CPU | 主机内存 | 时间 |
|---|---:|---:|---:|---:|
| 数据清洗/编译重放 | 0 | 8 | 16～32G | 1～4h |
| 模型加载烟测 | 1 | 8 | 32G | 30min |
| 冻结基线推理 | 1 | 8 | 32G | 1～2h |
| 7B/8B LoRA 或 QLoRA SFT | 1 | 8 | 32～48G | 每段 4～8h |
| DPO | 1 | 8 | 48～64G | 每段 4～8h |
| 自动评测 | 1 | 8 | 16～32G | 1～4h |

这只是起始值，必须通过 smoke job 的 MaxRSS、显存峰值和吞吐修正。

### 5.4 分段训练策略

- 第一版全部 1 GPU 串行；
- 每 100～200 optimizer step 保存 checkpoint；
- 每个分段支持 `resume_from_checkpoint`；
- 推荐 4～8 小时一段，不提交一个不可恢复的 24 小时训练；
- 可使用 `--array=0-N%1`，但每段必须能检查前一 checkpoint 完整性；
- 前期由用户验收一个阶段后再提交下一阶段，避免积累大量失效依赖；
- 降低时间不能解决瞬时 QOS，真正有效的是降低同时申请的 GPU/内存并串行运行。

### 5.5 推荐 sbatch 骨架

```bash
#!/bin/bash
#SBATCH --job-name=patchalign-smoke
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/slurm-%j.out

# 集群 profile 中有 Byobu 初始化；不要在 source /etc/profile 前启用 set -u。
source /etc/profile
set -eo pipefail

module load conda/3
module load cuda/13.0
conda activate /mingli01/project/ht/.conda_envs/patchalign-cpp

cd /mingli01/project/ht/patchalign-cpp
python -u <script.py> <args>
```

提交命令：

```bash
cd /mingli01/project/ht/patchalign-cpp
sbatch <job>.sbatch
```

---

## 6. 模型选择与 QLoRA 决策

### 6.1 用户最新授权

用户不排除 Qwen3-8B 系列，允许根据项目价值、资源和兼容性自由选择模型。

“允许选择”不自动等于“允许联网下载”。正式获取新权重前仍需确认平台下载/传输方式和用户授权。

### 6.2 当前默认推荐

| 角色 | 模型 | 当前建议 |
|---|---|---|
| 主训练基座 | `Qwen/Qwen2.5-Coder-7B` Base | 默认首选 |
| 现成强基线 | `/mingli01/models/Qwen3-8B` | Prompt/Few-shot 外部基线，不作为本人完整后训练起点 |
| 第二基座 pilot | `Qwen/Qwen3-8B-Base` | 有余力时比较“较新通用 Base vs 代码专用 Base” |
| 高风险扩展 | `Qwen/Qwen3-Coder-Next-Base` | 不作为第一版主模型 |

选择 `Qwen2.5-Coder-7B Base` 的原因：

- 代码专用，任务与 C++ 修复直接匹配；
- 7.61B dense 架构，LoRA/QLoRA 和评测链成熟；
- Base checkpoint 便于展示 Base → SFT → DPO 的本人贡献；
- 当前 Transformers 4.57.6 高于其最低兼容版本 4.37；
- 单张 A800 80GB 足以做 BF16 LoRA 或 NF4 QLoRA pilot。

### 6.3 当前已有 Qwen3-8B 的身份

`/mingli01/models/Qwen3-8B` 已只读确认：

- 约 8B、5 个 safetensors 分片；
- README 标记 `Training Stage: Pretraining & Post-training`；
- 支持 thinking / non-thinking；
- 它不是 `Qwen3-8B-Base`。

因此它适合：

- 固定 Prompt/Few-shot 强基线；
- 生成候选补丁或辅助构造 hard negative；
- 与本人训练的 Base checkpoint 结果比较。

不要把它已有的厂商后训练能力写成本人训练成果。

### 6.4 Qwen3-Coder-Next-Base 的位置

它是约 80B 总参数、3B 激活、512 专家的稀疏 MoE。虽然当前 Transformers 版本理论上已覆盖 `qwen3_next`，但仍有：

- 约 80B 总权重的存储和加载成本；
- 4-bit 权重也需要约数十 GB，加上量化元数据、adapter 和激活；
- 512 专家使 LoRA target、adapter 参数量和解释复杂；
- 当前环境没有 DeepSpeed；
- 普通 DDP 会复制模型，不能把“多 GPU”简单等同于模型自动分片。

第一版不要用它拖慢数据、评测和训练闭环。只有 7B/8B 项目完成后再作为扩展或上界。

### 6.5 QLoRA 可行性

对 7B/8B dense 模型，当前硬件和软件前置条件基本成立，但仍需真实 smoke：

1. 从固定 revision 加载 tokenizer/config；
2. `BitsAndBytesConfig(load_in_4bit=True)`；
3. NF4 + BF16 compute + double quant；
4. `prepare_model_for_kbit_training`；
5. 注入 LoRA adapter；
6. 单 batch 前向、反向、optimizer step；
7. 保存和重载 adapter；
8. 生成 C++ patch 并走一次编译/测试。

第一轮建议公平比较：

```text
同一 Base + 同一数据 + 同一 seed + 同一 max length
→ BF16 LoRA
→ NF4 QLoRA
→ 比较质量、显存、吞吐、耗时和失败样本
```

A800 80GB 上 7B/8B 的 BF16 LoRA 通常也能运行，因此 QLoRA 不能仅凭“更省显存”成为默认赢家，必须用实测冻结方案。

---

## 7. 数据方案

### 7.1 第一版来源

建议分工：

| 数据 | 用途 |
|---|---|
| CommitPackFT | 真实代码提交、SFT 候选和数据管线 |
| RunBugRun C++ | 有可执行测试的训练/验证样本 |
| Defects4C | C/C++ 外部评测 |
| SWE-bench Multilingual / Multi-SWE-bench C/C++ | 仓库级外部评测或扩展 |
| NIST SARD | 安全缺陷专项扩展，不作为第一主线 |

第一版不需要写通用网页爬虫。公开数据不足时再采用 API + Git clone + 容器重放的可审计采集方式。

### 7.2 数据闸门

每个来源必须记录：

- 数据集名称、URL、许可证、版本/revision；
- 下载时间、原始文件哈希；
- 仓库、commit、父 commit；
- 编程语言和构建系统；
- 数据来源允许的再分发范围；
- train/validation/test 归属；
- 是否能在固定容器/环境中重放；
- 过滤和去重原因。

### 7.3 切分顺序

必须：

```text
先按 repository family 隔离
→ 再在分区内生成样本
→ 再做精确和近似去重
→ 最后冻结 manifest
```

禁止先随机切样本再补仓库隔离。

### 7.4 建议样本 Schema

至少包含：

```text
sample_id
source_dataset
source_revision
repo_id / repo_family
base_commit / fix_commit
language
task_level
problem_statement
buggy_code / context
gold_patch
build_command
public_test_command
hidden_test_command（如可合法生成）
timeout_seconds
license
split
provenance_hash
```

gold patch 只用于训练或离线判定，生成时不得泄漏到 prompt。

---

## 8. 先评测、后训练

### 8.1 执行链必须先完成

```text
模型文本
→ 提取唯一 patch
→ 语法/路径校验
→ 在临时工作树应用 patch
→ 编译
→ public tests
→ hidden tests
→ 回归测试
→ sanitizer（适用时）
→ 资源和补丁规模统计
```

### 8.2 最低安全要求

- 每条样本使用隔离临时目录；
- 默认禁网；
- 限制 CPU、内存、进程数、文件大小和运行时间；
- 禁止 patch 越过仓库根目录；
- 禁止修改测试、构建脚本和评测器，除非任务契约明确允许；
- 捕获 stdout/stderr、exit code、timeout 和信号；
- 输出可重放 manifest；
- 不在主机直接执行不可信仓库脚本而无隔离。

### 8.3 主指标

- Patch parse rate；
- Patch apply rate；
- Compile rate；
- Public-test pass rate；
- Hidden-test pass rate / Pass@1；
- Regression rate；
- Patch size / changed files；
- 格式违规率；
- 推理和执行超时率。

资源指标：

- 峰值 GPU 显存；
- 主机 MaxRSS；
- tokens/s、samples/s；
- 训练总时长；
- 单样本推理时延；
- checkpoint 和 adapter 大小。

---

## 9. 分阶段建设路线

### A0：冻结任务与实验协议

交付：

- 项目 README；
- 任务契约；
- 输入/输出 Schema；
- 指标定义；
- 数据泄漏与真实性声明模板；
- 第一版模型和资源决策记录。

未完成 A0 不进入数据下载或训练。

### A1：数据清单与仓库隔离

交付：

- source registry；
- 许可证与 revision；
- repo family split；
- 原始/处理数据 manifest；
- 精确/近似去重报告；
- 小型合成 fixture 单元测试。

### A2：冻结基线与执行沙箱

交付：

- patch parser/apply；
- C++ 编译和测试 runner；
- timeout/resource limit；
- 固定小测试集；
- Base、Prompt/Few-shot 和现有 Qwen3-8B 外部基线；
- 每条预测和执行证据。

未完成 A2 不进入 SFT。

### A3：SFT

顺序：

1. 100～300 条 pilot；
2. BF16 LoRA；
3. NF4 QLoRA；
4. 同协议比较并冻结正式方案；
5. 扩大训练集；
6. 保存 adapter、配置、seed、日志和资源报告。

### A4：偏好数据

利用同一输入生成多个候选，根据真实执行结果构造 chosen/rejected：

- chosen：可应用、编译、通过隐藏测试、无回归、补丁较小；
- rejected：编译失败、只过 public test、破坏测试、过度修改或格式违规。

保留判定理由和执行证据，不只保存两个文本。

### A5：DPO

- 使用与 SFT 相同的冻结评测集；
- 比较 Base、SFT、DPO；
- 报告质量、回归、格式和资源；
- 检查 DPO 是否只学会更短或更保守的补丁；
- 保存完整配置和 adapter。

### A6：可选 RLVR/GRPO

只有满足以下条件才进入：

- reward 主要来自隐藏测试等不可直接篡改证据；
- 已有足够候选多样性；
- 能检测删测试、硬编码、跳过逻辑和超大补丁；
- DPO 已完成且仍有明确增益空间；
- 当前环境和资源支持。

默认不把它列为第一版必做。

### A7：推理、消融与失败分析

至少比较：

- Prompt-only；
- Few-shot；
- LoRA；
- QLoRA；
- SFT；
- SFT + DPO；
- 不同数据来源、上下文长度和 LoRA target/rank。

建立失败分类：解析失败、应用失败、编译失败、测试失败、回归、超时、越界修改、格式错误。

### A8：最终交付

- 固定 Demo；
- 从新环境执行说明；
- 数据卡、模型卡、评测卡；
- 消融和 Bad Case；
- CI 和单元测试；
- GitHub Release/Tag（用户同意后）；
- 基于真实结果填写简历和面试问答。

---

## 10. 推荐仓库结构

```text
patchalign-cpp/
├── README.md
├── pyproject.toml
├── configs/
│   ├── data/
│   ├── model/
│   ├── sft/
│   └── dpo/
├── docs/
│   ├── decisions/
│   ├── learning/
│   ├── data_card.md
│   ├── model_card.md
│   └── evaluation_report.md
├── manifests/
├── src/patchalign/
│   ├── data/
│   ├── prompts/
│   ├── patches/
│   ├── sandbox/
│   ├── evaluation/
│   ├── training/
│   └── reporting/
├── scripts/
│   ├── data/
│   ├── baseline/
│   ├── train/
│   └── eval/
├── slurm/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
└── artifacts/              # 默认 gitignore，仅保存小型公开摘要
```

原始数据、模型、完整预测和大型日志不要进入 Git。用 manifest 指向远端持久化路径。

---

## 11. 测试和真实性要求

最低测试层次：

1. Schema 和 manifest 单元测试；
2. patch parser/apply 单元测试；
3. CMake/Make/单文件 g++ fixture；
4. timeout、非法路径、删测试、超大输出等安全测试；
5. 小型端到端 fixture；
6. 真实数据 smoke；
7. 模型加载和单 batch 训练 smoke；
8. checkpoint 恢复 smoke；
9. adapter 保存/重载/推理 smoke；
10. 固定冻结评测回归。

任何报告数字都必须能回溯到：

```text
代码 commit
配置哈希
模型 revision
数据 manifest
seed
Slurm Job ID
原始预测
执行结果
汇总脚本版本
```

不能把以下内容写成事实：

- 未真正运行的训练；
- 只通过 public test 却声称修复成功；
- 只在训练集上测得的提升；
- 未知基础模型污染却声称完全无污染；
- 使用厂商 Instruct 能力却全部归因于本人 SFT/DPO。

---

## 12. 新对话的建议开工顺序

新 Codex 第一轮建议只做 A0 和安全检查：

1. 只读检查本地和远端目录；
2. 确认是否创建 `/home/lenovo/A/patchalign-cpp`；
3. 完成并验证仓库专属 Deploy Key；若仓库或 GitHub 页面操作尚未完成，向用户报告闸门；
4. 重新查询 `module avail`、参考环境版本和 QOS 快照；
5. 列出 `/mingli01/models` 可用模型，不修改；
6. 与用户确认主模型权重如何合法进入 `/mingli01/models`；
7. 创建本地 Git 仓库和 A0 文档；
8. 编写可审查的环境声明，并创建 `/mingli01/project/ht/.conda_envs/patchalign-cpp`；
9. 在计算节点完成专属环境的 CUDA、量化和单 batch smoke；
10. 建立最小测试、CI 和目录骨架；
11. 用户验收 A0 后再进入 A1；
12. A2 评测闭环通过后才提交任何正式训练作业。

第一条 GPU 作业应是模型/量化/单 batch smoke，不是正式长训练。

---

## 13. 当前冻结结论与未决事项

### 已冻结

| 事项 | 结论 |
|---|---|
| 项目 | PatchAlign-Cpp |
| 核心语言 | Python 工程 + C++ 缺陷/编译/测试 |
| 必做链路 | Base → SFT → DPO |
| 可选 | RLVR/GRPO |
| 默认主模型 | Qwen2.5-Coder-7B Base |
| 外部现成基线 | `/mingli01/models/Qwen3-8B` |
| 第一版 GPU | 1 张 A800，串行分段 |
| 训练方式 | LoRA/QLoRA pilot 后以证据冻结 |
| 环境 | 在 `/mingli01/project/ht/.conda_envs/patchalign-cpp` 创建项目专属 Conda 环境；其他环境只读 |
| GitHub 连接 | HTTPS fetch + 仓库专属 Deploy Key SSH push；方案已确定，当前尚未配置完成 |
| 数据 | CommitPackFT + RunBugRun C++；外部 Defects4C/SWE 类评测 |
| 爬虫 | 第一版不需要 |
| 评测 | patch → compile → public/hidden tests → regression |

### 未决，必须在新对话确认

1. 本地仓库是否采用 `/home/lenovo/A/patchalign-cpp`；
2. 创建 `HT-O-TA/patchalign-cpp`，生成仓库专属 Deploy Key，在仓库中启用写权限并完成首次推送验证；
3. Qwen2.5-Coder-7B Base 权重由谁下载/上传，平台是否允许联网下载；
4. 第一阶段只做函数级，还是同时加入给定文件上下文；
5. 公开 adapter、数据派生物和完整预测的范围；
6. 账户其他作业何时释放 GPU/内存。

---

## 14. 可直接发送给新 Codex 的开场提示

```text
请进入第二项目准备阶段，先完整阅读：
/home/lenovo/A/patchalign-cpp/docs/handoff/第二项目_PatchAlign-Cpp_Codex交接说明.md

再完整阅读：
/home/lenovo/A/meetingmind-agent/docs/项目规划/第二项目_PatchAlign-Cpp立项与实施路线.md

第二项目的目标是 PatchAlign-Cpp：C++ 缺陷修复可验证后训练。以我掌握数据、LoRA/QLoRA、SFT、DPO、可执行评测和工程复现为首要目标。

严格遵守交接说明中的祝融集群规则：使用系统 conda/3 和 cuda/13.0 模块，在 /mingli01/project/ht/.conda_envs/patchalign-cpp 创建项目专属 Conda 环境；所有依赖只安装到该环境，其他现有环境保持只读，不修改系统 CUDA、驱动或系统 Python。先完成 A0 任务契约与 A2 评测沙箱，再训练。不要修改 MeetingMind 仓库。

GitHub 使用仓库专属 Deploy Key：fetch 走 HTTPS，push 走 SSH Host alias github-patchalign-cpp。该配置当前尚未完成，先按交接文档检查并完成仓库、密钥、公钥写权限和首次推送；不得使用 PAT、协作者邀请或把私钥复制到祝融。

请先检查当前状态并给出 A0 的具体建设计划，然后在安全、已授权范围内开始实施。遇到模型权重获取、GitHub 新仓库或平台权限问题时暂停向我确认。
```

---

## 15. 官方参考入口

- Qwen2.5-Coder-7B Base：<https://huggingface.co/Qwen/Qwen2.5-Coder-7B>
- Qwen3-8B-Base：<https://huggingface.co/Qwen/Qwen3-8B-Base>
- Qwen3-Coder-Next-Base：<https://huggingface.co/Qwen/Qwen3-Coder-Next-Base>
- PEFT 量化训练：<https://huggingface.co/docs/peft/developer_guides/quantization>
- Transformers bitsandbytes：<https://huggingface.co/docs/transformers/quantization/bitsandbytes>
- TRL：<https://huggingface.co/docs/trl/>
- Qwen3-Coder 微调示例：<https://github.com/QwenLM/Qwen3-Coder/tree/main/finetuning>
- CommitPack：<https://huggingface.co/datasets/bigcode/commitpack>
- RunBugRun：<https://github.com/giganticode/run_bug_run>
- Multi-SWE-bench：<https://github.com/multi-swe-bench/>
