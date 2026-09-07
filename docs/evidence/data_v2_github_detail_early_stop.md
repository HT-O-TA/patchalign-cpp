# Data-v2 GitHub detail v1 早停审计

> 证据日期：2026-09-08。源 Job `96959` 已因冻结 outcome gate 数学不可达而停止；
> CPU-only 审计 Job `97150` 已完成。本文只说明 metadata detail v1，不授权内容取得、
> Data-v2、GPU、SFT 或 DPO。

## 为什么停止

固定选择按 train 160、validation 40 排列。一次性定时快照观察到日志中的前 144 个
train 候选已完成，只有 8 条合格；剩余 train 即使全部成功，合格数也最多为
`8 + 16 = 24 < 40`。因此继续运行不可能通过冻结的 train 数量门，Job `96959`
在 `2026-09-07T17:31:47Z` 被主动取消。这是确定性的无效工作早停，不是基础设施失败。

## 独立重建结果

Job `97150` 在提交 `a169fdfc4ae09cd69d466e77c7aae4195d913d82` 上完成
`391 passed in 25.88s`，总用时 35 秒。它先从 Slurm 账本核对源 Job 的状态、节点、
起止时间和耗时，再绑定源配置、采集脚本、固定选择与全部 246 个原子 checkpoint。

- 连续完成前缀：144；
- 合格：8，拒绝：136，中断：1，未开始：55；
- train 合格：8 条/8 仓库；validation 尚未开始；
- train 乐观上限：24 条/23 仓库，低于 40 条/30 仓库门；
- 第 145 个候选已有 pull checkpoint，但缺 issue checkpoint，按中断而非拒绝处理。

拒绝分布如下：

| 阶段与原因 | 数量 |
|---|---:|
| issue：关联 issue 无 bug 标签 | 58 |
| pull：无显式同仓库 closing issue | 34 |
| pull：变更文件数越界 | 20 |
| license：许可证不在 allowlist | 12 |
| pull：变更行数越界 | 9 |
| issue：HTTP 404 | 1 |
| issue：关联 issue 未关闭 | 1 |
| issue：关联目标实际为 PR | 1 |

最大的单项是 58 个不同仓库中的 issue 缺少 bug 标签。该结果不能证明这些 PR 都是
缺陷修复，但足以证明标签是高噪声的 discovery 门。后续若继续 GitHub 路线，应把
稳定 `buggy fail → fixed pass` 的真实执行证据作为最终缺陷资格，把标签只作为分层
字段；这必须是新版本方案，不能回写、恢复或降低 v1 门槛。

## 产物身份

目录：`artifacts/data-v2/github-detail-pilot-v1/early-stop-audit-v1/`

- checkpoint inventory：`7d1829a7...265c`（canonical inventory）；
- decisions：`3edcbb90...9c05`；
- qualified prefix：`067d5fba...ce81`；
- summary：`88517d7b...fd25`；
- run manifest：`d82b2bfc...e554`。

审计没有发出网络请求、读取 raw response、patch 或源码，也没有产生训练样本或使用
GPU。ADR-0019 的原 50 条内容 pilot 前件未成立，因此保持未激活。
