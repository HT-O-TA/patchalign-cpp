# ADR-0029：预注册 BugsCpp 项目 split 与许可证上界探针

- 状态：Accepted
- 日期：2026-09-08

## 背景

ADR-0028 将 BugsCpp 项目级审计确定为宽泛来源搜索结束后的唯一主路线。固定 upstream
revision `be5cc489cb2b3127ec3b73cb4adfdd290807f55b` 公开 215 个缺陷和 24 个
project ID。当前尚未读取任何项目的 `*-buggy.patch` 或 `*-fixed.patch` 内容。

`cppcheck` 与当前 Defects4C 外部评测仓库重叠，`example` 是 benchmark 演示仓库，二者
不参加训练/验证/新 held-out 划分。其余 22 个项目只按公开 defect count、固定 seed
`20260908` 和项目 ID 的 SHA256 顺序预注册，不使用描述、tag、patch 或测试结果：先取
至少 4 项目且至少 20% 缺陷为 held-out，再取至少 3 项目且至少 15% 缺陷为 validation，
剩余为 train。

## 固定 split

- held-out，7 项目/39 defects：`xbps`、`libxml2`、`libucl`、`coreutils`、
  `cpp_peglib`、`ndpi`、`libtiff`；
- validation，3 项目/41 defects：`proj`、`yara`、`libchewing`；
- train，12 项目/104 defects：`zsh`、`berry`、`wireshark`、`libtiff_sanitizer`、
  `libssh`、`exiv2`、`wget2`、`yaml_cpp`、`jerryscript`、`dlt_daemon`、`openssl`、
  `md4c`；
- excluded：`cppcheck` 30、`example` 1。

## 决策

1. 将 split 与项目 URL/count 写入机器配置后才允许取得 metadata；不得按许可证或后续
   C++ 产量重分项目；
2. benchmark 仓库只做 partial clone/no checkout，脚本只用 `git show` 读取 24 个
   `meta.json` 并验证 URL、base commit、defect ID/count；不得读取 patch blob；
3. 只对 train/validation 的 canonical GitHub 上游请求当前 license endpoint；不请求
   title、issue、commit message、源码或 LICENSE 正文。GitLab/自建 Git 主机在本探针
   fail-closed 为 unsupported，不以手工常识放行；
4. 当前 SPDX 只给出项目上界。allowlist 后 train 至少 40 defects/4 projects 且
   validation 至少 20/2，才允许另立 patch-header + 历史许可证审计；
5. 下一阶段仍须逐候选固定 base commit 的历史许可证、C++ patch path、变更规模、
   benchmark 污染和 buggy/fixed 构造；当前通过不等于内容或训练准入；
6. held-out 只验证 meta identity，不请求其许可证，也不读取其 patch；未来是否成为正式
   外部集由独立 qualification 决定；
7. 本阶段不运行上游代码，不申请 GPU。失败则保留 split 并关闭 BugsCpp 训练路线，
   不以换 seed、移动大项目或放宽许可证补考。

## 后果

该探针最多一次 partial clone 和 12 个 GitHub license 请求，预计十分钟级。它把项目
隔离先于内容选择，避免在看过 patch 或可执行结果后人为分配容易样本。
