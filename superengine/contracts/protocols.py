# -*- coding: utf-8 -*-
"""跨仓契约（**只含方法**的 ``typing.Protocol``，零依赖、零 import 三仓）。

设计约束
--------
* **零依赖**：只 import ``typing``。三仓都不 import 本模块之外的东西 ——
  契约必须能被任何一侧独立引用而不触发对另两仓的依赖。
* **只含方法**：``@runtime_checkable`` 的 Protocol 若带非方法成员，`issubclass()`
  会直接抛错。契约的版本号放在 `contracts/__init__.py` 的 `CONTRACT_VERSIONS` 注册表里，
  与 Protocol 本体分离 —— 这样结构校验（`isinstance`）与版本校验互不干扰。
* **上提而非新建**：`render/terrain/entity` 等能力 3dworld 已有自己的契约
  （`world3d.core.contracts`，15 个 Protocol）。本模块只定义**跨仓**接缝，
  表现层内部契约仍由 3dworld 自己管，避免两套契约漂移。

契约版本是**独立版本号**（不跟随任何一仓的发版节奏），各仓用兼容区间声明支持范围。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple, runtime_checkable

__all__ = [
    "WorldSpecSource",
    "TerrainSource",
    "MapGraphSource",
    "GameplayWorld",
    "TerrainSink",
    "RenderSink",
    "CONTRACTS",
]


@runtime_checkable
class WorldSpecSource(Protocol):
    """世界数据的产出/存取（worldspec v1 文件契约的生产者侧）。"""

    def generate(self, width: int, height: int, seed: int, **kw) -> dict: ...
    def save(self, world: dict, out_dir, *, tile_m: float, generator: str) -> dict: ...
    def load(self, spec_dir, *, layers: Optional[Iterable[str]] = None) -> dict: ...
    def validate_spec(self, spec_dir) -> List[str]: ...
    def meta(self, spec_dir) -> dict: ...


@runtime_checkable
class TerrainSource(Protocol):
    """高程数据与其采样器（喂给表现层的 ``HeightFn``）。"""

    def heightfield(self, source: Any): ...
    def make_height_sampler(self, hm, tile_m: float = 1.0,
                            height_scale: float = 1.0) -> Callable[[float, float], float]: ...


@runtime_checkable
class MapGraphSource(Protocol):
    """玩法侧的世界图（节点/边/寻路）。"""

    def mapgraph_from_worldspec(self, spec_dir, *, strict: bool = False) -> Any: ...
    def route(self, graph: Any, start: str, goal: str, **kw) -> List[str]: ...
    def nearest(self, graph: Any, x: float, z: float, **kw) -> Any: ...


@runtime_checkable
class GameplayWorld(Protocol):
    """玩法内核的托管容器（an-engine 侧：托管而非替换其 Context）。"""

    def new_context(self) -> Any: ...
    def provide_mapgraph(self, ctx: Any, graph: Any, key: str = "mapgraph") -> Any: ...


@runtime_checkable
class TerrainSink(Protocol):
    """表现层消费高程 → 网格（headless，零 GL）。"""

    def clipmap_config(self, levels: int = 5, grid: int = 32, base_cell: float = 1.0) -> Any: ...
    def terrain_mesh(self, height_fn: Callable[[float, float], float],
                     camera: Tuple[float, float] = (0.0, 0.0),
                     config: Any = None, world_size: float = None) -> Dict[str, Any]: ...


@runtime_checkable
class RenderSink(Protocol):
    """表现层直接吃高程阵列的入口（无需外部采样器时的路径）。"""

    def terrain_from_heightfield(self, hm, tile_m: float = 1.0,
                                 camera: Tuple[float, float] = (0.0, 0.0),
                                 config: Any = None,
                                 height_scale: float = 1.0) -> Dict[str, Any]: ...


#: 契约名 → Protocol（供结构校验与文档生成）
CONTRACTS = {
    "worldspec_source": WorldSpecSource,
    "terrain_source": TerrainSource,
    "mapgraph_source": MapGraphSource,
    "gameplay_world": GameplayWorld,
    "terrain_sink": TerrainSink,
    "render_sink": RenderSink,
}
