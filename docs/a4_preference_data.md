# A4 可执行偏好数据与保守配对协议

本文记录负责人授权的 exploratory A4 输入、协议和解释边界，不维护实时 Job 状态；当前进度见 [`status.md`](status.md)。该授权不等同于 A3.4 promotion success。

## 目标与边界

A4 只研究能否从同一训练样本的多个模型 completion 中提取可复现的执行偏好信号。来源限定为 A3.3 冻结 train 中的 RunBugRun C++，不消费 validation、internal holdout、confirmation、Defects4C，也不把 gold patch、fixed source、hidden tests 或执行反馈交给模型。

pre-A4 readiness 的机器事实保持 `a4_ready=false`，唯一 blocker 为独立确认集失败。负责人通过 ADR-0006 授权失败模式研究；A5/DPO 必须在 A4 质量报告后另行决定。

## 已冻结输入

- 可执行案例：264 条，其中 function 256、file-window 8；source manifest SHA256 为 `8cba1ec5472a4f4443b766c8fa136f6e928d3911feec9e06457a377775095495`。
- 生成模型：M1-R2；每例 4 个采样候选，temperature 0.7、top-p 0.95。
- 候选总数：1,056，全部生成成功；1,055 条为 strict unified diff；候选 SHA256 为 `ca497dbdd4a989c889d48d2fd9db7b77b4de4d3c327796665a1bde54e7ef0c67`。
- 评分：A3 scoring v2、`git apply --recount`、rootless Bubblewrap、固定 public/hidden/regression 顺序；全部案例的 sanitizer 均明确不适用。

## 排序与配对

ADR-0008 在看到执行结果前冻结以下规则：

1. 终止阶段从差到好依次为 generation、parse、policy、apply、build、public、hidden、regression、sanitizer、success。
2. 同一终止阶段只允许用 timeout 区分，无 timeout 优于 timeout；不用 patch 长度、局部测试比例或 gold 相似度细排。
3. 只在同一 case、同一 prompt 的四个候选内比较；每例最多形成一对，选最高档为 chosen、最低档为 rejected。若最高与最低排序键相同则不生成偏好对。
4. candidate index 只用于并列时的确定性选择，不代表质量。
5. 训练用 `preferences.jsonl` 只含 prompt、chosen/rejected 原始响应、身份与内容哈希；执行证据单独写入 `pair-audit.jsonl`。

## 可恢复执行

评分按 264 个案例拆分为 Slurm 数组，每个任务一次评分同题四候选并原子写入 checkpoint。preflight 同时检查干净工作树、完整测试、输入/配置/ADR/Schema/环境/Bubblewrap 哈希；聚合只有在 264 个 checkpoint 和 1,056 个唯一候选完整时才运行。

## 最终结果

CPU-only preflight Job `95651` 在排除异常节点后于 `gpu25` 用 18 秒完成 `249 passed` 和全部身份检查。评分数组 `95670` 完成 264/264 个案例 checkpoint，聚合 Job `95671` 用 2 秒完成，均为 `COMPLETED 0:0`。

- 1,056 个候选：parse 1,055、apply 805、compile 780、public 136、最终 Pass 123；regression failure 4、timeout 11。
- function 1,024 个候选中 Pass 112（10.94%）；file-window 32 个中 Pass 11（34.38%）。file-window 只有 8 个案例，不能据此宣称任务层优势。
- 77/264 个案例至少有一个成功候选，经验 Pass@4 为 29.17%；成功候选数为 0/1/2/3/4 的案例分别有 187/45/20/10/2 个。
- 182 个案例形成偏好对，82 个无严格差异而放弃；function/file-window 为 175/7。
- 75 对 chosen 为完整 success；其余 107 对只表示到达更晚执行阶段或同终态无 timeout。175 对由终止阶段区分，7 对仅由 timeout 区分。

最终 artifact：

- scores SHA256：`c218cd58ab05a8b7fa59188163cbfaabdf206b4482185cf297e1f63ff2e1cee2`；
- preferences SHA256：`5e6b56e4417d49d0a9fcf85e2ec37d3a4b1e358fda870737adea5ae8c0f578bf`；
- pair audit SHA256：`bcaf461d09e2f54f5b68e30e9a17025ada1c6827b9cb1829556445519b8b6ad2`；
- summary SHA256：`302e7a9aed6759373f579cee88027fc5991161a28d194e960d409a67261e6fc8`；
- run manifest SHA256：`03c61f0e3a376d4879274880634d8d12f4359d03775aa4b7c726cb3d844c7cbe`。

独立审计确认 1,056 个 candidate ID、182 个 pair ID 均唯一；所有 pair 通过 Schema，训练文件未出现 gold、fixed、测试路径或终态字段，manifest 内各文件哈希与实际字节一致。

## 工程观察

首次 preflight `95651` 和原数组 `95652` 被调度到 `gpu16` 后均出现零日志、零 checkpoint；将同一 preflight 重排、并以排除 `gpu16` 的替换数组运行后，分别在 18 秒内通过并快速产生 checkpoint，证明问题在节点侧而非代码。原数组与未运行聚合 `95653` 被取消，未产生可用评分，也未删除数据。

大部分案例为秒级，少数 timeout 补丁形成显著长尾。最慢的 case index 50 有 18 个 public tests，四个候选均为 `public_test_failed`，其中三个候选在 18 项上全部 timeout；完整记录使任务用时 54 分 6 秒。项目保持冻结的完整 outcomes 语义，没有看见长尾后改为 fail-fast 或删除该案例。

## 结果解释与下一门禁

候选级 11.65% Pass 和经验 Pass@4 29.17% 说明同题多次采样能产生可用执行差异，但数据来自训练分布且经过可执行资格筛选，不能与独立确认集或 Defects4C 的 greedy Pass@1 直接比较，也不能证明泛化。182 对中只有 75 对含完整 success，另外 107 对是较弱的阶段排序信号；是否足以进行 DPO 需要负责人结合规模、信号强度、timeout 风险与验证设计审阅。

A4 结果不得回写 A3.4 readiness。run manifest 保持 `a5_started=false`，A5 不会自动启动。
