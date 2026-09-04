# PatchAlign-Cpp 目录结构台账

> 用途：记录 PatchAlign-Cpp 本地、祝融、模型和环境目录的当前结构与职责边界。
> 更新规则：只在稳定目录新增、移动、删除、重命名或职责变化时更新；实时作业和 checkpoint 状态见[项目状态](../status.md)。
> 首次建立：2026-08-30
> 本页不维护阶段状态，避免与状态页重复。

## 1. 祝融当前结构

```text
/mingli01/project/ht/
├── patchalign-cpp/                         # Git 计算工作副本，与本机锁定到同一 commit
│   ├── .git/                               # Git 元数据；origin 指向 GitHub
│   ├── .gitignore                          # 忽略 artifact、日志、缓存、权重和密钥文件
│   ├── LICENSE                             # Apache License 2.0 原文
│   ├── NOTICE                              # 项目版权与许可边界说明
│   ├── THIRD_PARTY_NOTICES.md              # 模型、依赖和未来数据来源的审计清单
│   ├── README.md
│   ├── configs/
│   │   ├── data/
│   │   │   ├── a1_pilot_v1.json            # 旧 pilot artifact 重放
│   │   │   ├── a1_pilot_v2.json            # 隔离后的 A1 pilot
│   │   │   ├── a3_formal_v1.json           # A3.3 正式数据配额、隔离和路径契约
│   │   │   └── a3_sft_r2_v1.json           # A3.4 安全子集选择与哈希契约
│   │   ├── evaluation/
│   │   │   ├── quality_gates_v1.json       # SFT/DPO/pilot 机器门禁
│   │   │   ├── a3_baseline_v1.json         # A3.0 模型、prompt 与生成参数
│   │   │   └── a3_scoring_v2.json          # A3.1 终止 LF 规范化评分协议
│   │   ├── model/
│   │   └── training/
│   │       ├── a3_sft_pilot_v1.json         # A3.2 公平训练与评测配置
│   │       ├── a3_sft_formal_v1.json        # A3.3 NF4 QLoRA 训练与正式评测契约
│   │       └── a3_sft_r2_v1.json           # A3.4 adapter continuation 训练与评测契约
│   ├── docs/
│   ├── schemas/                            # A0/A2 Schema 与 A3.1 run manifest v0.2
│   ├── src/patchalign/evaluation/          # parser、评分器、paired bootstrap 与质量门禁
│   ├── tests/
│   │   ├── fixtures/a0/                    # A0 Schema 正例
│   │   ├── fixtures/scoring/               # 微型 C++ repo、sample、prediction 和失败 patch
│   │   └── unit/                           # Schema、parser、策略和评分闭环测试
│   ├── scripts/
│   │   ├── data/
│   │   │   ├── a2_sandbox_runtime.py       # 最小权限 Bubblewrap 命令与资源限制
│   │   │   ├── check_a2_sandbox.py         # A2b fail-closed 沙箱自检
│   │   │   ├── build_a2_holdout.py         # A2a 候选池构造
│   │   │   ├── qualify_a2_holdout.py        # 真实回放、稳定性门禁和 70 条分区
│   │   │   ├── run_a2_cases.py              # 冻结 holdout 独立重放
│   │   │   ├── a2_output_matcher.py         # RunBugRun legacy 输出匹配语义
│   │   │   ├── a2_stability.py              # 回放结果确定性投影
│   │   │   ├── check_a2_replay_stability.py # 资格回放与最终回放精确核验
│   │   │   ├── summarize_a2_results.py      # A2 汇总与验收门禁
│   │   │   └── build_a3_sft_r2_data.py     # A3.4 静态安全子集构造器
│   │   ├── setup/
│   │   │   └── build_bubblewrap.sh         # 固定版本的可复现工具构建入口
│   │   ├── baseline/                        # A3 预检、推理、版本化评分与比较脚本
│   │   ├── training/                        # A3.2 pilot 与 A3.3 可恢复训练、推理、冻结和比较
│   │   └── smoke/
│   │       └── patchalign_g0_smoke.py      # BF16 LoRA / NF4 QLoRA 真实模型综合 smoke
│   ├── slurm/
│   │   ├── a2_holdout.sbatch               # CPU-only A2a
│   │   ├── a2_sandbox.sbatch               # CPU-only A2b
│   │   ├── a3_preflight.sbatch              # CPU-only A3.0 预检
│   │   ├── a3_baseline.sbatch               # 单 GPU 基线推理，2 小时时限
│   │   ├── a3_score.sbatch                  # CPU-only rootless 评分
│   │   ├── a3_compare.sbatch                # CPU-only A3.0 双基线比较
│   │   ├── a3_1_rescore.sbatch              # CPU-only scoring v2 重评分
│   │   ├── a3_3_data.sbatch                # CPU 正式数据构建、资格回放、哈希锁与 preflight
│   │   ├── a3_3_qualify.sbatch             # CPU 可恢复资格筛选与正式 holdout 冻结
│   │   ├── a3_3_finalize.sbatch            # CPU SFT 构建、哈希锁与正式 preflight
│   │   ├── a3_3_infer.sbatch               # 单 GPU、可恢复的 M0/M1 正式推理
│   │   ├── a3_3_train.sbatch               # 单 GPU、checkpoint 可恢复的正式 NF4 QLoRA
│   │   ├── a3_3_score.sbatch               # CPU-only 正式 scoring v2
│   │   ├── a3_3_compare.sbatch             # CPU-only 冻结质量门比较
│   │   ├── a3_1_compare.sbatch              # CPU-only A3.1 可比性审计
│   │   ├── a3_2_preflight.sbatch            # CPU-only A3.2 fail-closed 预检
│   │   ├── a3_2_train.sbatch                # 单 GPU 训练、重载和生成
│   │   ├── a3_2_score.sbatch                # CPU-only scoring v2
│   │   ├── a3_2_compare.sbatch              # CPU-only 可比性审计与选择
│   │   └── g0_smoke.sbatch                 # 适配祝融和当前显式 prefix 的 G0 作业脚本
│   ├── pyproject.toml
│   └── artifacts/                          # 集群本地化产物；被 Git 忽略
│       ├── a2-diagnostics/                 # A2 环境探测和沙箱自检证据
│       │   └── selftest-code-v1/           # Job 93621、93628 使用的自检代码副本
│       ├── a3/                              # A3 预测、版本化评分、比较与 Slurm 日志
│       │   ├── baseline/{m0_base,external}/ # Job 93717、93718 预测与 strict-v1 评分
│       │   │   └── scoring-v2/{93822,93823}/# A3.1 两组独立重评分 artifact
│       │   ├── comparison/93721/            # A3.0 双基线可比性与汇总
│       │   ├── comparison-a31/93828/        # A3.1 v1/v2 可比性审计
│       │   ├── formal/                      # A3.3 preflight、M0/M1、checkpoint、评分和比较
│       │   │   └── history/                 # 不完整 M0 等失败正式产物，只读归档
│       │   ├── sft-pilot/{bf16_lora,nf4_qlora}/ # A3.2 adapter、预测与 scoring v2
│       │   ├── comparison-a32/93955/        # A3.2 可比性审计与方案选择
│       │   └── logs/                        # A3 各阶段 Slurm 原始日志
│       └── smoke/
│           ├── g0/
│           │   └── 90719/                  # 成功 G0 的 JSON、BF16/NF4 adapter 与哈希证据
│           ├── history/                    # 旧脚本、失败版本和生成文件归档
│           │   ├── 90574/
│           │   ├── 90699/
│           │   ├── 90719/
│           │   └── generated/
│           └── logs/                       # Job 90574、90699、90719 的原始 Slurm 日志
├── .conda_envs/                            # 项目环境统一父目录；不属于 Git 仓库
│   └── patchalign-cpp/                     # PatchAlign-Cpp 专属 Conda prefix
│       ├── bin/
│       ├── conda-meta/
│       ├── lib/
│       └── repro/                          # Conda explicit 清单与 pip freeze
└── .tools/
    └── bubblewrap/0.12.0/                  # 项目自带 rootless 沙箱工具；不属于 Git
        ├── build-env/                      # 独立 Conda 构建依赖
        ├── src/                            # 固定官方源码提交
        └── install/bin/bwrap               # A2b 固定执行文件
```

