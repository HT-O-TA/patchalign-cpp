# ADR-0008：A4 执行阶段排序与偏好对构造

状态：Accepted for owner-authorized exploratory A4
日期：2026-09-06

## 背景

A4 已从冻结 train-only RunBugRun 数据获得 264 个可执行案例，并由 M1-R2 为每例生成 4 个候选，共 1,056 个。GPU 生成只证明候选完整和可重放，不能直接判断补丁正确，也不能把 gold patch 文本相似度当成行为质量。

在执行评分前必须冻结候选比较方式，避免看过成功分布后选择有利的 reward 或偏好配对规则。

## 决策

1. 全部 1,056 个候选使用 A3 scoring v2：只允许补一个终止 LF，严格解析 unified diff，路径只允许 `main.cpp`，应用使用 `git apply --recount`，其余修复或恢复均禁止。
2. 每个候选在 A2 已验证的 rootless Bubblewrap 边界中独立 apply、编译并顺序执行 public、hidden、regression。264 个冻结案例均显式标记 sanitizer 不适用，本轮不运行 sanitizer，也不推断适用性。
3. 评分固定总分母为 1,056；generation、parse、policy、apply、build、public、hidden、regression 的失败和 timeout 均保留。评分按案例保存原子 checkpoint，允许只重跑缺失任务，但不得删除困难候选。
4. 偏好只在同一 case、同一 prompt 的 4 个候选中比较。终止阶段从差到好依次为：generation failed、parse failed、policy violation、apply failed、build failed、public failed、hidden failed、regression failed、sanitizer failed、success。
5. 同一终止阶段仅允许用 timeout 作安全性区分：无 timeout 优于 timeout。除此以外同档候选视为平局，不使用测试通过比例、patch 长度、candidate index 或 gold patch 相似度制造质量差异。
6. 每例最多形成一对：选严格排序键最高的候选为 chosen，最低的为 rejected；并列时只用最小 candidate index 保证确定性。最高与最低键相同则该例不生成偏好对。
7. DPO 训练文件只包含 prompt、原始 chosen/rejected completion、案例身份和内容哈希，不包含 gold patch、fixed code、测试内容或执行细节。终止分类与排序证据写入独立 pair audit。
8. A4 聚合只报告实际偏好对数量、任务层分布、chosen/rejected 终止类别和 success 对数量，不在看到结果前补设产量阈值。A5 不自动获批；项目负责人须在 A4 质量报告后另行决定。

## 解释边界

后置执行阶段通常代表候选通过了更多冻结检查，但不等价于语义距离连续可度量。该策略提供保守、可复现的偏好信号；它不声称所有非 success 候选之间存在细粒度质量顺序，也不把 A4 exploratory 结果改写为 A3.4 晋级成功。
