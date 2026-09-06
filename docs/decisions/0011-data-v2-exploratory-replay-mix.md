# ADR-0011：Data-v2 安全增量重放混合消融

- 状态：Accepted by project owner through delegated continuation authority
- 日期：2026-09-06

## 背景

Data-v2.1 的 GitHub 单查询 metadata pilot 只有 34 个候选仓库，低于 train 至少 100 个新仓库的容量门，不能据此冻结正式 Data-v2。现有 CommitPackFT/RunBugRun 池仍有 260 条 train 和 131 条 validation 安全增量；它们已排除 formal holdout、confirmation 和 Defects4C 身份，但 train 增量全部是 file-window，不能单独作为“函数级为主”的正式重训集。

项目负责人授权后续方案由执行方决定，直至一项合理 GPU 作业排队。该授权不改变 A3.4 readiness 失败、A5 延后或 Data-v2.1 正式容量门。

## 决定

建立一个独立命名的 `data-v2-exploratory-replay-v0.1` 消融，而不是伪称正式 Data-v2：

- train 使用全部 260 条安全增量，并从冻结 formal train 确定性选择 520 条 replay；
- replay 固定为 416 function + 104 file-window，使混合 train 为 780 条、其中 function 416、file-window 364，仍以 function 为多数；
- focused validation 使用全部 131 条安全 validation；冻结 formal validation 500 条只报告 continuation 前后 loss，不参与 checkpoint 选择；
- 保持 train/validation sample、payload 和 `repo_family` 零交叉；保持 v1+increment 每 family 最多 2 条的供给审计结论；
- 不读取 formal holdout、confirmation 或 Defects4C 的 prompt、源码、补丁、测试、预测或得分；只沿用供给审计已经冻结的身份排除结果；
- 从 M1-R2 最佳 adapter 继续训练，NF4 QLoRA、1 epoch、`1e-5` learning rate、batch 1、gradient accumulation 8，共 98 optimizer steps；
- 只在数据构建、Schema、哈希、隔离、token、环境、adapter 身份和全仓测试全部通过后提交单 GPU 作业。

## 解释边界

该实验只回答“在新来源尚未就绪时，安全 file-window/复杂修改增量加函数 replay 是否值得继续研究”。它不满足 Data-v2.1 的 2,000/200、100 个新仓库或 1,000 个新 sampling family 目标，不获得正式模型晋级资格，也不启动 A5/DPO。

GPU 训练完成后仍需在冻结 formal 500、confirmation 124 和 Defects4C 176 上按原评分协议评测；在这些结果完成前，只能称为 queued/running/completed exploratory training，不能声称泛化改善。
