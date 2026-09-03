# A2 安全执行与真实重放

## 当前状态

A2 的 holdout 构造器、执行器和 Slurm 入口已实现并提交到 GitHub；A2 尚未因代码存在而自动视为完成。必须在集群计算节点确认 bubblewrap 可用、禁网和非特权隔离有效，并保存真实执行结果后，才能关闭 A2 门禁。

实现提交：`9623d58`。

## 输入与抽样

`scripts/data/build_a2_holdout.py` 从 A1 使用的 RunBugRun C++ 原始数据读取记录，排除 A1 pilot 已出现的全部 `problem_id`，要求至少 5 个测试、源文件不超过 256 行、修改逻辑行数为 1–40，并用稳定 SHA256 顺序抽取：

- function：50 个；
- file-window：20 个；
- 每个问题只保留一个可用记录；
- 测试按稳定顺序分为 regression、public、hidden。

该 holdout 只用于 A2 执行闭环，不进入 SFT/DPO 训练数据。

## 集群运行

先同步 GitHub 工作副本，并确认工作树干净：

```bash
cd /mingli01/project/ht/patchalign-cpp
git fetch origin
git merge --ff-only origin/main
git rev-parse HEAD
```

提交作业：

```bash
sbatch slurm/a2_sandbox.sbatch
```

作业会在 `/mingli01/data/patchalign-cpp/a2/holdout-v1/` 构造 holdout，并将逐案例执行结果写入：

```text
/mingli01/data/patchalign-cpp/a2/execution-results.jsonl
```

脚本在缺少 `bwrap` 时立即失败，不执行任何不可信 C++。每次编译和运行均在 `bwrap --unshare-net` 环境中完成，并设置超时；作业使用 CPU，不申请 GPU，降低 Slurm QOS 内存压力。

## A2 验收证据

关闭 A2 前必须记录：Slurm Job ID、作业节点、Git commit、`holdout-report.json`、holdout manifest SHA256、执行结果 JSONL SHA256、bubblewrap 版本/隔离检查，以及 buggy/fixed 的编译、regression、public、hidden 汇总。若 bubblewrap 不可用、网络隔离无法证明、fixed 无法通过 regression，A2 保持未完成。
