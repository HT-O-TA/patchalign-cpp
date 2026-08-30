# PatchAlign-Cpp 目录结构台账

> 用途：记录 PatchAlign-Cpp 本地、祝融、模型和环境目录的当前结构与职责边界。  
> 更新规则：每次发生较大的目录新增、移动、删除、重命名或职责变化时，必须同步更新“当前结构”“目录备注”和“变更记录”。  
> 首次建立：2026-08-30  
> 当前状态：准备/G0 已完成，正式 A0 尚未开始。

## 1. 祝融当前结构

```text
/mingli01/project/ht/
├── patchalign-cpp/                         # 项目运行目录；当前尚未初始化为 Git 仓库
│   ├── .gitignore                          # 忽略 artifact、日志、缓存和密钥文件
│   ├── scripts/
│   │   └── smoke/
│   │       └── patchalign_g0_smoke.py      # BF16 LoRA / NF4 QLoRA 真实模型综合 smoke
│   ├── slurm/
│   │   └── g0_smoke.sbatch                 # 适配祝融和当前显式 prefix 的 G0 作业脚本
│   └── artifacts/                          # 大型或运行期产物；默认不得提交 Git
│       └── smoke/
│           ├── g0/
│           │   └── 90719/                  # 成功 G0 的 JSON、BF16/NF4 adapter 与哈希证据
│           ├── history/                    # 旧脚本、失败版本和生成文件归档
│           │   ├── 90574/
│           │   ├── 90699/
│           │   ├── 90719/
│           │   └── generated/
│           └── logs/                       # Job 90574、90699、90719 的原始 Slurm 日志
└── .conda_envs/                            # 项目环境统一父目录；不属于 Git 仓库
    └── patchalign-cpp/                     # PatchAlign-Cpp 专属 Conda prefix
        ├── bin/
        ├── conda-meta/
        ├── lib/
        └── repro/                          # Conda explicit 清单与 pip freeze
```

## 2. 相关外部路径

```text
/mingli01/models/
└── Qwen2.5-Coder-7B/                       # 主训练 Base 模型，只读使用

/home/lenovo/A/
├── patchalign-cpp/                         # 本地 Git 主工作区，main 分支
│   ├── README.md
│   ├── pyproject.toml
│   ├── configs/model/
│   ├── docs/
│   │   ├── a0/
│   │   ├── decisions/
│   │   ├── handoff/
│   │   └── records/
│   ├── schemas/
│   ├── src/patchalign/
│   └── tests/
└── new/                                   # PatchAlign-Cpp 文档已迁出，当前为空
```

GitHub 目标仓库：

```text
HT-O-TA/patchalign-cpp
```

当前为可访问的空仓库；Deploy Key 身份已验证，首次项目 push 尚未进行。

## 3. 目录备注

### 3.1 `/mingli01/project/ht/patchalign-cpp`

- 祝融上的项目运行目录；
- 后续用于同步本地仓库代码、配置和 Slurm 脚本；
- 当前只保存 G0 相关脚本和证据，还不是完整项目；
- 当前没有 `.git`，不得误写成已经完成 Git 初始化或推送；
- 原始数据、模型权重和大型训练产物不得进入 Git。

### 3.2 `scripts/smoke`

- 保存可维护、可复用的环境和模型 smoke 代码；
- 当前 `patchalign_g0_smoke.py` 已在 Job `90719` 上真实通过；
- 新 smoke 必须保存脚本哈希、环境版本、Job ID 和资源指标；
- 不把一次 smoke 的 loss 或短生成写成训练质量结论。

### 3.3 `slurm`

- 保存具有明确 `#!/bin/bash` 的 Slurm 作业文件；
- 不使用包含 Bash 专属语法的裸 `sbatch --wrap`；
- 提交前运行 `bash -n`；
- 当前显式 prefix 必须校验 `command -v python` 和 `sys.prefix`；
- 必须设置 `PYTHONNOUSERSITE=1`；
- 不在计算作业中安装依赖。

### 3.4 `artifacts`

- 保存运行产生的 JSON、adapter、日志、失败证据和资源记录；
- 已被 `.gitignore` 忽略；
- 小型公开摘要可在后续审核后复制到报告目录；
- 大型 adapter、完整预测和原始日志默认留在祝融；
- 删除或归档 artifact 前必须确认对应 Job ID、哈希和报告引用。

