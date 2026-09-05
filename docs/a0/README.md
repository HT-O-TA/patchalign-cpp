# A0：问题、边界与实验协议

状态：**A0 技术验收完成**。后续阶段现状见 [项目状态](../status.md)。
当前 canonical sample Schema 版本：`0.2.0`
任务协议版本：`0.1.0`

A0 的目标是在下载正式数据和运行基线之前，冻结项目要解决的问题、模型可见输入、输出格式、评分顺序、复现证据和真实性边界。

## A0 文档清单

| 文档 | 作用 | A0 验收状态 |
|---|---|---|
| [核心任务与评测协议](core_protocol.md) | 定义输入、输出、修改范围、执行顺序、指标和沙箱 | Accepted for A0 |
| [样本与运行 Schema](sample_schema.md) | 定义规范样本、预测、执行结果和 run manifest | Accepted for A0 |
| [实验与复现协议](experiment_protocol.md) | 定义模型角色、seed、配置、artifact 和可比性 | Accepted for A0 |
| [真实性、许可与发布治理](governance.md) | 定义证据、污染、归因、许可和发布门禁 | Accepted for A0；污染未知边界保留 |
| [ADR-0001](../decisions/0001-model-and-resource-strategy.md) | 模型、LoRA/QLoRA 和资源策略 | Accepted for A0 |
| [ADR-0002](../decisions/0002-patch-output-protocol.md) | 唯一 unified diff 输出与 `--recount` 应用协议 | Accepted for A0 |
| [ADR-0003](../decisions/0003-dataset-composition-v1.md) | 第一版数据配额、语言、任务层级、修改类型和测试覆盖 | Accepted for A0 |
| [ADR-0004](../decisions/0004-training-quality-gates-v1.md) | SFT/DPO 提升阈值、退化上限和 pilot 选择 | Accepted for A0 |
| [ADR-0006](../decisions/0006-owner-authorized-exploratory-a4.md) | 确认集失败后的 owner-authorized exploratory A4 边界 | Accepted; pre-A4 完成后执行 |

自动验收、fixture 和质量门禁的合并证据见 [`a0-validation.md`](../evidence/a0-validation.md)。历史执行细节保留在[执行记录](../records/第二项目_PatchAlign-Cpp_执行记录.md)，不在本索引重复展开。

机器可校验 Schema：

- [`sample-v0.2.schema.json`](../../schemas/sample-v0.2.schema.json)（当前 canonical sample）
- [`sample-v0.1.schema.json`](../../schemas/sample-v0.1.schema.json)
- [`prediction-v0.1.schema.json`](../../schemas/prediction-v0.1.schema.json)
- [`run-manifest-v0.1.schema.json`](../../schemas/run-manifest-v0.1.schema.json)
- [`run-manifest-v0.2.schema.json`](../../schemas/run-manifest-v0.2.schema.json)（A3.1 及后续）

`sample-v0.1` 保留用于历史记录重放；新建 A1 样本必须使用 `sample-v0.2`。

## 已冻结

- 项目名称：PatchAlign-Cpp；
- 第一阶段以函数级修复为主，Schema 兼容文件上下文；
- 必做训练链：Base → SFT → DPO；
- RLVR/GRPO 是可选扩展；
- 主训练起点：Qwen2.5-Coder-7B Base；
- 外部强基线：现有 Qwen3-8B；
- 第一版单张 A800 串行分段；
- BF16 LoRA 与 NF4 QLoRA 先公平 pilot，再冻结正式方案；
- gold patch 不得出现在生成 prompt；
- 第一主指标为 hidden-test Pass@1，同时报告解析、应用、编译和回归；
- 模型只输出唯一纯 unified diff；应用阶段用 `git apply --recount --check` 放宽 hunk 行数计数，不放宽内容、路径或修改范围；
- 不在 A2 执行闭环完成前训练。
- 仓库原创内容采用 Apache-2.0，版权标识为 `PatchAlign-Cpp contributors`；
- 正式 adapter 可在逐项审计后发布，中间 checkpoint、optimizer state 和 G0 smoke adapter 默认不公开；
- 未完成逐来源许可审计前不公开原始或重打包数据，完整预测需通过许可、敏感信息和漏洞披露检查。
- Qwen2.5-Coder-7B upstream revision 固定为 `0396a76181e127dfc13e5c5ec48a8cee09938b02`；
- 第一版数据组成和目标配额按 ADR-0003 冻结；最终可重放数量、来源 revision 和 manifest SHA256 在 A1 实测后冻结。
- SFT/DPO 正式质量门禁和 A3 pilot 选择规则按 ADR-0004 冻结；
- sanitizer 仅在 A2 执行配置显式标记适用的样本上运行和统计。

## A0 当时后置到 A2 的闸门

1. 禁网、非特权和资源限制曾作为 A2 进入闸门；该闸门后来由 rootless Bubblewrap 真实执行闭环关闭，终态证据见 [A2 文档](../a2_sandbox.md)。

## A0 验收条件

A0 只有在以下事项全部满足后才能标记完成：

- [x] 用户审阅并接受输出协议；
- [x] 用户审阅并接受完整任务契约；
- [x] 所有当前 JSON Schema 通过自动校验和正反例测试；
- [x] 有一个不依赖大模型的极小 fixture 可从预测文件重复评分；
- [x] 同一预测重复评分得到相同阶段结果、指标和规范化哈希；
- [x] 指标分母、跳过规则和失败优先级无歧义；
- [x] 模型角色、生成参数、seed 和 artifact 规则冻结；
- [x] 真实性与污染声明模板通过审阅；
- [x] 项目代码许可证与产物发布边界确定；
- [x] 所有未决事项都有明确 owner 或进入条件。

A0 的“完成”只证明本阶段协议、Schema、证据和治理模板；后续阶段是否完成必须从[项目状态](../status.md)及对应 artifact 核对。
