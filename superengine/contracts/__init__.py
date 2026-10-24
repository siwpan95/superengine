# -*- coding: utf-8 -*-
"""跨仓契约注册表：**契约版本独立于三仓发版**。

`CONTRACT_VERSIONS` 是唯一权威：改契约版本在这里改，各仓的 ``SUPPORTED_CONTRACTS``
声明的是**兼容区间**，装配期由 ``check_provider`` 校验。
"""

from __future__ import annotations

from typing import Any, Dict

from ._version import (ContractVersionError, check_all, check_compat,  # noqa: F401
                       parse_interval, parse_version, version_in_interval)
from .protocols import (CONTRACTS, GameplayWorld, MapGraphSource, RenderSink,  # noqa: F401
                        TerrainSink, TerrainSource, WorldSpecSource)

__all__ = [
    "CONTRACT_VERSIONS",
    "CONTRACTS",
    "ContractVersionError",
    "check_provider",
    "verify_provider",
    "WorldSpecSource",
    "TerrainSource",
    "MapGraphSource",
    "GameplayWorld",
    "TerrainSink",
    "RenderSink",
]

#: 契约名 → 版本号（**独立版本化**：不跟随任何一仓的发版节奏）
CONTRACT_VERSIONS: Dict[str, str] = {
    "worldspec_source": "1.0.0",
    "terrain_source": "1.0.0",
    "mapgraph_source": "1.0.0",
    "gameplay_world": "1.0.0",
    "terrain_sink": "1.0.0",
    "render_sink": "1.0.0",
}


def check_provider(obj: Any, supported: Dict[str, str]) -> None:
    """装配期校验一个提供方：版本兼容 + 契约结构都满足。

    * **版本**：`CONTRACT_VERSIONS` 必须落在 `supported` 声明的区间内
      （该仓没声明某个契约 ⇒ 直接报错，不允许「默默没有」）；
    * **结构**：该仓声明的每个契约，其对象都要 `isinstance` 满足对应 Protocol。
    """
    check_all(CONTRACT_VERSIONS, supported)
    for name in supported:
        proto = CONTRACTS.get(name)
        if proto is None:
            raise ContractVersionError(f"未知契约 {name!r}（不在注册表）")
        if not isinstance(obj, proto):
            raise ContractVersionError(
                f"{type(obj).__name__} 不满足契约 {name!r} 的结构（缺少必需方法）")


def verify_provider(obj: Any, supported: Dict[str, str]) -> Dict[str, str]:
    """与 `check_provider` 同校验，但返回结果而非抛错（供诊断/报告用）。"""
    out = {}
    for name in supported:
        try:
            check_compat(name, CONTRACT_VERSIONS[name], supported)
            ok = isinstance(obj, CONTRACTS[name])
            out[name] = "ok" if ok else "结构不满足"
        except ContractVersionError as exc:
            out[name] = f"FAIL: {exc}"
    return out