## 2. 相关外部路径

```text
/mingli01/data/patchalign-cpp/a3/
├── formal-holdout-candidates-v1/           # 冻结的 900/250 候选池
├── formal-holdout-qualification-v1/        # 已完成的候选级资格缓存，可审计和恢复
├── formal-holdout-v1/                      # token 门禁后的冻结 400 function + 100 file-window
├── formal-sft-v1/                          # 有效 5,000 train + 500 validation 与哈希锁
└── history/                                # 被后续门禁替代、未通过 preflight 的冻结产物
    ├── formal-holdout-v1-pre-prompt-token-gate-94174/
    ├── formal-sft-v1-pre-prompt-token-gate-94304/
    ├── formal-sft-v1-preflight-config-drift-94320/
    └── formal-sft-v1-preflight-input-mode-94328/

/mingli01/models/
└── Qwen2.5-Coder-7B/                       # 主训练 Base 模型，只读使用

/home/lenovo/A/
├── patchalign-cpp/                         # 本地 Git 主工作区，main 分支
│   ├── README.md
│   ├── LICENSE
│   ├── NOTICE
│   ├── THIRD_PARTY_NOTICES.md
│   ├── pyproject.toml
│   ├── configs/                            # data/model/training/evaluation 机器契约
│   ├── docs/
│   │   ├── README.md                       # 文档职责与防漂移规则
│   │   ├── status.md                       # 唯一实时状态页
│   │   ├── a0/                            # 索引、核心协议、Schema、实验、治理
│   │   ├── decisions/
│   │   ├── development/
│   │   ├── evidence/                      # A0/G0 证据与 A3.3 论文问题材料
│   │   └── records/                       # 执行记录与独立目录台账
│   ├── schemas/
│   ├── scripts/                            # data/baseline/training/smoke
│   ├── slurm/
│   ├── src/patchalign/
│   └── tests/
└── new/                                   # PatchAlign-Cpp 文档已迁出，当前为空
```

