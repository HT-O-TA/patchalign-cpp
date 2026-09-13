# M1-R2 泛化失败诊断

> 状态：已完成；证据日期：2026-09-06；正式作业：`96197`；运行提交：`6f1b453`。
>
> 历史边界：本诊断形成时，A5/DPO 仍按 ADR-0009 延后；后续 ADR-0031 已恢复并完成简历交付版 DPO。本文只消费冻结 manifest、prompt、预测和评分，不重新生成、不训练，也不把 confirmation/external 答案回流训练；其中 A3.4 readiness 与 `a4_ready=false` 仍是不可改写的历史事实，项目终态见 [项目状态](../status.md)。

## 1. 证据身份与方法

版本化配置为 `configs/evaluation/a3_generalization_diagnostic_v1.json`，分析入口为 `scripts/diagnostics/analyze_generalization_failure.py`。程序逐文件校验 SHA256、三组 case ID 全集合、固定分母和预期事件数；三套 R2 推理还必须由 run manifest 绑定同一 M1-R2 adapter：

```text
8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a
```

internal 与 confirmation 的 score manifest 还要反向绑定 prediction 和 execution artifact。输出只含聚合、case ID 和哈希，不复制源码、测试文本或模型补丁。

六项检查为：

1. 旧 formal holdout 与新 confirmation 的分布差异；
2. confirmation 的 M1-R2 终止阶段漏斗；
3. confirmation 全部 regression 与 timeout 个案；
4. formal 14 个 M1-R2 成功是否集中于狭窄类型；
5. Defects4C 唯一 M1-R2 成功是否具有代表性；
6. 证据更支持“模板/协议学习”还是“可泛化修复语义”。

## 2. 检查一：formal 与 confirmation 的分布差异

两集合 problem family 重叠为 `0`，prompt 版本完全相同，均为 `a3-cpp-repair-v1`。关键差异如下。

| 维度 | Formal 500 | Confirmation 124 | 差异量 |
|---|---:|---:|---:|
| Function / file-window | 400/100 | 100/24 | TV `0.0065`，基本一致 |
| Single-line / multi-line | 292/204 | 56/68 | 编辑类型 TV `0.1404` |
| Add-helper / localized-refactor | 3/1 | 0/0 | 样本极少 |
| `cpp_train0` 占比 | 267/500（53.4%） | 105/124（84.7%） | source-shard TV `0.3128` |
| Buggy code 行数均值/中位数 | 73.2/62.5 | 89.7/87.5 | KS `0.1967` |
| Prompt tokens 均值/中位数 | 777.8/663.5 | 938.0/828.5 | KS `0.1916` |
| 修改逻辑行均值/中位数 | 1.97/1 | 2.13/2 | KS `0.1344` |
| 测试总数均值/中位数 | 97.6/102 | 98.1/102 | KS `0.0659` |

测试分区几乎一致：formal/confirmation 的 public 均值为 `7.56/7.66`，hidden 为 `28.25/28.75`，regression 为 `61.79/61.69`。两集合都来自 upstream `train` split。

结论：confirmation 不是 prompt 模板、任务层级或测试覆盖突然改变；主要变化是全新的 problem family、更加集中于 `cpp_train0`、代码和 prompt 较长、multi-line 比例更高。存在真实协变量偏移，但“模板变了”不能解释 0/124。

## 3. 检查二：confirmation 终止阶段漏斗

| 阶段 | M0 | M1-R2 | M1-R2 比例 |
|---|---:|---:|---:|
| Parse | 0/124 | 123/124 | 99.19% |
| Policy | 0/124 | 123/124 | 99.19% |
| Apply | 0/124 | 104/124 | 83.87% |
| Build | 0/124 | 103/124 | 83.06% |
| Public pass | 0/124 | 6/124 | 4.84% |
| Hidden pass | 0/124 | 3/124 | 2.42% |
| Full pass after regression | 0/124 | 0/124 | 0% |

M1-R2 终态为：`parse_failed=1`、`apply_failed=19`、`build_failed=1`、`public_test_failed=97`、`hidden_test_failed=3`、`regression_failed=3`。

最大瓶颈是语义测试而不是格式：103 个已编译补丁只有 6 个通过 public，约 `94.2%` 在 public 阶段终止；6 个 public 成功中 3 个在 hidden 终止，余下 3 个全部被 regression 拦截。因此 0/124 不是单个解析器故障或单个异常样本造成。

## 4. 检查三：全部 regression 与 timeout 个案

七个重点样本互不重叠，所有模型补丁都能 parse/apply/build，但均不等于参考修复。

