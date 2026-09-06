# Third-party notices

状态：内部研究交付清单；公开 release 前仍需逐来源法律与安全审计。

PatchAlign-Cpp 的 Apache-2.0 许可证只覆盖本仓库原创代码、文档、Schema、配置和脚本，不重新许可任何第三方内容。

## 当前已识别项目

| 项目 | 用途 | 当前记录的许可证 | 分发状态 |
|---|---|---|---|
| Qwen2.5-Coder-7B Base revision `0396a76181e127dfc13e5c5ec48a8cee09938b02` | 主训练起点 | Apache-2.0（依据集群模型目录中的模型卡和许可证文件） | 权重不进入本仓库；四个元数据哈希已匹配，权重分片 LFS OID 待核验 |
| Qwen3-8B | 外部强基线 | 待正式基线前核验并固定 revision | 权重不进入本仓库 |
| PyTorch、Transformers、Datasets、Accelerate、PEFT、TRL、bitsandbytes | 运行与训练依赖 | 必须以实际冻结版本的上游许可证为准 | 依赖源码和二进制不进入本仓库 |
| Bubblewrap v0.12.0, source commit `2a76602a8c71f36c1527cf9fc3417d9149822e0c` | A2 非特权执行沙箱 | LGPL-2.0-or-later（依据官方源码 SPDX 与 COPYING） | 源码和二进制只保留在集群 `.tools`，不进入本仓库；项目仅跟踪构建脚本、版本和哈希记录 |
| RunBugRun data v0.0.1；匹配器语义固定到 legacy commit `5c023d6273ced705a5f83063b6b4cbf67aa81fa5` | A1/A2/A3/A4 C++ 数据、测试判定与训练 | CodeNet 来源许可仍须逐项审计 | 原始代码、测试、候选池、holdout 和派生偏好数据仅保留在集群，不进入 Git、不公开分发 |
| CommitPackFT C++ | A1/A3 SFT train/validation | 数据集及底层仓库许可尚未逐来源完成审计 | 原始和重打包数据仅保留在集群；本轮不公开数据或 adapter |
| Defects4C 官方源 commit `aecc2cf5f751d7c0894ae7d95ee0b8ae28e77b39` 及其 11 个上游 C++ 项目 | A3.4 外部资格与成对评测 | 数据集与各上游项目条款须逐项核验 | 官方源码 checkout、测试和完整预测只留在集群；Git 仅保存配置、处理代码、聚合指标与哈希 |
| 未来 C++ 修复数据源和 benchmark repository | 后续训练与评测 | 尚未开始逐来源审计 | 未获再分发许可前不发布原始或重打包内容 |

## 发布要求

每次增加模型、数据源、复制的第三方代码或再分发 artifact，必须记录：

- 名称、来源 URL 和用途；
- 固定版本或 revision；
- SPDX 标识或许可证原文路径；
- 修改情况、署名与 NOTICE 要求；
- 是否允许商用、修改和再分发；
- 本项目实际公开的内容和排除项。

依赖清单不等于许可证结论。正式公开 adapter、派生数据或完整预测前，必须完成对应来源的逐项审计。