### 3.5 `.conda_envs/patchalign-cpp`

- 这是环境，不是项目代码目录；
- 完整 prefix：`/mingli01/project/ht/.conda_envs/patchalign-cpp`；
- Conda 环境列表中的逻辑名称栏可能为空，脚本不得只依赖名称激活；
- 依赖只能安装到该 prefix；
- 不修改 `base`、`dirl_grpo`、`llamafactory_env` 等历史环境；
- 环境中不再存放项目 smoke 源码或运行 artifact。

### 3.6 `/mingli01/models/Qwen2.5-Coder-7B`

- 作为主训练 Base 模型只读使用；
- 不复制进项目仓库；
- 不在原目录保存 adapter、cache 或训练输出；
- 当前 4 个 safetensors 分片均存在；
- 精确 Hugging Face upstream revision 尚未从下载元数据恢复。

### 3.7 `/home/lenovo/A/patchalign-cpp`

- 已创建的本地 Git 主工作区，当前分支为 `main`；
- 已建立 README、A0 Draft 文档、ADR、Schema、模型配置和最小 Python 包骨架；
- 原 `/home/lenovo/A/new` 中三份项目文档已迁入本仓库；
- A0 尚未验收，不能写成已完成；
- 祝融运行目录不是本地 Git 仓库的替代品。

## 4. 预计的正式项目结构

以下是 A0～A2 逐步形成的目标结构。其中 README、pyproject、A0 文档、Schema 和最小包骨架已经存在，其余目录仍是规划：

```text
patchalign-cpp/
├── README.md
├── pyproject.toml
├── .gitignore
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
│   ├── smoke/
│   ├── data/
│   ├── baseline/
│   ├── train/
│   └── eval/
├── slurm/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
└── artifacts/                              # Git 忽略
```

在正式创建前，本节只能称为“预计结构”，不得和实际目录混淆。

## 5. 更新触发条件

以下变化必须更新本文：

1. 创建本地 Git 仓库；
2. 祝融运行目录初始化或同步 Git；
3. 新增或调整 `configs`、`src`、`tests`、`manifests`、`docs`；
4. 数据、checkpoint、预测、日志的持久化路径确定；
5. 新增训练、评测或沙箱专用环境/容器；
6. 模型路径、环境 prefix 或 Git remote 改变；
7. 大型 artifact 迁移、归档或删除；
8. A0、A1、A2、A3、A5、A8 等主要里程碑完成。

每次更新至少记录：

- 日期；
- 变更前后路径；
- 变更原因；
- 是否移动或删除文件；
- 是否影响 Git、复现命令、Slurm 脚本或报告引用；
- 相关 Job ID、commit 或 artifact 哈希。

## 6. 变更记录

### 2026-08-30：首次建立目录台账

- 建立本文；
- 记录准备/G0 完成后的真实目录结构；
- 明确项目目录与 Conda 环境并列；
- 记录本地 Git 仓库尚未创建；
- 记录未来正式项目结构仅为规划。

### 2026-08-30：smoke 文件从 Conda prefix 迁出

- 迁移前：`/mingli01/project/ht/.conda_envs/patchalign-cpp/smoke`；
- 迁移后：
  - 代码进入 `/mingli01/project/ht/patchalign-cpp/scripts/smoke`；
  - sbatch 进入 `/mingli01/project/ht/patchalign-cpp/slurm`；
  - 结果、历史和日志进入 `/mingli01/project/ht/patchalign-cpp/artifacts/smoke`；
- 迁移后关键脚本、结果 JSON 和 adapter 哈希保持不变；
- 清空并移除 Conda prefix 下旧 `smoke` 目录；
- 未移动或修改模型、Conda 包和其他项目文件。

### 2026-08-30：创建本地 Git 仓库与 A0 Draft

- 创建 `/home/lenovo/A/patchalign-cpp`，初始化 `main` 分支；
- 将 `/home/lenovo/A/new` 中三份 PatchAlign-Cpp 文档迁入 `docs/handoff` 和 `docs/records`；
- 新增 README、pyproject、A0 文档、ADR、模型配置和 JSON Schema；
- A0 明确标记为 Draft，尚未通过 fixture、评分闭环、许可证等验收门禁；
- 本轮未推送 GitHub、未下载数据、未运行训练。