GitHub 目标仓库：

```text
HT-O-TA/patchalign-cpp
```

作为代码和文档的同步中枢；本机通过仓库专属 Deploy Key 推送，集群通过 HTTPS 获取。

## 3. 目录备注

### 3.1 `/mingli01/project/ht/patchalign-cpp`

- 祝融上的 Git 计算工作副本；
- 从 GitHub 同步代码、配置、文档和 Slurm 脚本；
- 与本机工作区使用同一个 commit 作为一致性判据；
- 不在两端同时编辑同一个文件，正式作业前要求工作区干净；
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
- `jsonschema 4.26.0` 已安装在该 prefix 内；Schema 验收必须设置 `PYTHONNOUSERSITE=1`，禁止借用 `~/.local` 依赖。

### 3.6 `/mingli01/models/Qwen2.5-Coder-7B`

- 作为主训练 Base 模型只读使用；
- 不复制进项目仓库；
- 不在原目录保存 adapter、cache 或训练输出；
- 当前 4 个 safetensors 分片均存在；
- 下载目录未保存 snapshot 元数据；现已通过用户提供的官方 commit 和四个元数据文件哈希恢复 upstream revision `0396a76181e127dfc13e5c5ec48a8cee09938b02`，权重分片 LFS OID 对照仍待补强。

### 3.7 `/home/lenovo/A/patchalign-cpp`

- 已创建的本地 Git 主工作区，当前分支为 `main`；
- 已建立 README、分层文档、ADR、Schema、版本化配置和 Python 包；
- 当前 canonical sample 为 `schemas/sample-v0.2.schema.json`；v0.1 保留用于历史重放；
- 原 `/home/lenovo/A/new` 中三份项目文档已迁入本仓库；
- 阶段完成情况不在目录台账重复维护，统一见 `docs/status.md`；
- 作为主要开发与提交工作区；GitHub 是同步中枢，祝融是计算工作副本。

### 3.8 `LICENSE`、`NOTICE` 与 `THIRD_PARTY_NOTICES.md`

- 仓库原创代码、文档、Schema、配置和脚本采用 Apache-2.0；
- 当前版权标识为 `Copyright 2026 PatchAlign-Cpp contributors`；
- 仓库许可证不覆盖模型、数据集、生成补丁或第三方依赖；
- 第三方清单当前是初始记录，正式 release 前必须按实际 revision 重新审阅。

### 3.9 Git 同步与产物本地化

