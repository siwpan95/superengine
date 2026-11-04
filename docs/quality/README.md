# docs/quality/ —— 质量面文档索引

> 这一层只回答一个问题：**怎么证明「没坏」**。
> 「接缝是什么」→ `docs/design/`；「为什么这么搭」→ `docs/architecture/`；
> 「怎么发版」→ `docs/release/`。

## 三份文档 + 一份配置

| 文件 | 性质 | 回答什么 |
|---|---|---|
| [门禁标准.md](门禁标准.md) | **规则**（应然） | P0/P1/P2 分级、三道装配门禁、CI 闸门、平台矩阵、发布前额外门禁、判定速查 |
| [回归基线.md](回归基线.md) | **事实快照**（实然） | 本机实测的输出形态：fiber 全 ACTIVE、契约版本表、`registry=10`、依赖基线、判定流程、失效条件 |
| [测试覆盖审计.md](测试覆盖审计.md) | **缺口盘点** | 45 个测试函数覆盖了什么、**没**覆盖什么、缺口优先级与建议 |
| `../../.github/workflows/ci.yml` | **机械执行** | Windows / Linux headless / macOS 三平台把上面三份落成命令 |

## 判定速查（改完代码走这条）

```bash
python scripts/bootstrap.py --check-only     # 四仓 / cordis / 依赖 就位
python selfcheck.py                          # 契约层无头自检
python -m tests.run_tests                    # 7 模块 / ALL_TESTS_PASSED
python -m superengine.cli.boot --report      # 5 fiber ACTIVE + SUPERENGINE_BOOT_OK
python -m superengine.cli.dev --once         # registry=10 + SUPERENGINE_DEV_OK
```

全绿才算基线未破。**任一失败先定位，不要以「环境问题」绕过** ——
`pyglet` 漏声明就是这样被长期绕过、直到干净机 clone 才暴露的（见 [回归基线 §5](回归基线.md)）。

## 三层防线的分工

```
声明面   test_baseline.py     契约快照 / 依赖声明 / 零依赖边界   ← 最便宜，先跑
结构面   test_assembly.py     版本区间 / fiber 终态 / 依赖图
行为面   test_pipeline / live / backends / devloop / no_cross_import
```

`test_baseline` 是**不依赖 cordis 与三仓**的那一层，干净机上只装完依赖就能跑 ——
它的存在本身就是为了防「本机 venv 全绿、干净机跑不起来」。

## 快照的权威性

`回归基线.md` 与 `test_baseline.py` 里的数字都是**带失效条款的快照**，
权威归随日期演进的事实流水，不归快照。新增契约 / 插件 / 换 Python 大版本 / 改 CI 矩阵后，
必须重新实测并回写（见 [回归基线 §6](回归基线.md)）。
