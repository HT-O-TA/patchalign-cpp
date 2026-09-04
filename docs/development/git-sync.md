# 本机—集群 Git 同步规范

## 权威来源

- GitHub `HT-O-TA/patchalign-cpp` 是代码、配置和文档的同步中枢；
- 本机 `/home/lenovo/A/patchalign-cpp` 是主要开发与提交工作区；
- 集群 `/mingli01/project/ht/patchalign-cpp` 是计算工作副本；
- 训练和评测必须记录实际 Git commit，不以“当前 main”代替不可变身份。

## 进入 Git 的内容

- `src/`、`scripts/`、`slurm/`、`configs/`、`schemas/` 和 `tests/`；
- 项目文档、ADR、可公开的小型证据摘要；
- 不含权重或敏感信息的复现配置。

## 只在集群保存的内容

- `/mingli01/project/ht/.conda_envs/patchalign-cpp`；
- `/mingli01/models/` 下的模型权重；
- `artifacts/`、日志、checkpoint、adapter、完整预测和缓存；
- 原始或处理中间数据，除非经过专门审核并决定提交小型 fixture。

上述路径必须由 `.gitignore` 保护。不得使用 `git add -f` 绕过大型产物和密钥的忽略规则。

## 标准同步流程

本机开发完成后：

```bash
cd /home/lenovo/A/patchalign-cpp
git status --short
git diff --check
git push origin main
```

集群在没有未提交代码变更时：

```bash
cd /mingli01/project/ht/patchalign-cpp
git fetch origin
git status --short
git merge --ff-only origin/main
```

提交 Slurm 作业前：

```bash
git status --short
git rev-parse HEAD
bash -n slurm/<job>.sbatch
```

工作区必须干净；run manifest 必须保存 `git rev-parse HEAD` 的完整 40 位 commit。正式作业不得直接跟随正在变化的远端分支。

## 正式作业运行期间的固定

- 从 preflight 通过到整条依赖链终止，集群计算工作副本固定在 run manifest 记录的 commit；
- 即使本机/GitHub 只有文档更新，也不在运行中的依赖链之间 fast-forward 集群工作树；
- 本机可以继续提交和推送不影响实验的文档，但状态页必须写明正式链绑定的计算 commit；
- 只有全部相关作业进入终态，或必须修复会阻断实验的错误时，才评估集群同步；
- 若必须中途修复，取消尚未执行的依赖作业，提交新 commit，重新 preflight，并以新 Job 链和新 artifact 目录运行；不得沿用旧身份；
- 因此“本机/GitHub 暂时领先于集群固定 commit”可以是受控复现状态，不应使用强制重置或运行中同步来消除。

## 冲突和紧急修复

- 不在本机和集群同时修改同一个文件；
- 集群 `origin` 当前通过 HTTPS 只读获取，不配置写凭据；
- 若必须在集群临时修复，先建立本地分支并提交，再把 patch/bundle 带回本机审阅和推送；
- 不用 SSHFS、NFS 软链接或双向 `rsync --delete` 作为 Git 替代品；
- 不通过 `git reset --hard` 清理包含未知用户改动的工作区；
- 大型产物的备份、迁移或删除必须按 Job ID 和 SHA256 单独处理。

## 产物引用

Git 中的报告只记录集群绝对路径、Job ID、关键指标和 SHA256。大型文件保留在集群 `artifacts/`，其生命周期不由 Git 管理。若产物后续迁移，必须同步更新目录结构台账和引用它的报告。