- 跟踪内容：代码、配置、Schema、测试、Slurm 脚本和小型证据摘要；
- 集群本地化内容：`artifacts/`、数据、日志、checkpoint、adapter、模型和 Conda prefix；
- 不使用跨 SSH 软链接、SSHFS 或双向删除式 rsync；
- run manifest 必须记录完整 Git commit；
- 操作规范见 `docs/development/git-sync.md`。

### 3.10 `src/patchalign/evaluation` 与 `tests/fixtures/scoring`

- `patches.py` 严格解析唯一 unified diff，并实施单文件和允许路径策略；
- `scorer.py` 在固定 base commit 的临时 clone 中按 parse → policy → apply → build → public → hidden → regression 顺序评分；
- apply 固定使用 `--recount`，不启用忽略空白、三路合并或部分应用；
- scoring fixture 完全自建，只用于接口、分类和确定性测试，不进入正式数据配额；
- 正式不可信数据必须复用已验证的 A2 沙箱边界，不能直接套用 A0 fixture 的宿主执行方式。

### 3.11 `configs/evaluation/quality_gates_v1.json`

- 保存 A3 pilot、正式 SFT 和 DPO 的预注册质量门禁；
- 与 `evaluation/gates.py` 共同实现固定分母、paired bootstrap、退化上限和 validity veto；
- 正式运行必须保存配置 SHA256、有效 bootstrap 参数和决策 SHA256；
- 不允许通过命令行临时降低阈值；变更必须新增配置版本并修订 ADR-0004。

### 3.12 A2 数据、沙箱与 `.tools/bubblewrap`

- A2a 构造候选池，不运行 C++；A2b 资格阶段真实回放候选并执行双回放稳定性门禁；
- 正式 pilot 位于 `/mingli01/data/patchalign-cpp/a2/holdout-v3`，包含 50 条 function 和 20 条 file-window；
- 冻结集合必须先执行 `check_a2_sandbox.py`，自检通过后再独立重放，并用 `check_a2_replay_stability.py` 与资格结果逐测试核验；
- Bubblewrap v0.12.0 位于独立 `.tools` 前缀，不修改项目 Conda 环境；
- 沙箱不映射宿主根目录、`/home` 或 `/mingli01`，只映射系统运行目录和单案例工作区；
- A2 诊断日志保存在 Git 忽略的 `artifacts/a2-diagnostics`；
- Job `93650` 已完成 70/70 独立重放和验收，qualification 与 final 的状态及输出哈希完全稳定；全流程为 CPU-only。

## 4. 结构扩展规则

- 上文只展示已经存在的稳定目录，不预先维护“预计目录树”。
- 新目录必须有实际代码、配置或产物消费者后再创建和登记。
- 未来的 DPO、数据卡、模型卡和最终评测报告在对应阶段落地前只属于计划，不出现在当前结构树。
- 大型 artifact 内部的 Job/checkpoint 子目录由 manifest 和报告索引，不逐项复制到本文。

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
- 将 `/home/lenovo/A/new` 中三份 PatchAlign-Cpp 文档迁入仓库；初始交接说明后续合并并由 Git 历史保留；
- 新增 README、pyproject、A0 文档、ADR、模型配置和 JSON Schema；
- A0 明确标记为 Draft，尚未通过 fixture、评分闭环、许可证等验收门禁；
- 建立本地提交 `aaecacf`，并以 `2de6363` 规范化仓库空白；
- 本轮未推送 GitHub、未下载数据、未运行训练。

### 2026-08-30：建立 Git 同步与集群产物本地化边界

- 将祝融已通过 Job `90719` 的 `scripts/smoke/patchalign_g0_smoke.py` 与 `slurm/g0_smoke.sbatch` 原样纳入本机 Git；
- 新增 `docs/evidence/g0-smoke-90719.md`，只提交关键指标、路径和 SHA256，不复制两个约 77 MiB 的 adapter 或原始日志；
- 新增 `docs/development/git-sync.md`，规定本机开发、GitHub 中转、祝融计算工作副本的单向同步流程；
- 祝融的 `artifacts/` 与并列的 `.conda_envs/patchalign-cpp` 保持原位，没有移动或删除；
- 祝融项目目录初始化为 Git 工作副本，并与本机锁定到同一 commit；
- GitHub 完成首次 push，后续用完整 commit 校验两端一致性。

### 2026-09-01：冻结仓库许可证与产物发布边界

