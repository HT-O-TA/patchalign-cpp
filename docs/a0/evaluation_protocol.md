# A0 评测协议

状态：Draft  
版本：`0.1.0`

## 1. 固定执行顺序

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
→ sanitizer（适用时）
→ resource and patch-size accounting
→ terminal classification
```

阶段不得跳序。上游失败时，下游标记为 `not_run`，不得误记为失败或通过。

## 2. 终止分类优先级

| 优先级 | 分类 | 条件 |
|---:|---|---|
| 1 | `generation_failed` | 推理失败、OOM 或生成超时 |
| 2 | `parse_failed` | 无唯一合法 unified diff |
| 3 | `policy_violation` | 越界路径、禁止文件、超大 patch 等 |
| 4 | `apply_failed` | patch 不能应用到固定 revision |
| 5 | `build_failed` | 构建非零退出、超时或信号终止 |
| 6 | `public_test_failed` | 已知失败未修复 |
| 7 | `hidden_test_failed` | 未公开约束失败 |
| 8 | `regression_failed` | 原本通过的测试被破坏 |
| 9 | `sanitizer_failed` | 适用 sanitizer 报告问题 |
| 10 | `success` | 全部必需阶段通过 |

每条预测只有一个 terminal classification，同时保留所有已运行阶段的原始结果。

## 3. 主指标

所有比例默认以冻结评测集总样本数为分母，除非指标名称明确限定条件。不得通过排除困难或超时样本改变分母。

| 指标 | 定义 |
|---|---|
| Patch parse rate | 唯一合法 patch 数 / 总样本数 |
| Patch apply rate | 成功 apply 数 / 总样本数 |
| Compile rate | 构建成功数 / 总样本数 |
| Public-test pass rate | public tests 通过数 / 总样本数 |
| Hidden-test Pass@1 | 第一个候选完整成功数 / 总样本数 |
| Regression rate | 发生回归数 / 总样本数；越低越好 |
| Sanitizer pass rate | 适用 sanitizer 且通过数 / sanitizer 适用样本数 |
| Format violation rate | 解析或输出协议违规数 / 总样本数 |
| Timeout rate | 任一必需阶段超时数 / 总样本数 |

第一主指标是 hidden-test Pass@1。Compile rate 或 public pass 不能代替真实修复成功。

## 4. Pass@k

- `k`、temperature、top-p、seed 集合和最大输出 token 必须固定；
- 每个候选独立保留预测和执行证据；
- Pass@k 只作为候选潜力指标，不能替代 Pass@1；
- DPO 候选生成和最终 Pass@k 评测不得复用同一随机候选作为独立测试证据。

## 5. Patch 约束指标

至少报告：

- 修改文件数；
- added/deleted lines；
- 是否触及禁止路径；
- 空 patch 比例；
- 无关改动比例（有可靠判定时）；
- 输出 token 和 patch 字节数。

补丁更短不自动等于质量更好，只能作为约束或诊断。

## 6. 资源指标

- 推理峰值 GPU allocated/reserved memory；
- 主机 MaxRSS；
- 加载、首 token、总生成时间；
- tokens/s、samples/s；
- 编译/测试平均耗时和 P95；
- checkpoint/adapter/artifact 大小；
- GPU-hours。

## 7. 沙箱最低要求

- 每样本独立临时工作树；
- 默认禁网；
- 非特权执行；
- 只读输入和测试；
- 限制 CPU、内存、PID、文件大小、输出和时间；
- 禁止跟随符号链接逃逸；
- 子进程在超时后完整清理；
- stdout/stderr、exit code、signal 和 timeout 可回放；
- 不直接在宿主机无限制运行不可信仓库脚本。

当前仅确认 Slurm 暴露 `--container`；OCI 隔离仍未验收，因此 A2 尚未完成。

## 8. 可比性

Base、Prompt/Few-shot、SFT 和 DPO 必须使用：

- 相同冻结样本；
- 相同 prompt 信息和输出契约；
- 相同 tokenizer 上限和生成预算；
- 相同执行镜像/环境；
- 相同评分器 commit；
- 相同失败与超时处理。

模型官方模板可以不同，但不得给某一模型额外问题信息或更有利的示例。

## 9. 统计报告

- 关键比例报告 bootstrap 置信区间；
- 小规模消融尽量多 seed；
- 单次大训练明确资源限制；
- 同时报告绝对样本数和百分比；
- 不删除失败 run；
- 在正式 SFT 前冻结最小有意义提升和可接受退化阈值。

