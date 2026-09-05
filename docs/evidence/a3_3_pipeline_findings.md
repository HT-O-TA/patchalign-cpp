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

### 7. Prompt 输入模式原为隐式常量

- 证据：Job 94328 已再次稳定构建相同 5,000/500 数据，但新增 holdout token preflight 访问不存在的 `base_model_inference` 字段并失败；正式推理脚本此前直接写死 `raw_completion`。
- 根因：输入模式是正式推理行为的一部分，却没有作为正式训练/评测配置字段冻结；preflight 接入该行为时错误假设了配置结构。
- 修正：在 `evaluation.input_mode` 显式冻结 `raw_completion`，配置验证器、preflight 和正式推理共同读取该字段；Job 94329～94334 未运行即取消。
- 论文意义：提示模板相同不代表模型输入相同，chat template 与 raw completion 会产生不同 token 序列。输入模式必须进入可哈希配置，并由数据门禁和推理共享。

### 8. Base 模型在正式规模下没有遵守补丁输出协议

- 证据：M0 Job 94338 在冻结 500 条 holdout 上完成 500/500 生成，无 generation failure、OOM 或 timeout，3 条确定性 probe 逐字节稳定；但 `strict_diff_count=0`。scoring v2 Job 94339 将全部 500 条终态分类为 `parse_failed`，其中 function 400/400、file_window 100/100。
- 传输排除：scoring v2 对 478 条缺少终止 LF 的输出只追加一个 LF，仍没有任何输出形成合法 unified diff；因此不能把本结果归因于 A3.0 曾发现的单个换行传输问题。
- 解释：在冻结 raw-completion 输入、greedy decoding 和 512-token 输出预算下，未经指令微调的 Base 没有按要求生成唯一纯 unified diff。该结论只适用于本模型 revision、prompt 和评测集，不外推为 Base 模型一般能力。
- 方法学意义：格式遵循本身是代码修复流水线的首个质量瓶颈；若只统计可解析补丁，会删除全部 Base 失败并破坏固定分母。SFT 的正式比较应同时报告 parse、apply、compile 和最终 Pass，区分“学会协议”与“学会正确修复”。
- 关键身份：
  - predictions SHA256：`dadf0cfe5c0178ed3b2497536c8509a8437f9f8461f7c10ec86591cd99d7429e`；
  - run manifest SHA256：`8c35904e2ab2f5118c9b8fbec7913c51a45394779dc03a38e5421d3e2e28a87d`；
  - scores SHA256：`92ceb428df80ed772a2c9ce4dfaefd0f3d9b36fd7d96cc74e5cafd538fd6df3d`；
  - score summary SHA256：`f183fa2cf203c2be95dbab1a56bfe13ec9718c117da14f0ed0592c45376a5ed0`；
  - score manifest SHA256：`6e1b6f097c30f602a43b93cacff2cda83d589cfabccc5528755c0efab549ae6d`。

### 9. SFT 主修复率提升，但三条危险补丁造成真实超时退化

