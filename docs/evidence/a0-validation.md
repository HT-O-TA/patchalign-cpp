# A0 自动验收与质量门禁证据

日期：2026-09-01

本文合并 A0 确定性评分、任务契约和训练质量门禁证据。它只证明合成 fixture 上的接口、分类、确定性和机器门禁，不代表真实模型提升、正式数据可重放或 A2 安全沙箱已完成。

## 1. 确定性评分 fixture

固定输入：

- 实现提交：`c000f775071f7632f81edc5103455dfe93d271c2`；
- fixture base commit：`d68a0718b4a066cb319e89efc21e5c2af9d1d093`；
- sample：`tests/fixtures/scoring/sample.json`；
- prediction：`tests/fixtures/scoring/prediction.success.json`；
- 成功评分 SHA256：`sha256:199e2f57b505a9dd148bf9c57c219c8bd952ee90a2c7a74d44ed96b3a6a98dc0`。

成功 prediction 故意写错 hunk 行数计数。普通 `git apply --check` 拒绝，`git apply --recount --check` 接受；评分器不修复或重写内容。

覆盖 `generation_failed`、`parse_failed`、`policy_violation`、`apply_failed`、`build_failed`、public/hidden/regression 失败和 `success`，并验证：

- buggy revision 的 public/hidden 失败、regression 通过；
- 多文件、绝对/逃逸/未允许路径、二进制、围栏、解释和畸形 hunk 被拒绝；
- 上游失败后下游为 `not_run`；
- build 超时终止进程组；
- Hidden-test Pass@1 只计算完整成功；
- 同一 prediction 的记录、汇总和哈希一致。

集群环境为 Python 3.10.20、Git 2.34.1、g++ 11.4.0，设置 `PYTHONNOUSERSITE=1`。评分器引入时全量两次均为 `53 passed`，评分专项为 `12 passed`。

## 2. 任务契约与质量门禁

- 用户接受完整第一版任务契约；
- sanitizer 只在 A2 执行配置显式标记适用的样本执行；
- 用户接受 ADR-0004 的 SFT/DPO 最小提升、退化上限、paired bootstrap、固定分母和 validity veto；
- A3 pilot 只选择方案，不形成正式质量结论。

机器证据：

- 配置：`configs/evaluation/quality_gates_v1.json`；
- 配置规范化 SHA256：`sha256:a21772dbddf07b7c7d42f3813569515b23db1413f33c19f8dc062e7bd5bc7138`；
- 初始实现提交：`db758373ce0f0a3152613a6475f64dfbe648d2ef`；
- 最终实现验收提交：`b236fcafe0d22b4612e5d64c3e4b7c8aa20e1101`。

使用400条 function、100条 file-window 和150条 external 合成结果，默认10,000次 bootstrap、95%区间、seed `20260830`：

```text
SFT +2.0 pp boundary decision:
sha256:9b8823444d21647201c1766edc03ab5e9ae0f1cd37a0f07ae17ae1917a0963dc

DPO +1.0 pp boundary decision:
sha256:d873fe7b5306a5bb27fcd55825bf14610c01b3c53ed54409fbd03da46d562421
```

测试覆盖精确提升/退化边界、CI下界失败、七类退化、三类分母变化、validity veto、bootstrap 参数审计和双候选 pilot tie-break。

最终实现验收：

```text
全量 pytest：75 passed in 9.06s
质量门禁专项：22 passed in 4.04s
```

## 3. 本机跨平台复验（2026-09-02）

本机 Windows 复验发现评分 fixture 不应断言临时 Git 提交的固定 SHA；已改为动态读取 fixture commit，并保留同输入双次评分完全一致的断言。同时对 Windows 的 `.exe` 测试命令做平台适配。复验结果为 `74 passed, 1 skipped`；跳过项是 POSIX 进程组超时清理测试，集群 Linux 验证仍覆盖该路径。历史集群结果 `75 passed` 保持不变。

集群复验已完成：工作副本 commit 为 `6b45fdf0b9a230dea146cca366cfc048c9c6670e`，使用项目专属 Python 环境并设置 `PYTHONNOUSERSITE=1`，完整 pytest 结果为 `75 passed in 9.70s`。

## 4. 边界

测试均未使用 GPU、未提交 Slurm、未修改模型或数据；评分使用临时 clone，结束后 Git 工作树干净。A2 仍须验证 OCI/Slurm 隔离、不可信构建、正式执行结果 Schema、sanitizer 和真实数据重放。

## 5. A0 closeout

### 5.1 已确认边界

A0 已确认 C/C++ localized patch repair 的任务协议、sample/prediction/run-manifest Schema、严格 unified diff 解析与单文件路径策略、parse/policy/apply/build/public/hidden/regression 评分链、SFT/DPO 质量门禁，以及 BF16 LoRA/NF4 QLoRA 的 G0 运行兼容性。A0 不包含正式数据集构建、SFT/DPO 训练、模型质量结论、A2 安全沙箱或外部 benchmark 正式结果。

### 5.2 已知限制

- 临时 Git fixture 不再断言跨平台固定 commit SHA；评分确定性通过同一输入双次结果一致验证。
- Windows 跳过 POSIX 进程组超时清理测试；该路径已在 Linux 集群执行。
- 当前没有正式训练数据、真实 SFT/DPO 质量结果或 A2 安全沙箱结果。
- Qwen2.5-Coder-7B 的 revision 和元数据已核验，但四个权重分片的上游 LFS OID 尚未逐片核对。
- 模型、数据、adapter、日志和其他运行产物保留在集群，不进入 Git；Git 仅保存可复现代码、配置和证据摘要。

### 5.3 证据索引

- 代码与测试修复提交：`6b45fdf0b9a230dea146cca366cfc048c9c6670e`。
- 集群复验：项目专属 Python 环境，`PYTHONNOUSERSITE=1`，`75 passed in 9.70s`。
- 本机复验：`74 passed, 1 skipped`。
- 质量门禁配置：`configs/evaluation/quality_gates_v1.json`。
- 协议与治理：`docs/a0/core_protocol.md`、`docs/a0/governance.md`、`docs/development/git-sync.md`。
- 运行证据：本文档、`docs/records/第二项目_PatchAlign-Cpp_执行记录.md`、`docs/records/第二项目_PatchAlign-Cpp_目录结构.md`。
- 文档记录提交：`195c819`。

### 5.4 项目责任

本项目由用户本人独立完成。用户同时承担项目负责人、数据、评测、集群运维、模型训练和发布治理责任；A1/A2 的每项产物、运行记录和最终决策均由用户审核并确认。

结论：A0 技术验收与证据闭环完成，允许进入 A1 数据 pilot；A1/A2 和正式训练结果不得提前表述为已完成。
