# -*- coding: utf-8 -*-
"""G1 —— ``render_sink`` 契约的端到端机械断言。

调研结论（只读，2026-11-04）
----------------------------
**提供方**：``3dworld/world3d/bridge.py::terrain_from_heightfield`` 是真实实现。
它把高程阵列 ``hm`` 包成 ``sample(x, z)`` 闭包（``round(x/tile_m)`` → 列、
``round(z/tile_m)`` → 行，越界钳制，再乘 ``height_scale``），交给
``terrain_mesh`` → ``build_clipmap`` / ``build_ring_mesh`` / ``displace``，
产出带 ``positions`` / ``uvs`` / ``indices`` 的 ``MeshData`` 与高度统计。

**桥接 + 装配**：``superengine/bridges/tdworld_bridge.py::TdworldBridge``
把该方法薄转发到 ``self._mod``（= ``import_bridge("3dworld")``）；
cordis 依 ``configs/cordis.super.yml`` 把它挂成 ``ctx.tdworld``（外面包一层
``Traceable``），构造期用 ``check_provider(self, self.supported)`` 做结构门禁。
3dworld 在 ``SUPPORTED_CONTRACTS`` 里声明 ``render_sink: >=1.0,<2.0``。

**消费方**：**本仓内没有消费方**。全仓（含三个兄弟仓）grep 确认
``terrain_from_heightfield`` 除「Protocol 声明 / bridge 定义 / bridge 转发」外
**零调用点**。已覆盖的 M1 主路径 ``terrain_from_world`` 走的是
``terrain_mesh`` + worldbuilder 的采样器（即 ``terrain_sink``），不是本契约。

什么才算「端到端」
------------------
因此这里的端到端**不是**「提供方 → 渲染器 / 窗口」——本仓按设计全程
headless、零 GL（这是覆盖审计 G3 已显式接受的边界，不伪造）。
本模块钉住的是**数据面**的完整链路：

    真实上游 worldbuilder.generate() → heightfield() 产出的 numpy 高程阵列
      → 经 cordis 装配出的 ctx.tdworld（不是直接 import world3d.bridge）
      → RenderSink.terrain_from_heightfield(...) 契约方法
      → 真实 clipmap 网格（rings / meshes / 顶点 / 高度统计）

判据是「网格里的高度真的来自那张 hm」，而不只是 ``isinstance`` 通过或
返回一个非空 dict —— 只断言后者的话，一个返回固定桩数据的实现也能绿。

**诚实边界**：
* 链路终点是 ``MeshData`` 数据，**不建窗口、不上屏、不建 GL 上下文**；
  真实渲染归 3dworld 测试域。
* 无仓内消费方是设计事实（契约先行、备用路径），本模块不假装存在消费方；
  它保证的是「这条备用路径一旦被调用，数据能真跑通且不与 terrain_sink 漂移」。
* 全程不加载任何重量级 pyglet 子模块 —— 这是 Linux / macOS job 采用
  「精简依赖、不装 X11/GL 系统库」策略的前提，故也做成机械断言。

为什么单独一个模块（而不是并入 test_pipeline.py）
------------------------------------------------
``test_pipeline.py`` 的叙事是 M1/M2 里程碑，且带自己的 ``_CTX`` 缓存；把
8 条 render_sink 断言塞进去会冲淡那条主线，也会让 G1 这个登记过的缺口
在 ``run_tests.py`` 的输出里看不见。独立模块能让「G1 已闭环」成为一行
可单独判定的 ``[PASS]``。同时不改动任何既有测试模块，避开并行改动面。
"""

from __future__ import annotations

import inspect
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from superengine._locate import import_bridge  # noqa: E402
from superengine.assembly import boot  # noqa: E402
from superengine.contracts import (CONTRACTS, CONTRACT_VERSIONS,  # noqa: E402
                                   RenderSink, check_provider,
                                   verify_provider, version_in_interval)
from superengine.contracts._version import ContractVersionError  # noqa: E402

#: 重量级 pyglet 子模块 —— 这些会拉 X11 / GL / 窗口 / 音频驱动。
#: 在模块导入时取基线，后面断言整条链路不新增它们（见最后一个测试）。
_HEAVY_PYGLET_PARTS = frozenset(
    {'app', 'gl', 'window', 'display', 'input', 'font', 'lib', 'media'})


