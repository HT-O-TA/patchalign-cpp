# ADR-0028：关闭 BeetleBox 并结束宽泛来源搜索

- 状态：Accepted
- 日期：2026-09-08

## 背景

Job `97508` 在固定 BeetleBox Parquet 上得到 3,534 条元数据合格记录，但它们只来自
4 个非评测仓库；repository resplit 与 cap 后为 train 160、validation 0，未达到
400/50 样本和 15/4 仓库的 metadata 门。

此前 broad GitHub 固定 20 内容为 0/20，CommitPack 固定分片为 236/17 且缺少执行
证据，RunBugRun v2 与 TrickyBugs 存在逐记录来源权利问题，Multi-SWE C++ 与现有评测
仓库重叠。继续更换搜索条件、分片、hash seed 或同类大表不会解决“独立仓库 + 真实
修复 + 许可证 + 可执行”的交集问题。

## 决策

1. 关闭 BeetleBox 当前路线，不运行历史许可证 pilot，不下载源码、patch 或测试；
2. broad GitHub、CommitPack、BeetleBox、RunBugRun v2、TrickyBugs 不再做同类补跑；
3. 原 2,000/200 作为容量探针已完成并失败。ADR-0012 的 SFT/评测/DPO 质量门和最终
   交付条件继续有效，但其“2,000/200 全量 buggy-fail/fixed-pass 才可训练”的数据门
   必须由新的分层 Data-v2 契约显式取代，不能静默降低；
4. 下一步唯一主路线是 BugsCpp 项目级预注册审计：在不读取 patch gold 前，按项目
   身份、数量、现有评测重叠和历史许可证划分 train/validation/held-out；cppcheck 与
   任何现有 Defects4C 重叠继续禁止训练；
5. 新契约将把“真实开发者修复监督层”与“本地 buggy-fail/fixed-pass 执行层”分开，
   两层继续共享许可、provenance、repo split、污染、Schema、token 和哈希门；最终
   配额只在 BugsCpp 审计给出真实上界后一次冻结；
6. CppPerf 只可在正式 bug-repair SFT 通过后作为性能域消融，不参与当前容量补齐。

## 后果

项目不再以寻找 2,000 条全量可执行 C++ 修复为近期目标，也不把静态元数据数量包装成
训练就绪。下一次可能提交的作业是 CPU/网络的 BugsCpp 项目/许可证审计；在新契约、
数据 manifest 和三 seed 训练配置全部冻结前，不提交 GPU。
