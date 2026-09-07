# ADR-0014：Data-v2 评测 denylist 的完整性边界

- 状态：Accepted under delegated project decision authority
- 日期：2026-09-07

## 背景

Data-v2.1 要求在下载候选 patch/source 前完成保留评测身份清单。旧 GitHub
metadata pilot 的 denylist 明确标记为不完整，只能支持容量发现，不能支持内容
采集。本决策只处理“当前冻结评测集合”的身份隔离，不读取参考补丁、fixed code、
测试输出或其他 gold。

## 当前保留集合

1. formal holdout：500 条、500 个唯一 RunBugRun/CodeNet `problem_id`；
2. confirmation：124 条、124 个唯一 `problem_id`，与 formal 交集为 0；
3. Defects4C qualified-v1：176 条，覆盖 6 个明确仓库；
4. Multi-SWE-bench C++：官方 Multi-SWE-RL revision 所列 9 个 C++ 仓库；
5. BugsCpp：upstream revision `be5cc489cb2b3127ec3b73cb4adfdd290807f55b`，
   当前官方表 215 个缺陷、24 个项目标识；
6. LLVM APR Benchmark：upstream revision
   `765534776d06d355b026f713f265653f34d8b3ad`，包括 LLVM 主仓库和迁移后的
   benchmark 身份；
7. DebugBench：upstream revision `2761bab93c4c65351b19d0ef4a94b26abe47a185`，
   作为 LeetCode-derived 评测域保留。

## 决定

版本化 denylist 使用四层匹配：

- 精确 canonical `host/owner/repository`；
- 对大小写、连字符、下划线和点归一化后的仓库名/项目别名；
- fork lineage：候选若为 fork，必须解析 source/parent 根身份，任一根命中即拒绝；
- 对 RunBugRun 来源，直接从已绑定 manifest 读取 624 个 `problem_id`，而不是把
  CodeNet 误当作 GitHub 仓库。

只有上述所有来源 revision、manifest 哈希、计数、集合哈希和预期项目集合同时
通过，`complete_for_candidate_content_acquisition=true` 才成立。该状态只允许
下载被选中候选的必要内容进行后续审计，不等于训练准入。

## 内容取得后的第二道门

即使仓库/问题身份没有命中 denylist，候选仍须在训练文件冻结前完成：

- fix commit、parent commit 和变更文件身份核验；
- 与评测集合的 commit、path、patch/source 内容哈希去重；
- 仓库许可证文件与 SHA256 核验；
- buggy 必须失败、fixed 必须通过的确定性测试重放；
- train/validation 仓库零交叉及 family/repository cap。

因此“denylist 完整”不能被解释为“无污染”或“可训练”。未来新增任何评测集合、
上游项目或 revision 时，必须发布新版本清单；不得继续沿用本版本的 complete 标志。

## 隐私与 gold 边界

编译清单只消费 `problem_id` 和 `project` 身份字段，输出集合数量、稳定 LF 哈希和
仓库身份；不输出 prompt、buggy/fixed code、reference patch、测试或期望输出。
