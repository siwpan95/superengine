# -*- coding: utf-8 -*-
"""an-engine 桥接：把玩法内核挂到 cordis 上（提供 `gameplay_world` + `mapgraph_source`）。

**托管而非替换**（规划文档 §2.6-A）：
an-engine 的 ``core.context.Context`` 自述「源自 Cordis 三个算子」且**刻意零第三方依赖**。
本桥接不把 cordis 塞进去替换它，而是**托管** —— 外层 cordis 负责生命周期与回滚，
内层仍是它自己的 Context，零依赖与既有测试基线都不受影响。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._locate import ensure_cordis

ensure_cordis()
from cordis import Service  # noqa: E402

from .._locate import import_bridge  # noqa: E402
from ..contracts import CONTRACT_VERSIONS, check_provider  # noqa: E402


class AnengineBridge(Service):
    """满足契约 ``gameplay_world`` + ``mapgraph_source``。"""

    provide = "anengine"
    inject: Dict[str, None] = {"worldbuilder": None}

    def __init__(self, ctx, config):
        super().__init__(ctx, "anengine")
        cfg = config or {}
        self.config = cfg
        self._mod = import_bridge("an-engine")
        self.supported: Dict[str, str] = dict(self._mod.SUPPORTED_CONTRACTS)
        check_provider(self, self.supported)
        #: 被托管的 an-engine Context（懒建；零第三方依赖，不 import cordis）
        self._ctx = None

    # ---- gameplay_world ----
    def new_context(self) -> Any:
        """新建一个被托管的 an-engine Context。"""
        return self._mod.new_context()

    def provide_mapgraph(self, ctx: Any, graph: Any, key: str = "mapgraph") -> Any:
        return self._mod.provide_mapgraph(ctx, graph, key=key)

    @property
    def hosted(self) -> Any:
        """本服务持有的托管 Context（懒建）。"""
        if self._ctx is None:
            self._ctx = self.new_context()
        return self._ctx

    # ---- mapgraph_source ----
    def mapgraph_from_worldspec(self, spec_dir, *, strict: bool = False) -> Any:
        return self._mod.mapgraph_from_worldspec(spec_dir, strict=strict)

    def route(self, graph: Any, start: str, goal: str, **kw) -> List[str]:
        return self._mod.route(graph, start, goal, **kw)

    def nearest(self, graph: Any, x: float, z: float, **kw) -> Any:
        return self._mod.nearest(graph, x, z, **kw)

    # ---- 组合语义：从上游世界直接装配玩法世界 ----
    def world_from(self, worldbuilder, spec_dir, strict: bool = False) -> Any:
        """worldspec 目录 → 托管 Context 里挂好 MapGraph 的玩法世界（M2）。"""
        ctx = self.hosted
        graph = self.mapgraph_from_worldspec(spec_dir, strict=strict)
        self.provide_mapgraph(ctx, graph)
        return ctx

    def contract_report(self) -> Dict[str, str]:
        return {k: f"{CONTRACT_VERSIONS[k]} in {v}" for k, v in self.supported.items()}

    def __cordis_init__(self):
        return None


#: cordis Loader 按 entry ``name`` import 模块后取其 ``default``（Service 类）
default = AnengineBridge
