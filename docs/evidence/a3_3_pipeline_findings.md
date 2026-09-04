# A3.3 正式实验问题与论文材料

日期：2026-09-04
状态：持续更新；本文件记录正式实验中具有方法学价值的问题，不把失败作业误写成模型质量结论。

## 记录原则

每个问题保留作业编号、可复核现象、直接原因、处理策略和对论文表述的影响。只记录有证据支持的结论；排队时间、偶发节点状态等纯运维噪声不进入论文结论。所有失败产物均与后续有效产物分目录保存，禁止覆盖。

## 已确认问题

### 1. 全量资格回放无法在单次时限内完成

- 证据：Job 94111 运行 06:00:29 后 TIMEOUT，MaxRSS 98766828K；已完成 133 项测试、Bubblewrap 自检及 900/250 候选构建，但未生成正式 holdout。
- 根因：1,150 个候选共 109,024 个测试实例，旧流程全部回放结束后才选样和写盘，无法利用已经完成的中间计算。
- 修正：按固定任务层和候选顺序分批回放，每个候选原子写入检查点；恢复时核验候选 manifest、沙箱和匹配器身份。
- 论文意义：真实可执行代码修复数据的资格验证成本主要受测试实例数和双重稳定回放支配，候选数本身不足以估算成本。实验系统应把可恢复性作为数据构建协议的一部分。

### 2. 冻结配额超过真实合格样本容量

- 证据：Job 94175 报告 RunBugRun/function 请求 2,973、最多得到 2,930；Job 94288 报告 CommitPackFT/function 请求 1,320、最多得到 1,284。
- 根因：预设的来源比例、任务层比例和真实过滤后容量不能同时精确满足。
- 修正：保持总量 5,000/500、验证集 200/300 来源构成、family 隔离、Schema 和 token 门禁不变；首次调整后，加入 prompt-token 门禁的新 holdout 又排除了 1 个训练 family，最终训练来源冻结为 CommitPackFT 2,044、RunBugRun 2,956，训练任务层冻结为 function 4,213、file_window 787。相对原 85/15 任务层目标偏移 37 条，即总训练集的 0.74 个百分点。
- 论文意义：数据组成应报告过滤后的实际联合分布，而不能只报告边际目标。本文将该调整作为真实数据容量约束下的预注册修订，不合成样本填配额，也不放宽隔离条件。

### 3. 候选满足来源过滤但不满足最终 Schema

- 证据：Job 94295 在最终 Schema 校验发现 3 条 RunBugRun function 样本的 changed_logical_lines 为 1，低于该任务层最小值 2。
- 根因：构建器先计入配额、最后统一校验，导致无效候选占用了配额。
- 修正：每条候选在接纳前执行 Sample Schema v0.2 校验；失败候选记录拒绝原因并继续取下一条。Job 94304 随后完成 5,000 train + 500 validation，135 项测试通过。
- 论文意义：后置 Schema 校验只能发现错误，不能保证固定规模数据集可构建；流式“校验后接纳”才能使数据规模和有效性同时成立。

### 4. 训练 token 门禁未覆盖正式 holdout 的真实提示

- 证据：Job 94305 在模型加载前 38 秒失败；500 条中仅 case `rbr-formal-26136d9ab1aa0d762126` 超限，按正式 raw-completion 模板渲染为 9,876 tokens，冻结上限为 4,096；其余样本不超过上限。该作业未生成 predictions，仅留下不完整状态文件，不构成基线结果。
- 根因：原 preflight 校验了 SFT train/validation 编码长度和 holdout 数量，但未用正式推理模板、正式 tokenizer 和 public test 对全部 holdout 计算输入长度。
- 修正：资格选择新增模型绑定的精确提示 token 门禁；执行资格缓存与 token 门禁解耦，因此可复用既有 800 条双重回放结果。正式 preflight 同样对 500 条 holdout 重新渲染并 fail closed，防止 GPU 作业再次承担数据验证。
- 论文意义：源代码长度并不等于模型输入长度，测试输入、模板和 tokenizer 都会改变最终上下文长度。训练集和评测集必须使用各自真实消费路径进行长度验证。

