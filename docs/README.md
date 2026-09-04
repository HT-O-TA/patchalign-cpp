# 文档索引与维护规则

本文定义 PatchAlign-Cpp 文档的职责和优先级。项目当前进度只在[项目状态](status.md)维护；其他文档不再复制正在运行、排队或预计完成的信息。

## 单一事实源

| 信息类型 | 权威来源 | 说明 |
|---|---|---|
| 当前阶段与作业状态 | [`status.md`](status.md) | 带核验时间的状态快照；每次里程碑或正式作业状态变化时更新 |
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

- 当前进度：[项目状态](status.md)
- A0 契约：[A0 索引](a0/README.md)
- A1 数据 pilot：[数据来源与隔离](a1_data_sources.md)
- A2 执行闭环：[安全执行与真实重放](a2_sandbox.md)
- A3.0：[冻结基线](a3_baseline.md)
- A3.1：[scoring v2](a3_1_scoring.md)
- A3.2：[LoRA/QLoRA pilot](a3_2_sft_pilot.md)
- A3.3：[正式 SFT](a3_3_formal_sft.md)
- A3.4：[SFT-R2 安全修正轮次](a3_4_sft_r2.md)
- 正式实验问题：[A3.3 论文材料](evidence/a3_3_pipeline_findings.md)
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
