# 实验与运行证据

本目录保存关键阶段的运行回执、失败诊断和门禁分析。它们用于证明结论如何产生，而不是项目主页或操作教程。

## 使用边界

- 证据文档按形成时间描述当时状态；早期的“下一步”“延后”或失败判断可能已被后续决策覆盖。
- 当前终态以 [最终冻结状态](../status.md) 和 [最终实验报告](../delivery/final_report.md) 为准。
- 失败 Job、内部集群路径和中间哈希被保留，是为了避免只展示成功结果。
- 聚合指标可以公开；原始数据、完整预测、训练权重和可能受第三方许可约束的内容不在 Git 中发布。

## 推荐证据入口

- [A0 验收](a0-validation.md)
- [SFT 工程发现](a3_3_pipeline_findings.md)
- [M1-R2 泛化失败诊断](generalization_failure_diagnostic.md)
- [DPO 偏好数据审计](a5_resume_dpo_preference_audit_v1.md)
- [DPO 训练结果](a5_dpo_training_v1_1.md)
- [DPO 开发集选择](a5_dpo_dev_selection_v1.md)
- [DPO 正式集失败分析](a5_dpo_formal_failure_analysis.md)
- [DPO 最终恢复与外部评测](a5_dpo_final_recovery.md)

Data-v2 相关证据用于说明为何停止扩大数据来源及哪些候选来源未达到准入条件，不表示这些来源已经进入训练集。
