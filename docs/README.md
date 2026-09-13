# PatchAlign-Cpp 文档

本目录同时包含面向读者的项目说明和用于复现实验的审计材料。公开阅读建议从“核心文档”开始；ADR、证据回执与阶段记录主要用于追踪结论来源，不需要按顺序阅读。

## 核心文档

- [项目主页](../README.md)：目标、流程、最终结果与项目亮点。
- [项目全程总结与核心结论](项目全程总结与核心结论.md)：从数据、训练、对齐到评测的完整解释。
- [最终实验报告](delivery/final_report.md)：冻结指标、模型选择和实验结论。
- [系统架构](delivery/architecture.md)：数据、训练、推理和评分组件之间的关系。
- [复现说明](delivery/reproduction.md)：环境、测试和集群复现入口。
- [项目讲解与面试提纲](delivery/interview_brief.md)：适合简历与面试表达的项目摘要。
- [最终冻结状态](status.md)：各阶段完成情况和交付边界。

## 模型说明

- [M1-R2 模型卡](delivery/model_card_m1_r2.md)：默认交付模型。
- [DPO-beta0.3 模型卡](delivery/model_card_dpo_beta03.md)：Pass 更高但未通过超时门禁的研究模型。

## 协议与治理

- [任务与评分协议](a0/core_protocol.md)
- [数据和实验治理](a0/governance.md)
- [数据来源与许可](a1_data_sources.md)
- [执行沙箱](a2_sandbox.md)
- [SFT pilot](a3_2_sft_pilot.md)
- [正式 SFT](a3_3_formal_sft.md)
- [偏好数据构造](a4_preference_data.md)

## 审计附录

- `decisions/`：架构决策记录（ADR），用于说明关键实验选择及其变更历史。
- `evidence/`：运行回执、门禁结果和冻结证据。
- `configs/`、`schemas/`、`tests/`：机器可验证的配置、数据契约和测试实现，位于仓库对应目录。

历史过程材料已从公开入口中移除。若需要追溯某次决策或运行，优先使用 ADR、证据回执与 Git 历史，而不是把临时操作日志当作最终结论。
