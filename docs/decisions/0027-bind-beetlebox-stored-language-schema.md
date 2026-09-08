# ADR-0027：绑定 BeetleBox 固定文件的存储语言 Schema

- 状态：Accepted
- 日期：2026-09-08

## 背景

v1.1 Job `97505` 完成 `417 passed` 和固定文件审计，但因配置继续使用数据卡展示值
`C++`，实际匹配为 0/0。随后只读取两个 Parquet 的 `language` 列做一次聚合，确认
存储值为小写 `c++`；实际 C++ 数为 train 3,317、test 3,865。三条不含 title/body
的样本确认 repo、issue/PR URL、before/after SHA、updated_files 与时间字段编码均与
既有审计器兼容。

## 决策

1. 保留 v1.1 Job `97505` 及其 0/0 artifact，不把它解释为来源容量失败；
2. 新建 v1.2，将精确存储语言值固定为 `c++`，并将同一固定文件的实际 C++ 数
   3,317/3,865 写成硬观测；
3. 输出同时保留数据卡声明的 3,868/4,783 与实际数，明确标记不一致；
4. revision、path、bytes、SHA256、总行数、读取列、URL/SHA/updated_files 校验、
   denylist、repository resplit、40/20 cap 与 400/50、15/4 metadata gate 均不变；
5. v1.2 使用独立 artifact 目录。这是最后一次上游 Schema 映射修正：后续若失败，
   直接按实际内容/容量原因关闭 BeetleBox，不再修改 Schema 或门槛；
6. 即使通过也只授权一个版本化历史许可证 pilot，不授权 source/patch、训练或 GPU。

## 后果

项目不再把展示文档当作存储 Schema。真实文件哈希、总行数、实际列值和实际语言计数
共同形成 v1.2 身份，数据卡过期本身作为数据治理失败案例保留。
