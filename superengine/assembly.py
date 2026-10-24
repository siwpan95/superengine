# -*- coding: utf-8 -*-
"""装配层：按 `cordis.super.yml` 把三仓桥接成一张服务图，并做**装配期门禁**。

三道门禁（对应规划文档 §2.7）
------------------------------
1. **白名单校验 entry name**：cordis 会把 entry 的 ``name`` 当模块名 import，
   等同于执行代码 —— 只放行 `superengine.bridges.*`（3dworld 既有同款门禁）。
2. **先手工 import 再交给 Loader**：cordis 的 Loader **会吞掉插件构造期异常**
   （3dworld 已实证：只表现为"服务不就绪"）。先 import 一次让真实异常浮出来。
3. **终态断言 ACTIVE**：专治「PENDING 静默」—— 依赖名拼错时 cordis 不报错、
   只是一直等，进程可能静默退出。装配后逐个 fiber 查状态，非 ACTIVE 即报错并列出。
"""

from __future__ import annotations

import asyncio
import importlib
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from ._locate import ensure_cordis

ensure_cordis()
from cordis import Context  # noqa: E402
from cordis.fiber import FiberState  # noqa: E402
from cordis.loader import Loader  # noqa: E402

__all__ = [
    "AssemblyError",
    "CONFIG_DIR",
    "config_path",
    "load_tree",
    "await_ready",
    "mount",
    "boot",
    "fiber_report",
    "ALLOWED_ENTRY_PREFIXES",
]

#: entry name 白名单前缀（name 会被 import ⇒ 等同执行代码）
ALLOWED_ENTRY_PREFIXES: Tuple[str, ...] = ("superengine.bridges.",)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")


class AssemblyError(RuntimeError):
    """装配失败（依赖未就绪 / 插件构造异常 / 契约不兼容）。"""


def config_path(name: str = "cordis.super.yml") -> str:
    return os.path.join(CONFIG_DIR, name)


def _validate_entry_names(data, path: str) -> None:
    if not isinstance(data, list):
        raise AssemblyError(f"配置树 {path} 顶层必须是列表，实际 {type(data).__name__}")
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise AssemblyError(f"配置树 {path} 第 {i} 条不是 dict")
        name = entry.get("name")
        if not isinstance(name, str) or not name.startswith(ALLOWED_ENTRY_PREFIXES):
            raise AssemblyError(
                f"配置树 {path} 第 {i} 条 entry 的 name={name!r} 不在白名单内 —— "
                f"entry name 会被 cordis 直接 import（等同执行代码）。"
                f"允许前缀：{ALLOWED_ENTRY_PREFIXES}")


def _preimport(data) -> None:
    """门禁②：先手工 import 每个 entry 模块，让构造期异常**不被 Loader 吞掉**。"""
    for entry in data:
        importlib.import_module(entry["name"])


def fiber_report(ctx) -> List[Dict[str, Any]]:
    """所有已注册插件的 fiber 状态快照（排障与门禁③都用它）。"""
    out = []
    for _key, runtime in ctx.registry.entries():
        for fiber in list(runtime.fibers):
            out.append({
                "name": runtime.name,
                "state": FiberState(fiber.state).name if fiber.state is not None else "?",
                "inject": sorted(fiber.inject.keys()) if getattr(fiber, "inject", None) else [],
            })
    return out


async def load_tree(ctx, path: str):
    """用 cordis 原生 Loader 挂载配置树（**必须先 drain 事件循环**再 update）。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"配置树不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _validate_entry_names(data, path)
    _preimport(data)
    await ctx.plugin(Loader)
    loader = ctx.loader
    # 3dworld 实证：Loader 内部异步注册 isolate 等子插件，必须 drain 几轮再 update，
    # 否则首条 entry 建好时会因 _isolate 尚未提供而 KeyError。
    for _ in range(16):
        await asyncio.sleep(0)
    await loader.root.update(data)
    return loader


async def await_ready(ctx, loader, want: Sequence[str] = (), timeout: float = 10.0) -> bool:
    """等 `want` 里服务全部可达；超时抛 `AssemblyError`（带缺失清单）。"""
    want = tuple(want)
    dt = 1.0 / 60.0
    elapsed = 0.0
    while elapsed < timeout:
        await loader.await_()
        await asyncio.sleep(0)
        if all(getattr(ctx, n, None) is not None for n in want):
            return True
        elapsed += dt
    missing = [n for n in want if getattr(ctx, n, None) is None]
    report = fiber_report(ctx)
    raise AssemblyError(
        f"配置树未在 {timeout}s 内就绪；缺失服务: {missing}\n"
        f"  fiber 状态: {report}\n"
        "  提示：① 依赖名拼错 ⇒ fiber 停在 PENDING（cordis 不报错，只一直等）；"
        "② 插件构造期异常会被 Loader 吞掉 —— 本函数已先手工 import，"
        "若仍不就绪请单独 import 该 entry 模块看真实异常。")


def _assert_all_active(ctx) -> None:
    """门禁③：所有 fiber 终态必须是 ACTIVE —— 治 PENDING 静默。"""
    bad = [r for r in fiber_report(ctx) if r["state"] != "ACTIVE"]
    if bad:
        raise AssemblyError(
            f"装配后仍有 {len(bad)} 个 fiber 不在 ACTIVE：{bad}\n"
            "  PENDING = 依赖未就绪（最常见是 inject 里的服务名与提供方挂载名不一致）；"
            "  FAILED = 构造/校验抛错（cordis 不会自动重试）。")


async def mount(config: str = None, want: Sequence[str] = ("worldbuilder", "tdworld", "anengine")):
    """完整装配：建 Context → 挂配置树 → 等服务 → 断言终态。返回 ctx。"""
    ctx = Context()
    loader = await load_tree(ctx, config or config_path())
    await await_ready(ctx, loader, want)
    _assert_all_active(ctx)
    return ctx


def boot(config: str = None, want: Sequence[str] = ("worldbuilder", "tdworld", "anengine")):
    """同步入口（包一层 asyncio.run），返回 ``(ctx, 诊断报告)``。"""
    ctx = asyncio.run(mount(config, want))
    return ctx, {
        "fibers": fiber_report(ctx),
        "contracts": {
            name: getattr(ctx, name).contract_report()
            for name in want if getattr(ctx, name, None) is not None
        },
    }
