# Data-v2 新来源准入与污染审计

> 证据日期：2026-09-06。官方资料桌面审计已完成，负责人随后接受 ADR-0010 的分层 family 契约；GitHub metadata-only v1 实测为零查询结果，v1.1 检查前 18 条后仍为零准入，v1.2 分段续扫已冻结、待集群实测。未下载补丁或源码内容，未构造 Data-v2，未提交 GPU 作业。机器口径见 `configs/data/data_v2_source_admission_v1.json` 与 `configs/data/data_v2_contract_v2_1.json`。

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

## 已解决的 family 契约决策

桌面审计当时确认：若同一个 `repo_family` 既负责 split 隔离、又受每 family 最多 2 条限制，train 至少 1,600 条 `new_family` 的数学下界就是 800 个未见仓库。该冲突和当时的 blocker 作为历史事实保留。

负责人现已接受 [ADR-0010](../decisions/0010-data-v2-hierarchical-family-contract.md)：

- `repository_split_group` 使用规范化的 host/owner/repository，只负责仓库级 split 和 benchmark 隔离；
- `sampling_family` 使用 repository 加 issue/function 身份，负责重复控制，v1+增量仍最多 2 条；
- train/validation 每仓库分别最多 40/20 条；
- 2,000/200 保持容量探针，train 至少覆盖 100 个新仓库和 1,000 个新 sampling family，validation 至少覆盖 20 个新仓库和 100 个新 sampling family；
- 新来源单一来源占比不超过 70%，function 至少 1,200/120，file-window 至少 400/40。

该决定只解除元数据 pilot 的 family 设计阻断，不授权 patch/源码下载、Schema 转换、Data-v2 冻结、GPU 或训练。第一轮供给审计的 v1 配置和 800 仓库反证不被改写。

## 推荐的最小后续试采

契约已决定，下一步优先实施 CPU/网络元数据 pilot，不申请 GPU：

1. 固定完整评测仓库 denylist，包括当前 Defects4C 6 项目以及 Multi-SWE-bench、BugsCpp、LLVM APR、DebugBench 的保留身份；只消费仓库/实例 ID，不读取 gold。
2. v1.1 对最多 18 个候选 PR 形成最多 15 个不同 C++ 仓库的可复现查询快照；只存公开身份、统计、响应哈希和 LICENSE 内容哈希，不保存源码 blob、patch、标题/正文或许可证原文。
3. 用 changed files/lines、同仓库显式 issue 关联、linked issue 的 bug/defect 标签、仓库主语言、stars、时间和 SPDX allowlist 做元数据预筛；GitHub 详情响应不提供不含 patch 的文件类型证明，因此 C++ 文件变更与测试修改留到受控内容阶段核验。
4. 并行做 Multi-SWE-RL C++ 的 revision、行数、repo/日期/文件数投影，量化其对结构性样本的补充价值；任何 patch 正文落盘前再次检查与 Multi-SWE-bench 的实例和仓库重叠。
5. RunBugRun v2 只先核验 release 体积、版本 SHA、C++ problem ID 与 legacy 的集合差；若没有足够新 problem family，停止下载完整 dump。
6. 只有元数据报告证明修订后的容量门槛可达，才授权受控内容下载、Schema 转换和 CPU 资格重放；GPU 仍要等 Data-v2 manifest、三 seed 消融和评测门禁预注册完成。

## 验收证据

- 提交 `b93084c38d18e1254ae1111751124c5cdbce6f79` 已同步到集群；
- CPU-only 专项 Job `96326` 在 `gpu18` 用时 1 秒，得到 `5 passed in 0.03s`，registry validator 输出 3/4/2 决策计数与 800 仓库下界；
- one-off 全量 Job `96327` 因 `sbatch --wrap` 使用 `/bin/sh`、不支持 Bash `set -o pipefail`，在 pytest 前失败；
- POSIX 兼容替换 Job `96328` 用时 15 秒，得到 `265 passed in 13.50s`；
- 三个作业均未申请 GPU；失败 Job 没有被删除或写成测试失败。
- metadata pilot v1 Job `96406` 在 `gpu18` 用时 2 秒，10 项专项测试通过，但冻结查询返回 0 条、`target_met=false`。四组只返回总数的诊断显示：原查询 0、去掉 `archived:false` 仍为 0、再去掉 PR 级 `label:bug` 后为 48、再去掉 stars 后为 1,625,953；因此原因是 PR 标签筛选语义，不是网络、限流或采集器崩溃。
- v1.1 保留 v1 artifact，不覆盖原结果；改为核验被显式关闭的同仓库 issue 是否有 bug/defect 标签，并将最多 PR 详情请求从 25 收紧为 18。Job `96412` 用时 18 秒、11 项测试通过，共记录 21 次 API 响应；18 条分别因文件数 6、行数 3、无同仓库 issue 7、stars 1、许可证 1 被拒绝，0 条准入。
- 搜索页 48 条覆盖 34 个仓库，前 18 条只有 13 个仓库、剩余 30 条仍有 23 个仓库。v1.2 改为创建时间倒序并在详情前按仓库去重，最多再查 12 个仓库，最坏 36 次核心 API 请求，不超过 `96412` 结束时的 40 次余额。

## 当前决定

桌面准入审计已闭环，共 9 条候选：3 条进入元数据 pilot、4 条冻结为评测保留、2 条因语言不符拒绝。推荐主路线是自建 issue/PR 关联的真实 C++ 修复池，Multi-SWE-RL 仅作结构性补充，RunBugRun v2 只做 legacy 差量核验。当前没有来源获得“可直接进入训练”的许可。

负责人已接受分层 family 契约。下一实际动作不是提交训练，而是在集群运行 GitHub metadata-only v1.2，记录真实仓库供给、linked issue 标签、许可证预筛、denylist 命中和 API 可复现性；任何补丁内容准入仍需新的显式门禁。
