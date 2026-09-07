# ADR-0018：CommitPack C++ 有界第三来源审计

- 状态：Proposed；GitHub detail outcome gate 通过且第三来源缺口成立后再决定是否激活
- 日期：2026-09-07

## 背景

Data-v2.1 限制单一新来源最多占 70%。即使 GitHub 主路线合格，它对暂定
2,000/200 增量最多贡献 1,400/140；现有安全增量 train 只有 260 条，因此仍需
一个独立、可追溯的第三来源。RunBugRun v2 已因逐记录授权不明被 ADR-0015 排除。

CommitPack 官方数据卡说明每条记录提供 commit、old/new path、old/new contents、
subject/message、language、repository 和逐样本 license。它来源于 GitHub commit，
具有仓库与提交身份，但不发布可直接使用的测试命令，因此只能先作为供给候选。

## 固定上游身份与最小下载

- CommitPack revision：`5eee2c845bf88dbffcafedb6e80d2a72a43fe575`；
- `paths.json` SHA256：
  `3c269f7d51cfc1ca39a599afb2ed72f7eabbb9943beeb9d4b2f95ba9c097a2e3`；
- C++ 清单：365 个 JSONL 分片，Hub 页面总量约 191GB；
- 若激活，只允许下载按文件名升序的首分片
  `data/c++/c++-0001.jsonl`；大小 523,946,192 bytes，LFS SHA256
  `dfdd55f56f7be3bf4b8d2ccad8ea39910b4dd2c18ee296f5a991d134e57f367f`；
- 不允许根据首个分片结果追加或更换分片。若证据不足，应发布新 ADR，而不是在
  同一 pilot 中继续下载 191GB。

## 审计边界

单分片只做 CPU 供给审计：

1. 核验文件 SHA256，只输出计数、稳定身份哈希与拒绝原因；原 JSONL 保持集群本地，
   不进入 Git；
2. 只保留 C++ 路径、单仓库、合法 40-hex commit、allowlist license、old/new 都存在、
   内容不同、2～200 changed logical lines 的候选身份；
3. 用 subject/message 的通用 bug-fix 词形做供给分层，但不把关键词当成测试证据；
4. 应用 ADR-0014 仓库 denylist，并与 formal/confirmation problem identity 和现有
   CommitPackFT payload/commit/path 做精确去重；
5. 按 Data-v2.1 仓库 split、sampling-family×2 和 repository cap 报告 train/
   validation 最大供给、仓库数、长代码、长 prompt、复杂与结构性修改；
6. 不生成训练 JSONL，不申请 GPU，不宣称 executable。

## 后续硬门

只有单分片在去重、许可证和 cap 后仍能补足 GitHub+安全增量的明确缺口，才允许
固定一个小型仓库/commit 内容 pilot。每条仍须核验原仓库在对应 commit 的 LICENSE、
commit parent、目标 C++ 文件和真实测试；buggy 稳定失败、fixed 稳定通过才可计入
Data-v2。无法重建测试的 CommitPack 记录一律不用于训练。

## 官方依据

- CommitPack 数据卡：<https://huggingface.co/datasets/bigcode/commitpack>
- OctoPack 仓库：<https://github.com/bigcode-project/octopack>
- Hugging Face Dataset Viewer API：<https://huggingface.co/docs/dataset-viewer/quick_start>
