# PatchAlign-Cpp

PatchAlign-Cpp 是一个面向 C++ 缺陷修复的可验证后训练项目。项目研究在固定数据、提示和评测协议下，LoRA/QLoRA SFT 与 DPO 是否能提高开放权重 Base 模型生成可应用、可编译、通过隐藏测试且修改克制的补丁的能力。

当前状态：**A0 技术验收完成，A1 pilot 已生成，A2 rootless 安全执行与 70 条真实评分闭环完成，A3.0 双基线 executable pilot 已完成，A3.1 scoring v2 已冻结并进入 CPU 重评分**。正式训练尚未开始。

## 第一阶段范围

- 以函数级 C++ 修复为主；
- Schema 兼容给定文件上下文；
- 输入包含缺陷描述、已定位上下文和失败证据；
- 输出严格限制为一个 unified diff；
- 通过 patch 解析、应用、编译、公开测试、隐藏测试和回归测试验证；
- 仓库自主探索、联网搜索和长程 Agent 不属于第一版。

## 当前入口

- [A0 阶段索引](docs/a0/README.md)
- [核心任务与评测协议](docs/a0/core_protocol.md)
- [样本与运行 Schema](docs/a0/sample_schema.md)
- [实验与复现协议](docs/a0/experiment_protocol.md)
- [真实性、许可与发布治理](docs/a0/governance.md)
- [决策记录](docs/decisions/)
- [A0 自动验收证据](docs/evidence/a0-validation.md)
- [A2 沙箱与真实执行入口](docs/a2_sandbox.md)
- [A3.0 冻结基线协议](docs/a3_baseline.md)
- [A3.1 评分协议与重评分](docs/a3_1_scoring.md)
- [执行记录](docs/records/第二项目_PatchAlign-Cpp_执行记录.md)
- [目录结构台账](docs/records/第二项目_PatchAlign-Cpp_目录结构.md)
- [本机—集群 Git 同步规范](docs/development/git-sync.md)
- [G0 Job 90719 证据摘要](docs/evidence/g0-smoke-90719.md)

## 环境与模型

祝融项目路径：

```text
/mingli01/project/ht/patchalign-cpp
```

专属 Conda prefix：

```text
/mingli01/project/ht/.conda_envs/patchalign-cpp
```

主训练 Base：

```text
/mingli01/models/Qwen2.5-Coder-7B
```

所有 Slurm 作业必须设置 `PYTHONNOUSERSITE=1`，并验证 `command -v python` 与 `sys.prefix` 都指向项目专属 prefix。模型目录只读，环境、权重、数据和大型 artifact 不进入 Git。

## 真实性边界

- G0 仅证明环境、BF16 LoRA、NF4 QLoRA 和 adapter 生命周期兼容；
- 当前已有 A3.0 的 M0 Base/External 70 条 executable pilot 起点，但两组严格 Pass 均为 0，不能形成正式 Base/SFT/DPO 质量结论；
- 当前已完成 A1 pilot 和 A2 50 function + 20 file-window 可执行 pilot；正式 500 条内部评测集与训练规模数据尚未构建；
- A2 的 rootless Bubblewrap、官方兼容输出匹配、真实结果分区和三次稳定重放已闭环；`0.2.0-draft` execution Schema 仅冻结用于 A2 pilot，生产 Schema 仍待正式评测前升级；
- 基础模型预训练污染未知，只能披露，不能声称完全排除。

## 开发状态

A0 协议验收、A1 pilot、A2 安全执行闭环和 A3.0 双基线已完成；A3.1 已冻结终止 LF 的 scoring v2，正在对不可变基线预测执行 CPU-only 重评分，完成后再进入 LoRA/QLoRA 小规模训练 pilot。

## 许可证与发布边界

本仓库原创代码、文档、Schema、配置和脚本按 [Apache License 2.0](LICENSE) 发布，版权标识为 `Copyright 2026 PatchAlign-Cpp contributors`。模型、数据集、benchmark repository、生成补丁和第三方依赖仍受各自条款约束，详见 [治理规范](docs/a0/governance.md) 与 [第三方声明](THIRD_PARTY_NOTICES.md)。
