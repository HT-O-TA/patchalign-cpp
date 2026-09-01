# ADR-0004：训练质量门禁 v1

状态：Accepted for A0
日期：2026-09-01

## 背景

正式训练前必须预注册“有意义提升”和“可接受退化”，避免在看到结果后改变成功标准。A3 小规模 pilot 的统计能力不足，只用于选择可运行方案；正式 SFT 和 DPO 使用冻结的同一样本进行成对比较。

机器配置见 [`quality_gates_v1.json`](../../configs/evaluation/quality_gates_v1.json)，判定器见 `src/patchalign/evaluation/gates.py`。

## 决策

### 1. A3 pilot 选择

- 只比较 completed 且 stable 的方案；
- 成功数相差至少 2 条时选择成功数更高者；
- 相差不足 2 条时，不声称质量差异，依次按峰值显存更低、wall time 更短、名称字典序选择；
- pilot 百分比不得包装成正式模型提升。

### 2. 正式主指标门禁

比较均为相同的 400 条 `internal_test_function`，使用绝对百分点：

| 阶段 | 候选 | 基线 | 最小提升 |
|---|---|---|---:|
| SFT | M1 | M0 Base | `+2.0 pp`，即净提升至少约 8/400 |
| DPO | M2 | M1 SFT | `+1.0 pp`，即净提升至少约 4/400 |

同时对逐样本 Pass@1 布尔结果运行 paired bootstrap：

```text
confidence_level: 0.95
resamples: 10000
seed: 20260830
```

候选减基线的95%区间下界必须 `>= 0`。点估计阈值和区间门槛必须同时满足；相等视为通过。

### 3. 可接受退化上限

| 指标 | 候选相对基线的最大退化 |
|---|---:|
| parse rate | `-1.0 pp` |
| apply rate | `-1.0 pp` |
| compile rate | `-1.0 pp` |
| regression rate | 最多增加 `+1.0 pp` |
| timeout rate | 最多增加 `+0.5 pp` |
| 100 条 file-window Pass@1 | `-3.0 pp` |
| Defects4C C++ 外部切片 Pass@1 | `-2.0 pp` |

外部切片必须使用相同样本且至少 150 条；若 A1 实测后不足 150，必须修订数据 ADR 和本 ADR，不能静默降低门槛。

### 4. 分母与一票否决

- function 必须为同序的 400 对样本，file-window 必须为同序的 100 对样本；
- 外部切片候选和基线分母必须相同；
- generation failure、格式失败、apply/build/test 失败和 timeout 都保留在冻结总分母；
- sanitizer 只以显式 `sanitizer_applicable=true` 的样本为分母；不适用不算通过或失败；缺少显式标记的样本不能进入正式 sanitizer 指标；
- 数据泄漏、hidden test 暴露、修改测试、统计分母变化、artifact/manifest 不匹配等 validity violation 直接判整个比较无效，不能用指标提升抵消。

## 解释边界

通过门禁表示“满足本项目预注册的继续条件”，不自动等于具有广泛统计显著性、跨 benchmark 泛化或可发布结论。正式报告仍须披露样本数、绝对计数、区间、全部切片、失败 run 和已知限制。

## 验收

- 配置、paired bootstrap 和门禁结果均有版本与 SHA256；
- 单元测试覆盖精确边界、CI 下界失败、所有退化上限、分母改变、validity veto 和 pilot tie-break；
- 同一输入、配置和 seed 必须产生相同决策及哈希。
