# ADR-0015：RunBugRun v2 来源许可与训练边界

- 状态：Accepted under delegated project decision authority
- 日期：2026-09-07

## 问题

RunBugRun v2 发布了大规模、可执行的 buggy/fixed 程序对，但项目说明要求使用者
分别检查原始来源条款。它聚合的 Project CodeNet 数据包含 AtCoder、AIZU 等竞赛
平台提交。数据集或采集代码仓库的开源许可证，不能自动证明每条第三方程序提交
都已获得用于模型训练、再分发或衍生权重发布的授权。

官方 Project CodeNet 仓库标注 Apache-2.0，同时说明数据来自 AtCoder 与 AIZU；
CodeContests 也明确区分仓库材料许可与第三方代码/数据的独立权利。当前 AtCoder
条款说明程序著作权属于提交者，并把第三方 AI 训练使用与用户同意或授权关联；
其单独公告还提供训练许可的 opt-out。现有证据不足以把这些当前规则反推为
RunBugRun/CodeNet 历史数据中每条记录在采集时的授权状态。

本决策不是法律意见，也不宣称任何上游数据侵权；它只定义本项目在证据不足时
采用的 fail-closed 工程边界。

## 决定

1. RunBugRun v2 不作为 Data-v2、SFT 或 DPO 的训练供给；
2. 在不下载程序正文、测试正文或完整数据库的前提下，可以继续读取官方发布页、
   schema 和规模元数据，用于容量、problem-family 差量和执行机制研究；
3. `runbugrun.sql.lrz` 的完整下载继续保持未授权。若未来确有必要，必须先建立独立
   最小字段协议，证明不会把未获训练许可的代码或测试导入训练流水线；
4. 只有逐条可追踪到原始平台、能证明适用的训练/再分发授权，并能排除授权不明
   或 opt-out 内容时，才允许发布新版本 ADR 重新评估训练准入；
5. 该决定不回写或伪造此前基于 legacy RunBugRun 完成的实验事实。历史模型、数据
   和报告在对外发布前仍须保留来源限制说明，不把项目代码的 Apache-2.0 许可证
   解释为上游数据或衍生权重许可。

## 对当前路线的影响

- GitHub 自建、逐仓库许可证核验的真实修复池仍是 Data-v2 主路线；
- RunBugRun v2 不再承担 GitHub 容量门失败后的训练兜底，避免用更大规模的同域
  竞赛短程序制造“数据扩展”假象；
- 若 GitHub 路线失败，应转向能提供逐仓库身份、许可证和提交 provenance 的独立
  来源，并重新过相同污染与执行门，不能降低 Data-v2 冻结阈值；
- 当前作业和评测均不受影响，因为正在执行的 GitHub discovery 只读取公开身份
  元数据，不读取 RunBugRun v2 内容。

## 官方依据

- RunBugRun：<https://github.com/giganticode/run_bug_run>
- Project CodeNet：<https://github.com/IBM/Project_CodeNet>
- CodeContests：<https://github.com/google-deepmind/code_contests>
- AtCoder Terms of Service：<https://atcoder.jp/tos?lang=en>
- AtCoder AI training opt-out notice：<https://atcoder.jp/posts/opt-out-notify-en>
- PIE4Perf：<https://github.com/madaan/pie-perf>

