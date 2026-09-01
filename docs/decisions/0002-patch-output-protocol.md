# ADR-0002：补丁输出协议

状态：Accepted for A0
日期：2026-08-30

## 背景

自由文本解释会增加解析歧义，并可能让评测器从错误回答中“猜”出补丁。结构化 JSON 能携带元数据，但要求模型同时学习 JSON 转义和 diff，可能让第一版格式负担变大。

## 决策

第一版模型输出恰好一个纯 unified diff：

- 不允许 Markdown 围栏；
- 不允许解释；
- 不允许多个候选；
- 路径使用 `a/`、`b/` 前缀和仓库相对路径；
- 解析器只接受唯一完整 patch，不做自然语言容错拼接。

标准应用模式采用严格解析、宽松 hunk 计数：

- 在固定 `base_commit` 的独立干净工作树中执行 `git apply --recount --check`；
- `--recount` 只重新推断 hunk header 的旧/新行数计数；起始位置偏差能否应用仍由 Git 根据补丁携带的删除行和上下文判断；
- 不启用 `--ignore-whitespace`、`--3way`、`--reject`、`--unsafe-paths` 或 `--unidiff-zero`；
- prompt 默认要求每个 hunk 携带修改前后各 3 行上下文，文件边界不足时使用全部可用上下文；这是生成约定，Git 仍严格匹配补丁实际携带的全部上下文；
- check 通过后，实际应用必须使用同一 `--recount` 参数；
- `apply_success` 只进入 Patch apply rate；只有 build、public、hidden 和 regression 全部通过才是最终 `success`。

失败分类保持阶段边界：

- 非唯一或语法不完整的 unified diff 为 `parse_failed`；
- 多文件、越界/绝对路径、二进制 patch 等为 `policy_violation`；
- 语法和策略合法，但删除行或上下文不能应用到固定 revision，为 `apply_failed`。

预测元数据、解析状态和执行结果保存在模型输出之外的 JSON record 中。

## 理由

- 与 Git patch 工具链直接兼容；
- 比 JSON 内嵌 diff 少一层转义；
- 格式失败能清晰归因；
- 防止评测器过度修复模型输出；
- 后续如需工具 API，可在外层增加结构化 envelope，而不改变 patch 本体。

## 验收要求

- 至少包含新增、删除、上下文、多 hunk 和多文件禁止案例的 parser fixture；
- 路径逃逸、绝对路径、二进制 diff、代码围栏和多 patch 必须拒绝；
- 用户已于 2026-09-01 接受严格拒绝，以及仅通过 `--recount` 放宽 hunk 行数计数的取舍。
