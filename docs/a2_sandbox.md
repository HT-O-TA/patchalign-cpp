# A2 安全执行与真实重放

## A2 终态

A2 可执行 pilot 已于 2026-09-03 完成。最终证据使用 `a2-holdout-v3` 和 `execution-results-v3.jsonl`：50 个 function、20 个 file-window 案例均通过双资格回放和第三次独立重放；buggy/fixed 编译、测试分区、输出匹配、失败分类、确定性和最小权限沙箱闭环均已验证。

这只关闭 A2 的安全执行与 70 条真实数据 pilot 门禁，不自动代表 Base/SFT/DPO 模型质量；后续阶段现状见[项目状态](status.md)。

## 三段式流程

### A2a：候选池构造

`scripts/data/build_a2_holdout.py` 从 RunBugRun v0.0.1 C++ 数据读取记录，排除 A1 pilot 出现过的全部 `problem_id`，要求至少 5 个测试、源文件不超过 256 行、估计输入不超过 4,096 tokens、修改逻辑行数为 1–40，并按稳定 SHA256 排序。A2a 不编译或运行来源代码。

最终候选池为：

```text
/mingli01/data/patchalign-cpp/a2/candidates-v3/
```

包含 120 个 function 和 60 个 file-window 结构候选。Job `93646` 在 `gpu25` 完成，耗时 11 秒，未申请或使用 GPU 计算。

### A2b-qualification：真实资格回放与分区

每个候选在 Bubblewrap 中编译并执行全部测试。只有同时满足以下条件才可入选：

- buggy 和 fixed 都能编译；
- fixed 通过全部测试；
- 至少 2 个测试属于 `F = buggy 失败且 fixed 通过`；
- 至少 3 个测试在 buggy 和 fixed 上都通过；
- 初次合格后再完整回放一次；除耗时外，编译状态、退出状态、matched、stdout/stderr 长度和 SHA256 必须完全一致；
- sanitizer 必须显式标记；本批均为 `false / not_applicable`。

分区规则严格落实 ADR-0003：`F` 按候选内既定稳定测试顺序取 `ceil(20%)`、至少 1 条且为 hidden 保留至少 1 条作为 public；其余 `F` 为 hidden；buggy/fixed 都通过的测试为 regression。所有原始测试恰好进入一个分区。

最终共评估 114 个候选，选入 70 个；拒绝计数为：

```text
fewer_than_three_regression_passes  28
fewer_than_two_target_failures      14
fixed_test_failed                    3
nondeterministic_replay              1
```

非确定性案例 `rbr-a2-0023-093886e490419db0` / `p02971` 的 buggy 版本读取未初始化的 `rightMax[i]`；不同回放 stdout 哈希大面积变化。它被显式记录并排除，未进入最终 70 条。

冻结 holdout：

```text
/mingli01/data/patchalign-cpp/a2/holdout-v3/
```

### A2b-final：冻结集合独立重放

资格筛选完成后，`scripts/data/run_a2_cases.py` 对冻结的 70 条再执行一次。`scripts/data/check_a2_replay_stability.py` 忽略耗时和 suite 标签，仅按 test_id 比较资格结果与最终结果的编译/运行状态、matched、长度、截断标记和 stdout/stderr SHA256；70/70 完全一致。

最终结果与汇总：

```text
/mingli01/data/patchalign-cpp/a2/execution-results-v3.jsonl
/mingli01/data/patchalign-cpp/a2/execution-summary-v3.json
```

## 输出匹配语义

旧 v1 使用 `stdout.strip()` 精确比较，错误拒绝了仅浮点显示精度不同的 accepted submission。Job `93632` 的代表样本诊断确认 10 个案例仅是数值打印位数差异，1 个案例为真实运行异常。

v3 使用 `scripts/data/a2_output_matcher.py`，语义固定到 RunBugRun v0.0.1 对应的官方 legacy commit `5c023d6273ced705a5f83063b6b4cbf67aa81fa5`：保持行结构和非数值 token 严格相等；数值 token 默认按绝对误差 `1e-4` 比较，并应用官方 problem_id 特例阈值。来源：<https://github.com/giganticode/run_bug_run/blob/5c023d6273ced705a5f83063b6b4cbf67aa81fa5/lib/run_bug_run/submission_output_matcher.rb>。

全部 70 条结果均记录 matcher version `runbugrun-legacy-5c023d62`，并通过 `schemas/a2-execution-v0.2.schema.json` 校验。该 Schema 的 `0.2.0-draft` 内容与哈希作为 A2 pilot 冻结证据；正式评测发布前仍需另行提升为 production schema，不静默改写本批结果。