| Case | 类型 | 任务/编辑 | 代码/修改/测试 | 关键证据 |
|---|---|---|---:|---|
| `rbr-confirm-4183905b7e29dfc6fbdd` | Regression | function/multi-line | 115/4/101 | public 5/5、hidden 19/19；regression matched 0/77 |
| `rbr-confirm-429ad287a7bb3a977194` | Regression | function/single-line | 10/1/101 | public 11/11、hidden 44/44；regression matched 0/46 |
| `rbr-confirm-cf9ee2f0c8a9fd182270` | Regression | function/single-line | 169/1/91 | public 1/1、hidden 2/2；regression matched 51/88 |
| `rbr-confirm-13a1eacac89f238ecea2` | Timeout | function/single-line | 144/1/101 | public 2/2 outcomes timeout |
| `rbr-confirm-5b4e15f0f663e77e9b63` | Timeout | file-window/multi-line | 91/2/95 | public 6 个进程完成、5 个 timeout；matched 0/11 |
| `rbr-confirm-79a2f7a67089144b2ea0` | Timeout | file-window/multi-line | 114/6/100 | public 1/1 outcome timeout |
| `rbr-confirm-dbd7b90d60426ccca3e3` | Timeout | file-window/multi-line | 76/3/100 | public 7/7 outcomes timeout |

四个 timeout case 共 15 个 timeout outcome，全部终止于 public。即使把四个 case 全部作为最乐观上界移除，也只能影响 `4/124`，不能解释其余 120 条，更不能把 0/124 改写为已证明泛化。

三个 regression case 说明 public/hidden 的有限输入覆盖可被不完整或投机性补丁通过；回归集分别拦住 `77/77`、`46/46` 和 `37/88` 个不匹配输出。这里 outcome 的 `pass` 表示进程正常退出，不等于输出匹配，最终判断以 `matched/total` 为准。

## 5. 检查四：formal 14 个成功的集中度

M1-R2 在旧 500 条上为 `14/500=2.8%`，其中 `7/14` 应用后与参考 fixed source 逐字一致。另 7 个通过全部冻结测试但与参考实现不同，只能视为在当前测试闭包内行为可接受，不能据此证明全语义等价。

| 维度 | 成功分布 | 分母内成功率 | 判断 |
|---|---:|---:|---|
| Function / file-window | 11/3 | 2.75% / 3.00% | 不集中于任务层级 |
| Single-line / multi-line | 10/4 | 3.42% / 1.96% | 偏向 single-line |
| Code `<50` / `50-99` / `100-149` / `150-199` / `>=200` 行 | 8/5/0/1/0 | 4.15%/2.76%/0%/3.85%/0% | 13/14 位于 `<100` 行 |
| Prompt `<512` / `512-1023` / `1024-2047` / `>=2048` tokens | 9/4/1/0 | 5.39%/1.90%/0.88%/0% | 明显偏向短 prompt |
| 五个 source shard | 8/2/1/1/2 | 1.56%～4.55% | 五个 shard 均有成功，非单 shard 模板 |
| 测试数 `>=100` | 12/14 | 2.89% | 不是靠低测试覆盖集中产生 |

所有 formal 样本本来就只有一个 prompt 版本，因此无法用它检验跨模板泛化。现有证据支持“成功显著偏向较短代码/较短 prompt 和 single-line 修改”，但不支持“14 条只来自一个任务层级或一个 shard”。样本数只有 14，分组率只能用于诊断，不能作稳定效应量。

## 6. 检查五：Defects4C 唯一成功的代表性

M1-R2 唯一成功为 `d4c-0c3518e84b668975df03ac8b9620d7bf181bd349`，项目 `llvm___llvm-project`，文件 `llvm/lib/Transforms/Utils/SimplifyCFG.cpp`，输入 495 tokens，位于全体输入长度的第 `15.9` 百分位。

冻结外部集有 6 个项目，但 LLVM 占 `139/176=79.0%`；该成功落在占绝对多数的 LLVM 中，LLVM 内成功率仅 `1/139=0.72%`，其余 5 项目全部为 0。它能证明流水线存在一个真实端到端成功，不能证明跨项目泛化，也不能代表均衡的 C++ 项目生态。

## 7. 检查六：协议/风格学习与修复语义

