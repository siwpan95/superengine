# -*- coding: utf-8 -*-
"""M4 —— `reflect.Impl` 多实现可替换。

机制（cordis `reflect.provide(name, value, check)`）
---------------------------------------------------
`check` 是**实现校验器**：框架声明一个接口名（如 `terrain_backend`），
插件用 `ctx.reflect.provide(接口名, 实现, check=校验器)` 提供实现。
消费方只写 `inject = {'terrain_backend': None}` —— **完全不知道背后是哪个实现**。

由此得到三件事：
1. **换实现不动消费方**：dispose 提供方 → 消费方自动卸载（因为依赖消失）；
   mount 新实现 → 消费方自动重载。这就是"可替换"的全部代价。
2. **非法实现被拒而非崩溃**：`check` 不过的实现不会进 fiber 的 store，
   消费方转为 PENDING（不是异常退出）—— 与 cordis 的 inject 实时契约一致。
3. **多实现可并存选择**：同一个接口名，不同场景挂不同实现（真地形 / 平面 / 桩）。

为什么这比"直接 import 具体实现"好
----------------------------------
消费方不再持有具体类的引用，而只依赖接口名；新增一种地形后端时，
消费方**一行都不用改**。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from .._locate import ensure_cordis

ensure_cordis()
from cordis import Service  # noqa: E402
from cordis.fiber import FiberState  # noqa: E402

from ..contracts import TerrainSink  # noqa: E402

__all__ = [
    "TERRAIN_BACKEND",
    "BACKENDS",
    "satisfies_terrain_sink",
    "ClipmapBackend",
    "FlatBackend",
    "TerrainBackendHost",
    "TerrainConsumer",
    "backend_fiber_state",
]

#: 接口名（消费方 inject 的就是这个字符串）
TERRAIN_BACKEND = "terrain_backend"


# ------------------------------------------------------------ 校验器 ----
def satisfies_terrain_sink(obj) -> bool:
    """实现校验器：是否满足 `TerrainSink` 契约（交给 `provide(..., check=)`）。

    注意：cordis 会把它包成 `_InstanceView` 传进来，`isinstance` 对 Protocol
    在这种情况下可能不成立，所以这里**按方法存在性**判定 —— 更稳，也更能给出
    「缺哪个方法」的明确信息。
    """
    required = ("clipmap_config", "terrain_mesh")
    return all(callable(getattr(obj, m, None)) for m in required)


# -------------------------------------------------------- 实现一：真地形 --
class ClipmapBackend(Service):
    """真地形后端：把 3dworld 的 clipmap 包成接口实现。"""

    provide = TERRAIN_BACKEND
    #: `Service.__init__` 会取类的 `__cordis_check__` 传给
    #: `reflect.provide(name, self, check=...)` —— 这就是 Impl 的校验器挂载点。
    __cordis_check__ = staticmethod(satisfies_terrain_sink)

    def __init__(self, ctx, config):
        super().__init__(ctx, TERRAIN_BACKEND)
        cfg = config or {}
        self.config = cfg
        from .._locate import import_bridge

        self._mod = import_bridge("3dworld")
        self.name = "clipmap"

    def clipmap_config(self, levels=5, grid=32, base_cell=1.0):
        return self._mod.clipmap_config(levels=levels, grid=grid, base_cell=base_cell)

    def terrain_mesh(self, height_fn, camera=(0.0, 0.0), config=None, world_size=None):
        return self._mod.terrain_mesh(height_fn, camera=camera, config=config,
                                      world_size=world_size)

    def __cordis_init__(self):
        return None


# ------------------------------------------------------ 实现二：平面地形 --
class FlatBackend(Service):
    """平面后端（等高）：用来证明「换实现消费方无感」的另一个实现。

    它满足同一个 `TerrainSink` 契约，但产出**高度恒为 0** 的网格 ——
    测试据此判当前挂的是哪一个实现。
    """

    provide = TERRAIN_BACKEND
    __cordis_check__ = staticmethod(satisfies_terrain_sink)

    def __init__(self, ctx, config):
        super().__init__(ctx, TERRAIN_BACKEND)
        cfg = config or {}
        self.config = cfg
        self.name = "flat"

    def clipmap_config(self, levels=5, grid=32, base_cell=1.0):
        return {"levels": levels, "grid": grid, "base_cell": base_cell}

    def terrain_mesh(self, height_fn, camera=(0.0, 0.0), config=None, world_size=None):
        grid = int((config or {}).get("grid", 8))
        n = (grid + 1) * (grid + 1)
        return {
            "config": config,
            "rings": [],
            "meshes": [],
            "vertex_count": n,
            "height_min": 0.0,
            "height_max": 0.0,
            "stats": {"levels": 0},
        }

    def __cordis_init__(self):
        return None


#: 接口名 → 可选实现（供按名选择）
BACKENDS = {
    "clipmap": ClipmapBackend,
    "flat": FlatBackend,
}


class BadBackend(Service):
    """**反面样例**（测试用）：挂同一个接口名，但**不满足** `TerrainSink` 契约。

    它的 `__cordis_check__` 会返回 False，于是实现**不会进** fiber 的 store，
    消费方转为 PENDING —— 这正是我们要的行为：**拒绝而非崩溃**。
    """

    provide = TERRAIN_BACKEND
    __cordis_check__ = staticmethod(satisfies_terrain_sink)

    def __init__(self, ctx, config):
        super().__init__(ctx, TERRAIN_BACKEND)
        self.name = "bad"
        # 故意不实现 clipmap_config / terrain_mesh

    def __cordis_init__(self):
        return None


# ------------------------------------------------------------ 托管宿主 ----
class TerrainBackendHost(Service):
    """按名字挂载某个地形后端实现（**带 Impl 校验**）。

    `provide(接口名, 实现, check=...)`：校验不过的实现不会进 store，
    消费方自动转 PENDING —— 而不是抛异常炸掉。
    """

    provide = "terrain_host"

    def __init__(self, ctx, config):
        super().__init__(ctx, "terrain_host")
        cfg = config or {}
        self.config = cfg
        self.backend_name = cfg.get("backend", "clipmap")
        self._plugin_class = BACKENDS.get(self.backend_name)
        self._fiber = None

    async def mount_backend(self, name: Optional[str] = None) -> Any:
        """挂载指定实现（缺省用 config 里的），返回 fiber。"""
        name = name or self.backend_name
        cls = BACKENDS[name]
        if self._fiber is not None:
            await self.unmount_backend()
        self._fiber = self.ctx.registry.plugin(cls, self.config)
        await self._fiber
        self.backend_name = name
        return self._fiber

    async def unmount_backend(self) -> bool:
        """卸载当前实现 —— 消费方会因依赖消失而自动卸载。"""
        if self._fiber is None:
            return False
        cls = BACKENDS[self.backend_name]
        self.ctx.registry.delete(cls)
        self._fiber = None
        await _settle(self.ctx)
        return True

    async def swap(self, name: str) -> Any:
        """换实现：卸载旧的 → 挂新的（消费方自动重载，**代码不改**）。"""
        await self.unmount_backend()
        return await self.mount_backend(name)

    def __cordis_init__(self):
        return None


# -------------------------------------------------------------- 消费方 ----
class TerrainConsumer(Service):
    """消费方：只 inject 接口名，**不知道背后是哪个实现**。"""

    provide = "terrain_view"
    inject: Dict[str, None] = {TERRAIN_BACKEND: None}

    def __init__(self, ctx, config):
        super().__init__(ctx, "terrain_view")
        self.config = config or {}

    def build(self, height_fn, camera=(0.0, 0.0), tile_m: float = 1.0) -> Dict[str, Any]:
        """用**当前挂着的**后端建网格。"""
        backend = getattr(self.ctx, TERRAIN_BACKEND)
        return backend.terrain_mesh(height_fn, camera=camera)

    def backend_name(self) -> str:
        """当前后端自报的名字（排障用）。"""
        backend = getattr(self.ctx, TERRAIN_BACKEND, None)
        return getattr(backend, "name", "?")

    def __cordis_init__(self):
        return None


# ---------------------------------------------------------------- 工具 --
async def _settle(ctx, rounds: int = 8) -> None:
    """把挂起的 fiber 状态推进完（cordis 的挂载/卸载是异步的）。"""
    import asyncio

    for _ in range(rounds):
        await asyncio.sleep(0)


def backend_fiber_state(ctx) -> Optional[str]:
    """消费方 fiber 当前状态（PENDING = 没有可用实现 / 实现未通过校验）。"""
    for _key, runtime in ctx.registry.entries():
        for fiber in list(runtime.fibers):
            if TERRAIN_BACKEND in (getattr(fiber, "inject", None) or {}):
                return FiberState(fiber.state).name
    return None