def _heavy_pyglet_modules() -> set:
    return {m for m in sys.modules
            if m.startswith('pyglet.') and m.split('.')[1] in _HEAVY_PYGLET_PARTS}


_HEAVY_AT_IMPORT = frozenset(_heavy_pyglet_modules())

_CTX = None


def ctx():
    """装配一次复用（生成世界不便宜）。走真实 cordis 装配，不直接 import 三仓。"""
    global _CTX
    if _CTX is None:
        _CTX, _ = boot()
    return _CTX


def _arithmetic_hm() -> np.ndarray:
    """确定性高程阵列：纯算术构造，不依赖 RNG（避免 numpy 版本差异）。

    非退化（有起伏）、全为正值，便于用「×height_scale 恰好翻倍」做精确断言。
    """
    r, c = np.mgrid[0:32, 0:32]
    return (0.5 + 0.1 * np.sin(r * 0.3) + 0.05 * np.cos(c * 0.7)).astype(float)


# ------------------------------------------------------------ 契约 / 门禁 ----
def test_render_sink_is_registered_and_runtime_checkable():
    """契约必须在两个注册表里、版本 1.0.0、Protocol 可运行时检查且含该方法。"""
    assert 'render_sink' in CONTRACT_VERSIONS, '契约注册表缺 render_sink'
    assert CONTRACT_VERSIONS['render_sink'] == '1.0.0', \
        f"render_sink 版本漂移：{CONTRACT_VERSIONS['render_sink']}"
    assert 'render_sink' in CONTRACTS, 'Protocol 注册表缺 render_sink'
    proto = CONTRACTS['render_sink']
    assert proto is RenderSink
    assert getattr(proto, '_is_runtime_protocol', False), \
        'RenderSink 未标 @runtime_checkable，isinstance 门禁会失效'
    assert 'terrain_from_heightfield' in vars(proto), \
        'RenderSink 丢了 terrain_from_heightfield —— 契约形状被改了'
    print('  ok: render_sink 已注册（1.0.0）且 Protocol 含唯一方法')


def test_assembled_provider_passes_render_sink_gate():
    """装配出的 ctx.tdworld 必须真满足 render_sink 的结构 + 版本门禁。"""
    td = ctx().tdworld
    assert isinstance(td, RenderSink), \
        f'{type(td).__name__} 不满足 RenderSink（结构门禁形同虚设）'
    assert 'render_sink' in td.supported, \
        f'提供方未声明 render_sink：{sorted(td.supported)}'
    spec = td.supported['render_sink']
    assert version_in_interval(CONTRACT_VERSIONS['render_sink'], spec), \
        f"契约版本 {CONTRACT_VERSIONS['render_sink']} 不在声明区间 {spec}"
    check_provider(td, td.supported)                       # 不得抛
    assert verify_provider(td, td.supported)['render_sink'] == 'ok'
    print(f'  ok: 装配服务通过 render_sink 门禁（{CONTRACT_VERSIONS["render_sink"]} in {spec}）')


def test_gate_rejects_provider_missing_render_sink():
    """负例对照：缺 terrain_from_heightfield 的提供方必须被拒。

    ``runtime_checkable`` 的 Protocol 只查方法存在性；若有人把
    RenderSink 改空，上一条 isinstance 会对任何对象返回 True —— 这条负例
    就是为了防止门禁「空转」。这是机械断言，不是空测试。
    """
    class OnlyTerrainSink:                       # 有 terrain_sink 的全部方法，唯独缺 render_sink
        def clipmap_config(self, levels=5, grid=32, base_cell=1.0): ...

        def terrain_mesh(self, height_fn, camera=(0.0, 0.0), config=None,
                         world_size=None): ...

    fake = OnlyTerrainSink()
    assert not isinstance(fake, RenderSink), \
        '缺少 terrain_from_heightfield 的对象竟被判为满足 RenderSink'
    supported = {'render_sink': '>=1.0,<2.0'}
    try:
        check_provider(fake, supported)
    except ContractVersionError:
        pass
    else:
        raise AssertionError('缺方法的提供方未被 check_provider 拒绝（门禁空转）')
    assert verify_provider(fake, supported)['render_sink'] != 'ok'
    print('  ok: 缺方法提供方被拒（结构门禁非空转）')