### 5. Holdout 修订会改变训练候选容量

- 证据：新 holdout 通过 token 门禁后，Job 94313 报告 RunBugRun/function 请求 2,930、最多得到 2,929；与 Job 94304 使用的旧 holdout 相比恰好少 1 条。
- 根因：替换评测样本不仅改变评测 manifest，也改变必须从 SFT 中排除的 problem family；该影响只能在新 holdout 上重新执行联合配额选择后观测。
- 修正：将 1 条训练配额从 RunBugRun/function 转为 CommitPackFT/file_window；总量不变，来源和任务层边际各变化 1/5,000（0.02 个百分点）。Job 94314～94319 未运行即取消。
- 论文意义：评测集与训练集的隔离约束会让两者的冻结过程产生依赖，不能把 holdout 替换视为局部、无副作用的数据操作。

### 6. 冻结配置与独立验证器发生漂移

- 证据：Job 94320 已成功构建 5,000/500 数据和哈希锁，但 preflight 报告 `wrong task-level counts`；验证器仍写死修订前的 4,214/786 和 2,043/2,957。
- 根因：正式 JSON 配置、构建器常量和独立 fail-closed 验证器分别维护同一配额；原测试只检查前两者一致，没有调用第三者。
- 修正：同步验证器的冻结常量，并在配额一致性测试中直接调用 `validate_config`。Job 94321～94326 未运行即取消，Job 94320 的 SFT 以 preflight 未通过状态归档。
- 论文意义：冗余验证能阻止错误实验，但重复维护的冻结常量本身会产生配置漂移。实验系统应为每项冗余断言提供跨组件一致性测试，并把 preflight 作为正式产物有效性的必要条件。

## 已冻结且未放宽的条件

- 正式 holdout 仍为 400 function + 100 file_window。
- 最大输入仍为 4,096 tokens，超长样本由后备合格候选替换。
- 保留 exact payload 去重、problem/repository family 隔离、每 family 每 split 最多 2 条。
- 保留 Sample Schema v0.2、Bubblewrap、buggy/fixed 双重稳定回放及输出匹配规则。
- 不把 Job 94305 计为 M0 结果，不把数据管线修正计为模型提升。

## 当前有效数据证据

Job 94304 完成的旧 holdout 绑定版本在发现超长提示后停止用于正式 GPU 实验，相关产物将只读归档。其 SFT 构成为：

- train：5,000；CommitPackFT 2,043、RunBugRun 2,957；function 4,214、file_window 786；
- validation：500；CommitPackFT 200、RunBugRun 300；function 425、file_window 75；
- train 修改类型：single_line 2,703、multi_line 2,150、add_helper 64、refactor 83；
- validation 修改类型：single_line 255、multi_line 235、add_helper 6、refactor 4；
- 构建阶段额外拒绝 3 条 Schema 不合格样本。

因为替换 holdout 会改变 family 排除集合，正式 SFT、数据锁和 preflight 必须一起重建；不能只替换评测样本后继续使用旧训练集。

## 可用于论文的方法学表述草案

“我们采用 fail-closed 的分阶段数据冻结流程：执行资格、稳定性、数据隔离、Schema 合法性以及模型实际输入长度均在 GPU 推理前完成。资格回放结果以候选粒度持久化，允许在不改变筛选策略的前提下恢复长时数据验证。对于真实数据容量不足，我们保持总样本规模和有效性约束，仅对来源与任务层的联合配额作最小、可审计调整，并报告实际分布。”

## 待回填

- 加入提示 token 门禁后的 holdout manifest、资格报告和 token 分布哈希；
- 重建后的 SFT manifest、formal data lock 和 preflight 哈希；
- 新作业链编号、各阶段用时、CPU/GPU/内存峰值；
- M0、SFT、M1 的正式生成与评分结果；
- 失败样本类型是否与源码长度、测试输入长度或任务层相关的后续统计；
- 外部 Defects4C 门禁结果；完成前不得宣称完整 promotion gate 通过。
