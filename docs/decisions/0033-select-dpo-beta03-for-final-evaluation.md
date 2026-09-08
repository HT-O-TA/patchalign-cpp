# ADR-0033：选择 DPO beta=0.3 进入最终评测

- 状态：Accepted
- 日期：2026-09-08
- 依赖：ADR-0031、ADR-0032

## 决策

选择 `beta03`（DPO beta=0.3）作为唯一最终评测候选。其 adapter SHA256 为
`2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a`。

该决策由冻结的 `a5-dpo-dev-selection-v1` 产物自动生成的结论支持；selection SHA256 为
`248ad6dcb6783fd2e8c971b05191a87c5b5bd02b696e26f7076262631de665f4`。在 64 条独立 dev
样本上，beta03 与 baseline 均为 5 Pass，但 apply/build 为 57/57，对比 baseline 的 53/52
和 beta01 的 55/55 更高，同时 timeout=1、regression failure=1 均未退化。

## 后果

1. formal 500、confirmation 124、Defects4C 176 只运行 beta03；已有 M1-R2 结果作为配对
   baseline，不重复消耗 GPU。
2. beta01 保留为训练消融和开发集对照，不进入正式集，避免选择后再试验造成多重比较。
3. 正式集若 Pass@1 不提升或退化，仍按一次性结果形成真实结论，不回到 dev 调参重试。
4. 项目在最终评测、失败分析和交付材料完成后收尾；RLVR/GRPO 只作为可选后续，不属于本轮。
