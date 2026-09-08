# PatchAlign-Cpp 交付说明

本目录是 PatchAlign-Cpp 简历交付版的正式入口。项目已完成 SFT、执行偏好构建、真实 DPO、独立开发集选型和 formal/confirmation 评分；Defects4C 候选评分及最终 artifact 清单正在收尾。历史的阶段性收尾决定继续保留，但不作为当前项目状态。

当前默认模型是 **M1-R2**。DPO-beta03 在 formal 500 上将 Pass 从 14 提升到 19，但 timeout 从 2 增加到 5，`+0.6pp` 超过冻结的 `+0.5pp` 上限，因此被安全门禁否决。Defects4C 最终结果只会补充外部泛化画像，不能消除已经触发的 formal veto。

实时作业状态只在[项目状态](../status.md)维护；最终机器事实以 `artifacts/a5/final-evaluation-v1/comparison.json` 和 `artifacts/a5/delivery-manifest-v1.json` 为准。

## 交付入口

- [最终技术报告](final_report.md)：问题、阶段、SFT/DPO 结果、负结果、工程经验和限制；
- [架构与数据流](architecture.md)：数据隔离、后训练、受约束生成、沙箱执行和证据链；
- [复现指南](reproduction.md)：环境核验、CLI、DPO 训练、选型和一次性最终评测；
- [M1-R2 模型卡](model_card_m1_r2.md)：最终推荐模型的身份、训练、用途和风险；
- [DPO-beta03 模型卡](model_card_dpo_beta03.md)：候选模型的正收益、安全否决和非预期用途；
- [简历与面试复述](interview_brief.md)：AI 应用开发版与后训练版表达；
- [项目全程总结](../项目全程总结与核心结论.md)与[工程复盘](../interview_retrospective.md)：从立项到交付的稳定叙事。

## 最终模型决策

| 候选 | Dev 64 | Formal 500 | Confirmation 124 | 决策 |
|---|---:|---:|---:|---|
| M1-R2 | Pass 5；apply/build 53/52 | Pass 14；timeout 2 | Pass 0；timeout 4 | 推荐默认模型 |
| DPO beta=0.1 | Pass 5；apply/build 55/55 | 未进入正式评测 | 未进入正式评测 | dev 消融后未入选 |
| DPO beta=0.3 | Pass 5；apply/build 57/57 | Pass 19；timeout 5 | Pass 0；timeout 2 | formal timeout 安全否决 |

选择 beta=0.3 进入正式评测是按冻结的 dev 层级规则执行；最终回退 M1-R2 是按冻结的 formal 退化上限执行。两次决策使用不同数据和职责，不是事后改口径。

## 应用化边界

`patchalign-cpp` CLI 接收结构化 JSON 请求，将其渲染为冻结 prompt，加载固定 Base + LoRA，以 NF4 greedy decoding 生成一个候选补丁，并执行 strict unified diff 与路径策略校验。metadata 记录 Base config、adapter config、adapter 权重、prompt 和 patch SHA256，以及 token 数、延迟、峰值显存和 seed。

CLI 不会自动执行、提交或合并模型输出。真正的正确性判断由 rootless、禁网、限时的 Bubblewrap 链完成：`git apply --recount` → build → public → hidden → regression → 明确适用时的 sanitizer。通过 parse/apply/compile 不能替代端到端 Pass。

## 存储与同步边界

| 内容 | 位置 | 交付方式 |
|---|---|---|
| 代码、配置、Schema、测试、Slurm、文档 | GitHub `HT-O-TA/patchalign-cpp` 的 `main` | Git 跟踪 |
| 最终评测恢复代码 | GitHub 分支 `a5-eval-recovery-97614`，提交 `fbe0717be11ca55648cd4d9d69c22c0fa707471c` | Git 跟踪、只作评测溯源 |
| Base 模型 | `/mingli01/models/Qwen2.5-Coder-7B` | 集群只读，不进 Git |
| 项目环境 | `/mingli01/project/ht/.conda_envs/patchalign-cpp` | 集群 prefix，不进 Git |
| 训练、推理、评分和日志 | 集群仓库的 `artifacts/` | 不进 Git，以 manifest + SHA256 索引 |
| 最终推荐 adapter 本地副本 | `artifacts/delivery/model/m1_r2/` | 本机忽略目录，附 `PROVENANCE.json` |
| 原始与处理数据 | `/mingli01/data/patchalign-cpp/` | 集群数据目录，不进 Git |

