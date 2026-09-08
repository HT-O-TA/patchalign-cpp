# A5 DPO 独立开发集选型证据

运行日期：2026-09-08

## 结论

在与 A4 偏好训练 case/family 零重叠的 64 条 executable C++ function 样本上，M1-R2、
DPO `beta=0.1`、DPO `beta=0.3` 均完成确定性 greedy 推理与 Bubblewrap 真实执行评分。
三者 Pass@1 均为 `5/64`；DPO 没有改善最终正确率，但减少了 apply/build 前的结构性失败。
按 ADR-0032 预注册的词典序漏斗与非退化约束，`beta=0.3` 被选为唯一正式评测候选。

| 模型 | Pass | hidden 通过 | public 通过 | compile 通过 | apply 通过 | regression 失败 | timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| M1-R2 baseline | 5 | 6 | 7 | 52 | 53 | 1 | 1 |
| DPO beta=0.1 | 5 | 6 | 7 | 55 | 55 | 1 | 1 |
| DPO beta=0.3 | 5 | 6 | 7 | 57 | 57 | 1 | 1 |

`beta=0.3` 相对 M1-R2：Pass、hidden、public 不变，compile `+5`，apply `+4`；相对
`beta=0.1`：compile/apply 均 `+2`。两组 DPO 的 timeout 与 regression 均未高于 baseline，
因此均满足非退化约束；`beta=0.3` 在更靠后的词典序指标上占优。

## 作业与验收

| 环节 | Slurm 作业 | 结果 | 耗时 |
|---|---|---|---:|
| CPU 预检 | `97566` | `COMPLETED 0:0`，`431 passed` | 22 s |
| 三路推理 | `97567_0..2` | 全部 `COMPLETED 0:0` | 10m06s–10m30s |
| 三路执行评分 | `97570_0..2` | 全部 `COMPLETED 0:0` | 3m14s–3m18s |
| 冻结选择 | `97571` | `COMPLETED 0:0`，选择 `beta03` | <1 s |

三路均生成 64/64 个 `status=ok` 的严格 unified diff，3/3 重放探针稳定。推理峰值显存均为
6,385,006,080 B。

## 不可变身份

- 评测代码提交：`f6f05912e6e57c13298e4de2b7830c56c357824f`；
- 开发集 manifest SHA256：`457318d186ba056a970ac917f4161cacf98b07f2bd121327452a5eaaf601340f`；
- prompt artifact SHA256：`24c6c9ad31fe21c25418cabd0a0d0be8dcb6740bc44bf4fe379f38b406dcd713`；
- 评测配置 SHA256：`ab2b1fa2d5c9711d7a6665e44857478eb8a086df8bba66a1b1a09c1bd7eeb637`；
- baseline summary SHA256：`1a693effedc4f3b0b87929b412537c6e943c757076b8205deb7ef4846acc2459`；
- beta=0.1 summary SHA256：`22cf4418f0d862e5a0a1f0d658b9900e15c8d9048d41e5ea7303f04993f2ca0f`；
- beta=0.3 summary SHA256：`e12abbc3384860a703e5aa24f82e0ae334addb801c8d25c53b917f008ad64b0c`；
- selection SHA256：`248ad6dcb6783fd2e8c971b05191a87c5b5bd02b696e26f7076262631de665f4`；
- 胜出 adapter SHA256：`2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a`。

## 解释边界

- 开发集只有 64 条且全为 function 级，不能据此声称 DPO 提升了总体正确率或 file-window
  泛化能力。
- apply/build 提升是有价值的漏斗信号，但它只支持“更少结构性失败”，不能替代最终测试通过。
- 正式结论必须来自未参与选择的 formal 500、confirmation 124 和 Defects4C 176；三套数据只
  评测一次胜出模型，不再比较或重试 beta=0.1。
