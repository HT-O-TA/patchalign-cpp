# PatchAlign-Cpp 交付说明

本目录是“完成 SFT 与探索性研究”口径下的正式交付入口。项目在 A5/DPO 前收尾；历史实验事实不重写，未来若重启 A5 必须建立新的决策和机器配置。

## 交付内容

- [最终技术报告](final_report.md)：研究问题、阶段、正式结果、负结果、工程经验和限制；
- [M1-R2 模型卡](model_card_m1_r2.md)：模型身份、训练、评测、用途、风险和发布状态；
- [ADR-0009](../decisions/0009-close-after-sft-and-exploratory-a4.md)：负责人决定暂不启动 A5/DPO 的终态依据；
- [项目状态](../status.md)：本轮终态与阶段表；
- [项目全程总结](../项目全程总结与核心结论.md)与[面试复盘](../interview_retrospective.md)：稳定叙事和复述材料。

## 交付边界

| 内容 | 位置 | 交付方式 |
|---|---|---|
| 代码、配置、Schema、测试、Slurm、文档 | GitHub `HT-O-TA/patchalign-cpp` 的 `main` | Git 跟踪 |
| Base 模型 | `/mingli01/models/Qwen2.5-Coder-7B` | 集群只读，不进 Git |
| 项目环境 | `/mingli01/project/ht/.conda_envs/patchalign-cpp` | 集群 prefix，不进 Git |
| M1-R2 adapter/checkpoints | `artifacts/a3/sft-r2/training/` | 集群内部 artifact，不进 Git |
| 推理、评分、比较、日志 | `artifacts/a3/` | 集群内部 artifact，不进 Git |
| A4 候选、scores、preferences、audit | `artifacts/a4/` | 集群内部 artifact，不进 Git |
| 原始与处理数据 | `/mingli01/data/patchalign-cpp/` | 集群数据目录，不进 Git |

本轮没有创建公共模型 release、Git tag 或 GitHub Release，也没有复制大型 artifact 到本机。adapter、派生数据和完整预测仍未获准公开分发。

## 核心 artifact 清单

| Artifact | 集群相对路径 | SHA256 |
|---|---|---|
| M1-R2 adapter | `artifacts/a3/sft-r2/training/checkpoints/checkpoint-step-000150-epoch-1/adapter/adapter_model.safetensors` | `8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a` |
| R2 training manifest | `artifacts/a3/sft-r2/training/training-manifest.json` | `b85f43a5edf194b2edfc57cb456459ce1b149b015d5392ee66f1ec97c2ebd884` |
| R2 training summary | `artifacts/a3/sft-r2/training/training-summary.json` | `4cab1f118ebddc90e69e5f3d202b96906c5ab399d00906adc842c6f378cf2f4d` |
| R2 predictions | `artifacts/a3/sft-r2/inference/predictions.jsonl` | `c5fe4e6d90d59c24f749949c8df4f074e2b26f6af625e960ce95013367e7bb6a` |
| R2 scores | `artifacts/a3/sft-r2/inference/scoring-v2/scores.jsonl` | `f05b54a107850591c0cfc16564ef477488cacfe50cb6b703ace41fb093c650b8` |
| R2 score manifest | `artifacts/a3/sft-r2/inference/scoring-v2/score-manifest.json` | `b6d72c856bccb512ed228978a6778464e91a2138ccfaebdfdfa08c10bc714bf2` |
| Internal promotion | `artifacts/a3/sft-r2/comparison-v1/promotion-vs-m0.json` | `5425feb24a635cdad734756277680803c984ccb06386f3b91d2379d691b81027` |
| Confirmation comparison | `artifacts/a3/confirmation/comparison-v1.json` | `faca13cc9695c011e19ce1b30a28ce7a02c783b65eec4af07d71aecacf9e6094` |
| Defects4C comparison | `artifacts/a3/defects4c/external-v1/comparison.json` | `d8a1c14eb5ce7c5a19d59f159fc657dcdb0dee912e6b6124b934fe9cf975f67e` |
| pre-A4 readiness | `artifacts/a3/pre-a4-readiness-v1.json` | `c2a920bc021b95040f3bc97a8367bb68942f491c626c93ea0c2ae39d996c0fd0` |
| A4 candidates | `artifacts/a4/preference-generation-v1/candidates.jsonl` | `ca497dbdd4a989c889d48d2fd9db7b77b4de4d3c327796665a1bde54e7ef0c67` |
| A4 scores | `artifacts/a4/preference-scoring-v1/scores.jsonl` | `c218cd58ab05a8b7fa59188163cbfaabdf206b4482185cf297e1f63ff2e1cee2` |
| A4 preferences | `artifacts/a4/preference-scoring-v1/preferences.jsonl` | `5e6b56e4417d49d0a9fcf85e2ec37d3a4b1e358fda870737adea5ae8c0f578bf` |
| A4 pair audit | `artifacts/a4/preference-scoring-v1/pair-audit.jsonl` | `bcaf461d09e2f54f5b68e30e9a17025ada1c6827b9cb1829556445519b8b6ad2` |
| A4 summary | `artifacts/a4/preference-scoring-v1/summary.json` | `302e7a9aed6759373f579cee88027fc5991161a28d194e960d409a67261e6fc8` |
| A4 run manifest | `artifacts/a4/preference-scoring-v1/run-manifest.json` | `03c61f0e3a376d4879274880634d8d12f4359d03775aa4b7c726cb3d844c7cbe` |

所有相对路径均以 `/mingli01/project/ht/patchalign-cpp/` 为根。若路径与文档冲突，以 artifact manifest 的身份和实际 SHA256 为准。

## 接收方验证

在集群执行：

```bash
cd /mingli01/project/ht/patchalign-cpp
git status --short --branch
git rev-parse HEAD
PYTHONNOUSERSITE=1 /mingli01/project/ht/.conda_envs/patchalign-cpp/bin/python -m pytest -q
sha256sum artifacts/a3/sft-r2/training/checkpoints/checkpoint-step-000150-epoch-1/adapter/adapter_model.safetensors
sha256sum artifacts/a3/sft-r2/inference/scoring-v2/scores.jsonl
sha256sum artifacts/a4/preference-scoring-v1/preferences.jsonl
sha256sum artifacts/a4/preference-scoring-v1/run-manifest.json
```

预期工作树干净，测试通过，四个 SHA256 与上表完全一致。GitHub、本机和集群应通过完整 commit 相等判断代码一致，不使用跨 SSH 软链接或双向删除式同步。

## 最终接收清单

- [x] G0、A0～A3.4 代码和实验记录已固化；
- [x] exploratory A4 的固定分母、偏好对和防泄漏审计已固化；
- [x] 最终报告与 M1-R2 模型卡已建立；
- [x] adapter、预测、评分和 A4 产物已有路径与完整 SHA256；
- [x] 确认集失败、`a4_ready=false`、A5 未启动均持续披露；
- [x] Git 与集群 artifact 的边界明确。

## 本轮不交付

- adapter、数据或完整预测的公开 release：需另行完成许可与安全审计并取得明确批准；
- A5/DPO：负责人决定延后，未来重启需新增授权和版本化配置。

## 未来重启条件

若以后进入 A5，至少应重新决定：使用 75 对 strong-only、107 对弱信号消融还是扩大独立偏好数据；预注册新的未见验证集和 DPO 退化上限；重新核验 Base/adapter/data/environment 哈希；通过新的 ADR 授权 GPU 训练。现有 A3.4 readiness 和 A4 artifact 不得改写。
