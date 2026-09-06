# Data-v2 新来源准入与污染审计

> 证据日期：2026-09-06。当前只完成官方资料与元数据层面的桌面审计；未下载候选数据内容，未构造 Data-v2，未提交 GPU 作业。机器口径见 `configs/data/data_v2_source_admission_v1.json`。

## 审计问题与边界

第一轮供给审计证明现有 CommitPackFT/RunBugRun legacy 池只剩 260 条 train 与 131 条 validation，不能达到暂定 2,000/200 增量目标。本轮据此检查新来源的七个维度：许可证、可获得性、真实修复对、family 多样性、长输入/多行供给、可执行测试、现有及未来评测污染。

本轮只读取官方 README、数据卡、论文页和 API 文档。没有读取 confirmation、Defects4C 或新 benchmark 的 gold patch；没有下载源代码、JSONL、SQLite dump 或容器镜像。数据集许可证不自动替代其所收录仓库的许可证，GitHub 自动识别的 SPDX 也只作为筛选信号，后续仍需保存每个仓库的 LICENSE 内容和哈希。

## 候选结论

| 来源 | 官方可确认事实 | 准入结论 | 主要原因 |
|---|---|---|---|
| 自建 GitHub issue/PR 关联 C++ 修复池 | GitHub API 可读取仓库许可证、commit 和 PR 元数据 | 元数据 pilot，首选路径 | 最能增加新仓库、长代码和结构性修改；但必须先解决 family 契约、许可证、限流、测试重放和 benchmark 仓库 denylist |
| Multi-SWE-RL | 初始全语言 4,723 条；C++ 仓库存在；发布 fix/test patch 与执行结果字段 | 元数据 pilot，辅助来源 | 真实仓库上下文，但 C++ 仅约十个仓库、任务多为仓库级/多文件；数据卡 UI 标 `other`，正文为受底层仓库许可证约束的条件 CC0 |
| RunBugRun v2 | 全语言超过 70 万可执行 buggy/fixed 对；带测试、bug label、hunk 元数据和预定义 split | 仅做 legacy delta pilot | 新版规模大，但仍来自 CodeNet 短程序，与已审计 237,516 条 legacy C++ 处于同一 problem domain，不能直接增加 repository diversity |
| Multi-SWE-bench C++ | C++ 评测 129 条，真实 issue、专家筛选、Docker 环境 | 保留为未来外部评测 | 一旦用于训练即失去独立评测价值；仓库级 agent 任务也超出现有函数级补丁契约 |
| BugsCpp | 215 个 C/C++ 可复现缺陷，提供 checkout/build/test，框架 MIT | 保留为未来可执行评测 | 多项目且真实，但需实测严格 C++ 数量；cppcheck 与当前 Defects4C 重叠，必须剔除或单列 |
| LLVM APR Benchmark | 295 个 LLVM issue；264 single-file、227 single-function；完整回归测试 | 低优先级 LLVM 压力评测 | 只有 LLVM，而当前外部集已有 139/176 LLVM；用于训练会继续放大项目偏斜并污染公开 benchmark |
| DebugBench C++ | 全语言 4,253 条、四大类 18 小类 | 仅保留合成 taxonomy 辅助评测 | bug 是 GPT-4 向 LeetCode 片段植入，不是真实开发者修复对，也不提供仓库泛化证据 |
| FixEval | 官方预处理发布仅 Java/Python | 拒绝 | 无已发布 C++ 预处理集 |
| PatchEval-Verified | 230 个 CVE，当前覆盖 Go/JavaScript/Python | 拒绝 | 当前 verified 版本没有 C/C++ |

## 关键约束冲突

当前 Data-v2 草案用同一个 `repo_family` 同时承担两种职责：

1. train/validation 与评测之间的隔离键；
2. `v1 + increment` 每 family 最多 2 条的采样上限。

暂定 train 要求至少 1,600 条 `new_family` 样本。在“仓库就是 family、每仓库最多 2 条”的解释下，至少需要 800 个未见仓库。Multi-SWE-RL 的 C++ 部分只有约十个仓库，最多只贡献约 20 条；BugsCpp 和 LLVM benchmark 又应优先保留为评测。该矛盾不是增加下载量可以解决的。

进入数据内容试采前必须二选一，并建立新版本配置：

- 保留当前 family 定义与 2 条上限，同时显著缩小 Data-v2 增量及 new-family 目标；或
- 把 `repository_split_group` 与更细的 `sampling_family` 分开：按 repository 做 split/benchmark 隔离，按 issue/function 等细粒度 family 控制重复，再另设每仓库总上限。

本轮不替负责人选择，也不静默放宽冻结规则。

## 推荐的最小后续试采

契约决定之后，优先实施 CPU/网络元数据 pilot，不申请 GPU：

1. 固定完整评测仓库 denylist，包括当前 Defects4C 6 项目以及 Multi-SWE-bench、BugsCpp、LLVM APR、DebugBench 的保留身份；只消费仓库/实例 ID，不读取 gold。
2. 对 GitHub C++ 仓库做可复现查询快照，先取 100 个仓库的许可证、默认分支、活跃度和 merged PR/commit 身份，不下载源码 blob；自动许可证仅作预筛，保存 LICENSE 文件哈希后才可清除许可证 blocker。
3. 从通过仓库中只抽 200 个 issue/PR 关联修复的元数据，统计单文件、changed lines、测试修改、提交时间与 repo 分布；不据 commit message 单独判断“bug fix”。
4. 并行做 Multi-SWE-RL C++ 的 revision、行数、repo/日期/文件数投影，量化其对结构性样本的补充价值；任何 patch 正文落盘前再次检查与 Multi-SWE-bench 的实例和仓库重叠。
5. RunBugRun v2 只先核验 release 体积、版本 SHA、C++ problem ID 与 legacy 的集合差；若没有足够新 problem family，停止下载完整 dump。
6. 只有元数据报告证明修订后的容量门槛可达，才授权受控内容下载、Schema 转换和 CPU 资格重放；GPU 仍要等 Data-v2 manifest、三 seed 消融和评测门禁预注册完成。

## 当前决定

桌面准入审计已闭环，共 9 条候选：3 条进入元数据 pilot、4 条冻结为评测保留、2 条因语言不符拒绝。推荐主路线是自建 issue/PR 关联的真实 C++ 修复池，Multi-SWE-RL 仅作结构性补充，RunBugRun v2 只做 legacy 差量核验。当前没有来源获得“可直接进入训练”的许可。

下一实际动作不是提交训练，而是由负责人决定 family 契约的版本化修订方向；随后才能启动带网络访问的元数据 pilot。
