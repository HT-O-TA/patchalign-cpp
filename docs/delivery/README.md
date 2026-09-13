# PatchAlign-Cpp 交付说明

本目录是项目的公开交付入口。默认模型为 **M1-R2**，DPO-beta0.3 作为未通过稳定性门禁的研究模型一并记录。

## 交付结论

| 模型 | 正式集 Pass | 确认集 Pass | Defects4C Pass | 结论 |
|---|---:|---:|---:|---|
| M1-R2 | 14/500 | 0/124 | 1/176 | 默认交付 |
| DPO-beta0.3 | 19/500 | 0/124 | 1/176 | 正式集更高，但超时门禁失败 |

DPO-beta0.3 的正式集 Timeout 为 5/500，M1-R2 为 2/500；增加 0.6 个百分点，超过预设的 0.5 个百分点上限。项目因此优先交付更稳定的 M1-R2，而不是只按单一 Pass 指标选择模型。

## 阅读入口

- [最终实验报告](final_report.md)
- [系统架构](architecture.md)
- [复现说明](reproduction.md)
- [项目讲解与面试提纲](interview_brief.md)
- [M1-R2 模型卡](model_card_m1_r2.md)
- [DPO-beta0.3 模型卡](model_card_dpo_beta03.md)

## 交付边界

Git 仓库包含代码、配置、Schema、测试、报告与校验清单。模型权重、原始数据、处理后数据和大规模推理输出保存在受控存储中，不提交到 Git。

最终清单覆盖 39 个交付 artifact，清单 SHA-256 为：

```text
d7629910dc1bc23f9063cc2ac6e8259745c2ef34099cebe70c919579fbd30f35
```

历史运行回执位于 `docs/evidence/`，关键实验选择位于 `docs/decisions/`。这些内容用于审计，不是理解项目的必读前置材料。
