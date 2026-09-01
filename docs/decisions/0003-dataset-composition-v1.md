# ADR-0003：第一版数据集组成与上下文配额

状态：Accepted for A0
日期：2026-09-01

## 背景

第一版需要在个人项目可控的数据治理和单张 A800 的训练预算内，同时保留真实提交、可执行短程序和真实仓库外部评测。`public`、`hidden` 和 `regression` 是同一样本的测试阶段，不是三个互斥数据集。

本 ADR 冻结目标配额、筛选规则和报告分层。Defects4C 的最终可重放数量、所有数据源 revision 和 manifest SHA256 必须在 A1 实测后冻结；不得把目标数写成已经获得的样本数。

## 决策

### 1. 语言范围

- 第一版主训练、验证和主指标样本为 100% C++；
- Python 是数据、训练和评测工程语言，不是修复样本语言；
- Java 不进入第一版；
- C 样本如后续使用，只进入独立 `external_test_c` 切片，不与 C++ 主指标合并。

### 2. 数据配额与来源

| 集合 | 目标数量 | 来源 | 用途 |
|---|---:|---|---|
| `train` | 5,000 | 2,000 CommitPackFT C++ + 3,000 RunBugRun C++ | SFT；DPO prompt 只能从本集合派生 |
| `validation` | 500 | 200 CommitPackFT C++ + 300 RunBugRun C++ | loss、early stopping 和超参数选择 |
| `internal_test_function` | 400 | RunBugRun C++ 未见 `problem_id` | 函数级主指标 |
| `internal_test_file_window` | 100 | RunBugRun C++ 未见 `problem_id` | file-window 独立诊断 |
| `external_test_function` | 所有可重放且符合契约的 C++ 样本，目标至少 150 | Defects4C | 真实 C++ 外部函数级评测 |
| `external_test_repo` | 12 | SWE-bench Multilingual 当前 C++ 子集 | 仓库级扩展，不混入第一阶段主指标 |

约束：

- CommitPackFT 配额不足时不得降低许可证、去重或修复质量标准，也不得用 Python/Java 填充；任何改配额必须修订本 ADR；
- RunBugRun 按 `problem_id` 隔离，不能宣称 repository-family 隔离；
- Defects4C 和 SWE-bench/Multi-SWE-bench 的 repository family 必须从全部训练来源拉黑；
- 合成 fixture 不进入正式训练或评测配额；受控缺陷变异若未来进入训练，必须另立 ADR，且不得进入正式测试；
- 各评测切片分别报告，不计算跨 RunBugRun、Defects4C 和 SWE-bench 的混合总分。

### 3. 构建阶段

| 阶段 | 数量 | 目的 |
|---|---:|---|
| A1 数据管线 pilot | 300 train + 50 validation | 检查来源、Schema、过滤、去重和训练投影 |
| A2 评分闭环 | 50 function + 20 file_window | 检查编译、测试、失败分类与确定性 |
| 正式 v1 | 上表完整配额 | 只在 pilot 和评分闭环通过后构建 |

pilot 是正式配额的子集，不是额外样本。未经门禁不得直接处理或训练全量数据。

### 4. 任务层级

训练集和验证集按以下目标比例分层：

```text
function     85%
file_window  15%
```

正式内部评测固定为 400 条 function 主集合和 100 条 file-window 诊断集合。二者不得合并报告 Pass@1。

### 5. file-window 截取规则

- 必须完整保留目标函数；
- 目标函数前、后各最多保留 96 个物理行；
- 整个窗口最多 256 个物理行；
- 完整模型输入最多 4,096 tokens；
- 超过 token 上限时从两侧对称缩减，禁止截断目标函数；
- 目标函数自身超过 256 行或 4,096 tokens 时排除出第一版；
- 文件边界自然缩短窗口，不用空行补足固定长度。

冻结字段语义：

