# ADR-0031：从论文级扩展切换为简历交付版后训练闭环

- 状态：Accepted by project owner
- 日期：2026-09-08

## 背景

项目负责人明确本项目首先服务简历：投递 AI 应用开发时作为第二项目展示后训练与模型
评测能力，投递后训练岗位时可作为主项目。当前优先前者，因此目标是形成可信、可演示、
可复现的完整闭环，而不是继续追求论文级数据规模、随机种子和穷尽消融。

现有工程已经完成 Qwen2.5-Coder-7B NF4 QLoRA、500 条内部真实执行评测、124 条未见
确认集、176 条外部 Defects4C、1,056 个候选执行评分和 182 对偏好数据。继续寻找新
来源或重复三 seed SFT 的边际简历价值低于完成 DPO、统一报告和演示入口。

## 决策

1. GitHub、CommitPack、BeetleBox、BugsCpp、RunBugRun v2 等来源搜索保持关闭；不再
   构建此前设想的 2,000/200 Data-v2，也不运行三 seed Data-v2 SFT。
2. M1-R2 保持 DPO 起点。其 formal `14/500`、confirmation `0/124`、Defects4C
   `1/176` 和已知泛化限制必须继续披露，不能把 DPO 用来掩盖 SFT readiness 失败。
3. ADR-0030 的独立开发执行集继续完成，但用途收敛为 DPO 配方选择：只从未进入 A4
   偏好集的 train-only function family 中固定目标 64、最低 50 条，不进入 DPO 训练。
4. 对 A4 的 182 对执行偏好重新做自动审计。7 对仅由 timeout tiebreak 区分的 pair
   必须排除；其余样本必须逐项通过 prompt/completion 哈希、同 case、chosen 严格优于
   rejected、训练 family、无评测身份和无 gold/test 泄漏检查。
5. 旧研究门 `>=300 pairs`、`>=150 chosen-success` 保留为“未达到”，不得回写成通过。
   简历版 DPO v1 另设最低 `150` 对且 chosen full-success 至少 `70` 对；这是负责人改变
   交付范围后的新实验，不声称统计充分或论文级规模。
6. 只运行一个冻结 seed 的 DPO 主配置和一个必要对照。默认主配置为 `beta=0.1`，对照
   为相同数据、seed、steps、学习率下的 `beta=0.3`；具体 batch、epoch 和显存参数在
   GPU 前由一次 smoke/preflight 固定，不做结果驱动的多轮搜索。
7. 两个 DPO adapter 只在独立开发执行集上选择；以 M1-R2 为基线，优先级为最终 Pass、
   再依次是 hidden/public/build/apply，timeout 和 regression 不得恶化。若二者都没有
   正向执行信号，仍选风险较低者完成一次性正式评测，但结论必须是负结果或无提升。
8. 选定 DPO 对 formal 500、confirmation 124、Defects4C 176 各运行一次，与已冻结
   M1-R2 结果成对比较；不因某一门失败反复调参补考。
9. 最终只保留一个推荐 adapter，并交付：项目 README、架构/数据流、最小 CLI demo、
   模型卡、指标总表、失败分析、环境锁、复现命令和 artifact 索引。历史研究材料保留在
   docs，但首页突出可运行闭环和诚实指标。
10. RLVR/GRPO 不属于本轮实施范围。只有上述交付全部完成后，才单独评估是否值得继续。

## 对旧契约的影响

ADR-0012 的数据扩张、三 seed SFT/DPO 和 300/150 promotion gate 不再是当前简历交付版
的完成条件，但其历史结果与失败判断不被删除。Schema v0.2、执行沙箱、`git apply
--recount --check`、固定评测分母、sanitizer 适用性、不可变 manifest 和防泄漏边界继续
有效。

## 完成标准

本轮完成必须有真实 DPO 权重、一次核心对照、三套冻结评测、SFT/DPO 比较、失败分析和
可复现交付；仅完成脚本、排队或训练 loss 不算完成。
