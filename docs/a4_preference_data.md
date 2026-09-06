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

## 结果解释

GPU 生成成功只证明候选完整、格式与 seed replay，不证明补丁正确。A4 最终需报告各终态分布、实际偏好对数、function/file-window 组成、chosen/rejected 终态以及 success 对数量。结果不得回写 A3.4 readiness，也不会自动启动 A5。
