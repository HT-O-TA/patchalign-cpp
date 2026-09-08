# ADR-0023：修正 CommitPack 原始记录语言值

- 状态：Accepted
- 日期：2026-09-08

## 背景

CommitPack 单分片 v1 Job `97473` 在提交 `397647d9` 上完成 `411 passed`、输入哈希与
6,291 条 JSONL 流式读取，但得到 0 条候选；聚合拒绝原因全部为
`language_mismatch`。随后只统计字段值和字段名集合，确认固定分片 6,291/6,291 条的
`lang` 均为精确字符串 `C++`，而 v1 配置把 Hugging Face builder 的配置名 `c++`
误当成记录字段值。原始记录字段集合一致，额外的 `returncode`、`stderr` 不进入审计
或输出。

因此 v1 的 0/0 是配置 Schema 映射错误，不能用于判断 CommitPack 供给失败。

## 决策

1. 保留 Job `97473`、`commitpack-shard-audit-v1/` 及 v1 配置，不覆盖或删除；
2. 新建 v1.1，记录语言只接受精确值 `C++`；不做大小写模糊匹配；
3. v1.1 继续消费同一 revision、同一 `c++-0001.jsonl`、同一 bytes/SHA256，不重新
   下载，不增加或更换分片；
4. 许可证、仓库/commit/path、2～200 changed logical lines、denylist、legacy 去重、
   split/family/repository cap、70% 静态份额门和无源码 artifact 边界全部不变；
5. v1.1 结果写入独立目录 `artifacts/data-v2/commitpack-shard-audit-v1-1/`。通过只
   授权固定仓库执行 pilot，仍不授权训练或 GPU。

这是对实际上游 Schema 值的单点修正，不是看过质量结果后的阈值调整。
