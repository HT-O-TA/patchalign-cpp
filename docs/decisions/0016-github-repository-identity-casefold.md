# ADR-0016：修正 GitHub 仓库身份的大小写规范化

- 状态：Accepted under delegated project decision authority
- 日期：2026-09-07

## 发现

Job `96922` 在提交 `2d6f96378699eee7763beafec06f9da531c32f73` 上完成
250/250 个 metadata-only 请求，但把 2,955 条 PR 记为
`repository_identity_mismatch`。检查发现，内部 `repository_split_group` 按契约
规范化为小写，而 GitHub Issue Search 返回的 `repository_url` 与 `pull_request.url`
保留仓库官方大小写。实现却对完整 URL 做大小写敏感比较。

最小只读探针中，查询 `repo:clickhouse/clickhouse` 返回
`https://api.github.com/repos/ClickHouse/ClickHouse`。两者指向同一 GitHub 仓库，
却被旧实现拒绝。ClickHouse、QGIS、SFML 等多个仓库因此整页 100 条全部丢失。
所以 Job `96922` 报告的 train `79/100` 不是可信容量下界，不能据此关闭路线。

## 决定

发布 `data-v2-repository-pr-discovery-v2.1`：

1. Repository Search、PR Search、时间窗、排序、240 个仓库选择、250 次请求预算、
   Data-v2 容量阈值和隐私投影全部保持不变；
2. GitHub API host/path 结构仍须精确符合 `/repos/{owner}/{repo}` 和
   `/pulls/{positive_number}`，但 owner/repo 身份按 GitHub 的大小写不敏感语义比较；
3. v2.1 绑定 ADR-0014 的完整评测身份 denylist，而不是旧 metadata pilot 的临时
   清单；
4. Job `96922` 的原 artifact、日志和五个哈希保持不可变，标记为投影实现无效的
   工程证据，不覆盖、不删除，也不用于容量门结论；
5. 旧 checkpoint 没有保存被拒绝条目的身份，无法安全离线恢复。v2.1 使用独立
   输出目录和新脚本/配置哈希，重新发出同一组查询；不复用旧 checkpoint；
6. v2.1 仍不下载 patch、源码、正文、用户身份或 raw response，不授权训练或 GPU。

## 停止规则

- v2.1 若通过原容量门，才进入预先固定的详情 pilot；
- v2.1 若在正确身份投影下仍失败，按 ADR-0013 关闭该查询路线，不改变查询或阈值；
- 瞬时 API 错误只允许以同一 v2.1 配置/脚本从 checkpoint 有限续跑。

