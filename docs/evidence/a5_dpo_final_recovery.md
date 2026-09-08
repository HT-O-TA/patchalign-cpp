# A5 DPO 最终评测恢复证据

本文记录 A5 一次性最终评测中的两次基础设施恢复。它们不改变模型、数据、prompt、生成参数、评分
协议、固定分母或质量门禁；最终模型结论只取自动聚合产物。

## 1. 推理 array 被共享账号取消

- 原推理 array：`97586`；formal、confirmation、Defects4C 分别原子保存 118/112/84 条预测。
- 三个 task 在同一秒显示 `CANCELLED by 1039`，下游 `97589`～`97591` 随依赖取消。
- 远端登录用户 UID 同为 1039；作业没有 Python traceback、OOM、time limit 或节点故障证据，因此归类为
  共享账号主动取消，而不是模型或代码失败。
- 恢复 array `97608` 继续消费原 state/partial，不覆盖已保存预测。最终三套推理均达到固定分母，全部
  generation status 为 `ok` 且 3/3 determinism probe 稳定。

## 2. Defects4C 评分 role 白名单断层

### 现象

- 原评分 array：`97614`。
- 8 个在 strict parse/path policy 阶段终止的案例正常保存 checkpoint；其余 168 个需要进入 rootfs 的
  task 在 0～2 秒内以 exit 1 结束。
- 聚合作业 `97615` 因 `DependencyNeverSatisfied` 无法运行。

失败日志的确定性错误为：

```text
run_defects4c_prediction_case.py: error: argument --role: invalid choice:
'dpo_beta03' (choose from 'm0', 'm1_r2')
```

### 根因

外层 `score_a5_dpo_defects4c_case.py` 已使用冻结候选角色 `dpo_beta03`，但 Bubblewrap 内调用的历史
`run_defects4c_prediction_case.py` 仍把 argparse role 白名单限制为 `m0/m1_r2`。早期 parse/policy
失败不进入 rootfs，所以恰有 8 条成功落盘；这一对照也证明错误发生在执行边界，而非预测读取或补丁解析。

### 修正与验证

- 只把 rootfs runner 的显式白名单扩展为 `("m0", "m1_r2", "dpo_beta03")`；没有接受任意字符串。
- 新增单元测试固定这三个允许角色。
- 为避免把后续交付文档混入评测身份，集群从原评测提交
  `80eeed7eb9adacef858e7688635ea85bccb1da26` 建立 `a5-eval-recovery-97614` 分支，只 cherry-pick
  角色修复，形成恢复提交 `fbe0717be11ca55648cd4d9d69c22c0fa707471c`。
- 恢复提交在项目 Conda 环境中完成全仓 `435 passed in 28.38s`。
- 替换评分 array 为 `97901`，聚合作业为 `97902`。评分器对已存在 checkpoint 做完整 identity 比较后
  直接复用，因此 8 条有效结果不会重复改写；168 条缺失结果按原索引执行。

## 3. 结果解释边界

- 两次恢复都没有删除失败样本、改变 timeout、放宽 rootfs、修改补丁或更换节点以挑选结果。
- GPU 推理只通过原子 checkpoint 恢复一次；Defects4C 替换链只重做缺失 CPU 执行评分。
- 原 `97614` 的秒退不能计为 168 个模型 failure，也不能进入 Pass 分母；只有替换数组形成的 176 个
  身份完整 checkpoint 才能被最终聚合器消费。
- 这次故障说明：新增模型角色不仅要在外层配置和 scorer 中声明，还必须穿透沙箱内 CLI、文件标签和
  聚合器；未来增加 role 时应以端到端参数化测试覆盖这一接口，而不是只测试外层 Python 调用。
