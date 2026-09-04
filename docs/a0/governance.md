# A0 真实性、许可与发布治理

真实性与污染声明状态：Accepted for A0，版本 `0.2.0`
许可证与发布策略状态：**Accepted for A0**，版本 `0.1.0`
发布策略决策日期：2026-09-01

本文合并真实性、污染、归因、许可证和产物发布边界。它冻结工程声明模板，但不声称基础模型已完成预训练语料审计；A2 安全执行和后续模型实验必须各自提供独立证据。

## 1. 证据等级

| 等级 | 定义 | 可以声称 |
|---|---|---|
| Plan | 文档或配置尚未运行 | “计划”“设计”“待验证” |
| Synthetic test | 合成 fixture 或 tiny model | 接口、分支和错误处理可运行 |
| Smoke | 真实环境/模型的小规模运行 | 兼容性和最小链路通过 |
| Pilot | 真实数据小规模实验 | pilot 条件下的观察 |
| Frozen evaluation | 冻结数据、协议和 artifact | 可报告的模型比较 |
| Replicated result | 多 seed/重复或独立复现 | 稳定性范围内的结论 |

各阶段达到的证据等级随运行推进而变化，统一从[项目状态](../status.md)和对应 artifact 核对。无论当前进度如何，低等级证据都不得包装成高等级结论。

## 2. 污染与泄漏边界

本项目控制后训练数据：外部 benchmark repository family 拉黑、先按仓库族切分、精确/近似去重、训练输出与外部 gold 交叉审计，并保存 manifest、revision 和哈希。

CommitPackFT、RunBugRun 及后续外部数据的 revision、许可证和跨来源去重结果必须绑定到相应 manifest/lock。即使项目内 split 隔离检查通过，也不能声称基础模型预训练完全无污染。Qwen3-8B 仅作为外部 post-trained 基线，不归因于本项目。

基础模型预训练数据不可完全审计，只能声明：

> 已采取措施减少本人后训练数据对冻结评测集的污染；基础模型预训练污染未知。

禁止声称“完全无污染”。hidden test、验证/测试预测、gold patch 和执行反馈不得进入 SFT/DPO prompt 或训练数据。

## 3. 归因与禁止表述

- Qwen3-8B 现成能力属于外部 post-trained 基线；
- Base 模型已有知识不能归因于本项目；
- harness、prompt、采样预算、Agent 与 checkpoint 改进分别归因；
- public pass、GPU 可加载和 smoke 单步 loss 不能写成修复或训练质量提升；
- 合成 fixture 收益不能外推到真实仓库；
- 不报告未运行实验、无原始证据的百分比、删除失败 run 后的结果或训练集泛化结论。

## 4. 正式结论证据模板

```text
claim
evidence level
git commit
config hash
model id/revision/hash
dataset manifest/hash
seed
Slurm Job ID
prediction artifact/hash
execution artifact/hash
metric script/hash
known limitations
```

## 5. 仓库原创内容许可

- 原创代码、文档、Schema、配置和脚本采用 Apache License 2.0，原文见 [`LICENSE`](../../LICENSE)；
- 版权标识为 `Copyright 2026 PatchAlign-Cpp contributors`；
- 外部贡献除非标记 `Not a Contribution`，按 Apache-2.0 第5节处理；
- 仓库许可证不覆盖模型、数据集、benchmark、生成补丁或第三方依赖。

## 6. Adapter 与 checkpoint

| 类型 | 默认策略 | 公开前条件 |
|---|---|---|
| 正式 SFT/DPO adapter | 可以公开 | 模型条款、数据许可、敏感信息、模型卡和完整哈希通过审计 |
| 中间 checkpoint | 不公开 | 仅在有明确复现价值且通过相同审计后例外发布 |
| optimizer/scheduler state | 不公开 | 原则上只作内部恢复产物 |
| G0 Job 90719 adapter | 不公开 | 仅作集群兼容证据 |

正式 adapter 的许可证须结合基础模型和训练数据单独确定，不能由仓库 Apache-2.0 自动推导。

## 7. 数据、预测、报告与日志

- 未完成逐来源许可审计前不公开原始样本、重打包数据或含受限源码的派生数据；
- 可公开处理代码、Schema、来源/revision/哈希、去重规则和无受限内容的自建 fixture；
- 受限来源只公开复现索引或哈希，不复制内容；
- 默认可公开聚合指标、配置、Git commit、模型身份、seed、脱敏 Job ID 和报告；
- 完整预测须通过来源许可、敏感信息和漏洞披露检查；
- 原始日志、内部用户名、节点、绝对路径、环境变量和潜在密钥不公开；
- 发布限制不得导致失败样本从统计分母删除。

## 8. 第三方与发布门禁

第三方初始清单见 [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)。引入代码须保留版权、许可证和 NOTICE；模型、数据许可结论绑定明确 revision，release 前重新审阅清单。

任何 adapter、派生数据或完整预测发布必须满足：

1. artifact SHA256 和生成 commit 已记录；
2. 模型、数据和复制代码来源/revision 可追溯；
3. 许可证与 NOTICE 义务已检查；
4. 密钥、个人信息、内部路径和未披露漏洞已检查；
5. 模型卡、数据卡或评测报告准确描述限制；
6. 用户对该次发布明确批准。

本治理规范定义工程门禁，不替代正式法律意见。