| 数据 | 指标 | M0 | M1-R2 | 观察 |
|---|---|---:|---:|---|
| Formal 500 | Parse / Apply / Build / Pass | 0/0/0/0 | 499/412/392/14 | 前置能力大幅提升，最终 2.8% |
| Confirmation 124 | Parse / Apply / Build / Pass | 0/0/0/0 | 123/104/103/0 | 同 prompt 模板，最终不复现 |
| Defects4C 176 | Parse / Apply / Build / Pass | 94/24/17/1 | 174/72/55/1 | 跨模板前置能力提升，最终净增 0 |

综合判断为：`protocol_learning_without_demonstrated_semantic_generalization`。

证据支持以下陈述：

- SFT/R2 确实学到了统一 diff 输出协议、路径约束以及更多可 apply/compile 的局部修改；这种收益在 RunBugRun confirmation 和不同 prompt 的 Defects4C 上都可见，不只是背下一种输出后缀。
- confirmation 与 formal 使用同一 `a3-cpp-repair-v1` 模板却从旧 holdout 的 14/500 变为 0/124，因此“纯 prompt 模板变化”可排除。
- 端到端正确性没有稳定跨集合：confirmation 为 0，Defects4C 与 Base 均为 1/176。当前证据更符合“学会协议与部分分布特定修复模式，但没有证明通用修复语义”。
- 无法从这些观察数据唯一归因于某一个原因；problem-family、source shard、长度和编辑分布同时变化。结论是没有泛化证据，不是已经证明单一的过拟合机制。
- A4 的 train-only、多候选采样成功率 `123/1056=11.65%` 与未见集 greedy Pass@1 不同分布、不同采样机制，不能拿来反驳 confirmation 结果。

## 8. 对下一步的约束

本诊断不支持直接用现有 182 对 A4 偏好数据进入 DPO。更合适的顺序是：

1. 建立 Data-v2，增加独立 problem/repo family、较长代码和 prompt、更多 multi-line/重构样本，同时保留 family-level 隔离；
2. 以 confirmation 的 97 个 public failure、3 个 hidden failure、3 个 regression failure和 4 个 timeout case 设计失败分层，但禁止读取其 gold 形成训练样本；训练素材应从隔离 train family 中寻找同类风险模式；
3. 先做小规模、跨 family 的 SFT 数据消融和至少多 seed 复验，再决定重训规模；
4. A4 偏好对先做人工审计与信号分层，尤其区分 75 个 chosen success 与 107 个非 success 对；只有外部/新 confirmation 提升后再设计 A5。

因此优先级是“扩展并重构训练数据与独立评测覆盖”，不是立即 DPO，也不是在原 5,000 条上无变化地重跑 SFT。

## 9. 运行审计与工程发现

| Job | 结果 | 意义 |
|---:|---|---|
| `96099` | FAILED | 旧记录哈希与所指文件不一致，fail closed |
| `96102` | FAILED | 直接遍历 diff 生成器与 A2 的拼接后 `splitlines` 在末行边界不等价；改为逐字复用冻结实现 |
| `96103` | TIMEOUT | 30 分钟不足以覆盖共享盘冷缓存；未写半成品 |
| `96111`、`96131` | CANCELLED | 重复全量测试/未跟踪 artifact 扫描占用时间；已有 254 项完整回归后改为专项测试 |
| `96147` | FAILED | 错把 M1 目录当作 M1-R2，14 条门禁抓到实际 15 条；无输出 |
| `96186` | COMPLETED 后判无效 | M1 产物已归档到 `history/m1-path-misbinding-96186`，不进入结论 |
| `96197` | COMPLETED 0:0 | 6 个专项测试、三组模型身份和全部六项检查通过；正式证据 |

最重要的工程教训不是“改预期数字让程序通过”，而是同时绑定路径、文件哈希、run/score manifest 和 adapter SHA。相似目录名 `formal/sft-inference` 与 `sft-r2/inference` 仅靠人工辨认不足以保证模型身份。

## 10. 正式产物

集群和本地均保存：

```text
artifacts/a3/diagnostics/generalization-v1/
├── summary.json
├── case-audit.jsonl
└── run-manifest.json
```

SHA256：

```text
summary.json       bbca050250020783746e5efb09af060bd2f44b3aa2a321fb30b2059996d85eba
case-audit.jsonl   c7e61a4eaf4330f5e7a4804062bffee870c4a3257d0cd006740765bf4033f721
run-manifest.json  1587a8b5ecdc4fddad74362f7560f239d5930048a66df3fbe26eb999124a7243
```

`run-manifest.json` 绑定 22 个配置、数据、prompt、预测、评分和模型身份输入；正式 config SHA256 为 `48e505d7c3e882c5615c1528028ff75c9e688e67bda01ddf6a5504dcb7c7226a`。
