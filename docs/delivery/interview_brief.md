# PatchAlign-Cpp 简历与面试复述提纲

本文只提供求职表达，不替代[最终技术报告](final_report.md)、[模型卡](model_card_m1_r2.md)或
[artifact manifest](README.md)。正式投递前，最终模型和 DPO 指标必须与聚合产物一致。

## 项目定位

当前推荐把 PatchAlign-Cpp 作为 AI 应用开发方向的第二项目：它展示的不是通用聊天界面，而是如何把
代码模型接入结构化输入、受约束生成、隔离执行、质量门禁和可追溯交付。若投递后训练岗位，则把重点
切换到数据隔离、QLoRA/DPO、独立开发集选型和固定分母评测；不要同时堆满两个叙事。

## 30 秒版本

“我实现了一个面向局部 C++ 缺陷修复的可验证 AI 系统。用户提交 buggy code 和公开失败示例，
Qwen2.5-Coder-7B 加 LoRA adapter 生成严格 unified diff；输出先做单文件和路径校验，再在 rootless、
禁网、限时的 Bubblewrap 中应用、编译并运行公开、隐藏和回归测试。项目同时包含 QLoRA SFT、真实
执行反馈偏好数据和 DPO，但最终模型不是看训练 loss 决定，而是通过独立开发集选型和三套冻结正式
评测门禁决定。所有运行都绑定 Git commit、模型 revision、配置和 artifact SHA256。”

## 简历 bullet：AI 应用开发版

- 基于 Qwen2.5-Coder-7B 与 LoRA 构建局部 C++ 修复应用，将 JSON 请求转换为冻结 prompt 和严格
  unified diff；实现路径白名单、格式校验、模型/补丁哈希、延迟和显存 metadata，避免模型直接修改
  或执行宿主仓库。
- 建立 rootless Bubblewrap 执行闭环，以 `git apply --recount`、编译、public/hidden/regression tests
  和按需 sanitizer 代替文本相似度评测；使用固定分母、逐案例原子 checkpoint 和 Slurm 依赖链处理
  超时、节点异常与长任务恢复。
- 完成 Base→QLoRA SFT→DPO 的可复现模型适配：正式 SFT 将 500 条评测上的严格 diff 从 0 提升至
  499，并取得 14 个端到端 Pass；从 1,056 个真实执行候选中审计形成 175 对偏好数据，再通过 64 条
  独立 executable dev 选择 DPO 候选，最终只允许冻结正式门禁决定交付模型。

简历版不建议写“自动修复生产代码”或“显著提升泛化能力”。系统当前生成候选补丁，自动合并仍需
人工确认；独立确认集和外部集的历史结果说明语义泛化仍有限。

## 简历 bullet：后训练岗位版

- 为 7B Base 模型搭建 NF4 QLoRA SFT/DPO 管线，冻结 model revision、数据/环境哈希、prompt、seed、
  训练参数和退化上限；以真实编译测试结果构造 chosen/rejected，而非使用 gold 相似度作为偏好标签。
- 对 182 对源偏好执行防泄漏审计，排除 7 对 timeout-only，得到 175 对 DPO 输入；完成 beta=0.1/0.3
  控制变量训练，并在与偏好训练 family 零重叠的 64 条执行开发集上按预注册规则选择 beta=0.3。
- 将 parse、apply、compile、public、hidden、regression、timeout 分层统计并做 paired bootstrap；保留
  负结果和安全退化，证明协议遵循、工程可执行性与端到端语义正确率必须分别评估。

## 系统链路

```text
JSON repair request
  → request/schema validation
  → frozen prompt
  → Qwen2.5-Coder-7B Base + LoRA
  → strict unified diff / path policy
  → rootless Bubblewrap
  → git apply --recount
  → build
  → public → hidden → regression → optional sanitizer
  → structured result + hashes + model gate
```

CLI 本身只负责生成和校验候选，不执行或合并不可信代码。真实执行由沙箱评分层承担；这是有意的权限
边界，而不是功能遗漏。架构细节见[架构与数据流](architecture.md)，运行方法见[复现指南](reproduction.md)。

## 最值得讲的工程案例