- 新增根目录 `LICENSE`、`NOTICE` 和 `THIRD_PARTY_NOTICES.md`；
- 新增发布策略，状态为 `Accepted for A0`；该内容后合并至 `docs/a0/governance.md`；
- 仓库原创内容采用 Apache-2.0，版权标识暂定为 `PatchAlign-Cpp contributors`；
- 正式 adapter 只允许在逐项审计后发布；中间 checkpoint、optimizer state 和 G0 smoke adapter 默认不公开；
- 未完成许可审计前不公开原始/重打包数据，完整预测需通过许可和安全检查；
- 本次只新增和更新 Git 文档及元数据，没有移动、删除或发布集群 artifact。

### 2026-09-01：冻结模型 revision 与第一版数据组成

- 新增 `docs/decisions/0003-dataset-composition-v1.md`；
- 更新 `configs/model/qwen2_5_coder_7b_base.yaml`，记录 upstream revision、四个已匹配的元数据哈希和权重分片待核验状态；
- 更新 A0 任务、Schema 说明和状态索引，明确数据配额、100% C++ 主范围、85/15 task-level 比例、修改类型配额和 file-window 截取规则；
- 新增文件只属于 Git 跟踪的决策文档，没有创建、移动或删除数据目录、模型、环境或 artifact；
- 正式数据仍未下载或构建；A1 后续生成 manifest 时必须再次更新本文和执行记录。

### 2026-09-01：新增 sample Schema v0.2 并完成自动测试

- 新增 `schemas/sample-v0.2.schema.json`；保留 v0.1，不移动或删除历史 Schema；
- 在 `tests/fixtures/a0` 新增 3 个 v0.2 正例，在 `tests/unit/test_a0_schemas.py` 增加版本兼容和边界反例；
- 集群项目 Conda prefix 内补装 `jsonschema 4.26.0`，未修改其他 Conda 环境；
- 刷新 prefix 内 `repro/pip-freeze.txt`，保留环境依赖复现证据；
- 设置 `PYTHONNOUSERSITE=1` 后连续两次全量 pytest 均为 `30 passed`；
- Git 实现提交为 `ec9039646696fde16dfaf512350acf50ef877da2`；没有创建数据目录、GPU 作业或新 artifact。

### 2026-09-01：新增确定性评分 fixture 与评分器

- 新增 `src/patchalign/evaluation` 和 `tests/fixtures/scoring`；
- ADR-0002 状态改为 `Accepted for A0`，标准应用冻结为 `git apply --recount`；
- fixture base commit 固定为 `d68a0718b4a066cb319e89efc21e5c2af9d1d093`；
- 集群隔离模式全量 pytest 连续两次均为 `53 passed`，评分专项为 `12 passed`；
- 实现提交为 `c000f775071f7632f81edc5103455dfe93d271c2`；
- 没有创建或修改正式数据、模型、GPU 作业和集群 artifact。

### 2026-09-01：冻结完整任务契约与训练质量门禁

- 任务契约状态改为 `Accepted for A0`，sanitizer 显式适用字段由 A2 版本化执行 Schema 承接；该内容后合并至 `docs/a0/core_protocol.md`；
- 新增 ADR-0004、`configs/evaluation/quality_gates_v1.json`、`evaluation/gates.py` 和质量门禁单元测试；
- 集群首轮全量测试为 `73 passed`，专项为 `20 passed`；
- 初始实现提交为 `db758373ce0f0a3152613a6475f64dfbe648d2ef`；最终验收 commit 见执行记录；
- 最终实现提交 `b236fcafe0d22b4612e5d64c3e4b7c8aa20e1101` 验收为全量 `75 passed`、专项 `22 passed`；
- 未新增模型、数据、artifact、GPU 作业或 Conda 依赖。

### 2026-09-01：整理并合并当前文档

- A0 任务与评测合为 `docs/a0/core_protocol.md`；
- 真实性与发布治理合为 `docs/a0/governance.md`；
- A0 自动验收证据合为 `docs/evidence/a0-validation.md`；
- 删除已过期的初始 handoff 当前副本和6份被合并文档，历史均可从 Git 恢复；
- ADR、G0证据、Git同步规范、执行记录和目录台账保持独立；
- 文档数量由18份降为14份，整理提交 `b75fc0214d482cc77eaa929c392158cc267a58d1` 在集群全量测试为 `75 passed`；
- 未移动或删除代码、测试、环境、模型、数据和 artifact。

