# docs/design/ —— 契约面文档索引

> 这一层只回答一个问题：**跨仓接缝是什么、为什么这么定、怎么安全地改**。
> 不回答「怎么装配」（→ `docs/architecture/`）、「怎么判绿」（→ `docs/quality/`）、
> 「怎么发版」（→ `docs/release/`）、「新人怎么跑起来」（→ `docs/新人开发上手指南.md`）。

## 阅读顺序

| 顺序 | 文档 | 什么时候读 | 回答什么 |
|---:|---|---|---|
| 1 | [契约矩阵速查.md](契约矩阵速查.md) | 每次动手前，30 秒扫一眼 | 8 个契约的名字 / 版本 / 提供方 / 方法 / 归哪条干线 |
| 2 | [契约体系设计.md](契约体系设计.md) | 要理解「为什么」时 | 职责边界、两条正交轴、独立性论证、真缺口 vs 有意不做、代价 |
| 3 | [新增契约流程.md](新增契约流程.md) | 真要加 / 改一个契约时 | 从判需到落地的 10 步 SOP、版本号怎么 bump、禁止事项 |
| 4 | [悬空引用处置.md](悬空引用处置.md) | 看到注释里指向不存在的文档时 | 3 处历史悬空引用的处置结果与「注释引用」纪律 |

## 权威来源（文档与代码不一致时，以代码为准）

| 事实 | 权威文件 |
|---|---|
| 契约**形状**（有哪几个方法） | `superengine/contracts/protocols.py` |
| 契约**版本**（`CONTRACT_VERSIONS`） | `superengine/contracts/__init__.py` |
| 版本**区间算术** / `check_all` 方向性 | `superengine/contracts/_version.py` |
| 三仓**声明了哪些契约**、区间多少 | 各仓 `bridge.py` 的 `SUPPORTED_CONTRACTS` |
| 契约快照被机械断言 | `tests/test_baseline.py` 的 `EXPECTED_CONTRACTS` |

> 契约层是**零依赖**的：只 import `typing`，不 import 三仓、不 import cordis。
> 这条边界由 `tests/test_baseline.py::test_contracts_layer_is_dependency_free` 守着，
> 详见 [ADR-002](../architecture/ADR-002-桥接层独占跨仓导入.md)。

## 与相邻文档层的分工

```
docs/design/        「接缝是什么」        ← 本层
docs/architecture/  「为什么这么搭」      ADR + 架构总览 + 已知风险
docs/quality/       「怎么证明没坏」      门禁标准 + 回归基线 + 覆盖审计
docs/release/       「怎么交到别人手上」  版本策略 + 发布清单 + 发布流程 + NOTICE
```

改动跨层时，**四层都要回写**：加一个契约会同时牵动设计（本层）、
装配（architecture）、测试（quality 的基线快照）、发版说明（release 的 CHANGELOG）。
[新增契约流程.md](新增契约流程.md) 的第 9 步就是这张回写清单。
