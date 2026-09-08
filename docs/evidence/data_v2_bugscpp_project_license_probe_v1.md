# BugsCpp 项目预注册与许可证上界结果

> 正式 CPU-only Job `97515`；提交 `62575ffea6caf4246691c9de2fa2b11719c216bc`；
> 结果：`COMPLETED 0:0`，用时 `00:01:18`，`420 passed in 14.88s`。

## 结论

预注册的 train 上界通过，但 validation 上界失败，因此 BugsCpp 训练路线按
ADR-0029 关闭，不换 seed、不移动项目、不放宽许可证 allowlist，也不继续读取 patch、
LICENSE 正文、源码或测试。

| Split | 固定规模 | 当前许可证 allowlist | 门槛 | 结果 |
|---|---:|---:|---:|---|
| train | 12 projects / 104 defects | 5 / 64 | 4 / 40 | 通过 |
| validation | 3 / 41 | 1 / 5 | 2 / 20 | 失败 |
| held-out | 7 / 39 | 未请求 | 不适用 | 保持未读 |
| excluded | 2 / 31 | 未请求 | 不适用 | 保持排除 |

train 当前 allowlist 项目是 `berry`、`jerryscript`、`md4c`、`openssl`、
`yaml_cpp`；validation 只有 `yara`。`proj` 为 `NOASSERTION`，`libchewing` 为
`LGPL-2.1`。这些是 GitHub 当前 repository metadata，只是历史许可证审计的上界信号，
不是 base commit 时点的许可结论。

## 边界核验

- split 在任何 patch blob 被读取之前冻结；
- benchmark 只做 partial clone/no checkout，并读取 24 个 `meta.json`；
- 对 train/validation 发出 12 个 GitHub repository metadata 请求；
- held-out 不请求许可证；
- 没有取得 patch、LICENSE 正文、源码、测试或缺陷描述，没有执行上游程序；
- 没有产生训练数据，没有申请 GPU。

## 正式产物

目录：`artifacts/data-v2/bugscpp-project-license-probe-v1/`

```text
project-decisions.jsonl  542aa312b4f23562d55418458380274a5925a785d9fc868eac8604797831e7f3
summary.json             cf223270f5a93d8d2e4125243a72cc008515bbd5f6b88a819ee957441802f0fc
run-manifest.json        e5353042d9a84eb2583b0c93cb9fe3693ad78a4839a7388a1dbe2b8136ffcca4
```

该负结果有信息价值：BugsCpp 总量虽然看似足够，但预注册项目隔离后，可宽松许可的
validation 只剩 5 个 defects。若事后把 `proj` 移到 train 或改变 seed，得到的是选择偏差，
不是数据供给改善。
