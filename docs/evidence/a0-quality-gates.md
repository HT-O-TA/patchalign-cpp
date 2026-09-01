# A0 任务契约与质量门禁证据

日期：2026-09-01

## 决策

- 用户接受完整第一版任务契约；
- sanitizer 只在 A2 执行配置显式标记适用的样本上执行；
- 用户接受 ADR-0004 的 SFT/DPO 最小提升、所有退化上限、paired bootstrap、固定分母和 validity veto；
- A3 pilot 只做方案选择，不作为正式质量结论。

## 机器证据

- 配置：`configs/evaluation/quality_gates_v1.json`；
- 配置规范化 SHA256：`sha256:a21772dbddf07b7c7d42f3813569515b23db1413f33c19f8dc062e7bd5bc7138`；
- 实现：`src/patchalign/evaluation/gates.py`；
- 初始实现提交：`db758373ce0f0a3152613a6475f64dfbe648d2ef`；最终验收提交以执行记录中的三端同步 commit 为准。

使用400条 function、100条 file-window 和150条 external 合成布尔结果验证精确边界，正式默认参数为10,000次 bootstrap、95%区间、seed `20260830`：

```text
SFT +2.0 pp boundary decision SHA256:
sha256:9b8823444d21647201c1766edc03ab5e9ae0f1cd37a0f07ae17ae1917a0963dc

DPO +1.0 pp boundary decision SHA256:
sha256:d873fe7b5306a5bb27fcd55825bf14610c01b3c53ed54409fbd03da46d562421
```

测试覆盖：

- SFT/DPO 精确提升边界；
- 点估计达标但 paired-bootstrap 下界为负；
- parse、apply、compile、regression、timeout、file-window、external 七类退化；
- 精确退化边界允许通过；
- function/file-window/external 分母改变；
- 数据泄漏等 validity violation 一票否决；
- pilot 差异不足2条时资源 tie-break，达到2条时按质量选择；
- 相同输入、配置、seed 的决策和 SHA256 完全一致。

## 集群首轮验收

在 `/mingli01/project/ht/.conda_envs/patchalign-cpp` 设置 `PYTHONNOUSERSITE=1`：

```text
全量 pytest：73 passed in 9.19s
质量门禁专项：20 passed in 3.94s
```

最终同步提交和复跑结果记录在项目执行记录中。本证据不表示已运行真实模型比较，也不替代 A2 沙箱和正式数据 manifest。

## 最终实现验收

验收对象提交：`b236fcafe0d22b4612e5d64c3e4b7c8aa20e1101`。

```text
全量 pytest：75 passed in 9.06s
质量门禁专项：22 passed in 4.04s
```

最终版本额外验证实际 bootstrap 参数进入决策记录、零次 bootstrap 被拒绝，以及第一版 pilot 只允许比较两个候选。
