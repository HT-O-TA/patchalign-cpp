# ADR-0022：GitHub 路线关闭后激活有界 CommitPack 供给审计

- 状态：Accepted
- 日期：2026-09-08

## 背景

ADR-0018 原先把 CommitPack 单分片审计设为“GitHub detail 通过且需要第三来源”后的
条件步骤。随后 ADR-0020 关闭 detail v1，ADR-0021 的 evidence v2 虽得到 104 条
metadata 候选，但固定 20 条内容 pilot 在历史许可证和静态执行门后为 0/20。继续
扩大同一 broad GitHub 抽样、换样本或降低门槛没有依据。

项目仍需回答一个不同问题：大规模、逐样本带 repository/commit/license/old/new
内容的 C++ commit 来源，在许可、去重、仓库 split 与 cap 后是否有足够供给。这个
问题可以通过 ADR-0018 已固定的单个 524 MB 分片回答，不需要 GPU，也不需要执行
第三方代码。

## 决策

1. 激活 ADR-0018 的最小下载边界，仅下载 CommitPack revision
   `5eee2c845bf88dbffcafedb6e80d2a72a43fe575` 的
   `data/c++/c++-0001.jsonl`；字节数必须为 `523946192`，SHA256 必须为
   `dfdd55f56f7be3bf4b8d2ccad8ea39910b4dd2c18ee296f5a991d134e57f367f`；
2. 不下载第二分片，不改用更有利的分片。下载失败可从同一 URL/etag 恢复，但不能
   更换 revision 或文件；
3. 单分片只做流式 CPU 审计：schema、C++ 路径、40-hex commit、逐样本 permissive
   license、old/new 非空且不同、2～200 changed logical lines、bug-fix 关键词分层、
   评测仓库 denylist、现有 CommitPackFT payload/commit/path 去重；
4. 输出原始计数、拒绝原因、仓库/sampling-family 容量、split/cap 后上界、长代码、
   长 prompt、complex/structural edit 供给及稳定身份哈希；不输出源码正文或训练
   JSONL；
5. CommitPack 是单一新来源，受 70% 上限约束，最多只能贡献 train/validation
   `1,400/140` 条。现有安全增量为 `260/131`，GitHub 路线贡献为 0，因此即使
   CommitPack 通过，本轮 train 仍至少缺 340 条独立来源数据。单分片只有在全部
   静态门后能支撑其允许份额，并达到 train/validation 至少 `100/20` 个新仓库与
   `700/70` 个 sampling family，才另立固定 repository/commit 执行 pilot；同时继续
   寻找独立第四来源。CommitPack 字段和关键词不能替代真实 buggy-fail/fixed-pass；
6. 若单分片容量不足、逐样本 license 不可靠、仓库身份不可规范化或与现有/评测集
   污染无法排除，则关闭 CommitPack 路线，不追加 364 个分片。

## 资源与边界

- 下载与审计使用 CPU/网络，不申请 GPU；
- 原始 524 MB JSONL 仅保存在 `/mingli01/data`，不进入 Git；
- 审计不得读取 formal/confirmation/external 的 gold、源码、补丁或测试，只消费已
  冻结的身份 denylist/manifest；
- 该激活修订 ADR-0018 的启动条件，但不修改其上游 revision、单分片、许可证、去重、
  污染和执行硬门。
