# A0：问题、边界与实验协议

状态：**Draft，尚未验收**  
Schema 版本：`0.1.0`  
任务协议版本：`0.1.0`

A0 的目标是在下载正式数据和运行基线之前，冻结项目要解决的问题、模型可见输入、输出格式、评分顺序、复现证据和真实性边界。

## A0 文档清单

| 文档 | 作用 | 当前状态 |
|---|---|---|
| [任务契约](task_contract.md) | 定义输入、输出、允许修改范围和任务层级 | Draft |
| [样本与运行 Schema](sample_schema.md) | 定义规范样本、预测、执行结果和 run manifest | Draft |
| [评测协议](evaluation_protocol.md) | 定义解析、应用、编译、测试和指标 | Draft |
| [实验与复现协议](experiment_protocol.md) | 定义模型角色、seed、配置、artifact 和可比性 | Draft |
| [真实性、污染与泄漏声明](authenticity_and_leakage.md) | 定义证据强度和禁止表述 | Draft |
| [ADR-0001](../decisions/0001-model-and-resource-strategy.md) | 模型、LoRA/QLoRA 和资源策略 | Accepted for A0 |
| [ADR-0002](../decisions/0002-patch-output-protocol.md) | 唯一 unified diff 输出协议 | Proposed |

机器可校验 Schema：

- [`sample-v0.1.schema.json`](../../schemas/sample-v0.1.schema.json)
- [`prediction-v0.1.schema.json`](../../schemas/prediction-v0.1.schema.json)
- [`run-manifest-v0.1.schema.json`](../../schemas/run-manifest-v0.1.schema.json)

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
- 不在 A2 执行闭环完成前训练。

## 尚待冻结的闸门

1. 项目代码许可证；
2. adapter、派生数据和完整预测的公开范围；
3. Qwen2.5-Coder-7B 的精确 upstream revision；
4. 第一版冻结评测集的样本数和组成；
5. 正式训练前的最小有意义提升与可接受退化阈值；
6. OCI/Slurm 沙箱能否满足禁网、非特权和资源限制。

## A0 验收条件

A0 只有在以下事项全部满足后才能标记完成：

- [ ] 用户审阅并接受任务契约和输出协议；
- [ ] 三个 JSON Schema 通过自动校验和正反例测试；
- [ ] 有一个不依赖大模型的极小 fixture 可从预测文件重复评分；
- [ ] 同一预测重复评分得到相同阶段结果和指标；
- [ ] 指标分母、跳过规则和失败优先级无歧义；
- [ ] 模型角色、生成参数、seed 和 artifact 规则冻结；
- [ ] 真实性与污染声明模板通过审阅；
- [ ] 项目代码许可证确定；
- [ ] 所有未决事项都有明确 owner 或进入条件。

验收前禁止把本文档的 Draft 条款写成已经完成的实验事实。

