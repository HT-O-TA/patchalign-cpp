# ADR-0001：模型与资源策略

状态：Accepted for A0
日期：2026-08-30

## 背景

项目需要展示 Base → SFT → DPO 的本人贡献，同时受祝融单用户 GPU、主机内存和排队约束。旧规划中的 Qwen3-Coder-Next-Base 约 80B 总参数且为 MoE，会把第一版重点从数据和评测闭环转移到框架兼容和模型分片。

## 决策

- 主训练 Base：`Qwen/Qwen2.5-Coder-7B`；
- 固定 upstream revision：`0396a76181e127dfc13e5c5ec48a8cee09938b02`；
- 祝融只读路径：`/mingli01/models/Qwen2.5-Coder-7B`；
- 外部强基线：`/mingli01/models/Qwen3-8B`；
- 第一版单张 A800 80GB 串行；
- BF16 LoRA 和 NF4 QLoRA 使用相同数据、seed、上下文与评测协议进行 pilot；
- 根据质量、显存、吞吐、时长和失败样本冻结正式 SFT 方案；
- 不默认引入 DeepSpeed；
- RLVR/GRPO 不属于第一版必做项。

## 证据

Job `90719` 已完成真实模型 G0：BF16 LoRA 和 NF4 QLoRA 单步、adapter 保存/重载均通过。该证据仅支持兼容性，不支持质量选择。

2026-09-01 已核验官方 Hugging Face commit 存在，且集群模型的 `config.json`、`model.safetensors.index.json`、`tokenizer.json` 和 `tokenizer_config.json` SHA256 与该 revision 的官方文件一致。四个权重分片尚未逐片对照上游 LFS OID，因此完整供应链证明仍需补强。

## 影响

优点：

- dense Coder Base 与 C++ 修复匹配；
- 7B 规模能在单张 A800 上公平比较 BF16/NF4；
- Base 身份便于区分本人 SFT/DPO 贡献；
- 训练链和部署链较成熟。

代价：

- 模型代际早于 Qwen3；
- 基础模型污染未知；
- 权重转移目录未保留 snapshot 元数据，当前 revision 由用户提供并通过官方 commit 与四个元数据哈希恢复；
- QLoRA 是否值得采用仍需 pilot，而非由显存节省单独决定。

## 重新评估条件

- G4/G5 pilot 显示 Base 能力不足且数据/评测不是主要瓶颈；
- Qwen3-8B-Base 合法到位并能在同协议下比较；
- 7B/8B 主线已经完成，资源允许增加扩展实验。
