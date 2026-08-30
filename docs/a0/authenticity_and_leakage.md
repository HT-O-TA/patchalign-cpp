# A0 真实性、污染与泄漏声明

状态：Draft  
版本：`0.1.0`

## 1. 证据等级

| 等级 | 定义 | 可以声称 |
|---|---|---|
| Plan | 文档或配置尚未运行 | “计划”“设计”“待验证” |
| Synthetic test | 合成 fixture 或 tiny model 测试 | 接口、分支和错误处理可运行 |
| Smoke | 真实环境/模型的小规模运行 | 兼容性和最小链路通过 |
| Pilot | 真实数据小规模实验 | pilot 条件下的观察 |
| Frozen evaluation | 冻结数据、协议和 artifact | 可报告的模型比较 |
| Replicated result | 多 seed/重复或独立复现 | 稳定性范围内的结论 |

低等级证据不能包装成高等级结论。

## 2. 当前真实状态

- 已完成 G0 真实模型 smoke；
- 未下载或处理正式训练数据；
- 未运行 Base 冻结基线；
- 未完成 SFT 或 DPO；
- 未获得任何修复 Pass@1 提升；
- 未完成安全执行沙箱；
- 未建立简历可用的质量数字。

## 3. 数据污染声明

本项目能控制的是本人后训练数据：

- 外部 benchmark repository family 从训练源拉黑；
- 先按仓库族切分，再生成样本；
- 精确和近似去重；
- 训练输出与外部 gold patch 交叉审计；
- manifest、revision 和哈希可追溯。

基础模型预训练数据不可完全审计。因此只能声明：

> 已采取措施减少本人后训练数据对冻结评测集的污染；基础模型预训练污染未知。

禁止声明“完全无污染”。

## 4. 归因边界

- Qwen3-8B 的现成能力属于外部 post-trained 基线；
- Base 模型已有代码知识不能归因于本人；
- harness、prompt、采样预算和 Agent 改进必须与 checkpoint 改进分开；
- 只通过 public tests 不能声称修复成功；
- smoke 单步 loss 不能声称完成训练；
- 合成数据收益不能外推为真实仓库能力。

## 5. 禁止表述

- 未真正运行的训练或评测；
- 没有原始预测和执行日志支持的百分比；
- 在训练集上的提升作为泛化结论；
- 删除失败 run 后只报告成功配置；
- 把厂商 Instruct 能力全部归为本人 SFT/DPO；
- 把未参与隐藏测试的 public pass 写成最终成功；
- 把 GPU 可加载写成模型质量提高。

## 6. 报告模板

每个正式结论至少附带：

```text
claim
evidence level
git commit
config hash
model id/revision/hash
dataset manifest/hash
seed
Slurm Job ID
prediction artifact/hash
execution artifact/hash
metric script/hash
known limitations
```

## 7. 未决公开策略

以下内容需用户后续决定：

- adapter 是否公开；
- 训练数据派生物公开到何种粒度；
- 完整预测和失败日志是否公开；
- 受原仓库许可证约束的 patch/context 如何分发；
- 祝融内部路径在公开报告中如何脱敏。

