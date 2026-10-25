# -*- coding: utf-8 -*-
"""worldbuilder 桥接：把世界生成能力挂到 cordis 上（提供 `worldspec` + `terrain` 契约）。

只通过 ``worldbuilder.bridge`` 友好接口调用，不 import 其内部模块。
装配期即做**契约版本 + 结构**双校验（`check_provider`），不把不兼容留到运行期。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

from .._locate import ensure_cordis

ensure_cordis()
from cordis import Service  # noqa: E402

from .._locate import import_bridge  # noqa: E402
from ..contracts import CONTRACT_VERSIONS, check_provider  # noqa: E402


class WorldbuilderBridge(Service):
    """满足契约 ``worldspec_source`` + ``terrain_source``。

    挂载名 ``worldbuilder``，并同时给出短别名 ``worldspec`` / ``terrain``
    （消费方按语义选一个用即可）。
    """

    provide = "worldbuilder"

    def __init__(self, ctx, config):
        super().__init__(ctx, "worldbuilder")
        cfg = config or {}
        self.config = cfg
        self._mod = import_bridge("worldbuilder")
        #: 该仓声明的兼容区间（装配期校验用）
        self.supported: Dict[str, str] = dict(self._mod.SUPPORTED_CONTRACTS)
        check_provider(self, self.supported)
        # 短别名：让消费方能写 inject=['worldspec'] 或 ['terrain']
        ctx.reflect.provide("worldspec", self)
        ctx.reflect.provide("terrain", self)

    # ---- worldspec_source ----
    def generate(self, width: int = 256, height: int = 256, seed: int = 0, **kw) -> dict:
        return self._mod.generate(width=width, height=height, seed=seed, **kw)

    def generate_complete(self, width: int = 256, height: int = 256, seed: int = 0, **kw) -> dict:
        """完整世界（含 POI + 路网 ⇒ 落盘后有 graph.json，玩法侧才有节点可寻路）。"""
        return self._mod.generate_complete(width=width, height=height, seed=seed, **kw)

    def save(self, world: dict, out_dir, *, tile_m: float = 1.0,
             generator: str = "worldbuilder") -> dict:
        return self._mod.save(world, out_dir, tile_m=tile_m, generator=generator)

    def load(self, spec_dir, *, layers: Optional[Iterable[str]] = None) -> dict:
        return self._mod.load(spec_dir, layers=layers)

    def validate_spec(self, spec_dir) -> List[str]:
        return self._mod.validate_spec(spec_dir)

    def meta(self, spec_dir) -> dict:
        return self._mod.meta(spec_dir)

    # ---- terrain_source ----
    def heightfield(self, source: Any):
        return self._mod.heightfield(source)

    def make_height_sampler(self, hm, tile_m: float = 1.0,
                            height_scale: float = 1.0) -> Callable[[float, float], float]:
        return self._mod.make_height_sampler(hm, tile_m=tile_m, height_scale=height_scale)

    # ---- dungeon_source ----
    def generate_dungeon(self, width: int = 48, height: int = 32, rooms: int = 8,
                         seed: int = 0) -> dict:
        """生成房间型地牢（网格 + 房间矩形 + 连接）。"""
        return self._mod.generate_dungeon(width=width, height=height,
                                          rooms=rooms, seed=seed)

    def dungeon_graph(self, grid, *, locks: int = 1, loops: int = 2,
                      seed: int = 0) -> dict:
        """地牢网格 → **可解关卡图**（nodes/edges/keys/entrance/boss）。

        产物与 worldspec 的 ``graph.json`` 同形，所以 an-engine 的 ``MapGraph``
        可以直接吃它 —— 这就是「生成 → 玩法」共用一套契约形状的地方。
        """
        return self._mod.dungeon_graph(grid, locks=locks, loops=loops, seed=seed)

    def grammar_names(self, grammar: dict, n: int = 1, *, seed: int = 0) -> list:
        """文法命名（怪物 / 宝物 / 地名）。"""
        return self._mod.grammar_names(grammar, n, seed=seed)

    # ---- 诊断 ----
    def contract_report(self) -> Dict[str, str]:
        """契约版本 → 该仓声明的兼容区间（排障用）。"""
        return {k: f"{CONTRACT_VERSIONS[k]} in {v}" for k, v in self.supported.items()}

    def __cordis_init__(self):
        return None


#: cordis Loader 按 entry ``name`` import 模块后取其 ``default``（Service 类）
default = WorldbuilderBridge
