# 文档索引与维护规则

本文定义 PatchAlign-Cpp 文档的职责和优先级。项目当前进度只在[项目状态](status.md)维护；其他文档不再复制正在运行、排队或预计完成的信息。

## 单一事实源

| 信息类型 | 权威来源 | 说明 |
|---|---|---|
| 当前阶段与作业状态 | [`status.md`](status.md) | 带核验时间的状态快照；每次里程碑或正式作业状态变化时更新 |
| 本轮最终报告与交付 | [`delivery/`](delivery/) | 收尾口径、模型卡、artifact 清单和接收验证入口 |
| 项目全程与稳定结论 | [项目全程总结与核心结论](项目全程总结与核心结论.md) | 从立项到当前里程碑的稳定叙事；不维护分钟级作业状态 |
| 正式数据配额与路径 | [`configs/data/a3_formal_v1.json`](../configs/data/a3_formal_v1.json) | 机器读取的冻结配置；文档只解释，不另立一套数字 |
| 正式训练与生成参数 | [`configs/training/a3_sft_formal_v1.json`](../configs/training/a3_sft_formal_v1.json) | 模型、数据、训练和评测输入模式的机器契约 |
| 评分与质量门槛 | [`configs/evaluation/`](../configs/evaluation/) | 评分协议和 promotion gate 的机器配置 |
| Schema 字段与约束 | [`schemas/`](../schemas/) | JSON 实例合法性的最终依据 |
| 决策与变更理由 | [`decisions/`](decisions/) | ADR 记录当时为何作出选择；已接受的 ADR 不静默改写 |
| 单次运行身份与结果 | 集群 artifact 中的 manifest、lock、summary | Job、commit、输入哈希、输出哈希和最终指标的权威证据 |
| 阶段协议与结论 | A0、A1、A2、A3.x 阶段文档 | 描述范围、方法和已关闭阶段的终态，不承担实时状态 |
| 历史问题与论文证据 | [`evidence/`](evidence/) | 只记录可复核现象、原因、修正和解释边界 |
| 历史操作过程 | [`records/`](records/) | 按时间保留，不作为当前配置或当前状态依据 |

发生冲突时，先核对运行绑定的 artifact manifest；通用契约依次以版本化配置、Schema 和 ADR 为准。说明性阶段文档与历史记录不得覆盖机器契约。

## 阅读入口

- 最终交付：[交付说明](delivery/README.md)
- 最终报告：[PatchAlign-Cpp 最终技术报告](delivery/final_report.md)
- 最终模型候选：[M1-R2 模型卡](delivery/model_card_m1_r2.md)
- 全程总览：[项目全程总结与核心结论](项目全程总结与核心结论.md)
- 当前进度：[项目状态](status.md)
- A0 契约：[A0 索引](a0/README.md)
- A1 数据 pilot：[数据来源与隔离](a1_data_sources.md)
- A2 执行闭环：[安全执行与真实重放](a2_sandbox.md)
- A3.0：[冻结基线](a3_baseline.md)
- A3.1：[scoring v2](a3_1_scoring.md)
- A3.2：[LoRA/QLoRA pilot](a3_2_sft_pilot.md)
- A3.3：[正式 SFT](a3_3_formal_sft.md)
- A3.4：[SFT-R2 安全修正轮次](a3_4_sft_r2.md)
- A4：[可执行偏好数据与保守配对协议](a4_preference_data.md)
- 收尾决策：[ADR-0009：以 SFT 与探索性研究作为本轮交付终点](decisions/0009-close-after-sft-and-exploratory-a4.md)
- 正式实验问题：[A3.3 论文材料](evidence/a3_3_pipeline_findings.md)
- 泛化失败诊断：[M1-R2 六项诊断](evidence/generalization_failure_diagnostic.md)
- 下一研究轮次：[Data-v2 泛化增强计划](data_v2_plan.md)
- 新来源准入：[Data-v2 新来源准入与污染审计](evidence/data_v2_source_admission.md)
- GitHub 试采结果：[Data-v2 GitHub C++ 元数据 pilot](evidence/data_v2_github_metadata_pilot.md)
- Data-v2.1 family 契约：[ADR-0010：仓库隔离与采样 family 分层](decisions/0010-data-v2-hierarchical-family-contract.md)
- Data-v2 exploratory 消融：[ADR-0011：安全增量重放混合](decisions/0011-data-v2-exploratory-replay-mix.md)
- Data-v2 到 DPO 新轮次：[ADR-0012：分阶段治理与停止门](decisions/0012-data-v2-to-dpo-staged-governance.md)
- GitHub discovery 语义修正：[ADR-0013：Repository→PR 两级发现](decisions/0013-correct-github-discovery-endpoint-semantics.md)
- Data-v2 评测隔离：[ADR-0014：完整 denylist 边界](decisions/0014-evaluation-denylist-completeness-boundary.md)
- RunBugRun v2 训练边界：[ADR-0015：来源许可与 provenance 门](decisions/0015-runbugrun-v2-provenance-training-boundary.md)
- GitHub identity 修正：[ADR-0016：仓库 URL 大小写规范化](decisions/0016-github-repository-identity-casefold.md)
- GitHub 固定详情门：[ADR-0017：固定 detail 与后续可执行内容 pilot](decisions/0017-fixed-github-detail-and-execution-pilot.md)
- CommitPack 有界候选：[ADR-0018：C++ 单分片供给审计提案](decisions/0018-commitpack-cpp-bounded-supply-audit.md)
- GitHub 内容执行提案：[ADR-0019：固定 50 条的安全 commit/test 重建](decisions/0019-github-executable-content-pilot.md)
- GitHub detail v1 早停：[ADR-0020：不可达 outcome gate 的可审计终止](decisions/0020-stop-github-detail-v1-on-unreachable-gate.md)
- GitHub detail v1 早停证据：[144 条连续前缀与拒绝分布](evidence/data_v2_github_detail_early_stop.md)
- GitHub evidence v2：[ADR-0021：用真实执行证据替代标签资格](decisions/0021-use-executable-evidence-before-bug-label.md)
- 项目复盘：[面试复述与工程经历](interview_retrospective.md)
- Git 同步：[本机—集群同步规范](development/git-sync.md)
- 目录职责：[目录结构台账](records/第二项目_PatchAlign-Cpp_目录结构.md)
- 历史过程：[执行记录](records/第二项目_PatchAlign-Cpp_执行记录.md)

## 防漂移规则

1. `RUNNING`、`PENDING`、完成百分比和预计剩余时间只写入 `status.md`，并标注核验时间。
2. 配额、超参数、阈值、模型 revision 和路径先修改版本化配置；需要改变已接受决策时新增或修订 ADR，再更新说明文档。
3. 阶段关闭后只追加最终结果或勘误，不把后续阶段状态回填为该阶段当时的结论。
4. 失败作业和被替代方案保留在历史记录或 evidence，不与当前有效链并列称为“当前”。
5. 运行结果引用 Job ID、完整 Git commit、artifact 路径和 SHA256；不得以 `latest` 代替论文证据。
6. 目录台账只记录稳定目录与职责，不逐项复制容易变化的 checkpoint、日志或缓存文件。
7. 每次大更新至少检查 Markdown 相对链接、`git diff --check`、配置/文档关键数字以及本机和集群 commit。

## 更新节奏

- 正式作业状态变化：更新 `status.md`。
- 契约变化：更新机器配置/Schema、ADR、测试和对应阶段文档。
- 目录职责变化：更新目录结构台账并留下简短变更备注。
- 运行得到终态：先固化 artifact，再把摘要写入阶段文档/evidence，最后从状态页移入“已完成”。
