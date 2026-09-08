# Data-v2 独立来源可实现性审计 v2

> 证据日期：2026-09-08。这里只做官方固定 revision 与集群能力的桌面审计；没有取得
> 训练源码、运行第三方程序或申请 GPU。最终机器决策见 ADR-0025。

## 审计维度

本轮一次性检查：真实修复对、C++ 规模、仓库/任务多样性、可执行证据、数据与上游
许可证、现有评测污染，以及当前集群能否在无管理员协助下复现官方运行环境。

| 来源 | 固定 revision | 真实规模/结构 | 可执行与许可边界 | 决策 |
|---|---|---|---|---|
| BugsCpp | `be5cc489cb2b3127ec3b73cb4adfdd290807f55b` | 215 defects、24 project IDs；元数据实计 145 multi-line、69 single-line | 发布 checkout/build/test 与 Dockerfile；benchmark 框架 MIT，但各上游项目仍需历史许可证核验 | 继续作为评测保留，不进入训练 |
| CppPerf | `a7cba4f6ced9535ab652f1589f1e31bf324edfe6` | 347 个数据 JSON；官方论文报告 42 个成熟 C++ 仓库、39% multi-file | 提供预构建 Docker 和性能统计；框架 Apache-2.0，上游源码沿用各仓库许可 | 目标是性能优化，不作为语义修复主来源；仅保留未来消融 |
| TrickyBugs | `84411e82971413652f2e087505f7d47355c484f8` | 3,043 个 buggy programs、324 个竞赛 task；224 个 task 有 fixed_programs | 提供原始/新增测试和运行工具，但主体数据另置压缩包；竞赛提交逐条训练/再分发权利未闭环 | 拒绝当前训练准入 |
| BeetleBox | `ac12f9cd8afac9095498ff69cafe45ce8747b4ef` | 数据卡为 26,321 bugs/29 projects；C++ native train/test 3,868/4,783 | 含 issue/PR、before/after SHA 与修改文件；不含源码、测试命令或许可证声明 | 进入固定 20 MB metadata-only 审计 |

官方入口：[BugsCpp](https://github.com/Suresoft-GLaDOS/bugscpp)、
[CppPerf](https://github.com/vizual1/CppPerf)、
[TrickyBugs](https://github.com/RinCloud/TrickyBugs)、
[BeetleBox](https://huggingface.co/datasets/bug-localization/BeetleBox)。

## BugsCpp 细化结论

固定仓库 tree 完整且未截断，包含 24 个 `meta.json`、215 个 `*-buggy.patch`。24 个
project ID 中 `cppcheck` 与当前 Defects4C 仓库级外部评测重叠；其余项目也已由
ADR-0014 整体冻结为 future evaluation reserve。把它改作训练会立即损失目前唯一较
成熟的独立 C/C++ 可执行 benchmark，因此当前不改写 denylist。

官方执行依赖 Docker。集群 PATH 中没有 Docker、Podman、Apptainer、Singularity、
Enroot 或 Proot；已有 rootless Bubblewrap 0.12.0 和 Defects4C rootfs，但不能直接
等价执行 24 个项目各自的 Dockerfile。这个事实不代表永远无法适配，只说明现在不应
在没有分层选择和许可证门的情况下启动 215 项构建。

## 为什么只推进 BeetleBox 元数据

BeetleBox 的两个 Parquet 总计 19,375,255 bytes，LFS SHA256 已由固定 revision 提供。
它能低成本回答三项关键问题：C++ 记录和 SHA 是否真实完整、29 个项目在 native split
间如何重叠、排除现有评测仓库并按仓库重分后还能保留多少容量。

但它只是 bug-localization 元数据索引。即使 metadata gate 通过，也只允许下一轮固定
仓库历史许可证审计；不能据此声称补丁正确、测试可复现或 Data-v2 已冻结。

## 对总体方案的影响

当前证据不支持继续坚持“2,000/200 每条都必须执行”这一组合作为单一数据门，也不
支持直接把静态提交当成已验证修复。更可实现的方向是：SFT 的真实开发者修复监督层
负责新增仓库和复杂上下文，独立的可执行资格层负责 buggy-fail/fixed-pass、偏好排序
和质量门；两层共享污染、许可证、Schema、哈希与 repo split 约束。是否正式采用及
最终配额，要等 BeetleBox 固定分母结果后另立 ADR，不能在本页预先改门。
