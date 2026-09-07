# ADR-0012：Data-v2 到正式 DPO 的分阶段治理与停止门

- 状态：Accepted by project owner through explicit delegated decision authority
- 日期：2026-09-07

## 背景

`data-v2-exploratory-replay-v0.1` 已完成 780 条单 seed continuation 和 formal 500 真实评分。新 adapter 为 13/500 Pass，低于 M1-R2 的 14/500 和预注册下限 14；regression failure 从 3 增至 8。该分支作为负结果封存，不再用相同 780 条混合数据重训，也不继续为它消耗 confirmation/Defects4C GPU。

项目负责人现已把从 Data-v2 建设、可泛化 SFT、高质量偏好数据、正式 DPO、评测、消融、失败分析到最终交付的过程决策授权给执行方。RLVR/GRPO 明确不属于本轮目标。

## 决定一：来源路线和固定预算

### GitHub issue-linked C++ 修复

它是主供给路线，但旧 v1/v1.1/v1.2 的单查询只有 34 个仓库，不能继续通过修改同一查询反复试探。新 discovery 必须：

- 只读取 GitHub Search API 返回的最小 PR/仓库身份，不请求 patch、源码、PR/issue 正文、用户身份或许可证正文；
- 固定扫描 2018-01-01 至 2025-12-31 的 32 个季度窗口，每窗按 created 升序和降序各取一页 100 条，共最多 64 个 search 请求、6,400 个候选出现；
- 无口令请求间隔至少 7 秒，支持查询级原子 checkpoint；
- 使用当前保留仓库 denylist 过滤，但在 denylist 完整前保持内容下载关闭；
- 只有实际哈希分配后的 train/validation 仓库数至少 100/20、候选 PR 上界至少 1,000/100、按 family×2 和仓库 40/20 cap 投影的样本容量至少 2,000/200，才进入详情 pilot。

详情 pilot 固定最多 200 个 PR、至少覆盖 20 个仓库，并采用可恢复请求。若可执行内容资格率低于 20%，或许可证、父提交、测试重放无法闭环，则淘汰该路线，不降低质量门槛。

### Multi-SWE-RL

固定官方 revision `9777648932daa214ba18c70c81e85821b5836f32`。官方列出的 9 个 C++ 仓库均属于已保留的 Multi-SWE-bench C++ 仓库集合，训练可用仓库为 0。该路线从训练供给中关闭，不下载数据内容；保留为评测污染身份来源。

### RunBugRun v2

固定官方 tag `v2` / revision `bbac70b7ae7331d87892e861356cf133476bc938`。官方资产 `runbugrun.sql.lrz` 为 120,501,798 bytes。它只能作为次级、可执行 problem-family 差量来源，不能承担仓库多样性；先下载并验哈希、只统计 C++ train/validation 相对 legacy 的新 problem family、规模与 Schema。若安全增量不足以与 GitHub 路线共同满足单一新来源占比不超过 70%，则在训练前停止并寻找新的独立来源。

## 决定二：内容与 Data-v2 冻结门

任何 patch/source 下载前必须完成保留评测仓库 denylist。内容 pilot 通过后，Data-v2 仍须满足 `data-v2-contract-v2.1` 的全部条件：2,000/200 增量容量，100/20 个新仓库，1,000/100 个新 sampling family，function 为多数，长代码、长 prompt、complex/structural edit 配额，train/validation 和 benchmark 零交叉，许可证逐仓库核验，buggy/fixed 测试确定性重放，Schema/token/hash 可重复。

未同时满足这些条件时：不冻结训练 JSONL，不训练，不用 GPU。

## 决定三：SFT 路线与 staged early-stop

正式 Data-v2 通过后，从 Base 在“原正式训练集 + Data-v2”上重新 SFT，不继续叠加 exploratory adapter。先在独立 Data-v2 开发执行集建立 M1-R2 基线，再运行 3 个冻结 seed；至少 2/3 seed 的端到端 Pass 必须优于基线，且 timeout/regression 不恶化，才选择唯一候选。

正式评测严格分段：

1. formal 500：相对 M1-R2 总 Pass 必须至少 15/500，paired-bootstrap 95% 区间下界严格大于 0，timeout≤2、regression failure≤3；失败即停止晋级评测；
2. confirmation 124：Pass≥1、timeout≤4、regression failure≤3；失败即停止；
3. Defects4C 176：Pass≥1、timeout=0，且相对 M1-R2 的最大退化不超过 2pp；
4. 三门全部通过后，仍需单独 owner-delegated promotion ledger 才能成为 DPO 起点。

这些门槛在新结果出现前冻结。不得以 loss、strict diff、apply、compile 或 public success 代替最终 Pass。

## 决定四：偏好数据与 DPO

DPO 不用于修复尚未通过的 SFT。SFT 三门通过后才允许构造正式偏好数据。现有 A4 182 对只作为候选池重新审计；7 对仅由 timeout tiebreak 形成的数据默认排除。正式 DPO 数据至少 300 对，其中 chosen 完整 success 至少 150 对；必须同题、无评测泄漏、chosen/rejected 原始 completion 可追溯，执行证据与训练文件分离。

DPO 先做 3-seed 小规模消融，只有多数 seed 在独立 train-family-disjoint 开发执行集上优于 SFT 且风险不恶化，才运行一个正式配置。随后按与 SFT 相同的 formal→confirmation→Defects4C 顺序评测，并保留 SFT/DPO 成对比较、关键数据组成消融和失败案例分析。任一硬门失败即停止晋级，但保留负结果。

## 决定五：资源与等待策略

- CPU/网络任务优先；GPU 只由已通过的前置 artifact 依赖释放；
- 根据候选量和历史吞吐估算完成时间，在 ETA 附近加缓冲后检查，不高频轮询；
- 节点零日志、共享存储或调度异常先做同提交跨节点归因，可重排但不改实验；
- 模型结果异常先核验输入、配置、哈希、日志和评分链，再决定停止或版本化修正；
- 不重复没有新增信息的训练、查询或评测。

## 完成条件

本轮只有在正式 SFT、正式 DPO、三套冻结评测、必要消融、失败分析、模型选择、模型卡、报告、复现材料、artifact 索引及本地/GitHub/集群同步全部完成后结束。完成前不讨论 RLVR/GRPO 实施。
