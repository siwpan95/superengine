# -*- coding: utf-8 -*-
"""M3 —— cordis `Hmr` 热重载接入。

为什么值得做
------------
调世界参数（种子 / 格距 / 层数）时，以前要重启进程再重新装配三仓；
接入 Hmr 后改完源码直接生效 —— 旧 fiber 被完整回滚，新 fiber 换入，
**不出现「两份逻辑同时跑」**（这正是热重载最容易翻车的地方）。

cordis `Hmr` 的两阶段 reload（`vendor/cordis/src/cordis/hmr.py`）
-----------------------------------------------------------------
1. **先重导入**：把所有变更模块重新 import 一遍，旧模块对象留作备份；
   任一步失败就整体还原（不会留下半更新状态）；
2. **再换 fiber**：逐个 dispose 旧 fiber 并换入新插件，失败则回滚全部。

使用方式
--------
    ctx = ...                      # 已装配（含 loader）
    hmr = await enable_hmr(ctx)    # 挂载 Hmr（并停掉后台监听线程以便确定性调用）
    hot_reload(ctx, 'superengine.bridges.worldbuilder_bridge')

诚实边界
--------
* **Python import 系统的固有限制**（Hmr 源码自承）：`importlib` 无法重绑定
  其他模块已持有的引用，所以**只有自身模块变更的 entry 会被重载**，
  不像 JS 引擎那样做整图传递失效。改了被多处 import 的底层模块，需要把
  依赖它的 bridge 一并列入 reload 列表。
* 本模块的 `hot_reload` 走**确定性路径**（改 mtime + 显式 poll），
  不依赖后台文件监听线程 —— 测试里更可靠。
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, List, Optional

from ._locate import ensure_cordis

ensure_cordis()
from cordis.hmr import Hmr  # noqa: E402
from cordis.timer import TimerService  # noqa: E402

__all__ = ["enable_hmr", "hot_reload", "touch_module", "module_file", "HMR_READY"]


async def enable_hmr(ctx, config: Optional[dict] = None):
    """挂载 `Hmr` 服务；返回 hmr 实例。

    Hmr 的 `inject = ['loader', 'timer']`，所以要先有 Loader 与 TimerService。
    挂载后**立刻停止后台监听**：默认的 watchdog 监听线程在测试里不确定，
    而 `reload()` / `_poll()` 是显式同步 API，停掉监听后仍能正常调用。
    """
    if getattr(ctx, "timer", None) is None:
        await ctx.plugin(TimerService)
    await ctx.plugin(Hmr, config or {"base": ".", "debounce": 50})
    hmr = ctx.hmr
    hmr.stop()          # 停掉后台监听线程；热重载改用显式调用
    return hmr


def module_file(module_name: str) -> str:
    """模块对应的源文件路径（用于改 mtime 模拟「改了源码」）。"""
    mod = importlib.import_module(module_name)
    path = getattr(mod, "__file__", None)
    if not path:
        raise ValueError(f"模块 {module_name!r} 没有 __file__（无法热重载）")
    return path


def touch_module(module_name: str) -> str:
    """把模块文件的 mtime 推后一点 —— 等价于「改了源码」但**不改内容**。

    这样测试无需真的编辑源码文件（改内容会让测试自身变成写入操作，不可靠）。
    """
    path = module_file(module_name)
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 1.0))
    return path


def hot_reload(ctx, *module_names: str) -> List[str]:
    """确定性热重载：改 mtime → 显式 poll → Hmr 检测并重加载。

    返回被重载的模块名列表。调用前需先 `enable_hmr(ctx)`。
    """
    hmr = ctx.hmr
    for name in module_names:
        touch_module(name)
    # 确保 Hmr 已把这些 entry 纳入快照（entry 可能在 Hmr 启动后才加载）
    hmr.watch()
    hmr._poll()
    return [n for n in module_names]


def service_is_live(ctx, name: str) -> bool:
    """某个服务当前是否可达且处于 ACTIVE（排障「重载后服务没了」）。"""
    from cordis.fiber import FiberState

    svc = getattr(ctx, name, None)
    if svc is None:
        return False
    fiber = getattr(svc, "ctx", None)
    fiber = getattr(fiber, "fiber", None)
    return fiber is None or fiber.state == FiberState.ACTIVE


def registry_size(ctx) -> int:
    """registry 里已注册插件运行时的数量 —— **热重载不泄漏的判据**。

    旧 fiber 被完整回滚时，规模应**回到基线**；若涨了，说明旧的没被清掉
    （即「两份逻辑同时跑」）。
    """
    return ctx.registry.size


def snapshot_plugins(ctx) -> Any:
    """当前 registry 规模的快照（供前后比对）。"""
    return registry_size(ctx)
