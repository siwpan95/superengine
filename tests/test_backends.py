# -*- coding: utf-8 -*-
"""M4 —— `reflect.Impl` 多实现可替换门禁。

要钉的三件事：
1. **换实现消费方无感**：clipmap → flat，消费方代码一行不改，自动重载；
2. **没有实现时不崩溃**：消费方转 PENDING（cordis 的实时依赖契约）；
3. **不合格实现被拒**：`__cordis_check__` 不过 ⇒ 实现不进 store ⇒ 消费方 PENDING。

另有一条易踩坑记录：`ctx.plugin(X)` 返回的是 **Fiber**，服务实例要从
`ctx.<provide 名>` 取（这里就是 `ctx.terrain_host` / `ctx.terrain_view`）。
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine._locate import ensure_cordis  # noqa: E402

ensure_cordis()
from cordis import Context  # noqa: E402

from superengine.bridges.terrain_backends import (BACKENDS, BadBackend, ClipmapBackend,  # noqa: E402
                                  FlatBackend, TERRAIN_BACKEND,
                                  TerrainBackendHost, TerrainConsumer,
                                  backend_fiber_state,
                                  satisfies_terrain_sink)


async def _settle(rounds: int = 20) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _new(with_consumer: bool = True):
    ctx = Context()
    if with_consumer:
        await ctx.plugin(TerrainConsumer, {})
    await _settle()
    return ctx


def test_consumer_pending_without_implementation():
    """没有实现时消费方是 PENDING（不是异常、也不是静默拿到 None 就崩）。"""
    async def go():
        ctx = await _new()
        return backend_fiber_state(ctx)
    state = asyncio.run(go())
    assert state == 'PENDING', state
    print('  ok: 无实现时消费方 PENDING（等待实现，不崩溃）')


def test_mount_backend_activates_consumer():
    async def go():
        ctx = await _new()
        await ctx.plugin(TerrainBackendHost, {'backend': 'clipmap', 'grid': 8})
        await ctx.terrain_host.mount_backend('clipmap')
        await _settle()
        return backend_fiber_state(ctx), ctx.terrain_view.backend_name()
    state, name = asyncio.run(go())
    assert state == 'ACTIVE', state
    assert name == 'clipmap', name
    print('  ok: 挂载 clipmap 后消费方 ACTIVE，取到后端 clipmap')


def test_swap_implementation_without_touching_consumer():
    """**M4 核心**：换实现，消费方代码一行不改。"""
    async def go():
        ctx = await _new()
        await ctx.plugin(TerrainBackendHost, {'backend': 'clipmap', 'grid': 8})
        host = ctx.terrain_host
        await host.mount_backend('clipmap')
        await _settle()
        first = ctx.terrain_view.backend_name()
        await host.swap('flat')          # 换实现
        await _settle()
        return first, ctx.terrain_view.backend_name(), backend_fiber_state(ctx)
    first, second, state = asyncio.run(go())
    assert first == 'clipmap', first
    assert second == 'flat', second
    assert state == 'ACTIVE', state
    print(f'  ok: 换实现 clipmap → flat，消费方无感重载（状态 {state}）')


def test_swapped_backend_changes_output():
    """换了实现，产出必须真的不同（否则"换"只是换了名字）。"""
    async def go():
        ctx = await _new()
        await ctx.plugin(TerrainBackendHost, {'backend': 'clipmap', 'grid': 8})
        host = ctx.terrain_host
        await host.mount_backend('clipmap')
        await _settle()
        # 用一个有起伏的高度函数
        hilly = lambda x, z: 0.3 + 0.4 * (1.0 if (int(x) + int(z)) % 2 else 0.0)
        a = ctx.terrain_view.build(hilly)
        await host.swap('flat')
        await _settle()
        b = ctx.terrain_view.build(hilly)
        return a, b
    a, b = asyncio.run(go())
    assert abs(a['height_max'] - a['height_min']) > 1e-6, 'clipmap 后端应有起伏'
    assert abs(b['height_max'] - b['height_min']) < 1e-9, 'flat 后端应恒高'
    print(f"  ok: 换实现后产出真的不同（clipmap 起伏 "
          f"{a['height_min']:.2f}~{a['height_max']:.2f} → flat 恒 {b['height_max']}）")


def test_bad_implementation_is_rejected_not_crashing():
    """不合格实现（缺方法）被**拒绝**：消费方 PENDING，不抛异常。"""
    async def go():
        ctx = await _new()
        await ctx.plugin(BadBackend, {})
        await _settle()
        return backend_fiber_state(ctx), ctx.terrain_view is not None
    state, reachable = asyncio.run(go())
    assert state == 'PENDING', f'不合格实现应让消费方保持 PENDING，实际 {state}'
    assert not reachable, '不合格实现不应让消费方变得可用'
    print('  ok: 不合格实现被拒绝（PENDING + 不可达），未崩溃')


def test_check_function_semantics():
    """校验器本身：满足契约 → True；缺方法 → False。"""
    assert satisfies_terrain_sink(object()) is False

    class _Good:
        def clipmap_config(self): ...
        def terrain_mesh(self, fn): ...
    assert satisfies_terrain_sink(_Good()) is True
    print('  ok: 实现校验器按方法存在性判定（True/False 正确）')


def test_backend_registry_lists_options():
    assert set(BACKENDS) >= {'clipmap', 'flat'}, BACKENDS
    assert BACKENDS['clipmap'] is ClipmapBackend
    assert BACKENDS['flat'] is FlatBackend
    print(f'  ok: 实现注册表可用（{sorted(BACKENDS)}），接口名 {TERRAIN_BACKEND!r}')


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
    print(f'[test_backends] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_BACKENDS_TESTS_FAILED')
        return 1
    print('ALL_BACKENDS_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
