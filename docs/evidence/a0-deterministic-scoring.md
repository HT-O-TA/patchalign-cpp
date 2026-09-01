# A0 确定性评分 fixture 证据

日期：2026-09-01

## 范围

本证据使用仓库内完全自建的微型 C++ fixture，不使用模型、正式数据或 GPU。它验证严格 unified diff 解析、路径策略、`git apply --recount`、编译、三阶段测试、终止分类、固定分母汇总和重复评分确定性。

它不验证 OCI/Slurm 沙箱、不可信第三方构建、正式执行结果 Schema、sanitizer 或真实数据可重放性。

## 固定输入

- 实现提交：`c000f775071f7632f81edc5103455dfe93d271c2`；
- fixture base commit：`d68a0718b4a066cb319e89efc21e5c2af9d1d093`；
- sample：`tests/fixtures/scoring/sample.json`；
- prediction：`tests/fixtures/scoring/prediction.success.json`；
- 成功评分 SHA256：`sha256:199e2f57b505a9dd148bf9c57c219c8bd952ee90a2c7a74d44ed96b3a6a98dc0`。

成功 prediction 故意把 hunk header 的行数计数写错。测试证明普通 `git apply --check` 拒绝该 patch，而 `git apply --recount --check` 接受；删除行和新增行之外没有被评分器修复或重写。

## 覆盖结果

fixture 覆盖并断言以下 terminal classification：

```text
generation_failed
parse_failed
policy_violation
apply_failed
build_failed
public_test_failed
hidden_test_failed
regression_failed
success
```

同时验证：

- buggy revision 的 public/hidden 失败、regression 通过；
- 多文件、绝对/逃逸/未允许路径和二进制 patch 被拒绝；
- Markdown 围栏、解释前缀和畸形 hunk 被严格拒绝；
- 上游失败后所有下游阶段为 `not_run`；
- build 超时被记录，进程组被终止，下游测试不运行；
- Hidden-test Pass@1 只计算最终完整 `success`，不是单独 hidden 阶段通过；
- 同一 prediction 两次评分记录和汇总完全相同。

## 集群验收

环境：

```text
Python 3.10.20
Git 2.34.1
g++ 11.4.0
PYTHONNOUSERSITE=1
Conda prefix=/mingli01/project/ht/.conda_envs/patchalign-cpp
```

结果：

```text
全量 pytest 首轮：53 passed in 5.51s
全量 pytest复跑：53 passed in 5.23s
评分专项复跑：12 passed in 4.92s
```

测试没有提交 Slurm 作业，没有使用 GPU，没有修改模型或数据目录；每次评分使用临时 clone，结束后集群 Git 工作树保持干净。