GitHub、本机和集群通过 commit 同步代码，不使用跨 SSH 软链接或双向删除同步。模型、数据和运行产物按“集群原件 + 本地必要副本 + Git 中哈希索引”管理。

## 当前关键 artifact

所有相对路径均以 `/mingli01/project/ht/patchalign-cpp/` 为根。

| Artifact | 相对路径 | SHA256 |
|---|---|---|
| M1-R2 adapter | `artifacts/a3/sft-r2/training/checkpoints/checkpoint-step-000150-epoch-1/adapter/adapter_model.safetensors` | `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a` |
| DPO beta=0.3 adapter | `artifacts/a5/dpo-training-v1.1/beta03/final-adapter/adapter_model.safetensors` | `2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a` |
| DPO beta=0.3 training manifest | `artifacts/a5/dpo-training-v1.1/beta03/training-manifest.json` | `25a2265bcc264054cfd0ed7a7175803bcef0de24bc90bc14aa70e0f837db2dca` |
| DPO dev selection | `artifacts/a5/dev-evaluation-v1/selection.json` | `248ad6dcb6783fd2e8c971b05191a87c5b5bd02b696e26f7076262631de665f4` |
| DPO formal predictions | `artifacts/a5/final-evaluation-v1/formal/inference/predictions.jsonl` | `34a13513f11a40b7c10e0e30c8d99c8093afa9129236152c47cbaf56dfa3515e` |
| DPO formal scores | `artifacts/a5/final-evaluation-v1/formal/scoring/scores.jsonl` | `787871f4b63546f9564ce8f637086600311c02b1eaa8fcbf19d767540a82abfc` |
| DPO confirmation predictions | `artifacts/a5/final-evaluation-v1/confirmation/inference/predictions.jsonl` | `f71ec0b15d80f724ae004c1eb81badac0021cf001c3c3e0d5c33041a55910401` |
| DPO confirmation scores | `artifacts/a5/final-evaluation-v1/confirmation/scoring/scores.jsonl` | `65b97d79dab92ad3a1127a752659e20318f9adc19b50f4399c969bca8e66b35d` |

最终 Defects4C scores、comparison、failure analysis、CLI smoke 和 delivery manifest 的完整身份在后台链完成后一次补入，不使用运行中的部分检查点推断。

## 接收方验证

在集群最终 `main` 上执行：

```bash
cd /mingli01/project/ht/patchalign-cpp
git status --short --branch
git rev-parse HEAD

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
PYTHONNOUSERSITE=1 "$ENV_PREFIX/bin/python" -m pytest -q
sha256sum artifacts/a3/sft-r2/training/checkpoints/checkpoint-step-000150-epoch-1/adapter/adapter_model.safetensors
sha256sum artifacts/a5/dpo-training-v1.1/beta03/final-adapter/adapter_model.safetensors
"$ENV_PREFIX/bin/python" -m json.tool artifacts/a5/final-evaluation-v1/comparison.json >/dev/null
"$ENV_PREFIX/bin/python" -m json.tool artifacts/a5/delivery-manifest-v1.json >/dev/null
```

预期工作树干净、测试全部通过、两个 adapter SHA256 与上表一致；最终 comparison 应为 `recommended_model=m1_r2` 且包含 `formal_timeout_increase_exceeded`。交付 manifest 还会 fail-closed 核验模型、数据、评测、CLI smoke 与环境文件的实际哈希。

## 接收清单

- [x] G0、A0～A4 的代码、契约、实验和负结果已固化；
- [x] 175 对审计偏好与 beta=0.1/0.3 真实 DPO 已完成；
- [x] 64 条独立 dev 选型及 formal 500、confirmation 124 已完成；
- [x] M1-R2 与 DPO-beta03 模型卡已建立，最终默认模型已按安全门禁确定；
- [x] 应用 CLI、结构校验、provenance metadata 和固定 smoke 证据链已实现；
- [x] M1-R2 adapter 已本地化并核验；
- [ ] DPO Defects4C 176 条替换评分与自动聚合完成；
- [ ] 最终模型 CLI GPU smoke 完成；
- [ ] hash-complete delivery manifest、最终报告和三端一致性审计完成。

## 发布边界

本仓库原创代码和文档采用 Apache-2.0，但该许可证不自动覆盖 Base 权重、训练数据、adapter、生成补丁或第三方依赖。本轮不创建公共模型 release；大型权重、原始数据和完整预测的公开再分发仍需单独的许可、敏感信息和安全审计。

RLVR/GRPO 不属于本轮交付。只有以上待办全部关闭后，才会把它作为可选扩展重新评估，而不是用它替代当前交付缺口。
