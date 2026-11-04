# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **本仓的版本号有两套，不要混**：
> - **`superengine` 自身版本**（本文件、`pyproject.toml` 的 `version`）—— 计量的是**组合仓自己的装配层**变了没有。
> - **契约版本**（`contracts.CONTRACT_VERSIONS`）—— 计量的是**跨仓接缝**变了没有，**独立版本化，不跟随任何一仓发版**。
>
> 判定规则与两套计数器的区分见 [`docs/release/版本策略.md`](docs/release/版本策略.md)。

## [Unreleased]

（尚无代码条目；以下为发布状态补记，非功能变更。）

- **2026-11-04 收尾 · `v0.1.0` 已打出**：`master` 由 `a5fc431` 推进 6 笔至
  `51400e9` 并推送 `origin`；`v0.1.0` annotated tag（对象 `daaaf56`）已推送，
  `git ls-remote` 复核一致。GitHub 端为 Gitee 服务器侧异步镜像，稍后自同步。
  **已知缺口（P1，发布后补验）**：三平台 CI 的 Linux headless / macOS runner
  尚未实跑；本 tag 经主理人明确放行豁免「runner 验证闭环」前置，tag 消息内已留痕。
  **该补记不改动 tag 指向** —— `v0.1.0` 仍指向 `51400e9`。

## [0.1.0] - 2026-11-04

> **本仓的首次发布。**
>
> 本仓此前**从未打过任何 tag**（本地 `git tag -l` 与两端远端 `git ls-remote --tags` 均为空），
> 所以不存在更早的历史版本条目可写——本条把建仓至今的内容一次性归档。
> 内容对应 `a728b71`（建仓）到 `a5fc431`（发布面前置核对）之间的 10 个提交，
> 外加本次随发布补入的发布面 6 个文件（`NOTICE` / `CHANGELOG.md` / `docs/release/` 下 4 份），
> 以及同轮补齐的工程基线与质量门产物：`pyproject.toml` 依赖补全、`requirements.txt`
> 改单一来源、`scripts/bootstrap.py`、`tests/test_baseline.py`、`.github/workflows/ci.yml`、
> `docs/architecture/` 6 份、`docs/design/` 5 份、`docs/quality/` 4 份。
> 日期以 tag 实际打点日为准。

### Added

- **组合仓骨架：契约 / 桥接 / 装配 / 门禁四层就位**（`a728b71`，2026-10-24）。
  本仓自此只做这四件事，**不含任何算法**——三仓仍是独立仓、仍可各自发布。
  对使用者而言：拿到的是一条**能跑通的装配流水线**，而不是又一个被合并进来的单体仓。

- **契约独立版本化 + 装配期兼容区间校验**（`a728b71`）。
  8 个跨仓契约（`worldspec_source` / `terrain_source` / `mapgraph_source` / `gameplay_world` /
  `terrain_sink` / `render_sink` / `dungeon_source` / `rules_kernel`）各自带版本号，
  各仓用 `SUPPORTED_CONTRACTS` 声明兼容区间（如 `>=1.0,<2.0`）。
  **对使用者而言：兄弟仓自己发版不会把本仓拖下水**；而真出现接缝不兼容时，
  它在**装配期就报错**（不进运行期），而不是运行到一半才炸。

- **M1 · 补断腿：worldbuilder → 3dworld 接通**（`a728b71`）。
  三仓流水线此前断在表现层那一腿——worldbuilder 早已产出 worldspec、an-engine 早已消费，
  唯独 3dworld 没接。**对使用者而言：地形现在真的会出现在屏幕上**，
  且接缝全程 headless / 零 GL，可在 CI 里直接断言。

- **M2 · 玩法托管：an-engine 的 `Context` 被托管而非替换**（`a728b71`）。
  an-engine 的 `core/context.py` 自述「源自 Cordis 三个算子」且刻意零第三方依赖，
  所以本仓**不把 cordis 塞进去替换它**，而是外层管生命周期与回滚、内层仍是它自己的 `Context`。
  **对使用者而言：an-engine 的零依赖属性与既有测试基线都不受整合影响**——
  这是「组合」与「吞并」的分界线。

- **M3 · cordis `Hmr` 热重载接入**（`89e2352`，2026-10-24）。
  改 bridge 模块 → 旧 fiber 完整回滚、新 fiber 换入。
  **判据是 registry 规模不增长**（增长即意味着「两份逻辑同时跑」——热重载最容易翻车的地方）。
  **对使用者而言：改代码不必重启整条流水线**。

- **M4 · `reflect.Impl` 多实现可替换**（`89e2352`）。
  声明 `terrain_backend` 接口 + `__cordis_check__` 校验器；
  clipmap / flat 两个实现可热替换，**消费方代码一行不改**；
  不合格实现被拒（PENDING，不崩）。**对使用者而言：换地形后端是一次配置改动，不是一次改造**。

