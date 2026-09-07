# ADR-0020：在 outcome gate 不可达时停止 GitHub detail v1

- 状态：Accepted
- 日期：2026-09-08

## 背景

ADR-0017 将固定 detail 分母设为 200，顺序为 train 160 后 validation 40；门槛要求
train/validation 分别至少 40/10 条合格，且分别覆盖至少 30/8 个仓库。无令牌模式
按 61 秒最小间隔运行，每个候选最多经历 pull、issue、license 三次请求。

一次性定时快照在 2026-09-07T17:30:01Z 观察到 Job 96959 已完成日志中的前 144
个 train 候选，仅 8 条合格。train 固定分母只余 16 条，因此即使余下 train 全部
合格，乐观上限也只有 24，严格小于门槛 40。这个不等式不依赖 validation 结果、
后续许可证分布或统计推断，继续运行不可能改变 v1 outcome。

## 决策

1. 在 2026-09-07T17:31:47Z 终止 Job 96959；Slurm 终态为
   `CANCELLED by 1039`，运行 `04:10:31`，节点 `gpu25`；
2. 保留 selected candidates、全部原子 checkpoint 和日志，不删除、不覆盖、不将
   取消误报为基础设施失败；
3. 不恢复 Job 96959，不降低 40/10、30/8、issue/许可证规则，也不从余下样本中
   换入更容易通过的候选；
4. 通过独立 CPU-only early-stop audit 从 checkpoint 重建连续完成前缀、逐阶段
   拒绝、合格元数据、split 剩余量和乐观上限。只有源哈希、Job 身份与数学不可达
   均通过，才把 ADR-0017 v1 路线记为关闭；
5. ADR-0019 的 50 条内容执行 pilot 不激活，因为其必要前件
   `execution_content_pilot_authorized=true` 不成立；当前不得取得 patch/source、
   构造训练数据或申请 GPU；
6. 本结果只否定“当前 broad repository→linked-PR 抽样 + 显式 closing issue +
   bug label + allowlist license”的固定组合。是否建立新 GitHub 路线，必须先用本次
   拒绝分布证明新证据链不会降低最终 buggy-fail/fixed-pass 质量，并另立 ADR/配置；
   不能把同一作业的未完成后缀当作 v1 补考。

## 解释边界

- 8/144 是已完成日志前缀的观察值，不外推成所有 GitHub C++ 修复的自然通过率；
- `linked_issue_without_bug_label` 可能包含真实缺陷，也可能是非缺陷任务；在没有
  新证据契约前，两者都不能自动准入；
- 可执行测试证据在最终训练资格上强于标签，但用它替代 metadata label 属于新方案，
  需要固定分母、污染/许可证门和独立重放，不是对 v1 结果的追认；
- 终态数字以 early-stop audit artifact 为准，本 ADR 的定时快照不替代机器输出。
