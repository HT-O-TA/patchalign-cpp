# PatchAlign-Cpp

PatchAlign-Cpp 是一个面向 C++ 缺陷修复的可验证后训练项目。项目研究在固定数据、提示和评测协议下，LoRA/QLoRA SFT 与 DPO 是否能提高开放权重 Base 模型生成可应用、可编译、通过隐藏测试且修改克制的补丁的能力。

当前状态：**A0 Draft**。基础环境和 Qwen2.5-Coder-7B 的 G0 兼容性 smoke 已完成；数据、评测基线和正式训练尚未开始。

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
- 当前没有 Base/SFT/DPO 质量指标；
- 当前没有下载或处理正式训练数据；
- 当前没有完成 A2 安全执行沙箱；
- 基础模型预训练污染未知，只能披露，不能声称完全排除。

## 开发状态

在 [A0 验收条件](docs/a0/README.md#a0-验收条件) 全部满足前，不进入正式数据下载、基线生成或训练。

## 许可证与发布边界

本仓库原创代码、文档、Schema、配置和脚本按 [Apache License 2.0](LICENSE) 发布，版权标识为 `Copyright 2026 PatchAlign-Cpp contributors`。模型、数据集、benchmark repository、生成补丁和第三方依赖仍受各自条款约束，详见 [治理规范](docs/a0/governance.md) 与 [第三方声明](THIRD_PARTY_NOTICES.md)。
