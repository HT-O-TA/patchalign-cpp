# Data-v2 GitHub C++ 元数据 pilot 结果

> 证据日期：2026-09-06。结论范围仅限冻结查询与 metadata-only 预筛；没有请求或保存 patch/源码，没有形成训练准入，也没有使用 GPU。

## 目的与判定口径

本 pilot 检查自建 GitHub issue/PR 关联 C++ 修复池能否为 Data-v2.1 提供足够的新仓库。版本化契约要求 train 容量探针至少覆盖 100 个新 `repository_split_group`；metadata pilot 只能证明供给与治理可行性，不能代替许可证全文审计、父提交核验、C++ 文件确认或测试重放。

冻结查询时间窗为 2023-01-01 至 2024-05-31，仓库主语言为 C++、当前 stars 至少 100、PR 已合并。候选还必须满足：2–200 changed lines、最多 10 个 changed files、显式关闭同仓库 issue、linked issue 带 bug/defect 标签、仓库非 fork/archived、SPDX 在 permissive allowlist、LICENSE 内容可哈希、评测仓库 denylist 不命中。

## 三次运行

| 版本 | Job / commit | 查询或详情 | 结果 | 解释 |
|---|---|---:|---:|---|
| v1 | `96406` / `821467f01b24a6624ac29daddab2f8c3f6532e04` | 查询 0 | 0/15 | `label:bug` 被错误施加于 PR；代码、网络和 10 项测试正常 |
| v1.1 | `96412` / `40430360cbb06651d97eb3f293ca1742c0121dfb` | 查询 48，详情 18 | 0/15 | 改为核验 linked issue 标签；18 条全部被既有门槛拒绝 |
| v1.2 | `96417` / `29c6aee9a81709d0cda1bd7897b1f9779ca28b74` | 查询 48，详情 12 | 0/12 | 倒序并在详情前按仓库去重；12 条仍全部拒绝 |

v1 的四组只返回总数的消融查询为：原查询 0；去掉 `archived:false` 仍为 0；再去掉 PR 级 `label:bug` 后为 48；再去掉 stars 门槛后为 1,625,953。因此 v1 零结果由 PR 标签查询语义造成，不是 API 失败。

v1.1 和 v1.2 共请求 30 个 PR 详情。排除 v1.2 的 3 个搜索页仓库重复后，详情级拒绝合计正好为 30：changed files 越界 10、changed lines 越界 4、无同仓库显式 issue 10、stars 回落 3、fork 1、许可证不在 allowlist 2。只有后两条能走到 LICENSE 门，且均未进入 permissive allowlist；最终没有 selected record。

## 容量结论

搜索页的 48 条结果只覆盖 34 个不同仓库；前 18 条覆盖 13 个，剩余 30 条覆盖 23 个。即使假设未检查候选全部通过，当前冻结查询最多也只有 34 个仓库，仍小于 Data-v2.1 train 的 100 个新仓库最低目标。因此：

- 当前单查询路线的容量门明确失败；无需为了改变不了的容量结论继续消耗 API 扫描中段；
- 0 个 selected record 不等于 GitHub 上不存在可用 C++ 修复，而是说明当前时间窗、stars、改动规模、显式 issue 与 permissive license 的交集过窄；
- 不能通过取消许可证门、使用关键词替代 linked issue、放宽改动规模或纳入评测仓库来制造“成功”；
- 下一轮若继续，应先设计多查询/多时间窗的仓库发现层，并把“仓库发现”和“PR 资格筛选”分开，再做同样的 metadata-only 容量审计。

当前结论是 `current_query_capacity_gate_passed=false`、`content_download_authorized=false`、`training_data_frozen=false`、`gpu_authorized=false`。

## 可复核 artifact

集群与本机均保留以下被 Git 忽略的小型 artifact：

| 目录 | repositories SHA256 | summary SHA256 | manifest SHA256 | log SHA256 |
|---|---|---|---|---|
| `artifacts/data-v2/metadata-pilot-v1/` | `e3b0c442...b855` | `735a7c20...efc86` | `90aaf2bc...6a4f` | `5e577891...e80` |
| `artifacts/data-v2/metadata-pilot-v1.1/` | `e3b0c442...b855` | `ea3d1f50...d0f3` | `5dfb7b48...5926` | `973cc8bb...63b` |
| `artifacts/data-v2/metadata-pilot-v1.2/` | `e3b0c442...b855` | `65c26c90...7167` | `33e02789...aa6` | `c6ce9756...55a` |

三个 repositories 文件均为空文件，其 SHA256 相同是零条准入的真实结果，不是文件丢失。manifest 分别记录 1、21、15 次 API 响应及内容边界；v1.2 结束时无令牌 core 余额为 26/60。

专项测试在 v1/v1.1/v1.2 分别为 10/11/11 项通过。全仓替换回归 Job `96419` 为 `276 passed in 13.27s`。首次全仓 Job `96418` 在收集期误加载用户 site-packages 中不完整的 `boto3`，触发 `jmespath` 缺失和 `accelerate` 循环导入；设置项目标准 `PYTHONNOUSERSITE=1` 后恢复，项目 conda 环境本身 `pip check` 无损坏依赖。
