# A0 核心任务与评测协议

任务契约状态：**Accepted for A0**
任务契约版本：`0.1.0`
评测协议状态：Draft
评测协议版本：`0.3.0`

本文合并原任务契约与评测协议，作为第一版输入、输出、修改范围、执行顺序、指标和沙箱边界的唯一当前规范。

## 1. 任务定义与层级

给定缺陷描述、已定位的 C++ 上下文和失败证据，模型生成一个最小 unified diff。评测器在固定源码 revision 上应用补丁，并通过编译、公开测试、隐藏测试和回归测试判断是否修复。

### `function`

第一版主任务。输入覆盖一个目标函数及必要的相邻声明；主报告和主要模型比较只在冻结的函数级测试集上计算。

### `file_window`

兼容与诊断层级。目标函数必须完整保留，前后各最多96行，窗口最多256个物理行，完整输入最多4,096 tokens。目标函数自身超过任一上限时排除，不允许截断。该切片单独报告，不混入函数级主指标。

### 第一版不支持

- 未定位的仓库级搜索；
- 多文件自主探索；
- 联网搜索或 Agent 工具循环；
- 自动修改或生成测试；
- 修改构建系统以绕过任务。

## 2. 模型可见输入

prompt 按固定顺序包含：

1. 任务说明；
2. 输出格式约束；
3. `problem_statement`；
4. `failure_evidence`；
5. 允许修改的相对路径；
6. 目标文件和符号；
7. buggy code/context。

模型不得看到 gold patch、hidden test 内容、修复后代码、chosen/rejected 执行标签或外部评测参考补丁。

## 3. 输出与应用协议

模型必须输出恰好一个纯 unified diff，不允许 Markdown 围栏、解释或多个候选：

```diff
--- a/path/to/file.cpp
+++ b/path/to/file.cpp
@@ ... @@
-old line
+new line
```

禁止绝对路径、`../` 路径逃逸、二进制 patch 和未允许文件。解析器不得从自然语言中猜测或拼接 diff。

应用固定执行：

```text
git apply --recount --check -
git apply --recount -
```

两条命令必须在同一固定 `base_commit` 的独立干净工作树中依次执行。禁止 `--ignore-whitespace`、`--3way`、`--reject`、`--unsafe-paths` 和 `--unidiff-zero`。`--recount` 只重新推断 hunk header 的行数计数，不忽略删除行、上下文或空白差异。完整取舍见 [ADR-0002](../decisions/0002-patch-output-protocol.md)。

## 4. 允许修改范围

`allowed_paths` 显式定义可修改的仓库相对路径，第一版只允许一个目标 C/C++ 源文件或头文件。除非另立任务类型，禁止修改：

- 测试文件和测试数据；
- CMake、Makefile、CI 和评测脚本；
- sanitizer 或断言配置；
- vendored/generated 文件；
- 仓库外路径；
- 子模块指针和大文件引用。

## 5. 可执行样本前置条件

正式可执行样本必须证明：

1. 固定 base revision 可重建；
2. 修复前目标测试失败；
3. gold/fix revision 上目标测试通过；
4. 命令不需要密钥、私有服务或运行时联网；
5. 许可证和来源允许声明的使用方式。

不能满足 before-fail/after-pass 的样本可以进入非执行 SFT 候选，但不得进入 Hidden-test Pass@1 分母。

## 6. 固定执行顺序

```text
raw model text
→ unique patch extraction
→ patch/path policy
→ temporary worktree preparation
→ patch apply
→ build
→ public tests
→ hidden tests
→ regression tests
→ sanitizer（显式适用时）
→ resource and patch-size accounting
→ terminal classification
```

阶段不得跳序；上游失败时下游标记为 `not_run`，不得误记为失败或通过。

## 7. 终止分类

| 优先级 | 分类 | 条件 |
|---:|---|---|
| 1 | `generation_failed` | 推理失败、OOM 或生成超时 |
| 2 | `parse_failed` | 无唯一且语法完整的 unified diff |
| 3 | `policy_violation` | 越界路径、禁止文件、超大 patch 等 |
| 4 | `apply_failed` | 合法 patch 不能应用到固定 revision |
| 5 | `build_failed` | 构建非零退出、超时或信号终止 |
| 6 | `public_test_failed` | 已知失败未修复 |
| 7 | `hidden_test_failed` | 未公开约束失败 |
| 8 | `regression_failed` | 原本通过的测试被破坏 |
| 9 | `sanitizer_failed` | 适用 sanitizer 报告问题 |
| 10 | `success` | 全部必需阶段通过 |

