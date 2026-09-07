# ADR-0021：GitHub v2 先用可执行证据判定缺陷

- 状态：Accepted
- 日期：2026-09-08

## 背景

GitHub detail v1 的固定分母由 Job `97150` 独立重建：144 个连续完成的 train
候选只有 8 条合格，train 乐观上限 24/40，路线已关闭。136 个拒绝中有 58 条来自
58 个不同仓库，唯一失败条件是关联的关闭 issue 没有 `bug/defect` 标签。标签是项目
维护习惯，不是补丁语义；但仅删除标签门也不能证明一个提交修复了真实缺陷。

## 决策

建立独立的 `github-executable-evidence-v2`，不恢复、覆盖或重新解释 v1：

1. 固定复用 ADR-0017 的 200 条选择、顺序和 train 160/validation 40 分母；不得以
   后续成功率换样本；
2. metadata 候选仍须是已合并、小范围变更、显式关闭同仓库 issue，且 issue 已关闭
   并非 pull request；`bug/defect` 标签只记录为分层字段，不再是最终资格门；
3. 允许逐字节核验后复用 v1 的 pull/issue checkpoint。对
   `linked_issue_without_bug_label`，只从其绑定脚本的确定性拒绝原因推导
   `bug_label_matched=false`，不伪造原 projection；缺少的 pull/issue 请求写入 v2
   独立 checkpoint，仍不保存 title、body、label 原文、用户或 raw response；
4. metadata 阶段不再查询默认分支 LICENSE。默认分支不能证明历史 parent/fixed 的
   授权；许可证必须在内容阶段分别按固定 commit 核验路径、SPDX、内容哈希与一致性；
5. metadata outcome gate 保持至少 50 条，train/validation 至少 40/10，并覆盖至少
   30/8 个仓库。未通过就关闭本路线，不取得 patch/source；
6. outcome 通过后，先固定 20 条执行可行性分母（train 16、validation 4，仓库轮询，
   bug-label 分层交错）。全部候选取得 commit/files/license 与源码后均计入分母；
   只启用已冻结的 CMake/CTest profile，在 Bubblewrap 断网环境完成 fixed 与
   buggy+test-delta 双资格及独立稳定重放；
7. 至少 4/20 完整通过，才扩大为不重叠的正式 50 条执行 pilot；低于 4 时关闭
   GitHub executable 路线。20 条只验证执行可行性，不进入训练，也不取代正式
   50 条的 10/50 门；
8. 最终缺陷资格仍要求固定 parent/fixed 图一致、历史许可证 allowlist、生产 C++ 与
   测试变更可安全分离、fixed 全测试通过、buggy 至少 2 个 fail-to-pass、至少 3 个
   pass-to-pass、第二工作树结果一致。标签存在与否不能替代这些门。

## 资源与停止线

- v2 metadata 只使用 CPU 和 GitHub REST metadata；无 GPU；
- 20 条可行性 pilot 的网络阶段只 fetch 固定对象，执行阶段严格断网；每例独立
  checkpoint，可用 Slurm array，但不得因失败换样本；
- 只有 metadata gate、20 条可行性 gate、正式 50 条 10/50 gate 和后续容量审计
  依次通过，才允许构造 Data-v2；
- ADR-0019 继续作为旧 v1 的未激活提案保留，其前件失败，不能直接复用其
  `execution_content_pilot_authorized` 状态；本 ADR 的执行配置必须另行绑定。

## 解释边界

本决策没有降低真实执行、许可证、污染、仓库隔离或测试稳定性门槛。它只把一个
噪声较高的仓库管理标签从最终资格条件改成报告维度，并用更强的行为证据取代它。
即使 20 条 pilot 通过，也不能外推 7,721 条候选的通过率，更不能宣称 Data-v2 已就绪。
