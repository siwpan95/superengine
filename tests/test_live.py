# -*- coding: utf-8 -*-
"""M3 —— cordis Hmr 热重载门禁。

核心判据不是「看起来更新了」，而是**旧 fiber 真的被清干净**：
registry 规模必须回到基线。涨了就说明旧的没被回收，即热重载最典型的翻车形态
「两份逻辑同时跑」。
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine.assembly import mount  # noqa: E402
from superengine.live import (enable_hmr, hot_reload, module_file,  # noqa: E402
                              registry_size, touch_module)

TARGET = 'superengine.bridges.worldbuilder_bridge'


def _run(coro):
    return asyncio.run(coro)


async def _mounted():
    return await mount()


def test_hmr_service_mounts():
    """Hmr 服务挂载成功。

    注意：`ctx.hmr` 被 cordis 包了一层 `Traceable`（服务值追踪），
    `type(...).__name__` 是 `'Traceable'` 而不是 `'Hmr'` —— 所以按**行为**断言
    （有没有 reload / watch 方法），不要按类名断言。
    """
    async def go():
        ctx = await _mounted()
        hmr = await enable_hmr(ctx)
        return hmr, ctx.hmr
    hmr, via_ctx = _run(go())
    assert via_ctx is not None, 'ctx.hmr 不可达'
    for method in ('reload', 'watch', '_poll', 'stop'):
        assert hasattr(hmr, method), f'Hmr 缺少方法 {method}'
    print(f'  ok: Hmr 服务挂载成功（经 Traceable 包装，按行为断言：'
          f'reload/watch/_poll/stop 齐备）')


def test_hot_reload_does_not_leak_fibers():
    """热重载后 registry 规模必须**不增长** —— 旧 fiber 被完整回滚。"""
    async def go():
        ctx = await _mounted()
        await enable_hmr(ctx)
        before = registry_size(ctx)
        hot_reload(ctx, TARGET)
        after = registry_size(ctx)
        return before, after
    before, after = _run(go())
    assert after <= before, \
        f'热重载后 registry 从 {before} 涨到 {after} —— 旧 fiber 没被回收（两份逻辑同时跑）'
    print(f'  ok: 热重载后 registry 规模 {before} → {after}（无泄漏）')


def test_service_still_usable_after_reload():
    """重载后的服务必须**还能干活**（而不是只剩个空壳）。"""
    async def go():
        ctx = await _mounted()
        await enable_hmr(ctx)
        hot_reload(ctx, TARGET)
        wb = ctx.worldbuilder
        return wb.heightfield(wb.generate(32, 32, seed=1)).shape
    shape = _run(go())
    assert shape == (32, 32), shape
    print(f'  ok: 重载后服务仍可用（高程 {shape}）')


def test_terrain_rebuilds_after_reload():
    """M1 的腿在热重载之后依然通（生成 → 表现）。"""
    async def go():
        ctx = await _mounted()
        await enable_hmr(ctx)
        hot_reload(ctx, TARGET)
        wb, td = ctx.worldbuilder, ctx.tdworld
        world = wb.generate(64, 64, seed=7)
        return td.terrain_from_world(wb, world, tile_m=2.0)
    res = _run(go())
    assert res['vertex_count'] > 0, '重载后地形网格为空'
    assert abs(res['height_max'] - res['height_min']) > 1e-6, '重载后高度无起伏'
    print(f"  ok: 重载后地形仍可重建（{res['vertex_count']} 顶点）")


def test_touch_module_only_changes_mtime():
    """模拟「改源码」只推后 mtime，**不改内容** —— 测试自身不做源码写入。"""
    path = module_file(TARGET)
    with open(path, 'r', encoding='utf-8') as f:
        before = f.read()
    m0 = os.stat(path).st_mtime
    touch_module(TARGET)
    m1 = os.stat(path).st_mtime
    with open(path, 'r', encoding='utf-8') as f:
        after = f.read()
    assert before == after, 'touch 不应改动文件内容'
    assert m1 > m0, 'touch 应推后 mtime'
    print('  ok: touch 只改 mtime、不改内容（测试不写源码）')


def test_repeated_reload_is_stable():
    """连续多次热重载不应累积（每轮都完整回滚）。"""
    async def go():
        ctx = await _mounted()
        await enable_hmr(ctx)
        base = registry_size(ctx)
        for _ in range(3):
            hot_reload(ctx, TARGET)
        return base, registry_size(ctx)
    base, after = _run(go())
    assert after <= base, f'连续重载后 {base} → {after}（累积了）'
    print(f'  ok: 连续 3 次热重载规模稳定（{base} → {after}）')


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f'  ok: {name}')
        except AssertionError as exc:
            failed.append((name, exc))
            print(f'  FAIL: {name}: {exc}')
        except Exception as exc:                            # noqa: BLE001
            failed.append((name, exc))
            print(f'  ERROR: {type(exc).__name__}: {exc}')
    print('=' * 60)
    print(f'[test_live] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_LIVE_TESTS_FAILED')
        return 1
    print('ALL_LIVE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
