# -*- coding: utf-8 -*-
"""契约版本与兼容区间（**契约独立版本化**的核心机制）。

为什么契约要独立版本
--------------------
三仓各自独立发版。若契约版本跟随某一仓，另外两仓就被那一仓的节奏绑架；
若不做版本化，三仓静默漂移，装配期不报错、运行期才炸 —— 这正是整合最容易死的点。

约定
----
* **契约版本**由本组合仓独立管理（`contracts/<name>.py` 里的 `CONTRACT_VERSION`），
  语义化三段号 ``MAJOR.MINOR.PATCH``；
* **各仓声明兼容区间**（``SUPPORTED_CONTRACTS`` = {契约名: 区间串}），
  区间串形如 ``">=1.0,<2.0"``、``"==1.2.0"``、``">=1.1"``；
* 装配期校验：契约版本必须落在提供方声明的区间内，否则**装配期报错**（不进运行期）。

区间语义：主版本不同即视为不兼容（``>=1.0,<2.0`` 是最常用写法）。
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

__all__ = [
    "ContractVersionError",
    "parse_version",
    "format_version",
    "parse_interval",
    "version_in_interval",
    "check_compat",
    "check_all",
]

_VER_RE = re.compile(r"^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?\s*$")
_OP_RE = re.compile(r"^\s*(>=|<=|==|!=|>|<)?\s*(\d+(?:\.\d+){0,2})\s*$")


class ContractVersionError(ValueError):
    """契约版本不兼容 / 区间串无法解析。"""


def parse_version(text: str) -> Tuple[int, int, int]:
    """``'1.2.3'`` → ``(1, 2, 3)``；缺位补 0。"""
    m = _VER_RE.match(str(text))
    if not m:
        raise ContractVersionError(f"无法解析版本号: {text!r}")
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def format_version(v: Iterable[int]) -> str:
    return ".".join(str(int(x)) for x in v)


def parse_interval(spec: str) -> List[Tuple[str, Tuple[int, int, int]]]:
    """``'>=1.0,<2.0'`` → ``[('>=', (1,0,0)), ('<', (2,0,0))]``。"""
    out: List[Tuple[str, Tuple[int, int, int]]] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        m = _OP_RE.match(part)
        if not m:
            raise ContractVersionError(f"无法解析兼容区间片段: {part!r}（spec={spec!r}）")
        op = m.group(1) or "=="
        out.append((op, parse_version(m.group(2))))
    if not out:
        raise ContractVersionError(f"兼容区间为空: {spec!r}")
    return out


def version_in_interval(version: str, spec: str) -> bool:
    v = parse_version(version)
    for op, bound in parse_interval(spec):
        if op == ">=" and not (v >= bound):
            return False
        if op == "<=" and not (v <= bound):
            return False
        if op == ">" and not (v > bound):
            return False
        if op == "<" and not (v < bound):
            return False
        if op == "==" and not (v == bound):
            return False
        if op == "!=" and not (v != bound):
            return False
    return True


def check_compat(contract: str, version: str, supported: Dict[str, str]) -> None:
    """校验：某仓声明的 `supported` 是否覆盖契约 `contract` 的 `version`。

    不兼容抛 `ContractVersionError`（**装配期**就炸，不留到运行期）。
    契约未被声明同样报错 —— 静默「我没这能力」比显式失败更难查。
    """
    if contract not in supported:
        raise ContractVersionError(
            f"该仓未声明契约 {contract!r}（已声明: {sorted(supported)}）")
    spec = supported[contract]
    if not version_in_interval(version, spec):
        raise ContractVersionError(
            f"契约 {contract!r} 版本 {version} 不在该仓声明的兼容区间 {spec!r} 内")


def check_all(versions: Dict[str, str], supported: Dict[str, str]) -> None:
    """校验一个提供方：只查**它自己声明的**契约（不是反过来要求它满足全部契约）。

    方向很重要：`supported` 是「该仓能提供什么」，`versions` 是「契约现在是什么版本」。
    逐个取 `supported` 的键，到 `versions` 里查版本，再验区间。
    """
    for name in supported:
        if name not in versions:
            raise ContractVersionError(
                f"该仓声明了未知契约 {name!r}（契约注册表里有: {sorted(versions)}）")
        check_compat(name, versions[name], supported)
