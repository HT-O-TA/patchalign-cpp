# CommitPack 固定单分片供给审计 v1.1 结果

> 证据日期：2026-09-08。Job `97486` 已完成；该结果关闭当前 CommitPack 路线，
> 不生成训练数据、不授权仓库执行、不申请 GPU。

## 运行身份

- Git commit：`d9d8ab6f927d6cb3b8912d8e21f87498124ae72c`；
- Slurm Job：`97486`，`COMPLETED 0:0`，用时 `00:00:25`；
- 全仓测试：`412 passed`；
- 上游 revision：`5eee2c845bf88dbffcafedb6e80d2a72a43fe575`；
- 固定文件：`data/c++/c++-0001.jsonl`，523,946,192 bytes；
- 固定输入 SHA256：`dfdd55f56f7be3bf4b8d2ccad8ea39910b4dd2c18ee296f5a991d134e57f367f`。

v1.1 只把记录语言值从错误的 builder 名 `c++` 修正为实际上游精确值 `C++`；
revision、分片、筛选、split、去重、cap 和阈值均未变化。Job `97473` 的 v1 空结果
继续保留为 Schema 映射失败证据，不参与本次容量判断。

## 固定结果

审计流式读取 6,291 条记录，cap 前有 253 条通过静态门；cap 后为 train 236、
validation 17。仓库 cap 没有额外拒绝。主要拒绝原因为：

| 原因 | 数量 |
|---|---:|
| 记录不能解析为唯一合法 GitHub 仓库 | 5,910 |
| 修改逻辑行数不在 2～200 | 64 |
| 许可证字段不在 allowlist | 39 |
| 命中冻结评测仓库 denylist | 11 |
| 缺少 old/new contents | 9 |
| 不是 C++ 路径 | 4 |
| 与 legacy payload 精确重复 | 1 |

cap 后分布：

| split | 样本 | 仓库 | 新仓库 | sampling family | function / file-window | 长代码 | 长 prompt | 结构修改 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| train | 236 | 200 | 187 | 236 | 119 / 117 | 179 | 154 | 76 |
| validation | 17 | 17 | 17 | 17 | 9 / 8 | 15 | 13 | 7 |

静态份额门要求 train `1,400 / 100 repos / 700 families`，validation
`140 / 20 repos / 70 families`。train 只有新仓库数通过，其余五项均失败，因此
`static_share_gate_passed=false`。

## 决策与算术

CommitPack 当前真实贡献与 legacy 安全增量合并后只有 train `496`、validation
`148`。相对暂定 `2,000/200` 容量探针，仍缺 train `1,504`、validation `52`；
这已经不是增加同源分片能够解决的独立来源和真实执行证据问题。

因此执行以下硬停止条件：

1. 不下载 CommitPack 第二分片；
2. 不为这 253 条静态候选启动仓库重建或执行 pilot；
3. 不生成 Data-v2 JSONL，不授权 SFT/DPO/GPU；
4. 保留固定原始分片与 v1/v1.1 artifact，下一步只调查真正独立、带可复现
   buggy-fail/fixed-pass 证据的来源；
5. `2,000/200` 原本是容量探针，不把它偷偷降成结果；若后续证明严格全量可执行
   不可实现，必须另立 ADR 明确修改 Data-v2 的证据分层和训练配额。

## Artifact 哈希

- `candidate-audit.jsonl`：`46d71ba9deac63752e17cf37a1a67111a58babcac4f8f5627f8c7dc1d78e7ba0`；
- `summary.json`：`b579ce807fc07612673bc74cb7f4725876c49a1aa2580f167cc3a8bc56719765`；
- `run-manifest.json`：`61631ab53ef3c3dd15adce7807a68f0853e75d7231ef25d40b8324755cdf4206`；
- candidate identity set：`de43e94f9d01290d5a4e33db5b3c06b770823c79cadb0be00777051c69e36fa4`。

这些 artifact 不包含源码正文。许可证字段、bug 关键词和静态 task-level 推断只能作为
供给信号，不能冒充历史许可证核验或真实执行证据。
