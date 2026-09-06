# Data-v2 泛化增强计划

> 当前状态：进入只读供给审计；尚未冻结训练集，尚未训练模型，未授权 A5/DPO。

## 目标

M1-R2 的六项诊断表明，模型已经显著改善 unified diff 协议、apply 和 build，但端到端修复语义没有在新 confirmation 和 Defects4C 上稳定迁移。Data-v2 的目标不是简单扩大条数，而是补足以下缺口：

1. 增加未被 v1 使用的 repository/problem family；
2. 提高代码不少于 100 行、prompt 不少于 1,024 tokens 的覆盖；
3. 增加 multi-line、add-helper、localized-refactor；
4. 增加 file-window，但仍以函数级为主；
5. 保持现有 formal、confirmation 和 external 评测身份不受污染；
6. 用多 seed 小规模消融证明数据变化有效后，才考虑正式重训。

## 第一阶段：供给审计

机器契约为 `configs/data/data_v2_supply_audit_v1.json`，实现为 `scripts/data/audit_data_v2_supply.py`。审计读取 CommitPackFT/RunBugRun 原始训练池和冻结 manifest，输出：

- v1 基座分布；
- 在“v1+增量每 family 最多 2 条”约束下的真实剩余容量；
- 长代码、长 prompt、复杂编辑、结构性编辑、file-window、新 family 和 CommitPackFT 的同步覆盖；
- 一个 2,000/200 增量草案是否能同时满足预设最低值；
- 所有拒绝原因、输入哈希和候选身份哈希。

这一阶段只输出元数据统计和候选哈希，不输出新训练 JSONL，不申请 GPU。

## 防泄漏边界

- Formal holdout 只读取 `problem_id` 用于排除；
- Confirmation 只读取 `problem_id` 用于排除；
- Defects4C 只读取 `project` 用于保守仓库别名排除；
- 不读取 confirmation/external 的源码、prompt、补丁、测试、得分或执行反馈；
- 不将六项诊断中的失败 case gold 用作训练；
- RunBugRun 保留 upstream train/validation，CommitPackFT 新 family 通过稳定哈希分配 split；
- v1 与增量合并后同一 family 最多 2 条，train/validation family 零交叉；
- 所有原始文件、冻结 manifest、tokenizer 和模型 revision 均需哈希匹配。

## 暂定规模与解释边界

供给审计暂用 2,000 train + 200 validation 的增量假设，它只是容量探针，不是最终冻结配额。目标同时要求新 family、长输入、复杂/结构修改、file-window 和 CommitPackFT 覆盖；任何不足都应调低方案或引入新来源，不能通过复制、合成或使用评测集补齐。

CommitPackFT 当前仍缺少仓库级可执行复现，因此可作为 SFT 监督数据，但不能被描述为经过 A2/Defects4C 同等级真实执行资格。RunBugRun 的 problem family 隔离也不能被描述为 repository-family 隔离。

## 审计后的决策门

只有以下条件同时满足，才进入 Data-v2 构造：

1. 所有冻结输入和原始 shard 哈希一致；
2. confirmation/external gold 消费保持为 false；
3. 2,000/200 草案的同步覆盖门槛可实现，或先形成负责人认可的版本化修订；
4. 新训练集构造器能够拒绝覆盖、输出 Schema/隔离/token 报告并可重复得到相同哈希；
5. 训练方案预注册至少 3 个 seed 的小规模对照，评测继续使用冻结 greedy Pass@1 和真实执行评分。

如果供给不足，下一步应新增经过许可证与 family 治理的数据来源，而不是直接在 v1 上重复 SFT。
