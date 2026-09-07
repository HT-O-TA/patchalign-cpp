# ADR-0013：修正 GitHub Data-v2 discovery 的端点语义

- 状态：Accepted under delegated project decision authority
- 日期：2026-09-07

## 问题

`data-v2-multisource-discovery-v1` 把 `language:C++`、`stars:>=20` 和
`archived:false` 放进了 GitHub Issue/PR Search 查询。GitHub 官方的
Issue/PR 搜索条件支持 `is:pr`、`is:merged` 和 `linked:issue`，但不把
语言、star 数或 archived 状态定义为该端点的过滤条件。这些条件属于
Repository Search。一次真实语法探针只能证明服务接受了字符串，不能证明
每个条件按预期生效。

Job `96894` 在 11 个查询后因单次 HTTP 504 失败；同提交续跑 Job `96902`
到 19/64 个查询时被主动终止。两个作业都没有终态 manifest，也不产生可用于
容量判断的有效证据。现有 checkpoint 和日志保留为负面工程证据。

## 决定

用版本化的两级 discovery 替代 v1，不覆盖或解释性修补旧结果：

1. 通过 `/search/repositories` 查询活跃、非 fork、stars≥20、主语言为 C++
   的仓库；固定读取按 stars 降序的前 10 页，每页 100 条；
2. 过滤当前评测 denylist 后，按 Data-v2.1 的仓库哈希切分和固定哈希排序，
   选择 200 个 train 仓库与 40 个 validation 仓库；
3. 对每个选中仓库调用 `/search/issues`，查询
   `repo:owner/repo is:pr is:merged linked:issue merged:2018-01-01..2025-12-31`，
   固定读取按 created 降序的第一页 100 条；
4. Repository Search 10 次加 repo-local PR Search 240 次，总 search 请求上限
   固定为 250；无令牌请求间隔至少 7 秒；每个请求采用原子 checkpoint；
5. 只保存仓库身份、star 快照、PR 号/API URL、时间戳、查询身份与响应哈希。
   不保存标题、正文、标签、用户、raw response、patch 或源码；
6. 原容量门不变：实际有候选的 train/validation 仓库至少 100/20，候选 PR
   上界至少 1,000/100，应用 family×2 与仓库 40/20 cap 后的样本上界至少
   2,000/200；所有请求完整且无 incomplete result 才算通过。

## 停止规则

- v2 容量门失败：关闭该 GitHub 路线，不修改查询继续试探；转向另一个已经
  版本化准入的独立来源。
- v2 容量门通过：只授权固定 200 PR 的详情 pilot；在完整评测 denylist、
  许可证、父提交和执行闭环通过前仍不下载 patch/source，不生成训练数据。
- 任一外部瞬时错误可以从同配置、同脚本哈希的 checkpoint 有限续跑；不得用
  无限重试掩盖稳定失败。

## 经验结论

API 返回 200 只证明查询可解析，不证明所有 qualifier 属于该搜索域。此后所有
外部数据发现配置必须同时验证“端点—qualifier 对应关系”和真实投影字段，而不
把单次成功响应当成语义验证。
