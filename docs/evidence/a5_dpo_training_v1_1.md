# A5 简历交付版 DPO 训练证据

训练日期：2026-09-08
训练代码提交：`80cf19d1bd23a49118dc5fc4bfdda9b6d65f102d`
冻结配置：`configs/training/a5_dpo_v1_1.json`
配置 SHA256：`cc4a2afa39acc85f34b37a3529502d19fad96f3c54e3bce83a8dfd004f0a1459`

## 结论

175 对经审计偏好数据已在冻结的 M1-R2 SFT adapter 上完成两组真实 DPO 训练。主配方
`beta=0.1` 与单一消融 `beta=0.3` 均训练 2 epochs、44 optimizer steps，作业正常结束且
最终 adapter、训练摘要和运行清单已通过哈希绑定。训练完成只证明优化过程有效执行，不代表
下游修复质量提升；模型晋级由独立 64 条 executable dev 集决定，最终质量只由一次性
formal/confirmation/Defects4C 评测决定。

| 配方 | Slurm 作业 | 状态 | 训练损失 | 运行时间 | 峰值显存 | Adapter SHA256 |
|---|---:|---|---:|---:|---:|---|
| `beta01`，beta=0.1（主配方） | `97559_0` | `COMPLETED 0:0` | 0.675672 | 358.48 s | 29,723,163,136 B | `ac66be3432e0aa77f134f120e087aa9a7d23234dab474d5eccdd7b2c03bc869f` |
| `beta03`，beta=0.3（消融） | `97559_1` | `COMPLETED 0:0` | 0.643354 | 357.13 s | 29,723,163,136 B | `2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a` |

两组均使用 20,185,088 个可训练参数，总参数 4,373,157,376；共同来源 adapter SHA256 为
`8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a`。

## 分层验收

1. CPU 预检 Job `97557`：`COMPLETED 0:0`，`427 passed`；175 对输入均未截断，最长总序列
   2,913 tokens，低于 4,096 上限。
2. 单步 GPU smoke Job `97558`：`COMPLETED 0:0`，使用最长偏好对完成 1 个更新步，loss
   0.681687，峰值显存 29,471,249,920 B。
3. 正式 DPO array Job `97559`：两组配方均完成 2 epochs / 44 steps，无 OOM、无生成或保存
   失败。
4. 独立 dev 选型：使用与 A4 训练 case/family 零重叠的 64 条真实执行样本；选型规则在
   ADR-0032 中预注册，训练损失不参与选择。

## 不可变身份

| Artifact | `beta01` SHA256 | `beta03` SHA256 |
|---|---|---|
| `training-summary.json` | `1f9a55f39075bcac1bc08603bfe94030c181d09018179e5f41573d9a6facb843` | `69863dd3ea9334e545180ca910e1cfe298839ec0e182a4d40dc53e6f5718552f` |
| `training-manifest.json` | `50934ab13539c8b462fee2e4e8c426354d3a0508a65a6570ea643d81d0a07927` | `25a2265bcc264054cfd0ed7a7175803bcef0de24bc90bc14aa70e0f837db2dca` |
| `adapter_config.json` | `48f8242a55937bf1dd0d0f68c07ccfcb0464d39309783b645009109a4619ee37` | `8b271b43110c54aaeb90649f5b5c11de67e499fc331e9c542e73d8a0692c5ee0` |

共同输入及预检身份：

- 偏好数据 SHA256：`892812ae43f551aeff06486963e75806ce6da185f8f41d3df3cff64a6f6ba43c`；
- CPU 预检 SHA256：`bc6e6c45e93e4c6a010dfd07d723d7f497395bc071795e3585f78566e937d4d3`；
- GPU smoke SHA256：`fe9921ca25e1099d8aa3d57e204ab366a780037a1fc54ab4a29b357200df3bd2`；
- 环境锁 SHA256：`bef5b08f129a08a1f720e8698c99606832192d1f77b0f9cce1adc98e3baa43a4`；
- Base revision：`0396a76181e127dfc13e5c5ec48a8cee09938b02`。

## 解释边界与可复述问题

- `beta03` 的训练损失更低不表示修复 Pass@1 更高；DPO loss 的尺度受 beta 影响，必须以同一
  dev 执行漏斗比较。
- 固定 seed、冻结输入和 greedy 推理提供可复现实验契约，但训练日志中 PyTorch 对部分注意力
  内核给出 nondeterminism warning，因此不能声称权重逐 bit 可复现。
- 该轮只保留一个 beta 消融，不开展大范围超参数搜索，符合简历交付版的投入边界。
- 大权重保留在集群；本地只归档清单、摘要、adapter 配置和日志。最终只交付被 dev 选中的
  adapter，避免把两个候选都包装成最终模型。
