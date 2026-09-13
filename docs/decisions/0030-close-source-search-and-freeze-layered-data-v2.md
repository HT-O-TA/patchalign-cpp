# ADR-0030：结束来源搜索并冻结 family-disjoint 分层 Data-v2 路线

- 状态：Superseded as current delivery plan by ADR-0031（停止来源搜索的决定保留）
- 日期：2026-09-08

## 背景

2,000/200 全量新可执行增量是容量探针，不是已取得数据。GitHub fixed evidence 为
`0/20`，CommitPack 固定分片为 `236/17` 且不能重建测试，BeetleBox repository resplit
后为 `160/0`，BugsCpp 的预注册 validation 许可证上界为 `5 defects/1 project`。这些
路线均按事前门禁关闭；继续换查询、分片、seed 或 split 只会造成选择偏差。

另一方面，既有冻结正式池为 train 5,000、validation 500；独立供给审计已证明在不与
formal/confirmation/Defects4C 交叉、保持 family 总上限 2 和精确 tokenizer 限制后，
还能得到 train 260、validation 131 个安全监督增量。A4 另有 264 个 train-only、
family 唯一、双重 buggy-fail/fixed-pass 资格案例，但它们已经产生探索性偏好数据，不能
再兼任新的 SFT 模型选择集。

## 决策

1. 结束本轮所有宽泛新来源搜索。BugsCpp、BeetleBox、CommitPack 新分片、GitHub 同类
   查询、RunBugRun v2 和 TrickyBugs 不再补考；CppPerf 只保留为未来性能域消融。
2. 以“开发者修复监督层 + 独立本地执行开发层”替代失败的 2,000/200 全量执行合同。
   这是显式版本升级，不回写旧容量探针的失败结论。
3. 监督候选池固定为旧 formal train 5,000 加安全 train increment 260，以及旧 formal
   validation 500 加安全 validation increment 131。静态监督层不得描述为全量可执行。
4. 从 A4 candidate manifest 尚未用于 A4 偏好集的 146 个 train-only family 中，继续
   完成既有双重执行资格，按原 candidate order 固定选择 64 个 function 案例作为
   `data-v2-dev-exec-v1`。不根据模型输出或未来得分选样本。
5. 这 64 个案例的整个 `repo_family` 必须从监督 train、increment 和 validation 全部
   排除；开发执行集之间 family 唯一，且与 formal holdout、confirmation、Defects4C
   和 A4 264 个偏好 case 零交叉。它只用于三 seed SFT/DPO 模型选择，不进入训练。
6. 精确 train 数量与分布由一次 CPU 构建在执行全部 family 排除后冻结；门槛为 train
   至少 5,100、validation 恰为 631、function 至少占 train 75%、每 family 最多 2、
   Schema v0.2 全通过、4,096 tokens 内、sample/payload/family 跨 split 零交叉。
7. SFT 从固定 Base revision 重新训练三个 seed，不从 exploratory adapter continuation。
   三 seed 只在 64 条开发执行集上比较；至少 2/3 的 Pass 高于 M1-R2 在同集合的基线，
   且 timeout/regression 不恶化，才选唯一 SFT 候选并进入 ADR-0012 的三段正式评测。
8. A4 的 264 个 case 与 182 对旧偏好不参与 SFT 模型选择。它们可在 SFT 三段门全部
   通过后作为正式偏好数据的候选来源重新审计；DPO 的 300/150 门和全部停止线不变。
9. 本 ADR 只授权 Data-v2 CPU 构建、开发执行资格扩展及随后通过 preflight 的三 seed
   SFT；不能把重新组织的旧来源称为新增 benchmark 多样性，也不能声称已证明泛化。

## 停止线

- 若剩余候选不能得到 64 个新双资格 function family，则使用全部真实合格数并要求至少
  50；低于 50 时停止正式 SFT，不从 A4 已选 264 个 case 回填；
- 若 family 排除后 train 少于 5,100 或 function 比例低于 75%，停止并保留构建证据；
- 同一监督配方只运行冻结的三个 seed；不因单 seed formal 结果重新调参补跑；
- 任一 staged 正式评测门失败，保留负结果并停止向 DPO 晋级。

## 解释边界

该路线解决的是实验设计问题：把真实执行反馈用于独立开发选择，并让 SFT 从 Base 重新
吸收完整监督池。它没有凭空增加新仓库，也不能保证超过 confirmation。其价值在于用
有限但真实可得的数据回答“分层证据与 family 隔离是否比短 continuation 更稳健”，并
给出可以诚实结束或进入 DPO 的硬门。