- **M3 / M4 接入实际开发循环**（`f4257df`，2026-10-25）。
  `python -m superengine.cli.dev` 起常驻会话——改 `configs/dev.json`
  （`seed` / `tile_m` / `backend` / `levels` / `grid` / `base_cell`）或改三仓 bridge 源码，
  地形就地重建，**不用重启进程**。
  **诚实边界**（写进代码注释，不藏）：Python `importlib` 不会重绑定其他模块已持有的引用，
  所以只保证「三仓 bridge 接口 + 本仓 entry」两层被真正换掉；
  改更深的**内部**模块建议重启会话。

- **`dungeon_source` / `rules_kernel` 契约与桥接**（`6cfcbea`，2026-10-26）。
  地牢图的产物与 worldspec 的 `graph.json` **同形**，所以下游 an-engine 的 `MapGraph`
  能直接吃它——生成与玩法共用一套形状；`rules_kernel` 则把骰系纳入契约层。
  **对使用者而言：地牢图不必做形状转换就能接进玩法侧**。

- **无头自检 `selfcheck.py`**（`c20bce9`，2026-10-26）。
  不导入 cordis、不导入三仓、不开窗口，实跑契约层的语义版本解析、兼容区间算术、
  提供方门禁与注册表一致性（当前 23 项检查）。
  **对使用者而言：CI 里有一条不依赖任何 GUI / 三仓就位的自检路径**，
  也可被外部 registry 校验器驱动。

- **发布面补齐**（本次随 0.1.0 补入，6 个文件）：
  `NOTICE`（组合分发的 SRD 5.1 / CC-BY-4.0 署名义务与数据链条说明）、
  本 `CHANGELOG.md`、
  `docs/release/版本策略.md`（组合仓版本与契约版本两套计数器的判定规则）、
  `docs/release/发布清单.md`（可勾选的发布前门禁）、
  `docs/release/发布流程.md`（从 commit 到 tag 到 release 的可执行步骤）、
  `docs/release/README.md`（发布面索引）。

- **工程基线：依赖声明收敛到单一事实来源**（本次随 0.1.0 补入）。
  `requirements.txt` 改为 `-e .` 转发到 `pyproject.toml`，消除两份清单必然漂移的结构性隐患；
  `pyproject.toml` 补齐 **`pyglet==2.1.16`**（3dworld 侧经 `world3d/engine/mathkit.py`
  传递进来的硬依赖），并给 `PyYAML` / `watchdog` / `numpy` 加版本区间。
  **对使用者而言：干净机按文档装完依赖就能 `boot`，不再报 `No module named 'pyglet'`**。

- **一键引导 `scripts/bootstrap.py`**（本次随 0.1.0 补入）。
  `--check-only` 探测四仓 / cordis / 依赖是否就位，`--test` 建 venv 后跑全量回归，
  显式把「依赖缺失」与「仓没找到」分开报 —— 治的是 `_locate.py` 把
  `ImportError` 包成 `RepoNotFound` 的误导。

- **三平台 CI（`.github/workflows/ci.yml`）**（本次随 0.1.0 补入）。
  Windows / Linux headless / macOS 三个 job 各自 checkout **四仓**、不设 `CORDIS_SRC`
  强制走 vendored 自动定位，依次守六道闸门（布局 → 装依赖 → 依赖自检 →
  bootstrap → selfcheck → 装配 + 全量回归 + `dev --once`）。

- **回归基线测试 `tests/test_baseline.py`**（本次随 0.1.0 补入，9 个测试函数）。
  把契约注册表快照、Protocol 方法集合、依赖声明单一来源、入口文件存在性、
  `contracts/` 零第三方依赖固化成断言；全量聚合从 6 模块扩到 **7 模块**。
  **对使用者而言：「本机 venv 全绿、干净机跑不起来」这类漏声明问题以后在 CI 里就会红**。

- **架构 / 设计 / 质量三层文档**（本次随 0.1.0 补入，共 15 份）：
  `docs/architecture/`（架构总览 + 3 条 ADR + 已知风险与缓解 + 索引）、
  `docs/design/`（契约体系设计 + 契约矩阵速查 + 新增契约流程 + 悬空引用处置 + 索引）、
  `docs/quality/`（门禁标准 + 回归基线 + 测试覆盖审计 + 索引）。

### Changed

