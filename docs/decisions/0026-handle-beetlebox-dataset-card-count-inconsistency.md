# ADR-0026：修正 BeetleBox 数据卡语言计数的一致性假设

- 状态：Accepted
- 日期：2026-09-08

## 背景

BeetleBox metadata v1 Job `97503` 在提交 `eab4cda` 上完成 `417 passed`、配置
preflight 和两个 Parquet 的 bytes/SHA256 验证，随后因 train C++ 实际计数不等于
数据卡表格声明的 3,868 而 fail-closed，没有生成 artifact。

固定 revision 的数据卡内部本身不一致：YAML frontmatter 声明 train 10,191、test
10,445，共 20,636 行；语言统计表的 train 五种语言合计 13,184、test 合计 13,137，
共 26,321 行。两个固定 Parquet 的总行数与 frontmatter、文件 bytes 和 LFS SHA256
完全一致，因此不能同时把语言表计数作为文件级硬身份。

## 决策

1. 保留 Job `97503` 与 v1 配置/日志，标记为错误的一致性假设，不覆盖；
2. 新建 v1.1，只把 `published_cpp_rows` 从硬相等条件改为对照字段：输出实际 C++ 数、
   数据卡声明数和是否相等；
3. Parquet revision、path、bytes、SHA256、总行数、Schema、非正文读取列、denylist、
   URL/SHA/修改文件检查、repository resplit、40/20 cap 与 400/50、15/4 门全部不变；
4. v1.1 写入独立 artifact 目录，不复用 v1 输出；
5. 若实际 C++ 记录仍通过原 metadata gate，只授权历史许可证 pilot；不授权源码、
   patch、训练或 GPU。

## 后果

这是一项固定文件与官方说明冲突的观测修正，不是看到质量结果后的阈值调整。最终报告
必须同时披露数据卡声明和文件实际计数，不能继续引用 3,868/4,783 作为实际分母。