### 2026-09-03：拆分 A2 并建立 rootless Bubblewrap 边界

- 将 A2 拆为 CPU-only `a2_holdout.sbatch` 和 `a2_sandbox.sbatch`；
- 新增 A2 execution Draft Schema、正反 fixture 和沙箱单元测试；
- 新增 `/mingli01/project/ht/.tools/bubblewrap/0.12.0`，构建环境与项目 Conda prefix 隔离；
- Bubblewrap 固定官方 tag `v0.12.0`、源码 commit `2a76602a8c71f36c1527cf9fc3417d9149822e0c`；
- Job `93628` 在 `gpu28` 完成九项自检，包含最小边界、受控 C++ 编译和执行；
- 诊断 Job 均未申请 GPU，也未运行数据集中的 C++；
- 此状态后由正式 A2 pilot 关闭，见下一条变更记录。

### 2026-09-03：关闭 A2 真实安全执行 pilot

- 候选池扩大为 120 function + 60 file-window，并对初次合格候选执行第二次完整回放；
- 非确定性样本 `p02971` 被稳定性门禁剔除，未进入冻结集合；
- 冻结 `/mingli01/data/patchalign-cpp/a2/holdout-v3`，共 50 function + 20 file-window；
- Job `93650` 在 `gpu25` 以 CPU-only 资源完成第三次独立重放，70/70 满足 buggy 目标失败、fixed 全通过和分区契约；
- 共执行 4,470 个 regression、518 个 public、1,931 个 hidden 测试，超时和输出截断均为 0；
- 新增资格/最终回放精确稳定性检查器，70/70 的状态、匹配结果、输出长度和 SHA256 一致；
- A2 安全执行与真实评分 pilot 已关闭；正式 500 条评测集、模型质量和训练仍未开始。

### 2026-09-03：完成 A3.0 双基线 executable pilot

- 新增 `configs/evaluation/a3_baseline_v1.json`、`scripts/baseline`、四个 `slurm/a3_*.sbatch` 和 `docs/a3_baseline.md`；
- 集群 `artifacts/a3` 新增 M0 Job `93717`、External Job `93718`、CPU 评分 Job `93719`/`93720` 和比较 Job `93721`；
- 两个推理作业各使用 1 张 GPU，在 `gpu14` 串行完成；其余 A3.0 作业均未申请 GPU；
- 完整预测、逐案例评分和日志只留在集群并被 Git 忽略，Git 只跟踪协议、代码、测试和摘要；
- 两组 70 条生成均无 failure/OOM/timeout，确定性 probe 全部稳定；严格原样评分均为 0/70；
- 发现 56 个 strict parse 成功的 raw completion 中有 55 个缺少终止 LF，作为 A3.1 协议问题记录，未修改或回填 A3.0 artifact；
- A3.0 已关闭；正式 500 条评测集、SFT/DPO 训练和质量结论仍未开始。

### 2026-09-03：完成 A3.1 scoring v2 重评分

- 新增 `a3_scoring_v2.json`、ADR-0005、A3.1 文档、版本化评分入口和比较器；
- 新增 CPU-only `a3_1_rescore.sbatch` 与 `a3_1_compare.sbatch`，所有 A3.1 作业均未申请 GPU；
- 集群保留 M0 Job `93822`、External Job `93823` 的独立 `scoring-v2` 目录，以及成功比较 Job `93828`；
- 原 A3.0 prediction 与 strict-v1 评分保持不变；v2 artifact 单独落盘并记录 raw/evaluated SHA256；
- scoring v2 令 M0 apply/compile 从 0 增至 2，External 从 0 增至 13，但两组 Pass 仍为 0；
- A3.1 已关闭；下一步进入 LoRA/QLoRA 小规模训练 pilot。

### 2026-09-03：完成 A3.2 SFT 训练 pilot