# --------------------------------------------------------------- 端到端 ----
def test_end_to_end_real_heightfield_to_clipmap_mesh():
    """核心 E2E：真实上游高程阵列 → 装配服务 → 网格数据真的吃到 hm。"""
    c = ctx()
    wb, td = c.worldbuilder, c.tdworld
    world = wb.generate(32, 32, seed=7)
    hm = wb.heightfield(world)
    assert getattr(hm, 'ndim', None) == 2 and hm.size > 0, '上游高程阵列无效'

    res = td.terrain_from_heightfield(hm, tile_m=2.0)
    assert isinstance(res, dict), f'返回值不是 dict：{type(res).__name__}'
    for key in ('config', 'rings', 'meshes', 'vertex_count',
                'height_min', 'height_max', 'stats'):
        assert key in res, f'网格结果缺字段 {key}'
    assert res['vertex_count'] > 0, '顶点数为 0（表现侧没吃到数据）'
    assert len(res['rings']) >= 1, '没有任何 ring'
    assert len(res['meshes']) == len(res['rings']), \
        f"meshes({len(res['meshes'])}) 与 rings({len(res['rings'])}) 数量不一致"
    assert all(len(m.positions) > 0 and len(m.positions) % 3 == 0
               and len(m.indices) > 0 for m in res['meshes']), \
        '存在空的 / 非三角形的 MeshData'
    # 关键判据：高度统计必须落在 hm 的真实值域内，且非退化。
    # 全部采样点都是 hm[r, c] * 1.0（钳制过边界），所以这是**必然成立**的
    # 不变量；一个返回全 0 / 固定桩数据的实现会在这里红。
    lo, hi = float(hm.min()), float(hm.max())
    assert lo - 1e-9 <= res['height_min'] <= res['height_max'] <= hi + 1e-9, \
        f"网格高度 {res['height_min']}~{res['height_max']} 不在 hm 值域 {lo}~{hi} 内"
    assert res['height_max'] - res['height_min'] > 1e-6, \
        '高度无起伏（上游高程根本没被采样）'
    print(f"  ok: 端到端接通 —— {res['vertex_count']} 顶点 / {len(res['rings'])} ring，"
          f"高度 {res['height_min']:.3f}~{res['height_max']:.3f} ⊂ hm[{lo:.3f},{hi:.3f}]")


def test_height_scale_and_config_reach_provider():
    """薄转发最典型的回归是「漏传某个参数」——这里做两个变异体敏感的断言。"""
    td = ctx().tdworld
    hm = np.full((32, 32), 3.25)                # 常数场 ⇒ 高度可精确比较
    base = td.terrain_from_heightfield(hm, tile_m=2.0)
    scaled = td.terrain_from_heightfield(hm, tile_m=2.0, height_scale=2.0)
    # 漏传 height_scale 的变异体会得到 3.25 而非 6.5 → 这里会红。
    assert abs(base['height_max'] - 3.25) < 1e-12
    assert abs(scaled['height_max'] - 2 * base['height_max']) < 1e-12, \
        f"height_scale 未透传：{base['height_max']} → {scaled['height_max']}"
    assert abs(scaled['height_min'] - 2 * base['height_min']) < 1e-12

    cfg = td.clipmap_config(levels=2, grid=8, base_cell=2.0)
    small = td.terrain_from_heightfield(hm, tile_m=2.0, config=cfg)
    # 漏传 config 的变异体会退回默认 5 层 → 顶点数不变 → 这里会红。
    assert small['vertex_count'] != base['vertex_count'], \
        f"config 未透传（顶点数仍是 {small['vertex_count']}）"
    assert len(small['rings']) == 2 and len(base['rings']) == 5, \
        f"config 层数未生效：{len(small['rings'])} vs {len(base['rings'])}"
    print(f"  ok: height_scale 精确翻倍、config 改变几何"
          f"（{base['vertex_count']} → {small['vertex_count']} 顶点）")


