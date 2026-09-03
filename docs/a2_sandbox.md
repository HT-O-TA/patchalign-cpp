# A2 安全执行与真实重放

## 当前状态

A2 已拆分为安全的数据构造阶段 A2a 和不可信代码执行阶段 A2b。A2a 不依赖沙箱；A2b 必须先通过计算节点上的 Bubblewrap 自检，随后才允许编译或运行 holdout C++。

2026-09-03 已在计算节点通过 rootless Bubblewrap 最小边界自检，但尚未生成正式 A2 holdout，也尚未运行 70 个真实案例。因此 A2 门禁仍未关闭，不能进入正式训练或报告模型质量。

## A2a：holdout 构造

`scripts/data/build_a2_holdout.py` 从 A1 使用的 RunBugRun C++ 原始数据读取记录，排除 A1 pilot 已出现的全部 `problem_id`，要求至少 5 个测试、源文件不超过 256 行、修改逻辑行数为 1–40，并用稳定 SHA256 顺序抽取：

- function：50 个；
- file-window：20 个；
- 每个问题只保留一个可用记录；
- 测试按稳定顺序分为 regression、public、hidden。

该 holdout 只用于 A2 执行闭环，不进入 SFT/DPO 训练数据。A2a 是 CPU 数据任务，不编译或运行来源代码：

```bash
sbatch slurm/a2_holdout.sbatch
```

输出目录：

```text
/mingli01/data/patchalign-cpp/a2/holdout-v1/
```

作业拒绝覆盖已存在的 holdout，成功时生成 manifest、报告和 SHA256。

## A2b：沙箱执行

A2b 使用项目自带、非 setuid 的 Bubblewrap v0.12.0：

```text
/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
```

上游 tag 为 `v0.12.0`，源码 commit 为 `2a76602a8c71f36c1527cf9fc3417d9149822e0c`，当前安装二进制 SHA256 为：

```text
c69d2514ecdcbb927af4129caccceb8bfc122954e59ab8aa6f9ec50e9a09afda
```

构建依赖位于独立 `.tools` 前缀，不修改项目 Conda 环境。A2b 每次启动必须先运行 `scripts/data/check_a2_sandbox.py`，确认：

- 使用独立 user、PID、IPC、UTS 和 network namespace；
- 网络空间仅有 loopback；
- `/home` 和 `/mingli01` 不可见；
- 不再使用 `--ro-bind / /`；
- 系统工具目录只读；
- `/tmp` 是独立 tmpfs；
- 只有单案例临时 `/work` 可写。

每个版本在独立临时目录编译，每条测试再复制到新的临时目录执行，避免测试间互相修改。命令设置 wall/CPU timeout、地址空间、输出文件、文件描述符和 core dump 限制；原始 stdout/stderr 不写入结果 JSON，只保存截断后的错误尾部、字节数和 SHA256。

提交 A2b：

```bash
sbatch slurm/a2_sandbox.sbatch
```

结果写入：

```text
/mingli01/data/patchalign-cpp/a2/execution-results.jsonl
```

每条结果写入前使用 `schemas/a2-execution-v0.1.schema.json` 校验。当前 Schema 明确标记为 draft，并显式记录 `sanitizer_applicable`；本批 RunBugRun 回放暂记为 `false / not_applicable`。Schema 未冻结前不得生成正式评测报告。

## 已验证证据

- Job `93569`、`93575`：旧脚本因计算节点缺少系统 `bwrap` 静默失败，没有执行 C++；
- Job `93602`：确认 `gpu28` 上项目 Python、仓库、RAW、PILOT 均可用，系统 `bwrap` 缺失；
- Job `93603`：确认组合 user+network namespace 可用，单独 network namespace 无权限；
- Job `93620`：因计算节点不可见管理节点 `/tmp` 而未进入自检；
- Job `93621`：在 `gpu22` 完成 rootless Bubblewrap 自检，全部七项检查通过；未运行数据集代码。
- Job `93628`：在 `gpu28` 完成升级自检，九项检查通过，包括受控 C++ 的沙箱内编译和执行；未运行数据集代码。
- Job `93629`：A2a 在 `gpu28` 因批处理 shell 没有 `module` 函数而于数据构造前失败；A2 脚本随后删除不必要的 module/conda.sh 依赖，继续使用绝对 prefix。

诊断证据位于：

```text
/mingli01/project/ht/patchalign-cpp/artifacts/a2-diagnostics/
```

## A2 关闭条件

关闭 A2 前仍须记录：A2a/A2b Slurm Job ID、作业节点、Git commit、`holdout-report.json`、holdout manifest SHA256、执行结果 JSONL SHA256、Bubblewrap 构建来源与自检结果，以及 buggy/fixed 的编译、regression、public、hidden 汇总。

若自检失败、网络或文件系统隔离无法证明、输出不符合 Draft Schema，或 fixed 无法通过 regression，A2 保持未完成。
