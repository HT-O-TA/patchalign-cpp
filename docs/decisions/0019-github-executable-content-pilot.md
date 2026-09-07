# ADR-0019：GitHub 可执行内容 pilot 的安全重建提案

- 状态：Proposed；仅在 ADR-0017 detail outcome gate 通过后激活
- 日期：2026-09-07

## 背景

ADR-0017 只允许取得 PR、issue 与许可证的最小 metadata。即使 200 条固定
detail 分母通过，也尚未证明任意 GitHub C++ 仓库能在本项目环境中重建。

A2 的短程序 runner 可以复用网络隔离、资源限制、测试分区和稳定重放语义；
Defects4C 的下载、逐例 checkpoint 与 Slurm array 结构也可以复用。但
Defects4C 的资格率依赖上游数据集提供的逐项目 build/test 模板，不能把这些模板
误称为任意 GitHub 仓库的通用执行器。

## 激活与固定分母

1. 只有 detail `summary.json` 的 `execution_content_pilot_authorized=true`，且
   summary、qualified metadata 与 run manifest 的 Job、commit、配置及 SHA256
   全部写入新机器配置，才允许激活本 ADR；
2. 从 detail 合格记录按 split、仓库轮询和既有 seed 固定 50 条：train 40、
   validation 10；先每仓库 1 条，再取第 2 条；
3. 固定分母后不以构建成功与否替换候选。404、仓库删除、依赖缺失、无测试、
   timeout 和不支持的 build system 都进入拒绝统计；
4. 至少 10/50 通过完整双资格和独立稳定重放，才允许扩大内容取得。低于 20%
   时关闭当前 GitHub 训练路线，不降低门槛、不换样本补考。

## commit 对与变更身份

GitHub 官方说明，合并后的 `merge_commit_sha` 在 merge commit、squash 与 rebase
三种方式下语义不同。因此内容 pilot 不信任 PR detail 中的 `base.sha` 能单独证明
buggy parent。

每条固定候选必须：

1. 取得 `merge_commit_sha` 对应 commit 及 parent 列表、PR commits 清单和完整 PR
   files 清单；详情门已限制最多 10 个文件，因此 files 必须在单页内完整返回；
2. 网络阶段只 fetch 固定 commit/parent/submodule 对象；执行阶段完全断网；
3. 以本地 Git 图导出候选 parent→fixed diff，并与 PR files 的路径、状态、增删行
   和总统计交叉核验；无法证明完整对应关系的 merge/rebase/squash 情形拒绝；
4. `fix_commit_sha` 与 `parent_commit_sha` 必须是 40-hex 且可由 `git cat-file`
   验证；仓库、commit、target path 与 payload 同时进入跨来源去重；
5. 分别在 parent/fixed commit 核验 LICENSE 路径、SPDX 与内容 SHA256。只看当前
   默认分支许可证不足以准入历史代码。

官方依据：

- [GitHub pull request REST 文档](https://docs.github.com/en/rest/pulls/pulls)：
  说明 `merge_commit_sha` 在三种合并方式下的不同含义，并提供 PR commits/files；
- [GitHub license REST 文档](https://docs.github.com/en/rest/licenses/licenses)：
  license 查询支持固定 Git `ref`。

## 文件与任务范围

- 必须同时存在至少一个生产 C++ target 和测试变更；生产扩展名固定为 `.cc`、
  `.cpp`、`.cxx`、`.h`、`.hh`、`.hpp`、`.hxx`；
- v1 只接受单一生产 target，默认构造 function 任务；无法可靠定位单函数边界时
  才按 Schema 构造固定 file-window；
- 测试路径只接受冻结的 path-component 规则，例如 `test/tests/testing/spec/specs`；
  仅凭文件名含 `test`、PR 文本或 issue 文本不能证明测试；
- buggy 工作树只允许叠加从 parent→fixed diff 中机械提取的测试变更。测试目录
  内的构建文件可以直接包含；目录外 build manifest 只有在逐 hunk 静态检查与
  独立 audit 共同证明它只注册测试 target/path、未改变生产 target、编译选项或
  依赖时，才可进入 `test_registration_delta`。不得人工改写补丁；
- 无法安全分离测试与生产修改时拒绝，不能把完整 gold fix 混入 buggy；
- fixed 与 buggy+test-delta 都必须成功配置和编译；编译失败不冒充测试失败。

## 受限构建 profile

自动默认 profile 为版本化的 `cmake_ctest_out_of_tree_v1`：

```text
cmake -S . -B build -G Ninja -DBUILD_TESTING=ON
cmake --build build --parallel <fixed_cpu_count>
ctest --test-dir build --output-on-failure
```

固定 50 条选择形成后，可以为其中仓库建立显式、版本化且人工可审计的 declarative
profile，例如 Meson/Ninja、Bazel 或 Make 的标准测试入口；这不改变固定分母。每个
profile 必须绑定检测文件、工具哈希、完整 argv、环境白名单和资源上限。禁止从
README/CI 日志中直接复制 shell 字符串执行，也禁止通过 profile 修改源码或测试。

- 所有 profile 在只读 rootfs、断网 Bubblewrap、无 capability、独立可写 checkout
  中执行；仓库构建代码不得在登录节点或宿主环境运行；
- 不自动执行 README、workflow、curl、包管理器或任意安装脚本；构建若试图联网
  获取依赖，因断网失败并记录 `offline_dependency_missing`；
- 未被版本化 profile 覆盖的 build system 记为固定候选拒绝，不能临时猜命令；
- 每例固定 CPU、内存、文件输出与 wall-time，build 目录在记录结果后删除，源码
  checkout 和日志保留集群本地且不进入 Git。

## 双资格、分区与稳定性

1. fixed 必须全量测试通过；
2. buggy+test-delta 必须编译成功，且至少 2 个确定性测试呈现 buggy fail / fixed
   pass；至少 3 个测试在 buggy/fixed 均通过作为 regression；
3. 目标测试按稳定 ID 排序，`ceil(20%)`、至少 1 条进入 public，且至少保留 1 条
   hidden；其余双通过测试进入 regression，所有原始测试恰好进入一个分区；
4. 新工作树中再独立运行一次，测试集合、分区、退出状态和规范化输出哈希必须
   一致；timeout、flaky、sanitizer-only 或基础设施错误都不能计入资格分子；
5. sanitizer 仍只在仓库/样本明确适用且机器配置声明时执行。

## 输出与停止线

训练样本冻结前只输出 source plan、逐例资格 checkpoint、拒绝原因、测试身份与
哈希、聚合和 run manifest。仓库源码、patch、测试正文、构建目录和完整日志均为
集群本地 artifact；不得进入 Git 或 prompt。10/50 通过只授权下一轮容量构建，
不等于 Data-v2 已达到 2,000/200，也不授权 GPU、SFT 或 DPO。
