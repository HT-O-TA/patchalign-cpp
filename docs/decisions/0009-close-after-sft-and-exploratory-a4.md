# ADR-0009：以 SFT 与探索性研究作为本轮交付终点

状态：Accepted by project owner
日期：2026-09-06

## 背景

PatchAlign-Cpp 已完成 G0、A0～A3 的工程与实验闭环，并在 A3.4 后完整记录正式晋级失败：旧 500 条内部门禁通过，Defects4C 外部门禁通过，但独立 124 条确认集失败，因此 pre-A4 ledger 保持 `a4_ready=false`。负责人随后依据 ADR-0006 授权 exploratory A4；该阶段已完成 264 条可执行 train-only 数据、1,056 个候选的真实执行评分和 182 对保守偏好数据构造，run manifest 保持 `a5_started=false`。

A4 产出的 182 对中只有 75 对 chosen 为完整 success，其余 107 对是后置执行阶段或 timeout 信号；同时数据来自经过资格筛选的训练分布，不能替代独立泛化证据。项目负责人现决定暂不进入 A5/DPO，按“完成 SFT 与探索性研究”收尾。

## 决策

1. 本轮项目交付范围冻结为 G0、A0～A3.4 和负责人授权的 exploratory A4；A5/DPO 不属于本轮已完成范围。
2. M1-R2 是本轮最终模型候选，但不是通过全部 promotion gate 的发布模型。模型卡必须持续披露确认集 0/124、Defects4C 1/176 无提升、`a4_ready=false` 和已知 timeout/regression 风险。
3. A4 的 182 对偏好数据作为内部研究产物交付，不启动 DPO，不以“DPO-ready”“已完成偏好优化”或“正式晋级 A4”描述。
4. 代码、配置、Schema、测试、阶段报告和小型证据摘要通过 Git 交付；adapter、checkpoint、数据、完整预测、逐例评分、日志和大体积 artifact 继续留在集群并以路径、manifest 和 SHA256 索引。
5. 本轮不公开发布 adapter、派生数据或完整预测。任何对外分发仍须完成来源许可、敏感信息、漏洞披露和 NOTICE 审计，并获得负责人对该次发布的明确批准。
6. 项目状态由“等待 A5 决策”改为“本轮已收尾，A5 延后”。历史 ADR-0001/0004 中的 Base→SFT→DPO 研究规划保留为当时设计，不改写为已完成事实。
7. 若未来重启 A5，必须新增决策记录和版本化训练/评测配置；不得改写现有 readiness、A4 manifest 或本轮最终报告。

## 交付口径

允许表述：

> PatchAlign-Cpp 完成了可验证 C++ 补丁 SFT、独立确认与外部评测，以及一次负责人授权的探索性偏好数据研究；SFT 显著改善 diff 协议遵循和执行前置阶段，但未证明未见分布上的端到端泛化。本轮在 DPO 前收尾。

禁止表述：

- SFT 已通过全部正式 promotion gate；
- M1-R2 在独立确认集或 Defects4C 上提高了最终 Pass；
- exploratory A4 等同于正式晋级；
- 182 对偏好数据已经用于 DPO；
- 本轮已完成 Base→SFT→DPO 全链路。