```text
file_window_lines_max: 256
file_window_context_before_max: 96
file_window_context_after_max: 96
input_tokens_max: 4096
```

### 6. 修改类型配额

训练集和验证集使用以下目标比例；外部评测保留自然分布，只分层报告：

| 修改类型 | 比例 | 5,000 条训练目标 |
|---|---:|---:|
| `single_line` | 35% | 1,750 |
| `multi_line_local` | 50% | 2,500 |
| `add_helper` | 10% | 500 |
| `localized_refactor` | 5% | 250 |

操作定义：

- `single_line`：只修改一个逻辑源代码行；
- `multi_line_local`：修改 2～20 个逻辑行且只涉及目标函数；
- `add_helper`：新增一个辅助函数并由目标函数调用；
- `localized_refactor`：涉及多个符号，但局限于一个文件且不超过 40 个逻辑修改行。

纯格式化、纯重命名、纯注释、生成文件、超过 40 个逻辑修改行或修改多个源文件的样本不进入第一阶段。`add_helper` 和 `localized_refactor` 主要进入 file-window 切片。

### 7. public、hidden 与 regression

全部 500 条内部评测样本必须同时覆盖三类阶段，因此覆盖样本数均为 500，而不是三个互斥集合。

对每条可执行样本：

1. 在 buggy revision 和 gold/fix revision 上运行全部候选测试；
2. `F` 为 buggy 失败且 gold 通过的测试；
3. 从 `F` 中按稳定哈希确定性选择约 20%、至少 1 条作为 public；
4. 其余 `F` 作为 hidden，至少 1 条，优先至少 2 条；
5. buggy 和 gold 上都通过的测试作为 regression，至少 3 条；
6. gold 上仍失败的测试不得进入正式评测。

无法同时满足 public、hidden 和 regression 最低门槛的样本可以进入非执行 SFT 候选，但不得进入 Hidden-test Pass@1 分母。模型 prompt 不得包含 hidden test 内容。

### 8. 隔离与派生约束

- CommitPackFT：先按 `repository_family` 分配 split，再生成函数或窗口样本；
- RunBugRun：先按 `problem_id` 分配 split，再选择 buggy/fixed pair；
- 同一 commit、近似代码、fork、mirror、vendor、历史改名和同源测试不得跨 split；
- DPO 候选只从 train prompt 生成；
- validation、internal test 和 external test 的预测、gold patch 或执行反馈不得进入 SFT/DPO 数据；
- 外部 benchmark 保持原始自然难度分布，不为匹配训练配额而重采样。

## 依据

- CommitPackFT 官方数据卡当前列出 4,992 条原始 C++ 样本，且每条带仓库许可证字段；2,000 条是过滤后的目标，不是已获得数量：<https://huggingface.co/datasets/bigcode/commitpackft>
- RunBugRun 官方仓库说明其包含超过 700,000 个可执行 buggy/fixed pair、测试、bug 标签和预定义 split：<https://github.com/giganticode/run_bug_run>
- Defects4C 官方说明包含 248 个普通 C/C++ 缺陷和 102 个 CVE 缺陷及相应测试：<https://sites.google.com/view/defects4c/home>
- SWE-bench Multilingual 当前共有 300 个任务；C++ 子集为 `nlohmann/json` 1 条和 `fmt` 11 条，并使用 fail-to-pass / pass-to-pass 测试：<https://www.swebench.com/multilingual.html>

## A1 必须补齐的证据

- 每个数据源的固定 revision、许可证审计和原始文件 SHA256；
- 过滤前后数量、拒绝原因和实际语言/修改类型分布；
- repository-family / problem-ID 隔离与外部黑名单报告；
- public/hidden/regression 构造脚本版本及覆盖统计；
- 最终 split manifest 和 SHA256；
- 不足配额、不可重放样本和与本 ADR 偏差的显式报告。

上述证据完成前，只能称“组成和目标配额已冻结”，不能称“正式数据集已经构建完成”。
