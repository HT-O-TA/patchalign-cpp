# Third-party notices

状态：初始清单，随依赖、模型和数据来源审计持续更新。

PatchAlign-Cpp 的 Apache-2.0 许可证只覆盖本仓库原创代码、文档、Schema、配置和脚本，不重新许可任何第三方内容。

## 当前已识别项目

| 项目 | 用途 | 当前记录的许可证 | 分发状态 |
|---|---|---|---|
| Qwen2.5-Coder-7B Base revision `0396a76181e127dfc13e5c5ec48a8cee09938b02` | 主训练起点 | Apache-2.0（依据集群模型目录中的模型卡和许可证文件） | 权重不进入本仓库；四个元数据哈希已匹配，权重分片 LFS OID 待核验 |
| Qwen3-8B | 外部强基线 | 待正式基线前核验并固定 revision | 权重不进入本仓库 |
| PyTorch、Transformers、Datasets、Accelerate、PEFT、TRL、bitsandbytes | 运行与训练依赖 | 必须以实际冻结版本的上游许可证为准 | 依赖源码和二进制不进入本仓库 |
| 未来 C++ 修复数据源和 benchmark repository | 训练与评测 | 尚未开始逐来源审计 | 未获再分发许可前不发布原始或重打包内容 |

## 发布要求

每次增加模型、数据源、复制的第三方代码或再分发 artifact，必须记录：

- 名称、来源 URL 和用途；
- 固定版本或 revision；
- SPDX 标识或许可证原文路径；
- 修改情况、署名与 NOTICE 要求；
- 是否允许商用、修改和再分发；
- 本项目实际公开的内容和排除项。

依赖清单不等于许可证结论。正式公开 adapter、派生数据或完整预测前，必须完成对应来源的逐项审计。
