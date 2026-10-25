# -*- coding: utf-8 -*-
"""实际开发循环 —— 把 M3（热重载）与 M4（多实现可替换）接到日常开发里。

一句话：起一个常驻会话，**改配置或改三仓源码，地形就地重建**，不用重启进程。

    python -m superengine.cli.dev            # 常驻：监听并自动重建
    python -m superengine.cli.dev --once     # 只构建一次并打印报告

它监听两类变化：

1. **配置文件**（`configs/dev.json`）：``seed`` / ``tile_m`` / ``backend`` / ``levels``
   / ``grid`` / ``base_cell``。改 ``backend`` 走 **M4** 的实现热替换
   （clipmap ⇄ flat，消费方代码不动）；改其余参数是重建。
2. **源码文件**：三仓各自的 bridge 接口 + 本仓的三个 bridge entry。
   改了某个仓的接口 ⇒ 先把它从 ``sys.modules`` 剔掉重导（绕开 Python 的引用
   重绑定限制），再让 **M3** 的 cordis Hmr 换掉对应 entry 的 fiber。

为什么能同时用到 M3 和 M4
--------------------------
* 世界数据来自 `ctx.worldbuilder`（生成 + 高程采样）—— 改 worldbuilder 侧代码
  由 **M3 热重载**接住；
* 地形网格走 `ctx.terrain_view`（只 inject `terrain_backend` 接口的消费方）——
  换后端由 **M4 多实现替换**接住。

诚实边界
--------
* Python 的 `importlib` **不会**重绑定其他模块已持有的引用：改了某个仓的
  **内部**模块（不是 bridge 接口）时，已 import 它的对象仍指向旧代码。
  开发循环只保证「bridge 接口 + 本仓 entry」这两层被真正换掉；
  更深的内部模块改动建议重启会话。
* 监听用**轮询**（默认 0.5s）而非后台线程 —— 确定性更好，也便于测试直接调 `tick()`。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

from ._locate import ensure_cordis

ensure_cordis()

from .assembly import mount  # noqa: E402
from .bridges.terrain_backends import (BACKENDS, TerrainBackendHost,  # noqa: E402
                                       TerrainConsumer)
from .live import (changed_modules, enable_hmr, mtime_snapshot,  # noqa: E402
                   reload_entries, reload_module_files, registry_size)

__all__ = [
    "DEV_CONFIG",
    "WATCHED_REPO_MODULES",
    "ENTRY_OF",
    "DEFAULT_PARAMS",
    "DevLoop",
    "start",
    "load_params",
    "save_params",
]

DEV_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "dev.json")

#: 监听的**三仓 bridge 接口**模块（改了它们 ⇒ 重载对应 entry）
WATCHED_REPO_MODULES = (
    "worldbuilder.bridge",
    "world3d.bridge",
    "allin_engine.bridge",
)

#: 仓库 bridge 模块 → 本仓里要重载的 entry 模块
ENTRY_OF = {
    "worldbuilder.bridge": "superengine.bridges.worldbuilder_bridge",
    "world3d.bridge": "superengine.bridges.tdworld_bridge",
    "allin_engine.bridge": "superengine.bridges.anengine_bridge",
}

#: 本仓三个 bridge entry 自身也监听（改自己 ⇒ 重载自己）
ENTRY_MODULES = tuple(ENTRY_OF.values())

DEFAULT_PARAMS = {
    "seed": 7,
    "tile_m": 2.0,
    "backend": "clipmap",
    "levels": 4,
    "grid": 16,
    "base_cell": 2.0,
}


def load_params(path: str = None) -> Dict[str, Any]:
    """读开发配置；缺失字段用默认值补齐。"""
    path = path or DEV_CONFIG
    p = dict(DEFAULT_PARAMS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            p.update(json.load(f) or {})
    except (OSError, ValueError):
        pass
    return p


def save_params(params: Dict[str, Any], path: str = None) -> str:
    """写回开发配置（供 `--set` 之类用）。"""
    path = path or DEV_CONFIG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)
    return path


class DevLoop:
    """常驻开发会话。

    典型用法::

        loop = await DevLoop.start()
        report = loop.build()          # 构建一次
        events = loop.tick()           # 轮询一次：检测变化 → 重载/换实现 → 重建
        loop.run(iterations=20)        # 持续跑（默认 0.5s 一轮）
    """

    def __init__(self, ctx, params: Dict[str, Any], config_path: str = None):
        self.ctx = ctx
        self.params = dict(params)
        self.config_path = config_path or DEV_CONFIG
        self.config_mtime = self._config_mtime()
        # 源码快照（只读）
        self.snapshot = mtime_snapshot(list(WATCHED_REPO_MODULES) + list(ENTRY_MODULES))
        self.rebuilds = 0
        self.reloads = 0
        self.swaps = 0
        self.last_report: Dict[str, Any] = {}
        #: 开发循环专用的**单一持久事件循环**（cordis 的挂载/换实现是异步的，
        #: 必须始终在同一个 loop 上跑，不能每次 asyncio.run 新建）
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _run(self, coro):
        """在会话自己的 loop 上跑完一个协程（轮询主体是同步的）。"""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(coro)

    # ---------------------------------------------------------- 启动 --
    @classmethod
    async def start(cls, params: Dict[str, Any] = None, config_path: str = None) -> "DevLoop":
        """装配三仓 + M4 后端宿主 + 消费方 + M3 Hmr。"""
        p = dict(params or load_params(config_path))
        ctx = await mount()
        # M4：后端宿主 + 只认接口的消费方
        await ctx.plugin(TerrainBackendHost, {
            "backend": p.get("backend", "clipmap"),
            "levels": p.get("levels", 4),
            "grid": p.get("grid", 16),
            "base_cell": p.get("base_cell", 2.0),
        })
        await ctx.terrain_host.mount_backend(p.get("backend", "clipmap"))
        await ctx.plugin(TerrainConsumer, {})
        await _settle()
        # M3：热重载
        await enable_hmr(ctx)
        await _settle()
        return cls(ctx, p, config_path)

    # ---------------------------------------------------------- 构建 --
    def build(self) -> Dict[str, Any]:
        """按当前参数构建一次地形，返回报告。"""
        wb = self.ctx.worldbuilder
        world = wb.generate(64, 64, seed=int(self.params.get("seed", 7)))
        hm = wb.heightfield(world)
        sampler = wb.make_height_sampler(hm, tile_m=float(self.params.get("tile_m", 2.0)))
        cfg = self.ctx.terrain_view.make_config(
            levels=int(self.params.get("levels", 4)),
            grid=int(self.params.get("grid", 16)),
            base_cell=float(self.params.get("base_cell", 2.0)),
        )
        res = self.ctx.terrain_view.build(sampler, config=cfg)
        self.rebuilds += 1
        report = {
            "backend": self.ctx.terrain_view.backend_name(),
            "seed": int(self.params.get("seed", 7)),
            "vertex_count": int(res.get("vertex_count", 0)),
            "height_min": float(res.get("height_min", 0.0)),
            "height_max": float(res.get("height_max", 0.0)),
            "registry": registry_size(self.ctx),
        }
        self.last_report = report
        return report

    # ---------------------------------------------------------- 轮询 --
    def _config_mtime(self) -> Optional[float]:
        try:
            return os.stat(self.config_path).st_mtime
        except OSError:
            return None

    def _apply_config(self) -> List[str]:
        """配置文件变了 ⇒ 应用新参数（backend 走 M4 热替换）。"""
        events = []
        new = load_params(self.config_path)
        backend_changed = new.get("backend") != self.params.get("backend")
        self.params = new
        if backend_changed:
            name = new.get("backend")
            if name in BACKENDS:
                self._run(self.ctx.terrain_host.swap(name))
                self.swaps += 1
                events.append(f"backend→{name}")
            else:
                events.append(f"backend 未知: {name}（保持 {self.params.get('backend')}）")
        else:
            events.append("params")
        return events

    def _apply_source_changes(self) -> List[str]:
        """源码变了 ⇒ M3 热重载（先剔掉底层模块，再换 entry fiber）。"""
        changed = changed_modules(self.snapshot)
        if not changed:
            return []
        events = []
        repo_changed = [m for m in changed if m in ENTRY_OF]
        entry_changed = [m for m in changed if m in ENTRY_MODULES]
        # ① 底层（三仓 bridge 接口）先失效
        if repo_changed:
            reload_module_files(repo_changed)
            events += [f"reimport:{m}" for m in repo_changed]
        # ② 再让 Hmr 换掉对应 entry（含自身变更的 entry）
        entries = sorted({ENTRY_OF[m] for m in repo_changed} | set(entry_changed))
        if entries:
            reload_entries(self.ctx, entries)
            self.reloads += 1
            events += [f"reload:{e.split('.')[-1]}" for e in entries]
        return events

    def tick(self) -> List[str]:
        """轮询一次：检测 → 应用 → 重建。返回事件列表（空 = 无变化）。"""
        events = []
        cm = self._config_mtime()
        if cm is not None and cm != self.config_mtime:
            self.config_mtime = cm
            events += self._apply_config()
        events += self._apply_source_changes()
        if events:
            self.build()
            events.append("rebuild")
        return events

    def close(self) -> None:
        """收尾：停掉 Hmr、关闭会话自己的事件循环。"""
        try:
            hmr = getattr(self.ctx, "hmr", None)
            if hmr is not None:
                hmr.stop()
        except Exception:                                   # noqa: BLE001
            pass
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
            self._loop = None

    def run(self, iterations: Optional[int] = None, interval: float = 0.5,
            printer=None) -> int:
        """持续跑；`iterations=None` 表示一直跑（Ctrl-C 退出）。"""
        printer = printer or _default_printer
        printer(self.build(), ["startup"])
        n = 0
        try:
            while iterations is None or n < iterations:
                events = self.tick()
                if events:
                    printer(self.last_report, events)
                n += 1
                if iterations is None or n < iterations:
                    _sleep(interval)
        except KeyboardInterrupt:                            # noqa: BLE001
            printer(self.last_report, ["interrupt"])
        return n


# -------------------------------------------------------------- 辅助 --
def _sleep(sec: float) -> None:
    import time

    time.sleep(sec)


async def _settle(rounds: int = 20) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


def _default_printer(report: Dict[str, Any], events: List[str]) -> None:
    print(f"[{', '.join(events)}] backend={report['backend']} "
          f"verts={report['vertex_count']} "
          f"h={report['height_min']:.3f}~{report['height_max']:.3f} "
          f"registry={report['registry']}")


def boot(params: Dict[str, Any] = None, config_path: str = None) -> "DevLoop":
    """**推荐入口**（同步）：在**一个**事件循环上完成装配并返回会话。

    别用 `asyncio.run(DevLoop.start())` —— 它会在结束时关闭 loop，
    后续 `tick()` 里的换实现（异步）就找不到原来的 loop 了。
    """
    loop = asyncio.new_event_loop()
    try:
        dev = loop.run_until_complete(DevLoop.start(params, config_path))
    except BaseException:
        loop.close()
        raise
    dev._loop = loop
    return dev


async def start(params: Dict[str, Any] = None, config_path: str = None) -> DevLoop:
    """异步入口（高级用法）；同步开发循环请用 `boot()`。"""
    return await DevLoop.start(params, config_path)
