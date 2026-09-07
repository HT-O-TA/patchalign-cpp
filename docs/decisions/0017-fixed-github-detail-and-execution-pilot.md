# ADR-0017：固定 GitHub 详情与可执行内容 pilot

- 状态：Accepted under delegated project decision authority
- 日期：2026-09-07

## 目的

容量 discovery 只能证明存在候选身份，不能证明 PR 是小而真实的 C++ bug fix、
许可证可接受、父提交可取得或测试可以重放。本 pilot 用固定分母量化这些损耗，
在大规模下载和训练前尽早停止低质量路线。

## 固定详情分母与抽样

1. 输入只允许是通过容量门的 v2.1 `candidates.jsonl`、`summary.json` 和
   `run-manifest.json`，三者须写死 SHA256 与 Job/commit 身份；
2. 固定选择 200 个 PR：train 160、validation 40；
3. 每个 split 先按契约哈希顺序遍历仓库各取 1 条，再进行第 2 轮；每仓库最多
   2 条。train/validation 至少覆盖 100/20 个仓库，仓库 split 不变；
4. PR 在仓库内按 `sha256(seed NUL candidate_id)` 排序。选择与 API 返回顺序无关；
5. 任一候选命中 ADR-0014 denylist、身份重复或输入 manifest 漂移即 fail closed。

## 详情门

按下列顺序请求，前一门失败后不发后续请求：

1. PR detail：核验同一 canonical 仓库和 PR 号、已合并、base/head/merge commit、
   主语言 C++、非 fork/archived、changed files 1～10、changed lines 2～200；
2. 从 PR body 只在内存提取最多 1 个 `fixes/closes/resolves` 的同仓库 issue 号；
   body、title、用户、label 原文均不落盘；
3. issue detail：必须是 issue 而非 PR，并包含 token 化后的 bug/bugs/bugfix/defect/
   defects 标签；只保存判断结果、issue 号和响应哈希；
4. 每仓库最多请求一次 LICENSE；SPDX 必须属于现有 permissive allowlist，许可证
   文本只在内存解码计算 SHA256，不保存原文；
5. 不调用 files/patch/blob/contents、Actions artifact 或仓库 clone 接口。本阶段仍
   不取得源代码、补丁和测试。

固定 200 条中至少 50 条通过详情门，且 train/validation 至少为 40/10、通过仓库
至少为 30/8，才允许建立 50 条可执行内容 pilot。否则关闭当前 GitHub 路线，不改
查询、改动规模、issue 或许可证条件。

## 请求预算与恢复

- 最坏请求数为 200 次 PR + 200 次 issue + 200 次按仓库缓存的 LICENSE = 600；
- 无令牌时每次 core 请求间隔至少 61 秒，理论上限约 10 小时 10 分；Slurm 时限
  12 小时；有令牌与否写入 manifest，但不改变样本或过滤条件；
- PR、issue、license 均使用 config/script/input hash 绑定的原子 checkpoint；
  瞬时 429/5xx 最多 3 次尝试，可在同提交恢复，不能无限重试；
- final artifact 禁止覆盖，保存固定选择、逐例门结果、聚合与运行 manifest；不保存
  raw response、正文、用户身份、patch/source 或评测 gold。

## 后续可执行内容 pilot

若详情门通过，从合格记录中继续用同一分层顺序固定 50 条（40/10）。只有此时才
为每条记录建立独立内容取得与沙箱协议，核验 commit/parent、C++ target、Schema、
去污染和逐仓库测试。buggy 必须稳定失败、fixed 必须稳定通过；可执行资格至少
10/50（20%）才继续扩容。timeout、基础设施失败和无测试不得计入资格分子。

详情或 50 条执行门通过都不等于 Data-v2 已冻结，也不授权 GPU、SFT 或 DPO。


## 激活证据

Job 96939 在提交 3dbdbb0c0e0ecd5b94ed476a506a713248d3db9c 上完成 250/250 个请求并通过全部容量门：train/validation 有候选仓库 143/29、PR 上界 6,565/1,156、cap 后样本上界 4,078/440，总候选 7,721。candidates、summary、run manifest SHA256 分别为 9af2a04b33bdf7b0e12419072904423754039ec5dda83c24cd19e18ad39d0493、6893c69ee78395fa08c193a1cc6d7cdadf50f4a9ec113cc207421f9848048dd1、9f1faede1218bc1d6ec19c66c68a12dc75fe734ee5b5b3b8c17cd21e7cb8e324。
