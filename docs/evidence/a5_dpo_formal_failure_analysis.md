# A5 DPO formal/confirmation 配对失败分析

本文只消费冻结的 M1-R2 与 DPO beta=0.3 predictions/scoring artifact，不重新生成、不重评分，也不
读取 gold/fixed source。Defects4C 结果由最终聚合补充；本页聚焦已完成的 formal 500 与 confirmation 124。

## 1. Formal 500 漏斗

| 指标 | M1-R2 | DPO beta=0.3 | 变化 |
|---|---:|---:|---:|
| Parse | 499 | 500 | +1 |
| Apply | 412 | 437 | +25 |
| Compile | 392 | 424 | +32 |
| Public success | 22 | 28 | +6 |
| Pass | 14 | 19 | +5 |
| Function Pass | 11/400 | 17/400 | +1.5pp |
| File-window Pass | 3/100 | 2/100 | -1.0pp |
| Regression failure | 3 | 5 | +0.4pp |
| Timeout | 2 | 5 | +0.6pp |

Function Pass 的冻结 paired bootstrap 结果为 observed `+1.5pp`、95% CI `[0,+3.0pp]`。主提升达到
`+1pp` 门槛且区间下界不低于 0；parse/apply/compile、regression 和 file-window 也在各自退化上限
内。但是 timeout 相对 M1-R2 增加 `+0.6pp`，超过冻结 `+0.5pp` 上限，因此 formal 门禁已经包含
`formal_timeout_increase_exceeded`；外部评测只能增加其他失败理由，不能消除这一理由。

## 2. 成功样本迁移

- 11 个案例在 M1-R2 与 DPO 下都成功；
- 8 个案例由失败转为成功，其中 3 个来自 apply failure、5 个来自 public-test failure；
- 3 个原成功案例被破坏，其中 1 个变为 apply failure、2 个变为 public-test failure；
- 500 个 completion 中 363 个发生变化，说明 DPO 不是只对少量边界样本做微调；
- 8 个新增成功和 3 个丢失成功的补丁均为单 hunk、单行替换。净提升来自更好的局部选择，但没有证明
  更复杂补丁或新确认分布上的能力。

## 3. Timeout 迁移与逐例原因

Formal 中 1 个 timeout 被保留、1 个被修复、4 个由 DPO 新增，净变化为 `+3`。四个新增案例均能
apply/compile，超时发生在 public tests，因此必须算进固定分母：

| Case | Task level | DPO 修改 | 风险机制 |
|---|---|---|---|
| `rbr-formal-0e0362e32b7329520edc` | function | 将 `que.pop();` 注释掉 | 队首永不移除，`while (!que.empty())` 无法结束 |
| `rbr-formal-4ce83abb0c4271e87415` | function | 把 `for` 的 `j++` 改为只求值的比较表达式 | 循环变量不增长，条件成立时无限迭代/递归 |
| `rbr-formal-3ed77c7c0d78c5e83628` | file-window | 将相邻相等扩展条件由 `==` 改为 `!=` | 链式边界推进方向错误，可能在环/哨兵上无法收敛 |
| `rbr-formal-58fc987ec812a5fa14e0` | file-window | 将初始化调用 `Get();` 改为 `solve();` | 在 `solve` 内再次进入自身，形成无终止递归 |

这些不是节点抖动或评分器错误：同一评分链中其他 495 条均完成，四个补丁的控制流改动也能直接解释
稳定超时。DPO 偏好数据排除了 timeout-only pair，但仍未消除生成时的非终止风险，说明“去除弱 timeout
偏好信号”不等于“模型学会控制流安全”。

## 4. Regression failure 迁移

DPO 的 5 个 regression failure 中，2 个由 M1-R2 保留，另外 3 个分别从 2 个 apply failure 和
1 个 public-test failure 转入。也就是说，更高的 apply/compile/public 漏斗通过率把部分原本较早终止
的补丁推进到了更严格的行为检查，但其中仍有错误。这再次说明前置阶段成功不能替代最终正确性。

## 5. Confirmation 124

| 指标 | M1-R2 | DPO beta=0.3 | 变化 |
|---|---:|---:|---:|
| Parse / Apply / Compile | 123/104/103 | 124/110/109 | +1/+6/+6 |
| Public success | 6 | 5 | -1 |
| Pass | 0 | 0 | 0 |
| Regression failure | 3 | 3 | 0 |
| Timeout | 4 | 2 | -2 |

DPO 改变了 86/124 个 completion，并改善格式、应用、编译和 timeout，但没有产生任何端到端成功。
两个 baseline timeout 被修复，另外两个 timeout 在候选中保留，没有新增 timeout。该结果与 formal 的
净提升形成清晰边界：DPO 学到的局部可执行偏好在旧 formal 分布上有效，但没有转化为独立确认分布的
修复语义泛化。

## 6. 工程结论

1. DPO 的正结果真实存在：formal Pass 从 14 增至 19，不能因为最终门禁失败而抹去。
2. DPO 的退化也真实存在：净增 3 个 formal timeout 足以触发预注册 veto，不能用总 Pass 提升覆盖。
3. 偏好优化提高了补丁进入更后执行阶段的概率，同时也把部分错误从 apply/public failure 推进到
   regression；多阶段漏斗必须保留。
4. 对当前简历交付目标，继续调 beta 或追加训练会引入结果驱动搜索。更合理的产品选择是遵守门禁，
   回退 M1-R2 作为推荐模型，并把 beta=0.3 作为有正收益但安全 veto 的实验候选。