def test_all_parameters_match_provider_oracle():
    """与底层 provider 逐项比对：5 个参数全部非默认值，防漏传 / 错序。

    这是本模块最强的「防静默漂移」断言：桥接层只要吞掉或错位任一参数，
    顶点数 / 高度统计就会与真实实现分叉。用 ``import_bridge`` 走
    ``_locate.py`` 的统一定位，路径不写死盘符。
    """
    td = ctx().tdworld
    mod = import_bridge('3dworld')               # 真实实现作为 oracle
    assert hasattr(mod, 'terrain_from_heightfield'), '3dworld bridge 缺真实实现'
    hm = _arithmetic_hm()
    cfg = td.clipmap_config(levels=2, grid=8, base_cell=2.0)
    kw = dict(tile_m=3.0, camera=(4.0, 6.0), config=cfg, height_scale=1.5)
    via_service = td.terrain_from_heightfield(hm, **kw)
    via_provider = mod.terrain_from_heightfield(hm, **kw)
    for key in ('vertex_count', 'height_min', 'height_max'):
        assert via_service[key] == via_provider[key], \
            f'{key} 不一致：服务 {via_service[key]} vs provider {via_provider[key]}'
    assert len(via_service['rings']) == len(via_provider['rings'])
    assert len(via_service['meshes']) == len(via_provider['meshes'])
    print('  ok: 5 参数全链路透传，产出与底层 provider 逐项一致')


def test_parity_with_terrain_sink_on_constant_field():
    """G1 登记的风险就是「render_sink 与 terrain_sink 静默漂移」。

    常数高程场上，``render_sink`` 的最近邻采样与 ``terrain_sink`` 侧
    worldbuilder 的双线性采样**必然**返回同一常数，两者几何也应完全一致。
    任一侧改了默认 config / 采样坐标 / ring 构造，这条就会分叉。
    """
    c = ctx()
    wb, td = c.worldbuilder, c.tdworld
    hm = np.full((32, 32), 3.25)
    a = td.terrain_from_heightfield(hm, tile_m=2.0)                 # render_sink
    s = wb.make_height_sampler(hm, tile_m=2.0)
    b = td.terrain_mesh(s)                                          # terrain_sink
    assert a['vertex_count'] == b['vertex_count'], \
        f"顶点数漂移：render_sink {a['vertex_count']} vs terrain_sink {b['vertex_count']}"
    assert len(a['rings']) == len(b['rings']), 'ring 数漂移'
    assert a['height_min'] == b['height_min'] == 3.25
    assert a['height_max'] == b['height_max'] == 3.25
    print(f"  ok: 常数场上两契约几何一致（{a['vertex_count']} 顶点 / "
          f"{len(a['rings'])} ring / h=3.25）")


def test_chain_stays_headless_without_gl_or_window():
    """整条链路不得拉进重量级 pyglet 子模块（CI 精简依赖策略的前提）。

    本机已实测：装配 + render_sink 调用全程只加载 ``pyglet`` /
    ``pyglet.math``；Linux / macOS job 正是据此不装 X11/GL 系统库。
    若将来有人给这条路径引入窗口 / GL 上下文，这里会先红，并给出
    「需回退到 apt 清单」的明确指向。
    """
    c = ctx()
    hm = _arithmetic_hm()
    res = c.tdworld.terrain_from_heightfield(hm, tile_m=2.0)
    assert res['vertex_count'] > 0, '链路没跑通，边界断言无意义'
    assert 'pyglet' in sys.modules, 'pyglet 根本没被加载，探测条件失效'
    # 只断言「本模块导入之后**新增**了什么」：独立跑（run_tests.py 起子进程）
    # 与并到 pytest 一起跑（可能已被别的模块加载过 pyglet 子模块）都成立，
    # 不会因为环境里本来就有 gl 就假红。
    new_heavy = _heavy_pyglet_modules() - set(_HEAVY_AT_IMPORT)
    assert not new_heavy, (
        f'链路新增了重量级 pyglet 子模块 {sorted(new_heavy)} —— '
        'Linux / macOS 精简 CI 会随之失败，需按 docs/quality/门禁标准.md §3 '
        '回退到 X11/GL apt 清单，或把该依赖从这条路径移走')
    print('  ok: 全程 headless（未新增 app/gl/window/display 等重量级模块）')


# ------------------------------------------------------------------ 入口 ----
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and callable(f) and inspect.isfunction(f)]
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
    print(f'[test_render_sink] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_RENDER_SINK_TESTS_FAILED')
        return 1
    print('ALL_RENDER_SINK_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
