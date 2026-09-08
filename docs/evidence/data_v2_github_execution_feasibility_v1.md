# GitHub execution feasibility v1 结果

> 证据日期：2026-09-08。固定 20 条内容与静态资格 Job `97292` 已完成；0/20 可进入
> 断网执行，故当前 GitHub broad-discovery 路线关闭。没有运行第三方构建，没有 GPU。

Job `97292` 在提交 `bda0c133fc03268ad860927e937e1066b4291315` 上完成
`405 passed in 16.12s`，总用时 `01:29:07`。固定分母为 20 条/20 个仓库，train/
validation 16/4，各 split 内有/无 bug 标签平衡，失败后没有换样本。

每条依次核验 merge commit、PR commit 列表、PR files、parent/fixed 历史许可证，再
只 fetch 固定两个 Git 对象并检查本地 diff。共发出 88 次无 token API 请求、完成
8 次 Git fetch，集群本地 Git 对象约 160 MiB；raw API response、许可证正文、patch
或源码均未进入 Git。

## 固定拒绝分布

| 原因 | 数量 |
|---|---:|
| parent 历史许可证不在 permissive allowlist | 11 |
| 根目录缺少 CMakeLists.txt | 4 |
| 生产 C++ target 数量不等于 1 | 2 |
| parent 历史许可证 API 404 | 1 |
| 仓库含 submodule，当前 profile 不支持 | 1 |
| PR 没有测试路径变更 | 1 |

静态执行候选为 0，严格低于 4/20，所以 `offline_execution_array_authorized=false`。
这不是编译失败，也不能解读为模型失败；它证明当前 broad repository→PR 分布与
permissive 历史许可、单生产目标、测试变更、CMake/CTest 可重放 profile 的交集为零。

正式 artifact 位于
`artifacts/data-v2/github-executable-evidence-v2/feasibility-content-v1/`：

- content plan：空文件 SHA256 `e3b0c442...b855`；
- decisions：`6e57452a...fbe0`；
- summary：`6f35cf92...aaac`；
- run manifest：`83548db9...e3de`。

本结果关闭 ADR-0021 当前路线，不通过扩展许可证、换样本或放松测试证据补考。后续
先执行 ADR-0022 激活的 CommitPack 单分片 CPU 供给审计；只有它在许可、仓库隔离、
去重和配额后显示足够容量，才值得另立小型 repository/test 重建 pilot。
