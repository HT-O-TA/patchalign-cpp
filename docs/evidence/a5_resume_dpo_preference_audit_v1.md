# A5 简历交付版 DPO 偏好审计证据

核验时间：2026-09-08T09:10Z
审计作业：Slurm Job `97540`，`COMPLETED 0:0`，耗时 `00:00:19`，CPU-only
代码提交：`4fe942fb8671ab410f65133157e4cf0280bb2ec4`

## 结论

Job 97540 先完成全仓 `424 passed`，随后对冻结 A4 偏好逐对验证 Schema、prompt/response
哈希、候选评分绑定、终止阶段、严格排序、train-only 来源以及与独立开发执行集的 case/family
隔离。182 对源偏好中，7 对仅由 timeout 次数打破平局，按预注册规则排除；最终训练集为
175 对，其中 chosen 完整成功 75 对。

| 项目 | 结果 |
|---|---:|
| 源偏好对 | 182 |
| 批准训练对 | 175 |
| 排除 timeout-only 对 | 7 |
| chosen full-success | 75 |
| function / file-window | 168 / 7 |
| 与独立 dev 重叠 | 0 |
| 与正式/确认/外部评测重叠 | 0 |
| gold 或测试正文进入训练 | 否 |

简历交付版门槛为至少 150 对且 chosen full-success 至少 70 对，本次为 `175/75`，通过。
旧论文级门槛 `300/150` 未通过；该事实不得改写为论文级偏好数据充分。

## 不可变身份

| Artifact | SHA256 |
|---|---|
| `preferences.jsonl` | `892812ae43f551aeff06486963e75806ce6da185f8f41d3df3cff64a6f6ba43c` |
| `audit.jsonl` | `bf84024e26d97b239ec3f03eb01b3948a36ac2fd6dfd838ac1ab8812944532eb` |
| `summary.json` | `e352dc1a2ec78744a6119ed8358ba38184890ea031d8ac32d7b664c34b24e634` |
| `run-manifest.json` | `5f116658b815ea63d11cc6331c8d0a08e00a09822305400ec29e624d1de36ffe` |

训练文件位于集群
`/mingli01/project/ht/patchalign-cpp/artifacts/a5/dpo-preference-v1/`；本地忽略目录已同步同名
副本。独立开发集 manifest SHA256 为
`457318d186ba056a970ac917f4161cacf98b07f2bd121327452a5eaaf601340f`。

## 解释边界

- 175 对来自经过执行资格筛选的 train-only A4 分布，只能用于 DPO 训练，不能充当独立评测。
- 75 对 chosen success 提供最强正信号；其余 100 对仍是严格更晚终止阶段信号，不等同于正确补丁。
- 64 条独立 dev 只用于在两个冻结 beta 配方间选型，不参与梯度更新。
- 最终质量结论必须来自 formal 500、confirmation 124 和 Defects4C 176 的一次性真实执行评测。
