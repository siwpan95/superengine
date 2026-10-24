# superengine —— 基于 cordis 的三仓「超级引擎」组合仓

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
# 依赖：PyYAML、watchdog（cordis 自身需要）；cordis 可用 CORDIS_SRC 指向
# 3dworld/vendor/cordis/src，或与三仓并排放置自动定位。
export CORDIS_SRC=/path/to/3dworld/vendor/cordis/src
export WORLDBUILDER_SRC=/path/to/worldbuilder
export TDWORLD_SRC=/path/to/3dworld
export ANENGINE_SRC=/path/to/an-engine

python -m superengine.cli.boot --report     # 装配 + 门禁 + 契约版本报告
python -m tests.test_assembly               # 装配门禁
python -m tests.test_pipeline               # 三仓流水线（M1/M2）
python -m tests.test_no_cross_import        # 三仓互不引用门禁
python -m tests.test_live                   # M3 Hmr 热重载
python -m tests.test_backends               # M4 Impl 多实现可替换
python -m tests.run_tests                   # 以上五个模块聚合跑
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
├── cli/boot.py        # headless 装配验证入口
└── _locate.py         # cordis 与三仓路径解析（唯一处理路径的地方）
configs/cordis.super.yml
tests/                 # 三道门禁
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

## 许可

MIT。组合分发时须一并携带 `an-engine` 的 `NOTICE`（SRD 5.1 / CC-BY-4.0 数据条款）。
