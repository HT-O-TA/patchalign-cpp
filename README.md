# PatchAlign-Cpp

PatchAlign-Cpp 是一个面向 C/C++ 程序修复的模型微调与真实执行评测项目。项目以 Qwen2.5-Coder-7B 为基座，完成了数据治理、LoRA/QLoRA SFT、执行沙箱、偏好数据构造、DPO 训练、消融实验和冻结交付。

> 当前状态：实验与交付已冻结。默认交付模型为 **M1-R2（NF4 QLoRA SFT）**；DPO-beta0.3 作为研究模型保留，不替代默认模型。

## 项目目标

输入包含缺陷的 C/C++ 代码与任务信息，模型生成补丁；补丁随后经过结构校验、应用、编译、公开测试、隐藏测试、回归测试和资源限制检查。项目关注的不只是“生成看起来合理的代码”，而是补丁能否在隔离环境中真实执行并通过测试。

核心流程：

```text
CommitPackFT + RunBugRun
        ↓ 清洗、去重、分组切分
SFT（BF16 LoRA / NF4 QLoRA）
        ↓
沙箱执行评测（apply → compile → test）
        ↓
真实执行轨迹构造偏好对
        ↓
DPO 与消融实验
        ↓
冻结模型、报告和复现材料
```

## 最终结果

正式测试集共 500 条，确认集 124 条，外部 Defects4C 集 176 条。`Pass` 表示补丁成功应用、编译并通过规定测试。

| 模型 | 正式集 Pass | Apply | Compile | Timeout | 交付结论 |
|---|---:|---:|---:|---:|---|
| M0 Base | 0/500 | 0 | 0 | 0 | 原始基线 |
| M1 SFT | 15/500 | 391 | 373 | 3 | 首个有效模型 |
| **M1-R2 SFT** | **14/500** | **412** | **392** | **2** | **默认模型** |
| DPO-beta0.3 | 19/500 | 437 | 424 | 5 | Pass 更高，但超时门禁失败 |

确认集上 M1-R2 与 DPO-beta0.3 均为 0/124；Defects4C 上均为 1/176。结果说明训练显著改善了补丁格式、应用率和编译率，但跨分布语义修复能力仍然有限。DPO-beta0.3 将正式集 Pass 从 14 提高到 19，同时 Timeout 从 2 增加到 5，超过预设门禁，因此没有替代更稳定的 M1-R2。

## 工程与实验要点

- 数据治理：按来源、仓库家族和上游划分隔离数据，执行去重、许可证和长度过滤，降低直接泄漏风险。
- 参数高效训练：比较 BF16 LoRA 与 NF4 QLoRA 的效果、显存和稳定性；两者 pilot Pass 持平，最终按预注册资源规则选择 NF4 QLoRA。
- 真实执行评分：评分链覆盖补丁解析、应用、编译、测试、回归与超时，不以文本相似度代替正确性。
- 偏好对齐：使用执行结果构造 chosen/rejected 对，比较不同 DPO beta，并设置 Pass、回归和超时门禁。
- 可复现交付：冻结配置、Schema、测试、模型卡、评测报告和带校验和的交付清单。

## 快速验证

以下命令面向 Linux 环境；完整评分链依赖 `resource`、Bubblewrap 和 GNU/Linux 隔离语义，Windows 本机只适合文档与非沙箱组件检查。

```bash
python -m pip install -e ".[dev]"
pytest -q
python -m patchalign.cli prompt --help
python -m patchalign.cli evaluate --help
```

模型权重与大规模数据不提交到 Git；集群路径、环境和完整复现步骤见复现文档。

## 公开文档

- [最终实验报告](docs/delivery/final_report.md)
- [系统架构](docs/delivery/architecture.md)
- [复现说明](docs/delivery/reproduction.md)
- [项目讲解与面试提纲](docs/delivery/interview_brief.md)
- [M1-R2 模型卡](docs/delivery/model_card_m1_r2.md)
- [DPO-beta0.3 模型卡](docs/delivery/model_card_dpo_beta03.md)
- [任务与评分协议](docs/a0/core_protocol.md)
- [数据和实验治理](docs/a0/governance.md)
- [最终冻结状态](docs/status.md)

完整文档导航见 [docs/README.md](docs/README.md)。

## 已知限制

- 正式集上的绝对 Pass 率仍低，项目尚未证明具备通用 C/C++ 自动修复能力。
- 确认集与 Defects4C 的结果显示明显的跨分布泛化瓶颈。
- RunBugRun 与 CommitPackFT 的任务形态、上下文和测试可执行性并不完全一致。
- 当前结论只适用于已冻结的数据、模板、沙箱、推理参数和评分协议。

## License

代码采用 [Apache License 2.0](LICENSE)。上游数据和模型分别遵循其原始许可证与使用条款。
