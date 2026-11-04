# superengine —— 基于 cordis 的三仓「超级引擎」组合仓

## 仓库角色定位（投资组合分级 ①）

> 本仓在 siwpan 投资组合（根目录记作 `/projects/repos`，共 133 仓）中定级为 **① 核心推进**，领域 **游戏引擎/框架**，定位 **引擎平台层**。
> **角色**：cordis 三仓组合流水线，随引擎层维护。
> **维护策略**：① 核心推进——持续投入、不允许冻结；随所属收敛点 / 流水线长期演进。
> 投资组合统一分级索引（多机可查）：[组合分级决策索引 · allin 事实源](https://gitee.com/siwpan/allin/blob/master/docs/事实源/组合分级决策索引.md)。

把三个独立仓组合成一条流水线，**但不吞并它们**：

| 仓 | 角色 | 协作方式 |
|---|---|---|
| `worldbuilder` | 世界生成（纯 numpy） | 提供 `worldspec_source` / `terrain_source` |
| `an-engine` | 玩法 / 规则内核 | 提供 `gameplay_world` / `mapgraph_source` |
| `3dworld` | 表现 / 渲染 / 引擎层 | 提供 `terrain_sink` / `render_sink` |

本仓只做四件事：**契约、桥接、装配、门禁** —— 不含任何算法。

## 四条核心纪律

1. **独立仓**：三仓平等，天然阻断「某一仓吞并另两仓」的耦合倾向。
2. **契约独立版本化**：`contracts.CONTRACT_VERSIONS` **不跟随任何一仓发版**；
   各仓用 `SUPPORTED_CONTRACTS` 声明**兼容区间**，装配期校验。
3. **文件契约与服务契约并存**：
   `worldspec v1` 管离线 / 跨进程 / 独立发布，cordis 服务契约管同进程在线装配 ——
   **不互相替代**（worldspec 正是「三仓互不引用却仍能协作」的底线）。
4. **唯一 import 三仓的地方是 `bridges/`**，且只经各仓的 `bridge` 友好接口。

## 快速开始

```bash
# 依赖以 pyproject.toml 为单一事实来源（requirements.txt 通过 -e . 转发）：
#   PyYAML / watchdog（vendored cordis 硬依赖）、numpy（worldbuilder）、
#   pyglet==2.1.16（3dworld 经 mathkit 传递，只走纯 Python 的 pyglet.math）
python scripts/bootstrap.py --check-only    # 一键核对：依赖 / 四仓 / cordis 就位
python scripts/bootstrap.py --test          # 或：自动建 .venv 并跑全量回归

# 三仓源码并排即可自动定位；不在并排位置时显式指路（路径不写死盘符）：
export CORDIS_SRC=/path/to/3dworld/vendor/cordis/src
export WORLDBUILDER_SRC=/path/to/worldbuilder
export TDWORLD_SRC=/path/to/3dworld
export ANENGINE_SRC=/path/to/an-engine

python -m superengine.cli.boot --report     # 装配 + 门禁 + 契约版本报告
python -m tests.run_tests                   # 7 个模块聚合跑（见 docs/quality/回归基线.md）
python -m superengine.cli.dev --once        # 开发循环单次（M3 + M4）
```

装配产物（示意）：

```
ok: WorldbuilderBridge ACTIVE inject=[]
ok: TdworldBridge      ACTIVE inject=['worldbuilder']
ok: AnengineBridge     ACTIVE inject=['worldbuilder']
```

挂载顺序**不由 yml 书写顺序决定**，而由各 Service 的 `inject` 依赖图决定。

## 目录

```
superengine/
├── contracts/         # 跨仓契约（零依赖 Protocol）+ 独立版本号 + 区间校验
├── bridges/           # 唯一 import 三仓的地方（worldbuilder / 3dworld / an-engine）
├── assembly.py        # 装配：白名单 → 预导入 → Loader → 终态 ACTIVE 断言
├── live.py            # M3 cordis Hmr 热重载
├── devloop.py         # M3 + M4 接入日常开发循环
├── cli/               # boot / dev 两个入口
└── _locate.py         # cordis 与三仓路径解析（唯一处理路径的地方）
configs/cordis.super.yml
scripts/bootstrap.py   # 一键引导（--check-only / --test）
tests/                 # 7 个模块：三道门禁 + 流水线 + M3/M4 + 开发循环 + 回归基线
.github/workflows/ci.yml   # Windows / Linux headless / macOS 三平台六闸门
docs/
├── architecture/      # 架构总览 + 3 条 ADR + 已知风险与缓解 + 索引
├── design/            # 契约体系设计 / 矩阵速查 / 新增契约流程 / 悬空引用处置 + 索引
├── quality/           # 门禁标准 / 回归基线 / 测试覆盖审计 + 索引
└── release/           # 版本策略 / 发布清单 / 发布流程 + 索引
NOTICE · CHANGELOG.md
```

## 三道门禁（治 cordis 已记录的坑）

| 门禁 | 治什么 |
|---|---|
| entry name 白名单 | cordis 把 entry `name` 当模块 import ⇒ 等同执行代码 |
| 装配前手工 import | cordis Loader **会吞掉插件构造期异常**（只表现为"服务不就绪"） |
| 终态断言 ACTIVE | **PENDING 静默**：依赖名拼错不报错、一直等，进程可能静默退出 |
| 三仓互不引用扫描 | 防止某天有人图省事跨仓 import，让三仓从"可独立发布"退化成"一损俱损" |

## 里程碑

- **M1 ✅ 补断腿**：worldbuilder → 3dworld 接通（此前表现层那一腿是断的）。
- **M2 ✅ 玩法托管**：an-engine 的 `Context` 被**托管**（非替换，保其零第三方依赖）。
- **M3 ✅ cordis `Hmr` 热重载**：改 bridge 模块 → 旧 fiber 完整回滚、新 fiber 换入；
  判据是 **registry 规模不增长**（否则就是"两份逻辑同时跑"）。
- **M4 ✅ `reflect.Impl` 多实现可替换**：声明 `terrain_backend` 接口 + `__cordis_check__`
  校验器；clipmap / flat 两个实现可换，**消费方代码一行不改**；不合格实现被拒（PENDING，不崩）。
- **M3/M4 已接入实际开发循环**：`python -m superengine.cli.dev` 起常驻会话 ——
  改 `configs/dev.json`（seed / tile_m / backend …）或改三仓 bridge 源码，
  地形就地重建，**不用重启进程**。

## 开发循环（日常怎么用）

```bash
python -m superengine.cli.dev                # 常驻：监听配置 + 三仓源码，自动重建
python -m superengine.cli.dev --once         # 只构建一次
python -m superengine.cli.dev --set backend flat    # 改配置（下一轮生效，走 M4 换实现）
python -m superengine.cli.dev --status              # 看当前配置与默认值的差异
```

两条联动：

| 改什么 | 走哪条 | 表现 |
|---|---|---|
| `configs/dev.json` 的 `backend` | **M4** | 实现热替换（clipmap ⇄ flat），消费方代码不动 |
| 三仓 bridge 源码 | **M3** | 底层模块重导 + entry fiber 换新，registry 规模不增长 |
| `seed` / `tile_m` / 网格参数 | 重建 | 地形随之变化，同参数结果一致 |

输出形如：`[backend→flat, rebuild] backend=flat verts=289 h=0.000~0.000 registry=10`

**诚实边界**：Python `importlib` 不会重绑定其他模块已持有的引用，所以只保证
「三仓 bridge 接口 + 本仓 entry」两层被真正换掉；改更深的**内部**模块建议重启会话。
监听用轮询（默认 0.5s）而非后台线程 —— 确定性更好，也便于测试直接调 `tick()`。

## 许可

MIT。组合分发时须一并携带 `an-engine` 的 `NOTICE`（SRD 5.1 / CC-BY-4.0 数据条款）——
本仓根 [`NOTICE`](NOTICE) 已把署名义务与传播链条写实，随包分发即可。

## 文档与发布

| 我想… | 看这里 |
|---|---|
| 新人跑起来 / 四仓 clone / 漂移核对 | [`docs/新人开发上手指南.md`](docs/新人开发上手指南.md) |
| 理解四层架构与设计决策 | [`docs/architecture/README.md`](docs/architecture/README.md)（架构总览 + ADR 索引） |
| 查 / 改跨仓契约 | [`docs/design/README.md`](docs/design/README.md) |
| 判绿 / 看覆盖缺口 / 跑门禁 | [`docs/quality/README.md`](docs/quality/README.md) |
| 发版 / 打 tag / 版本怎么动 | [`docs/release/README.md`](docs/release/README.md) · [`CHANGELOG.md`](CHANGELOG.md) |

CI 三平台（Windows / Linux headless / macOS）定义见
[`.github/workflows/ci.yml`](.github/workflows/ci.yml)；**目前仅 Windows 在本机实测**，
Linux/macOS 需远端 runner 跑过一轮后才算兑现（见
[`docs/quality/测试覆盖审计.md`](docs/quality/测试覆盖审计.md) 缺口 G2）。