- 新增 `configs/training/a3_sft_pilot_v1.json` 与 `docs/a3_2_sft_pilot.md`；
- 新增 `scripts/training`，承载 fail-closed 预检、BF16/NF4 训练、adapter 重载生成、比较与提交入口；
- 新增四个 `slurm/a3_2_*.sbatch`，训练链以依赖方式串行，最多同时使用一张 GPU；
- 预检发现旧 A1 的 26 个跨 split family 重叠，Job `93938` 重建 `pilot-v2-isolated`，旧 v1 保留审计但禁止训练；
- 最终预检 Job `93946` 完成 129 项测试及数据、token、prompt、Bubblewrap 和 gold patch 闭环；
- GPU Job `93951`/`93952` 在 `gpu19` 严格串行完成 BF16 LoRA 与 NF4 QLoRA 训练、adapter 重载和 70 条生成；
- CPU Job `93953`/`93954`/`93955` 完成 scoring v2 与可比性选择；新增两组 `sft-pilot` 和一个 `comparison-a32` artifact 目录；
- BF16/NF4 的 parse/apply/compile/Pass 分别为 70/42/38/1 与 70/39/36/1；成功数相同，按资源 tie-break 选择 NF4；
- A3.2 已关闭，正式 SFT 尚未启动。

### 2026-09-04：A3.3 资格筛选拆分与恢复目录

- 保留 Job 94111 构建的 formal-holdout-candidates-v1/，不重建、不覆盖；
- 新增集群数据目录 formal-holdout-qualification-v1/，其中 manifest 锁定候选与执行策略，每个候选结果使用独立原子 JSON；
- 新增 a3_3_qualify.sbatch 与 a3_3_finalize.sbatch，把长时间资格回放和较短的数据冻结/preflight 解耦；
- 新增 submit_a3_3_pipeline.sh，一次提交 CPU 前置与单 GPU 正式训练/评测依赖链；
- a3_3_data.sbatch 保留为从候选构建开始的一体化兼容入口，同样支持 progress 恢复并修正为“先冻结锁、后 preflight”；
- 集群冻结环境验证 6 项相关测试与 135 项全量测试均通过；
- 此次结构更新提交为 b8063ecc89549811ef6d72f364ad6dcb8a62d384。

### 2026-09-04：A3.3 prompt 门禁与正式历史归档

- formal-holdout-v1 绑定 Qwen2.5-Coder-7B tokenizer、raw_completion 模式和 4,096-token 上限；Job 94312 复用执行缓存完成替换。
- 新增数据 history/，保存旧 holdout、旧 SFT 及两次未通过 preflight 的 SFT；artifacts/a3/formal/history/ 保存 Job 94305 不完整 M0。
- 新增 docs/evidence/a3_3_pipeline_findings.md，按“证据—根因—修正—论文意义”累计正式实验问题。
- Job 94337 完成有效数据锁与 preflight；集群仓库在正式 GPU 链期间固定为 b9aa00248d4264eca0f75c378b004f462ddea9a6。

### 2026-09-04：建立文档单一事实源

- 新增 `docs/README.md`，定义配置、Schema、ADR、阶段文档、证据与历史台账的职责和冲突优先级；
- 新增 `docs/status.md`，作为阶段和 Slurm 作业的唯一实时状态页；
- 根 README、A0/A2/A3 阶段文档不再各自维护动态作业状态；
- 修正祝融结构树中 `configs` 被错误缩进到 `NOTICE` 下的问题，并补入正式数据/训练配置；
- 删除已与现有仓库不符的 A0 “预计目录树”，改为只登记真实存在的稳定目录；
- 历史执行记录保留原事实，但明确所有“当前/尚未/正在”只对当时记录点有效；
- 本次只调整 Git 跟踪文档，没有移动、删除或改写集群数据、模型、环境和 artifact。

### 2026-09-04：恢复项目并建立 A3.4 SFT-R2 结构

- 新增 `configs/data/a3_sft_r2_v1.json`，冻结安全子集来源、选择规则、1,200/117 计数和数据哈希；
- 新增 `configs/training/a3_sft_r2_v1.json`，冻结 M1 adapter continuation、低学习率单轮训练和原 A3.3 评测语义；
- 新增 `scripts/data/build_a3_sft_r2_data.py`，只从冻结 RunBugRun/function train/validation 静态选择循环、边界和复杂度相关样本；
- 新增 `tests/unit/test_a3_sft_r2.py` 与 `docs/a3_4_sft_r2.md`，覆盖选择信号、跨配置一致性和防泄漏边界；
- 当前只建立 Git 跟踪协议和 CPU 数据入口，尚未新增集群数据目录、artifact 或 Slurm 作业。