### 情境

正式 SFT 在 function Pass 上达到主提升要求，但新增 3 个 timeout，使总体质量门禁失败。只看平均 loss、
parse 或 compile 都会误判模型已经改进。

### 行动

保持固定分母和原始预测不变，在相同 Bubblewrap、2 GiB 和 3 秒限制下分别重放 buggy、fixed 与模型
补丁；逐例定位到循环变量不推进和复杂度爆炸。随后只从训练/validation 中静态选择一般风险模式做
SFT-R2，不读取 holdout 参考答案，并复用同一 prompt 与评分协议。

### 结果

R2 将 timeout 从 3 降到 2、regression failure 从 5 降到 3，apply/compile 从 391/373 提高到
412/392，但 Pass 从 15 降到 14。这个结果说明安全指标之间会迁移，也说明为什么产品选择必须依赖
多目标门禁，而不能事后只挑一个好看的指标。

## 可核验数字

| 项目 | 数字 | 能说明什么 |
|---|---:|---|
| 正式 SFT 数据 | 5,000 train + 500 validation | 真实训练规模，不含 holdout |
| 正式 internal holdout | 400 function + 100 file-window | 固定 greedy Pass@1 分母 |
| 独立 confirmation | 100 function + 24 file-window | 防止只在旧 holdout 上优化 |
| Defects4C external | 176 function | 外部项目分布，但 LLVM 占 139 条 |
| A4 执行候选 | 1,056 | 264 题 × 4 个候选，全部真实评分 |
| DPO 训练输入 | 175 对 | 从 182 对排除 7 对 timeout-only；75 对 chosen 为完整 success |
| DPO 训练 | 2 个 beta，各 2 epochs / 44 steps | 控制变量消融，不做结果驱动搜索 |
| DPO dev | 64 条 | 三模型均 5 Pass；beta=0.3 以 apply/build 57/57 胜出 |
| 当前自动验收基线 | 434 passed | 最终评测 preflight 的全仓测试证据 |

最终 formal/confirmation/Defects4C 的 DPO 数字、门禁结果和推荐 adapter 只从最终聚合产物引用，不在
本文提前猜测。

## 常见追问

### 为什么不用 BLEU 或 patch 相似度？

同一个缺陷可能有多个语义等价补丁，文本不同不代表错误；相反，与 gold 很像也可能无法应用、无法
编译或破坏隐藏行为。因此端到端 Pass 必须来自真实执行，文本指标最多只能做诊断。

### `git apply --recount` 是否放宽过头？

它只重新计算 hunk 头声明的行数，删除行和上下文仍必须与目标文件匹配；项目没有启用忽略空白、三路
合并或部分应用。内容找不到仍然是 apply failure。

### 为什么 Base 的 parse 很差？

项目固定使用 Base 而不是 Instruct，并要求 raw completion 只输出一个 unified diff。SFT 的首要收益是
学会输出协议；这不能自动推出修复语义已经泛化。

### 为什么开发集三者 Pass 相同还选择 beta=0.3？

选择规则在看结果前冻结：先要求无 regression/timeout 退化和正执行信号，再按 Pass、hidden、public、
compile、apply 的层级比较。三者 Pass/hidden/public 相同，beta=0.3 的 compile/apply 最高，因此胜出；
它仍必须经过一次性正式评测，不能把 dev 结果当最终结论。

### 为什么没有继续调参或做 RLVR/GRPO？

当前目标是简历级、可复现的 AI 应用交付。一次 beta 消融、独立 dev 和三套正式评测已经能证明完整
工程方法；继续搜索会增加选择偏差和成本。RLVR/GRPO 只有在本轮交付闭环后才作为可选扩展评估。

## 诚实边界

可以声称：实现了真实 Base/SFT/DPO 训练、严格补丁接口、隔离执行、正式评测、故障恢复和 artifact
追踪；所有主要正负结果都有 Job、commit 与 SHA256。

不能声称：模型适用于任意仓库、多文件修复或生产自动合并；通过 parse/apply/compile 就等于正确；
训练数据和 adapter 已获准公开再分发；单 seed 结果等价于多次重复实验。
