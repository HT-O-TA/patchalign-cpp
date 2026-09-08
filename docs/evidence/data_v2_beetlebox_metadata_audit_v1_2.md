# BeetleBox C++ 元数据审计 v1.2 结果

> 证据日期：2026-09-08。最终 Job `97508` 已完成；BeetleBox 因仓库多样性与
> validation 容量失败而关闭，不进入许可证、源码、训练或 GPU 阶段。

## 运行身份

- Git commit：`7c81153`；
- Slurm Job：`97508`，`COMPLETED 0:0`，用时 25 秒；
- 全仓测试：`417 passed in 20.09s`；
- 数据 revision：`ac12f9cd8afac9095498ff69cafe45ce8747b4ef`；
- train/test Parquet SHA256：`976a51ba...dc09` / `a0b257e7...b9d2`；
- 两个文件总行数：10,191 / 10,445。

Job `97502` 因集群 HTTPS 零字节停滞取消；相同文件经本机临时下载、双端验哈希和
原子传输落入集群，本机临时文件已删除。Job `97503`、`97505` 分别保留数据卡语言
计数硬身份错误和展示值 `C++`/存储值 `c++` 映射错误；它们不参与最终容量结论。

## 数据卡漂移

固定文件实际 `language="c++"` 数为 train 3,317、test 3,865；数据卡表格声明为
3,868/4,783。其 frontmatter 总行数为 20,636，但语言表五类合计 26,321。v1.2
同时报告两个口径，以文件 SHA、总行数、实际列值和实际计数作为运行身份。

## 最终筛选结果

在只读取非正文列并要求 repo/URL、before/after SHA、issue/PR URL、C++ 修改文件和
评测 denylist 后，接受 3,534 条元数据，但只来自 4 个非评测仓库：

| 项目 | train native | test native | 合计 |
|---|---:|---:|---:|
| 实际 C++ 行 | 3,317 | 3,865 | 7,182 |
| 元数据合格 | 2,633 | 901 | 3,534 |
| 合格仓库 | 2 | 2 | 4 |

拒绝计数：无 C++ 修改文件 2,065；重复 identity/commit pair 1,208；命中现有评测
denylist 375。native train/test 的合格仓库零交叉，但 native split 不直接用作训练
split。

按 seed `20260908` 重新做 repository split 后，4 个仓库全部落入 train；在每仓库
40/20 cap 后为 train 160 / validation 0。相对预注册门：

| split | 实际样本 / 目标 | 实际仓库 / 目标 | 结果 |
|---|---:|---:|---|
| train | 160 / 400 | 4 / 15 | 失败 |
| validation | 0 / 50 | 0 / 4 | 失败 |

因此 `historical_license_pilot_authorized=false`，不允许通过改 seed、复用 native split、
提高 cap 或把同仓库 issue 当成仓库多样性来补考。

## Artifact 哈希

- `summary.json`：`0f1e739a3f7252c26f5366f4feb31b93cd157ee648723c8b154e5e5598c1e3af`；
- `run-manifest.json`：`8fe3dc55d272a282b8ebb9facc0345912eca0bca030810f584e4fee07d9143b8`；
- candidate identity set：`44fabf72f76ffe27d7741475c19c910ba1c04c85f64ed981861efccae58e6965`。

Artifact 不含 title/body、URL、仓库名、源码、patch 或测试内容。
