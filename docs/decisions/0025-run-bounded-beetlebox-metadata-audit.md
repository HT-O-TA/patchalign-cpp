# ADR-0025：执行有界 BeetleBox C++ 元数据审计

- 状态：Accepted
- 日期：2026-09-08

## 背景

CommitPack 固定分片与 broad GitHub 内容路线均已按预注册停止条件关闭。下一步不能继续
扩大同源静态提交，也不能在集群缺少 Docker/Podman/Apptainer 的情况下直接运行大型
容器 benchmark。

对四个独立候选的官方固定 revision 做桌面核验后：

- BugsCpp `be5cc489...` 有 215 个可复现缺陷、24 个项目和 145 个 multi-line 标签，
  但已被 ADR-0014 完整保留为未来外部评测；其中 cppcheck 还与当前 Defects4C 重叠；
- CppPerf `a7cba4f6...` 发布 347 个容器化性能补丁，但目标是性能优化，不是当前语义
  缺陷修复主任务，只保留为以后独立消融候选；
- TrickyBugs `84411e82...` 有 3,043 个竞赛程序、324 个 task，只有 224 个 task 具有
  fixed_programs；逐提交者训练/再分发权利与单仓库域多样性仍不满足当前治理门；
- BeetleBox `ac12f9cd...` 的固定数据卡声明 26,321 个 issue-linked 修复、29 个项目，
  其中 C++ native train/test 为 3,868/4,783；记录含 repo、issue/PR、before/after SHA
  和修改文件，但不含源码、测试命令或逐仓许可证。

因此 BeetleBox 是唯一值得进入下一道低成本门的候选，但只能先做元数据审计。

## 决策

1. 只下载固定 revision 的两个 Parquet 文件，共 19,375,255 bytes，并逐文件验证 LFS
   SHA256；原始文件只写入集群 `/mingli01/data/patchalign-cpp/data-v2/beetlebox/`；
2. 读取时排除 `title` 与 `body`，只处理语言、仓库、issue/PR URL、before/after SHA、
   修改文件和时间字段；artifact 只写聚合统计与哈希，不写正文、URL、仓库名或用户信息；
3. 审计 native split 的 C++ 数量、SHA/URL/文件字段有效性、重复、仓库重叠、冻结评测
   denylist 命中以及按 repository 重分 split 后的乐观 cap 容量；
4. metadata gate 暂定为 cap 后 train 至少 400、validation 至少 50，且分别至少覆盖
   15/4 个非评测仓库。它只决定是否值得做历史许可证 pilot，不是 Data-v2 训练配额；
5. 通过不授权源码、patch、测试重放、训练或 GPU；下一步仍须固定仓库级历史许可证
   与内容抽样门。失败则关闭 BeetleBox，不换 native split 或降低本门补考；
6. 原 `2,000/200` 继续保持容量探针身份。是否建立“静态监督层 + 可执行资格层”以及
   最终 Data-v2 配额，必须等待本审计真实结果并由新 ADR 冻结。

## 后果

这项审计最大下载量小于 20 MB，只使用 CPU/网络，预计分钟级完成。它以一次固定分母
回答 BeetleBox 是否有可治理的 C++ 仓库容量，避免直接取得数千条源码或反复试建异构
仓库。
