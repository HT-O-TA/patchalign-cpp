# A0 样本与运行 Schema

状态：Draft
版本：`0.1.0`

## 1. 设计原则

- 规范记录和训练投影分离；
- 来源、许可证、revision、切分和执行命令不可丢失；
- gold patch 只存在于规范记录，生成 prompt 明确排除；
- 所有路径是仓库相对 POSIX 路径；
- 时间以 UTC RFC 3339 表示；
- 内容和配置使用 SHA256；
- 缺失信息显式为 `null` 或缺失字段，不用空字符串伪装已知值。

## 2. 规范样本

机器定义见 [`sample-v0.1.schema.json`](../../schemas/sample-v0.1.schema.json)。核心字段：

| 字段 | 说明 |
|---|---|
| `schema_version` | 固定为 `0.1.0` |
| `sample_id` | 稳定样本 ID，不随训练投影改变 |
| `source_dataset` | CommitPackFT、RunBugRun、Defects4C 等 |
| `source_revision` | 数据集 revision；未知时必须披露 |
| `repo_id` | 原始 owner/repo 或数据集等价标识 |
| `repo_family` | fork/mirror/vendor 归一化后的仓库族 |
| `base_commit` | buggy revision |
| `fix_commit` | 已知修复 revision，可为空 |
| `task_level` | `function` 或 `file_window` |
| `problem_statement` | 缺陷描述 |
| `failure_evidence` | 编译错误、失败测试或运行现象 |
| `context` | 目标文件、符号、行范围和 buggy code |
| `allowed_paths` | 模型 patch 允许修改的路径 |
| `gold_patch` | 训练/离线验证可用；生成时禁止进入 prompt |
| `build_command` | 受控构建命令数组 |
| `public_test_command` | 公开验证命令数组 |
| `hidden_test_command` | 隐藏验证命令数组或 `null` |
| `regression_test_command` | 回归命令数组 |
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

## 7. 已冻结的数据组成与下一版字段

第一版目标配额、100% C++ 主范围、85/15 task-level 比例、修改类型配额、file-window 上限和 public/hidden/regression 覆盖规则见 [ADR-0003](../decisions/0003-dataset-composition-v1.md)。

当前 `sample-v0.1.schema.json` 尚未编码以下字段；A1 必须先形成向后兼容的 Schema 版本升级和正反例测试，再生成正式 manifest：

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

冻结 ADR 不等于数据已经构建，也不允许在 Schema 未升级时把这些属性塞入 `additionalProperties: false` 的 v0.1 样本。
