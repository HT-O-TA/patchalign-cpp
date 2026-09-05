# ADR-0006：A4 负责人授权的探索性续行

状态：Accepted by project owner, execution contingent on completed pre-A4 ledger
日期：2026-09-05

## 背景

A3.4 在旧 500 条冻结 holdout 上通过内部门禁，但在新的 124 条确认集上失败：M0 与 M1-R2 均为 0/124 Pass，且 M1-R2 引入 3 条 regression failure 和 4 条 timeout。确认集是预注册的合取门禁，因此最终 pre-A4 readiness 必须如实记录 `supplementary_confirmation_passed=false`、`a4_ready=false`，不能把后续外部结果用于覆盖这一失败。

项目负责人随后明确要求：完成全部 pre-A4 外部评测和 readiness 后，仍进入 A4 并留下 GPU 作业排队。该要求是对后续探索实验的显式授权，不是对冻结 promotion gate 的修改。

## 决策

1. 必须先完整完成 Defects4C 资格、M0/M1-R2 成对推理、离线执行评分、外部门禁聚合和 pre-A4 readiness；不得跳过失败样本或缩小分母来提前进入 A4。
2. readiness 保持机器事实：若确认集仍失败，输出必须为 `a4_ready=false`、包含 `supplementary_confirmation_passed` blocker，并保持 `a4_started=false`。
3. readiness 落盘并核验后，允许以 `owner_authorized_exploratory` 模式启动 A4。该模式不得写成“晋级成功”“门禁通过”或“模型已泛化”。
4. A4 起始策略使用 M1-R2 adapter，因为它是当前风险修正后的最新训练产物；其确认集失败必须在 A4 manifest、报告和后续模型卡中持续披露。
5. A4 候选 prompt 只能来自 A3.3 冻结 `train`，并优先使用其中可执行的 RunBugRun 样本。不得读取或派生自 validation、正式 internal holdout、新 confirmation、Defects4C external 的预测、gold patch、fixed source、hidden test 内容或执行反馈。
6. 候选生成 prompt 不包含 gold patch、fixed code、hidden test、chosen/rejected 标签或执行结果。执行反馈只能由后端在生成后用于构造偏好关系。
7. A4 使用独立的配置、输出目录、manifest、哈希和 Slurm 日志；不得覆盖 A3 artifact，不得修改 A0～A3 的历史门禁。
8. A4 GPU 作业只能在 pre-A4 ledger 存在且其三个输入 artifact 哈希均已验证后提交。preflight 必须显式接受“readiness 失败但 owner override 身份匹配”的组合，其他绕过方式 fail closed。
9. 本 ADR 只授权 A4 数据准备和候选生成；A5 DPO 训练仍需 A4 可执行偏好数据完成、质量报告通过并另行进入。

## 报告口径

允许表述：

> A3.4 独立确认门禁失败，项目未获得正式晋级资格；在完整闭环外部负结果和 readiness 后，由项目负责人明确授权继续生成探索性 A4 偏好数据，用于研究失败模式，不改变原门禁结论。

禁止表述：

- A3.4 promotion gate 已通过；
- M1-R2 已在未见分布上泛化；
- owner override 等同于质量门禁通过；
- A4 或后续 DPO 结果可以反向修正 A3 readiness。