- 正式结果：M1 Job 94341 完成 500/500 生成，scoring Job 94342 得到 parse/apply/compile/Pass 499/391/373/15；function Pass 为 12/400，相对 M0 提升 +3pp，paired bootstrap 95% 区间为 +1.5pp～+4.75pp。主提升门通过，但 3/500 timeout 相对 M0 增加 0.6pp，超过冻结上限 0.5pp，Job 94343 因此给出 `internal_gate_passed=false`。
- `rbr-formal-020137ad770189b0c280`（p02549）：模型把 `modify(1, 1)` 改为 `modify(0, 1)`。Fenwick 更新循环在 `x=0` 时执行 `x += x & -x` 后仍为 0，形成确定性死循环。参考补丁实际修正区间查询右端的 off-by-one。
- `rbr-formal-27a1be561eea53c3ae8e`（p03352）：模型把循环保护条件从 `j == 1` 改为 `j == x`。外层 `i=1` 时 `j *= i` 永远保持 1，输入 `x>1` 时形成确定性死循环。参考补丁把内层初值从 `i` 改为 `i*i`。
- `rbr-formal-29456a56a2c230497296`（p02968）：模型把外层界限从 `i <= N` 改为 `i <= M`。公开样例为 `N=21, M=5139566`，使带二维 DP 分配的循环从 22 轮扩大到约 514 万轮，造成确定性的复杂度爆炸。参考补丁实际修正内层 `k` 的上界。
- 排除环境噪声：资格回放中三例的 buggy 与 fixed 均无 timeout，public 最大耗时分别不超过 1.120/0.068/0.067 秒（buggy）和 0.118/0.036/0.368 秒（fixed）。CPU-only Job 94493 在相同 Bubblewrap、2 GiB 内存和 `-O2 -std=c++17` 下，对每例首个 public test 做 3 秒对照；buggy/fixed 均在 0.04 秒内退出，而三条 M1 补丁均在 3.00 秒超时且无输出。故三例均是模型引入的真实运行时退化，不应重分类为集群抖动。
- 诊断审计：Job 94491 因 `sbatch --wrap` 默认 `/bin/sh` 不支持 `set -o pipefail` 而在执行前失败；Job 94492 因登录节点 `/tmp` 不与计算节点共享而在执行前失败；共享 Git 忽略目录上的 Job 94493 为 `COMPLETED 0:0`、用时 19 秒、无 GPU。两次无效提交不构成模型实验。
- 方法学意义：可编译、可应用并不保证补丁安全。对循环初值、循环边界和索引更新的错误单行修改可把快速程序变成死循环或复杂度爆炸；timeout 应保留为独立门禁，而不能并入普通 public failure 或为了主指标提升而事后放宽。
- 证据路径：`artifacts/a3/diagnostics/timeouts-94342-repro-v1/reproduction.json`，SHA256 `d60940873639974eeec8d2015ad9b26a1a12146b8b6cc2436d9614f688c2ef7a`；正式 comparison SHA256 `13e1a0b39f74cae60fb633ea77c5d53f9573a622743dfe148c37f3b605396517`。

### 10. 外部评分 rootfs 未继承可用的 Python 导入路径

- 证据：M0/M1-R2 外部 GPU Job `94928`/`94929` 均完成 176/176；随后评分数组 `94930` 中，所有需要进入 rootfs 的案例均在约 1 秒内失败，只有 4 条可在 parse/policy 阶段提前终止的案例写出检查点。诊断 Job `95140` 保留了此前被丢弃的子进程输出，显示 `ModuleNotFoundError: No module named 'scripts'`。
- 根因：外层 Slurm 的 `PYTHONPATH` 使用宿主机 `/mingli01/...` 路径，Bubblewrap 内只挂载为 `/patchalign`；runner 以 `scripts/external/*.py` 文件直接启动时，Python 默认搜索路径不包含 `/patchalign`，因此无法导入顶层 `scripts` 包。
- 修正：rootfs 命令显式设置 `PYTHONPATH=/patchalign/src:/patchalign` 与 `PYTHONDONTWRITEBYTECODE=1`，并让解析异常保留最近 4,000 字符子进程输出。提交 `bff21bc` 通过专项 11 项和全量 243 项测试；单样本 Job `95141` 用时 5 分 17 秒完成，M1-R2 真实经历 apply、fixed build 和 patch build，最终正常分类为 `build_failed`。替换数组 `95144` 复用冻结预测和既有有效检查点。
- 方法学意义：隔离运行时的路径命名空间也是实验契约的一部分。preflight 只证明环境可启动并不能覆盖每个实际 runner 的 import graph；失败包装必须保留子进程输出，否则基础设施错误会被压缩成无信息的“未返回结果”。此问题不构成模型失败，也不改变固定分母。

### 11. 外部前置阶段大幅改善，但最终 Pass 没有提升

- 证据：176 条 Defects4C 固定分母上，M0 parse/apply/build/Pass 为 94/24/17/1，M1-R2 为 174/72/55/1；双方 timeout 均为 0。配对转换各有 1 条 introduced 和 1 条 resolved，最终差为 0，bootstrap 95% 区间为 `-1.7045pp～+1.7045pp`。
- 门禁解释：最大允许外部 Pass 退化为 2pp，本轮无退化，因此 Job `95150` 给出 `external_gate_passed=true`。该布尔值只说明没有触发外部退化上限，不能改写为 M1-R2 在外部分布上优于 M0。
- 方法学意义：SFT 把 strict diff 遵循和可构建补丁数量提高数倍，但端到端正确修复仍停留在 1/176。格式、apply 与 build 是必要的漏斗阶段，不是最终质量代理；外部门禁采用“最大退化”语义时尤其要同时报告原始计数和配对转换。
- 泛化边界：冻结集 139/176 来自 LLVM，不能代表均衡 C++ 生态；同时独立确认集仍为 0/124 且出现回归/超时，因此 readiness 必须由确认集 blocker 保持失败。

