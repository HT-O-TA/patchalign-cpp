# ADR-0010：Data-v2 分离仓库隔离组与细粒度采样 family

状态：Accepted by project owner
日期：2026-09-06

## 背景

Data-v2 第一轮供给审计保持 `repo_family` 每组最多 2 条，只得到 260 条 train 与 131 条 validation。随后新来源桌面审计发现：若把真实仓库直接当作 family，train 至少 1,600 条 new-family 样本在每 family 最多 2 条的规则下，需要至少 800 个未见仓库。该下界与公开 C++ 修复来源源的真实供给不相称，也把“防止 train/validation 泄漏”和“限制相似样本重复”错误绑定到同一个键。

负责人认可分离两个身份层级，并允许继续冻结新版本契约与执行元数据 pilot。该决定不改写 A3 formal v1、第一轮 Data-v2 供给审计或任何既有评测身份。

## 决策

1. `repository_split_group` 只负责 split 与 benchmark 隔离。仓库来源使用规范化 `host/owner/repo`；竞赛程序来源使用 `dataset/problem_id`。
2. `sampling_family` 负责细粒度重复控制。仓库来源优先使用 `repository_split_group + target path + symbol/issue cluster`；缺 symbol 时使用稳定 hunk anchor。竞赛来源保持 problem family，不从相似提交伪造新 family。
3. train、validation 和所有冻结/保留 benchmark 的 `repository_split_group` 必须零交叉；已存在的 v1 split 映射优先，新 split group 才使用固定 seed 哈希分配。
4. `v1 + increment` 每个 `sampling_family` 最多 2 条；Data-v2 增量每个 train repository split group 最多 40 条、validation 最多 20 条。
5. 2,000/200 仍是容量探针，不是已经获得的数据。同步最低值调整为：train 至少 100 个新 split group 和 1,000 个新 sampling family；validation 至少 20 个和 100 个。
6. 任何单一新来源最多占增量 70%；function 继续为主，train/validation 至少 1,200/120 条 function，file-window 最低 400/40 条。
7. `new_repository_split_group`、`new_sampling_family`、样本数量必须分别报告，禁止再用含义不清的 `new_family samples` 合并表述。
8. 当前契约只授权元数据可行性研究，不授权源代码/patch 内容下载、Data-v2 构造、SFT、DPO 或 GPU 作业。

## 解释边界

- 同仓库多个独立 issue/function 不等于跨仓库泛化；最终报告必须同时披露仓库数和细粒度 family 数。
- repository-disjoint split 能减少本人后训练污染，但不能证明基础模型预训练无污染。
- GitHub 自动识别 SPDX 仅作预筛；逐仓库 LICENSE 原文、revision 和 SHA256 仍是内容准入门禁。
- 元数据 pilot 不验证 patch 语义、编译或测试，不能写成“训练样本合格”。

机器契约为 `configs/data/data_v2_contract_v2_1.json`。
