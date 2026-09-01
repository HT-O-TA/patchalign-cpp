# A0 样本与运行 Schema

状态：Draft
当前 canonical sample 版本：`0.2.0`

## 1. 设计原则

- 规范记录和训练投影分离；
- 来源、许可证、revision、切分和执行命令不可丢失；
- gold patch 只存在于规范记录，生成 prompt 明确排除；
- 所有路径是仓库相对 POSIX 路径；
- 时间以 UTC RFC 3339 表示；
- 内容和配置使用 SHA256；
- 缺失信息显式为 `null` 或缺失字段，不用空字符串伪装已知值。

## 2. 规范样本

机器定义见 [`sample-v0.2.schema.json`](../../schemas/sample-v0.2.schema.json)。`sample-v0.1` 原样保留用于历史记录重放，不接受 v0.2 新字段；A1 新建样本必须使用 v0.2。核心字段：

| 字段 | 说明 |
|---|---|
| `schema_version` | 当前版本固定为 `0.2.0` |
| `sample_id` | 稳定样本 ID，不随训练投影改变 |
| `source_dataset` | CommitPackFT、RunBugRun、Defects4C 等 |
| `source_revision` | 数据集 revision；未知时必须披露 |
| `repo_id` | 原始 owner/repo 或数据集等价标识 |
| `repo_family` | fork/mirror/vendor 归一化后的仓库族 |
| `base_commit` | buggy revision |
| `fix_commit` | 已知修复 revision，可为空 |
| `task_level` | `function` 或 `file_window` |
| `edit_type` | `single_line`、`multi_line_local`、`add_helper` 或 `localized_refactor` |
| `changed_logical_lines` | 逻辑修改行数，按修改类型联动限制且总上限为 40 |
| `problem_statement` | 缺陷描述 |
| `failure_evidence` | 编译错误、失败测试或运行现象 |
| `context` | 目标文件、符号、行范围和 buggy code |
| `file_window_lines` | file-window 实际物理行数；function 样本为 `null` |
| `file_window_context_before` | 目标函数前实际上下文行数；function 样本为 `null` |
| `file_window_context_after` | 目标函数后实际上下文行数；function 样本为 `null` |
| `input_token_count` | 固定 tokenizer 下完整模型输入 token 数，最大 4,096 |
| `allowed_paths` | 模型 patch 允许修改的路径 |
| `gold_patch` | 训练/离线验证可用；生成时禁止进入 prompt |
| `build_command` | 受控构建命令数组 |
| `public_test_command` | 公开验证命令数组；非执行 train/validation 候选可为 `null` |
| `hidden_test_command` | 隐藏验证命令数组或 `null` |
| `regression_test_command` | 回归命令数组 |
| `public_test_count` | public 测试数量；internal test 至少 1 |
| `hidden_test_count` | hidden 测试数量；internal test 至少 1 |
| `regression_test_count` | regression 测试数量；internal test 至少 3 |
| `timeout_seconds` | 单样本总或阶段超时 |
| `license` | SPDX 表达式或审计状态 |
| `split` | train/validation/internal/external |
| `provenance_hash` | 规范化来源与内容哈希 |

命令使用字符串数组而不是 shell 字符串，减少二次解析和注入歧义。确需 shell 的样本必须显式声明，并由沙箱策略单独审核。

## 3. 预测记录

机器定义见 [`prediction-v0.1.schema.json`](../../schemas/prediction-v0.1.schema.json)。每次生成必须保留：

- `run_id`、`sample_id`；
- 模型 ID、revision、adapter hash；
- prompt template 版本和 prompt hash；
- tokenizer/config hash；
- seed 和生成参数；
- 原始模型文本；
- 提取后的 patch 或 `null`；
- 输入/输出 token 数；
- 推理耗时和峰值显存；
- 生成状态与错误。

原始文本不得被解析器覆盖。解析逻辑升级时，应从同一原始文本重新派生新结果。

## 4. 执行结果

执行结果后续在 A2 固化独立 Schema，至少包含：

- sandbox/backend 版本；
- base revision 和临时工作树 ID；
- parse、policy、apply、build、public、hidden、regression、sanitizer 阶段结果；
- 每阶段 exit code、signal、timeout、stdout/stderr artifact；
- 修改文件数、增加/删除行数；
- CPU time、wall time、MaxRSS、最大进程数和输出大小；
- 最终失败分类和成功布尔值。

在 A2 Schema 冻结前，不得生成正式评测报告。

## 5. Run manifest

机器定义见 [`run-manifest-v0.1.schema.json`](../../schemas/run-manifest-v0.1.schema.json)。一个可报告 run 必须绑定：

```text
run_id
git_commit
dirty_worktree
model_id + revision + config hash
adapter hash（适用时）
dataset manifest + hash
prompt version + hash
evaluation protocol version
environment evidence hash
random seed
Slurm Job ID
prediction artifact hash
execution artifact hash
summary script commit/hash
```

`dirty_worktree=true` 的 run 可以用于调试，但默认不得作为最终报告唯一证据。

## 6. 切分约束

必须先确定 `repo_family` 和外部 benchmark 黑名单，再分配 split，之后才生成函数或上下文样本。禁止先随机切分样本再补仓库隔离。

RunBugRun 按题目/程序标识隔离，不得把它描述成 repository-family 隔离。

## 7. 已冻结的数据组成与 v0.2 编码

第一版目标配额、100% C++ 主范围、85/15 task-level 比例、修改类型配额、file-window 上限和 public/hidden/regression 覆盖规则见 [ADR-0003](../decisions/0003-dataset-composition-v1.md)。

`sample-v0.2.schema.json` 已编码以下字段：

```text
edit_type
changed_logical_lines
file_window_lines
file_window_context_before
file_window_context_after
input_token_count
public_test_count
hidden_test_count
regression_test_count
```

联动规则：

- `single_line` 固定为 1 个逻辑修改行；`multi_line_local` 为 2～20 行；`add_helper` 和 `localized_refactor` 为 2～40 行；
- `function` 的三个 file-window 字段必须为 `null`；`file_window` 必须填写实际值，且遵守 256/96/96 上限；
- 所有样本的 `input_token_count` 为 1～4,096；
- `internal_test` 必须提供三个测试命令，并满足 public ≥ 1、hidden ≥ 1、regression ≥ 3；
- 单文件范围通过 `allowed_paths` 最多一个路径实施。

冻结 ADR 和 Schema 验收不等于正式数据已经构建。不得把 v0.2 字段塞入 `additionalProperties: false` 的 v0.1 样本。

## 8. 自动验收证据

2026-09-01 在集群项目环境 `/mingli01/project/ht/.conda_envs/patchalign-cpp` 中设置 `PYTHONNOUSERSITE=1` 后，全量 pytest 连续运行两次，均为 `30 passed`。验收覆盖：

- v0.1 历史正例继续通过，且拒绝 v0.2 字段；
- v0.2 三类正例通过；
- 修改行数联动、file-window/token 上限和 internal test 数量门槛；
- `null` 命令语义、非法路径、多文件、未知字段、缺失字段和错误版本。

该结果关闭 Schema 自动测试门禁，不关闭确定性评分 fixture、输出协议验收或沙箱门禁。
