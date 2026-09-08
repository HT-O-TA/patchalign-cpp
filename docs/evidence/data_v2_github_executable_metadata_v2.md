# GitHub executable-evidence metadata v2 结果

> 证据日期：2026-09-08。CPU/网络 Job `97210` 已完成；本结果只授权固定 20 条内容
> 可行性 pilot，不代表任何样本已通过执行资格，也不授权训练或 GPU。

ADR-0021 保持 ADR-0017 的固定 200 条分母和顺序，逐哈希复用 v1 的 145 个 pull、
81 个 issue checkpoint，只对缺口发出新请求。关闭 issue 的 bug 标签改为分层字段；
PR 身份、合并状态、显式同仓库 closing issue、issue 关闭状态、改动文件/行数和完整
评测仓库 denylist 仍是硬门。默认分支 LICENSE 不再作为 metadata 门，历史许可证将
在内容阶段对 parent/fixed commit 分别核验。

Job `97210` 在提交 `76161d56ec6a502f968cd1bf69a85d9f4e9ee6a0` 上运行
`01:24:08`，完整回归为 `395 passed in 84.39s`。它新增 81 个逻辑/API 请求，无重试，
得到：

| 指标 | Train | Validation | 合计 |
|---|---:|---:|---:|
| metadata 候选 | 86 | 18 | 104 |
| 唯一仓库 | 81 | 14 | 95（split 内相加） |

标签分层为有 bug 标签 31、无 bug 标签 73。全部 outcome gate 均通过：总数至少 50、
split 至少 40/10、仓库至少 30/8。96 条拒绝为无显式 closing issue 46、文件数越界
28、行数越界 19、issue 404/未关闭/实际为 PR 各 1。

正式产物位于
`artifacts/data-v2/github-executable-evidence-v2/metadata/`：

- candidate metadata：`a7f67ef2...f0eb`；
- decisions：`20dcbf82...eb72`；
- summary：`9ef07936...e484`；
- run manifest：`4e457e99...a0df`。

下一步按 ADR-0021 固定 20 条（train 16、validation 4），在两个 split 内各平衡
有/无 bug 标签并保持仓库唯一。固定后不得因 clone、许可证、构建系统、依赖、测试
数量或重放结果失败而换样本；至少 4/20 完成严格双资格，才进入不重叠的正式 50 条
执行 pilot。