### 12. A4 冻结备用池与真实测试覆盖不可同时满足

- 证据：CPU Job `95574` 在 243 项测试通过后，于第 14 个候选触发 `A4 test source missing`。全量审计显示冻结训练中 27 个 file-window 仅 26 个具有至少 5 条测试，原稳定排序还会选入 75 个少于 5 条测试的 function。
- 根因：配置在未对固定输入做全量可满足性检查时，同时冻结了候选池数量和最小测试覆盖；单元测试只构造数量足够的合成行，没有覆盖真实 tests 映射。
- 修正：保留至少 5 条测试、双重回放和最终 256+8 目标；排序前过滤测试覆盖，并将 file-window 备用池最小修正为 26。关联 GPU Job `95575` 未运行即取消，部分目录归档；提交 `a0caffc` 通过 243 项测试和真实数据 626 条选择审计，新链为 `95586 → 95587`。
- 方法学意义：配置文件能通过 schema 与单元测试，不代表冻结约束在真实输入上可同时满足。数据阶段 preflight 应同时验证“硬阈值、分层配额、去重约束”的联合可行域，并区分最终目标规模与备用候选池规模。
- 解释边界：修正发生在资格结果和模型输出产生前，且没有降低质量阈值或最终组成，因此属于输入可行性勘误，不是观察结果后的样本筛选。

## 已冻结且未放宽的条件

- 正式 holdout 仍为 400 function + 100 file_window。
- 最大输入仍为 4,096 tokens，超长样本由后备合格候选替换。
- 保留 exact payload 去重、problem/repository family 隔离、每 family 每 split 最多 2 条。
- 保留 Sample Schema v0.2、Bubblewrap、buggy/fixed 双重稳定回放及输出匹配规则。
- 不把 Job 94305 计为 M0 结果，不把数据管线修正计为模型提升。

## 正式数据证据

Job 94337 在 Git 提交 `b9aa00248d4264eca0f75c378b004f462ddea9a6` 上完成最终冻结与 preflight：

- holdout manifest：`5c438d36a0d4efc833dd6d0d26c67a1579f2c2e26de13f42ce01a809c07c3386`；
- qualification results：`4fcee2470087d2a5f525555682caf6729a039a8e10afe0241b29f7d51364a08d`；
- SFT dataset manifest：`50b0dd1b49a7f14297e2e70871be910673b725ece8de4795938548d256384c02`；
- formal data lock：`f37eef03ce0a96ad1fa14622b8b7ef6f30c3f6bcc8dad85addbb1e4c53d12a12`；
- preflight report：`c398dfc3a1539ec65c23b38865f26b73745dc8e6db280a0ac8d9cbfdde067922`；
- train：5,000；CommitPackFT 2,044、RunBugRun 2,956；function 4,213、file_window 787；
- validation：500；CommitPackFT 200、RunBugRun 300；function 425、file_window 75；
- train/validation 最大编码长度分别为 3,461/2,198；holdout 500 条实际 prompt 为 170～3,589；
- 修改类型仍为 train 2,703/2,150/64/83、validation 255/235/6/4（single/multi/add-helper/refactor）。

Job 94304 的旧 holdout 绑定版本、Job 94320/94328 未通过 preflight 的 SFT 和 Job 94305 不完整 M0 均保留在 history，不进入正式结果。有效运行身份为 M0 94338、M0 评分 94339、SFT 94340、M1 94341、M1 评分 94342、比较 94343；实时状态见[项目状态](../status.md)。

## 可用于论文的方法学表述草案

“我们采用 fail-closed 的分阶段数据冻结流程：执行资格、稳定性、数据隔离、Schema 合法性以及模型实际输入长度均在 GPU 推理前完成。资格回放结果以候选粒度持久化，允许在不改变筛选策略的前提下恢复长时数据验证。对于真实数据容量不足，我们保持总样本规模和有效性约束，仅对来源与任务层的联合配额作最小、可审计调整，并报告实际分布。”

## 待回填

- 全体非成功样本的错误类型、源码长度、测试输入长度和任务层关联统计；
- A4 可执行候选的评分分布、偏好对产量和质量审计；
- 针对循环/复杂度危险修改的后续候选过滤方案及预注册复评。