## Bubblewrap 边界

A2 使用项目自带、非 setuid 的 Bubblewrap v0.12.0：

```text
/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
```

- 上游源码 commit：`2a76602a8c71f36c1527cf9fc3417d9149822e0c`；
- 二进制 SHA256：`c69d2514ecdcbb927af4129caccceb8bfc122954e59ab8aa6f9ec50e9a09afda`；
- 独立 user、PID、IPC、UTS 和 network namespace；
- 网络空间只有 loopback；
- `/home`、`/mingli01` 和宿主根目录不映射；
- `/usr`、`/bin`、`/lib*` 只读，`/tmp` 为私有 tmpfs；
- 只有单案例临时 `/work` 可写；
- 每个版本独立编译，每条测试使用新的临时工作区；
- wall/CPU、地址空间、输出、文件描述符和 core dump 均有限制；原始 stdout/stderr 不写入结果，只保留哈希、长度、截断标记和有限错误尾部。

每次 A2b 都先运行九项自检。最终 Job `93650` 的九项边界与受控 C++ 编译/执行检查全部通过。

## 最终结果

Job `93650` 在 `gpu25` 完成，状态 `COMPLETED 0:0`，耗时 `00:30:05`，MaxRSS `216292K`；脚本未请求 GPU。

```text
case count                         70
function / file-window             50 / 20
buggy compile pass                 70 / 70
fixed compile pass                 70 / 70
buggy target failures observed     70 / 70
fixed all tests matched            70 / 70
partition contract satisfied       70 / 70
qualification/final exact stable   70 / 70
timeouts / truncations              0 / 0
regression tests                  4470  (buggy/fixed 均通过)
public target tests                518  (buggy 全失败、fixed 全通过)
hidden target tests               1931  (buggy 全失败、fixed 全通过)
```

关键 SHA256：

```text
candidate-v3 manifest       5fe077acd96ed6c6da13b2da144a3071c6b42731c9387f9bba3ca1755aeae930
candidate-v3 report         72a3f09b708bb131f19d97f0d8fcf5c9942ba3bbe6b1a8551a59537501a2c31d
candidate-v3 checksum file  a9ea161fb563b5266f135bdd94131276b9a964f8a2c9c40ca45ae501f19a1319
holdout-v3 manifest         10930b2dc915606b8ad17e15bb61c34919d8fc74f755d55e4c0b885899b28305
qualification report        addb1df9db26b62f999a29e762f1b9af845048b337488b838bea82caebf790e7
qualification results       7383c8fe0af13423a7f7339407bed859348b034b381845e2ffb0459914563150
holdout checksum file        ee75e1bcd076fa636678b95a86d5906548b63af7bead5dfe55f22139242e37a8
final execution results      0742cfea8a93c6fe9c2a72d6eeeb3ddf0a781fce24ad6494a39db9139c4bba95
final execution summary      f96c6d3730c2403e0ebacd9819737ecc2a6524bdc28f1b2b60b7cb3f54798b4b
```

运行代码 commit：`8843963a03c25154d74120f921c9b1507d44b63a`。最终自动稳定性检查补入后续可复用 Slurm 入口；其结果已在同一 v3 artifact 上独立验证为 `{"cases": 70, "stable": true}`。

## 历史失败的用途

- Jobs `93569`、`93575`：定位系统 `bwrap` 缺失和旧脚本静默退出；未执行数据集 C++；
- Jobs `93621`、`93628`：建立并升级 rootless Bubblewrap 自检；
- Job `93629`：定位 batch shell 无 `module` 函数；
- Jobs `93630`、`93631`：完成 v1 构造/执行并暴露错误的精确字符串匹配与执行前分区；
- Job `93632`：代表样本重放，区分浮点格式误报和真实异常；
- Job `93639`：取消；发现资格阶段可能对慢候选重复等待，未生成正式产物；
- Job `93645`：fail-closed；75+30 候选不足以填满 50+20，未生成正式产物；
- Job `93647`：完成 v2，但第三次回放发现 p02971 未定义行为导致 69/70 分区稳定；v2 保留为诊断，不用于正式统计；
- Job `93650`：v3 最终成功证据。

## A2 结论与边界

A2 安全执行与真实 70 条评分闭环已关闭。本次 A2 数据构造、资格和重放均未申请 GPU；A2 结果不得外推为正式 500 条评测或模型训练质量，后续结果必须引用各自的冻结数据和 artifact。