- **三道装配门禁 + 一道互不引用扫描**成为本仓的硬门禁（`a728b71` / `89e2352`）。
  治的是 cordis 上已记录的三个坑，每个都有具体后果：

  | 门禁 | 治什么 | 不做会怎样 |
  |---|---|---|
  | entry name 白名单 | cordis 把 entry `name` 当模块 import ⇒ 等同执行代码 | 配置里一个名字就能执行任意代码 |
  | 装配前手工 import | cordis Loader **会吞掉插件构造期异常**（只表现为「服务不就绪」） | 真异常被藏起来，排查从小时级变天级 |
  | 终态断言 ACTIVE | **PENDING 静默**：依赖名拼错不报错、一直等，进程可能静默退出 | 装配「成功」但服务没起来 |
  | 三仓互不引用扫描 | 防止有人图省事跨仓 import | 三仓从「可独立发布」退化成「一损俱损」 |

  **对使用者而言：门禁失败会响亮报错，而不是让流水线悄悄半死不活**——
  这是组合仓区别于「把三个脚本凑在一起跑」的地方。

- **`README.md` 补入仓库角色定位与组合分级索引引用**（`5ecce2e` / `5436e74`，2026-10-29）：
  本仓在投资组合中定级为 ① 核心推进、领域游戏引擎/框架、定位引擎平台层，
  维护策略是持续投入、随所属收敛点演进。

- **新增《新人开发上手指南》模板并补入漂移核对清单**（`091bba9` / `a5fc431`，2026-10-29）：
  四段式（环境准备 / 代码获取 / 启动 / 常见问题）+ 可勾选的漂移核对清单。
  清单末行为**流程类**核对项：双远程推送前先 `fetch` + `ls-remote` 核对两端、确认无分叉再推，
  推后再 `ls-remote` 复核 IN_SYNC——**不轻信 `git push` 打印的输出**。

### Fixed

- **补齐 `pyglet` 依赖声明**（实测，2026-11-04）。
  原 `requirements.txt` / `pyproject.toml` 只声明 `PyYAML` / `watchdog` / `numpy`，
  但装配路径 `tdworld_bridge → world3d.bridge → world3d/engine/mathkit.py → pyglet.math`
  是硬依赖，干净机按 README 装完跑 `boot` 直接 `No module named 'pyglet'`，
  当时 6 个测试模块只有 1 个能过。现已把 `pyglet==2.1.16` 写进 `pyproject.toml`、
  `requirements.txt` 收敛为 `-e .` 单一来源，并由
  `test_baseline.py::test_pyglet_is_declared` 机械防复发。**该条已从下方「已知限制」移出。**

- **清理 3 处代码注释的悬空文档引用**（`规划文档 §2.6 / §2.7` → 仓内真实文档路径），
  处置记录与「注释引用」纪律见 `docs/design/悬空引用处置.md`。

### 已知限制（0.1.0 打 tag 时的事实状态）

- ~~**`requirements.txt` 漏声明 `pyglet`**~~ → **已修复，移入上方 `Fixed`**。
  该缺口是本仓首发前最重要的 P0：报错被 `_locate.py` 包成
  `RepoNotFound: 仓 '3dworld' 缺少 bridge 接口模块`，真实原因藏在
  `原始错误：No module named 'pyglet'`，会把排障方向带偏。**保留这条索引**是为了让下次
  遇到同类 `RepoNotFound` 的人**先读 `原始错误` 那一段**；当前状态：`pyproject.toml`
  已声明、`test_baseline` 机械守卫、干净机可跑。

- **三平台 CI 已配置但仅 Windows 本机实测**：Linux headless / macOS 两个 job
  需要远端 runner 跑过一轮，才能宣称「三平台全覆盖」。见
  `docs/quality/测试覆盖审计.md` 缺口 G2 / G11（**P1，发布前须处理**）。

- **`render_sink` 契约无端到端测试**：8 个契约里唯一只有结构断言与快照、
  没被真跑过一条数据的备用路径。见 `docs/quality/测试覆盖审计.md` 缺口 G1（P2，已登记）。

- **本机到 GitHub 的直连可用性是「时点事实」，不是恒定结论**：
  3dworld 的 CI 注释记录过直连断；本仓 release 面在 2026-11-04 另一次实测中
  `curl https://github.com` / `api.github.com` 返回 200、`ssh -T git@github.com` 认证成功。
  两次结论相反 ⇒ **默认仍按「Gitee 镜像从服务器侧推、最短间隔 5 分钟」执行**
  （不依赖本机网络的稳定路径），直连是否可用**每次发布前当场复核**；
  「两端远端都 IN_SYNC」要在镜像跑完后才复核得出来。

- **按中文路径过滤 git 输出必须带 `-c core.quotepath=false`**：
  否则非 ASCII 文件名被转义成 `"\347\233\256..."`，按名字过滤**恒假**，
  会误判「文件不在仓库里」。本仓的 `docs/新人开发上手指南.md` 正是中文文件名，
  每次核对发布物清单时都会撞上这条。

- **中文 Windows 下 Python 文本 I/O 默认 GBK**：所有 `.md` / `.txt` 一律 **UTF-8 无 BOM**
  （往返改写会烤坏中文）；带 emoji 的输出需 `sys.stdout.reconfigure(encoding="utf-8")`。
