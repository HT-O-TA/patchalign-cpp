# A0 任务契约

状态：Draft
版本：`0.1.0`

## 1. 任务定义

给定缺陷描述、已定位的 C++ 上下文和失败证据，模型生成一个最小 unified diff。评测器在固定源代码 revision 上应用补丁，并通过编译、公开测试、隐藏测试和回归测试判断是否修复。

第一版不要求模型搜索仓库、定位文件、联网查询或进行多轮工具调用。

## 2. 任务层级

### 2.1 `function`

第一版主任务。输入上下文覆盖一个目标函数及必要的相邻声明。主报告和主要模型比较只在冻结的函数级测试集上计算。

### 2.2 `file_window`

兼容层级。输入可以包含目标文件中的较大窗口，但仍提供目标文件和符号定位。第一版可用于 fixture、诊断或后续扩展，不得在未分层报告时混入函数级主指标。

第一版截取规则按 [ADR-0003](../decisions/0003-dataset-composition-v1.md) 冻结：目标函数必须完整保留，函数前后各最多 96 行，窗口最多 256 个物理行，完整输入最多 4,096 tokens。目标函数自身超过任一上限时排除，不允许截断目标函数。

### 2.3 第一版不支持

- 未定位的仓库级搜索；
- 多文件自主探索；
- 联网搜索；
- Agent 工具循环；
- 自动修改或生成测试；
- 修改构建系统以绕过任务。

## 3. 模型可见输入

按固定顺序构造 prompt：

1. 任务说明；
2. 输出格式约束；
3. `problem_statement`；
4. `failure_evidence`；
5. 允许修改的相对路径；
6. 目标文件和符号；
7. buggy code/context。

模型不得看到：

- `gold_patch`；
- hidden test 内容；
- 修复后代码；
- chosen/rejected 的执行标签；
- 外部评测仓库的参考补丁。

## 4. 输出契约

模型必须输出恰好一个 unified diff：

```diff
--- a/path/to/file.cpp
+++ b/path/to/file.cpp
@@ ... @@
-old line
+new line
```

禁止：

- Markdown 代码围栏；
- diff 前后的解释；
- 多个候选答案；
- 绝对路径；
- `../` 路径逃逸；
- 二进制 patch；
- 修改契约未允许的文件。

解析器不得从任意自然语言中猜测或拼接多个 diff。无法提取唯一合法 patch 时记为 `parse_failed`。

应用阶段采用 ADR-0002 的标准模式：先运行 `git apply --recount --check`，通过后使用同一 `--recount` 参数实际应用。该参数只重新推断 hunk header 的行数计数，不忽略删除行、上下文或空白差异。语法合法但无法应用时记为 `apply_failed`，不混入 `parse_failed`。

## 5. 允许修改范围

样本通过 `allowed_paths` 显式定义可修改的仓库相对路径。第一版默认只允许目标 C/C++ 源文件或头文件。

除非单独任务类型明确允许，否则禁止修改：

- 测试文件和测试数据；
- CMake、Makefile、CI 和评测脚本；
- sanitizer 或断言配置；
- vendored/generated 文件；
- 仓库外路径；
- 子模块指针和大文件引用。

## 6. 执行前置条件

可执行样本必须先证明：

1. 固定 base revision 可重建；
2. 修复前目标测试失败；
3. gold/fix revision 上目标测试通过；
4. 命令不需要密钥、私有服务或运行时联网；
5. 许可证和来源允许所声明的使用方式。

不能满足 before-fail/after-pass 的样本可以进入非执行 SFT 候选，但不得进入 hidden-test Pass@1 结论。

## 7. 成功定义

单个样本只有同时满足以下条件才记为修复成功：

- patch 唯一且可解析；
- 路径和修改范围合法；
- patch 可应用到固定 revision；
- 构建成功；
- public tests 通过；
- hidden tests 通过；
- 回归测试通过；
- 未触发适用的 sanitizer；
- 未修改禁止对象；
- 未超出资源和时间限制。

空 patch、只通过 public test、删除测试或硬编码公开输入都不算成功。

## 8. 确定性与版本

- prompt template、Schema 和评分器都必须有版本；
- 样本内容由 `provenance_hash` 标识；
- 同一预测和执行环境重复评分必须产生相同阶段状态；
- 契约变化必须通过 ADR 和版本号记录，不能静默覆盖历史结果。
