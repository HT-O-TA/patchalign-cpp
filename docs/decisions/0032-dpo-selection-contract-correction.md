# ADR-0032：DPO 开发集选型顺序修正

- 状态：Accepted
- 日期：2026-09-08
- 影响范围：A5 简历交付版 DPO 配方选择；不改变偏好数据、训练 seed、beta、step、学习率或正式评测分母

## 背景

首版 `a5-dpo-v1` 已通过 CPU preflight，但在设计开发集评分器时发现其机器配置把
regression 和 timeout 排在主要执行漏斗之前，与 ADR-0031 已接受的“Pass，再依次
hidden/public/build/apply；timeout 和 regression 不得恶化”不完全一致。GPU smoke Job
97552 与训练数组 97553 当时均为 pending、运行时间 `00:00:00`，已在任何 GPU 或梯度
计算发生前取消。

## 决策

1. 建立 `a5-dpo-v1.1`，训练数据、M1-R2 起点、seed、beta=0.1/0.3、两轮、44 steps、
   学习率与 token 上限全部保持不变。
2. M1-R2 是比较基线，不是待选 DPO candidate；待选项仅为 beta01 与 beta03。
3. 对满足 timeout、regression 均不高于 M1-R2 的候选，按 Pass、hidden、public、build、
   apply 的成功数依次降序选择。
4. 正向执行信号定义为上述执行漏斗相对 M1-R2 的严格字典序提升。
5. 若没有候选同时满足非退化约束，或二者均无正向信号，仍按 ADR-0031 选择风险较低者
   完成一次性正式评测：先最少 regression failure，再最少 timeout；完全相同时选
   beta03，因为更大的 beta 对参考模型约束更强。结果必须标注为负结果或无提升。
6. 首版 CPU preflight Job 97551 作为“数据、token、依赖通过但选型元数据已废止”的历史
   证据保留；v1.1 使用新输出目录重新执行，不覆盖旧 artifact。

## 结果

该修正只消除决策文档与机器配置的漂移，不读取 dev 结果、不调整训练超参，也不构成
结果驱动调参。v1.1 CPU preflight 通过后才能重新提交 GPU smoke 和训练数组。