每条预测只有一个 terminal classification，同时保留所有已运行阶段的原始结果。

## 8. 成功、指标与分母

成功要求 patch 唯一可解析、路径和范围合法、可应用、构建成功、public/hidden/regression 全部通过、未触发适用 sanitizer，且未超出资源限制。空 patch、只通过 public、删除测试或硬编码公开输入均不算成功。

所有比例默认以冻结评测集总样本数为分母；不得排除困难、格式失败或 timeout 样本改变分母。

| 指标 | 定义 |
|---|---|
| Patch parse rate | 唯一合法 patch 数 / 总样本数 |
| Patch apply rate | 成功 apply 数 / 总样本数 |
| Compile rate | 构建成功数 / 总样本数 |
| Public-test pass rate | public 通过数 / 总样本数 |
| Hidden-test Pass@1 | 第一个候选完整成功数 / 总样本数 |
| Regression rate | 发生回归数 / 总样本数；越低越好 |
| Format violation rate | parse 或 policy 违规数 / 总样本数 |
| Timeout rate | 任一必需阶段超时数 / 总样本数 |
| Sanitizer pass rate | 适用且通过数 / 显式适用样本数 |

第一主指标为 function Hidden-test Pass@1。正式 SFT/DPO 的提升、退化、paired bootstrap 和一票否决门禁见 [ADR-0004](../decisions/0004-training-quality-gates-v1.md)。

## 9. Sanitizer 适用性

- A2 执行配置/结果 Schema 必须显式记录 `sanitizer_applicable`；
- `true` 时必须绑定受控命令、工具版本、环境和 timeout；
- `false` 时阶段记为 `not_applicable`，不进入 sanitizer 分母；
- 缺少标记不得推断为 `false`，样本不能进入正式 sanitizer 指标；
- `sample-v0.2` 不静默追加该字段，由 A2 版本化执行 Schema 落地。

## 10. Pass@k、Patch 与资源诊断

- Pass@k 必须冻结 `k`、temperature、top-p、seed 和最大输出 token；候选独立保留，不能替代 Pass@1；
- 至少报告修改文件数、added/deleted lines、越界路径、空 patch、输出 token 和 patch 字节数；
- 至少记录推理显存、MaxRSS、加载/生成时间、tokens/s、编译测试均值/P95、artifact 大小和 GPU-hours；
- 补丁更短不自动等于质量更好。

## 11. 沙箱最低要求

- 每样本独立临时工作树，默认禁网、非特权；
- 输入和测试只读；限制 CPU、内存、PID、文件、输出和时间；
- 禁止符号链接逃逸，超时后清理完整进程组；
- stdout/stderr、exit code、signal 和 timeout 可回放；
- 不在宿主机无限制运行不可信仓库脚本。

当前仅确认 Slurm 暴露 `--container`；OCI 隔离尚未验收，因此 A2 未完成。

## 12. 可比性、统计与版本

Base、Prompt/Few-shot、SFT 和 DPO 必须使用相同冻结样本、输入信息、生成预算、执行环境、评分器 commit 和失败处理。关键比例报告绝对计数及 bootstrap 区间，不删除失败 run。

prompt、Schema、评分器和协议必须版本化；样本由 `provenance_hash` 标识；同一预测和环境重复评分必须产生相同阶段状态。契约变化必须通过 ADR 和版本号记录。

## 13. 验收状态

- 用户已于 2026-09-01 接受完整任务契约和 ADR-0002 输出协议；
- 严格 parser、`--recount`、阶段分类和重复评分已通过合成 fixture；
- 指标分母、跳过规则、失败优先级和质量门禁已机器化测试；
- A2 不可信仓库沙箱和正式执行结果 Schema 仍待完成。

合并后的 A0 验收证据见 [`a0-validation.md`](../evidence/a0-validation.md)。
