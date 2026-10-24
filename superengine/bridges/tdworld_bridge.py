# -*- coding: utf-8 -*-
"""3dworld 桥接：把表现层能力挂到 cordis 上（提供 `terrain_sink` + `render_sink` 契约）。

**这一条就是三仓流水线此前断掉的一腿**：worldbuilder 早已产出 worldspec、
an-engine 早已消费，唯独表现层没接。本桥接把「高程 → 网格」的接缝暴露出来，
且全程 headless / 零 GL，可在 CI 直接断言。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from .._locate import ensure_cordis

ensure_cordis()
from cordis import Service  # noqa: E402

from .._locate import import_bridge  # noqa: E402
from ..contracts import CONTRACT_VERSIONS, check_provider  # noqa: E402


class TdworldBridge(Service):
    """满足契约 ``terrain_sink`` + ``render_sink``。"""

    provide = "tdworld"
    #: 依赖上游的世界/高程服务（装配顺序由 cordis 依 inject 图决定，与 yml 书写顺序无关）
    inject: Dict[str, None] = {"worldbuilder": None}

    def __init__(self, ctx, config):
        super().__init__(ctx, "tdworld")
        cfg = config or {}
        self.config = cfg
        self._mod = import_bridge("3dworld")
        self.supported: Dict[str, str] = dict(self._mod.SUPPORTED_CONTRACTS)
        check_provider(self, self.supported)

    # ---- terrain_sink ----
    def clipmap_config(self, levels: int = 5, grid: int = 32, base_cell: float = 1.0) -> Any:
        return self._mod.clipmap_config(levels=levels, grid=grid, base_cell=base_cell)

    def terrain_mesh(self, height_fn: Callable[[float, float], float],
                     camera: Tuple[float, float] = (0.0, 0.0),
                     config: Any = None, world_size: float = None) -> Dict[str, Any]:
        return self._mod.terrain_mesh(height_fn, camera=camera, config=config,
                                      world_size=world_size)

    # ---- render_sink ----
    def terrain_from_heightfield(self, hm, tile_m: float = 1.0,
                                 camera: Tuple[float, float] = (0.0, 0.0),
                                 config: Any = None,
                                 height_scale: float = 1.0) -> Dict[str, Any]:
        return self._mod.terrain_from_heightfield(
            hm, tile_m=tile_m, camera=camera, config=config, height_scale=height_scale)

    # ---- 组合语义：直接吃上游服务，产出网格（M1 的主路径）----
    def terrain_from_world(self, worldbuilder, source, tile_m: float = 1.0,
                           camera: Tuple[float, float] = (0.0, 0.0),
                           config: Any = None) -> Dict[str, Any]:
        """worldbuilder 的世界 → 3dworld 地形网格（**M1 主路径**）。

        `source` 可以是 world dict 或 worldspec 目录。走的是真正的跨仓接缝：
        ``worldbuilder.heightfield`` → ``worldbuilder.make_height_sampler``
        → ``3dworld.terrain_mesh`` —— 坐标解释权归产出方（worldbuilder），
        表现层只消费 ``f(x, z) -> h``。

        全程同进程、不落盘；需要存档/跨进程时才走 worldspec 文件契约
        （两条路径并存，见规划文档 §2.6-B）。
        """
        hm = worldbuilder.heightfield(source)
        sampler = worldbuilder.make_height_sampler(hm, tile_m=tile_m)
        return self.terrain_mesh(sampler, camera=camera, config=config)

    def contract_report(self) -> Dict[str, str]:
        return {k: f"{CONTRACT_VERSIONS[k]} in {v}" for k, v in self.supported.items()}

    def __cordis_init__(self):
        return None


#: cordis Loader 按 entry ``name`` import 模块后取其 ``default``（Service 类）
default = TdworldBridge
