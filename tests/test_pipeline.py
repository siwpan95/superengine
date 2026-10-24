# -*- coding: utf-8 -*-
"""门禁三：三仓流水线真的通（M1 表现腿 + M2 玩法腿）。

这两条是整合的**业务价值**所在，不是装配花架子：

* **M1（先做）**：worldbuilder → 3dworld。此前三仓流水线的表现层那一腿是断的
  （worldbuilder 早已产出 worldspec、an-engine 早已消费，唯独 3dworld 没接）。
* **M2（后做）**：worldbuilder → an-engine 的玩法世界被**托管**进组合上下文。

两条都 headless / 零 GL，CI 可直接跑。
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine.assembly import boot  # noqa: E402

_CTX = None


def ctx():
    """装配一次复用（生成世界不便宜）。"""
    global _CTX
    if _CTX is None:
        _CTX, _ = boot()
    return _CTX


def test_m1_worldbuilder_to_3dworld_terrain():
    """M1：worldbuilder 的高程 → 3dworld 的 clipmap 网格（断腿接通）。"""
    c = ctx()
    wb, td = c.worldbuilder, c.tdworld
    world = wb.generate(64, 64, seed=7)
    hm = wb.heightfield(world)
    assert hm.ndim == 2 and hm.size > 0, hm.shape
    res = td.terrain_from_world(wb, world, tile_m=2.0)
    assert res['vertex_count'] > 0, '网格顶点数为 0（表现侧没吃到数据）'
    # 高度必须有起伏 —— 否则说明上游高程根本没被采样
    assert abs(res['height_max'] - res['height_min']) > 1e-6, \
        f"高度无起伏（{res['height_min']} ~ {res['height_max']}）：上游没接通"
    assert len(res['rings']) >= 1
    print(f"  ok: M1 接通 —— {res['vertex_count']} 顶点 / {len(res['rings'])} 层 ring，"
          f"高度 {res['height_min']:.3f}~{res['height_max']:.3f}")


def test_m1_sampler_matches_heightfield():
    """采样器语义：格点上的采样值应等于高程阵列对应格（坐标解释权归产出方）。"""
    c = ctx()
    wb = c.worldbuilder
    world = wb.generate(32, 32, seed=3)
    hm = wb.heightfield(world)
    s = wb.make_height_sampler(hm, tile_m=2.0)
    # 整数格点处双线性插值应回到格值本身（tile_m=2 ⇒ 世界 10m → 第 5 列）
    assert abs(s(0.0, 0.0) - float(hm[0, 0])) < 1e-6
    assert abs(s(10.0, 20.0) - float(hm[10, 5])) < 1e-6   # x=10→c=5, z=20→r=10
    assert abs(s(6.0, 4.0) - float(hm[2, 3])) < 1e-6      # x=6→c=3,  z=4→r=2
    print('  ok: 高程采样器与阵列一致（r→+z、c→+x，tile_m 归产出方解释）')


def test_m1_worldspec_roundtrip():
    """文件契约路径：写盘 → 校验 → 读回，高程逐位一致（离线/跨进程那条路仍通）。"""
    c = ctx()
    wb = c.worldbuilder
    world = wb.generate(32, 32, seed=11)
    d = tempfile.mkdtemp()
    wb.save(world, d, tile_m=2.0)
    assert wb.validate_spec(d) == [], f'worldspec 校验失败: {wb.validate_spec(d)}'
    back = wb.load(d, layers=['height'])
    import numpy as np
    assert np.array_equal(np.asarray(back['height']),
                          np.asarray(world['height'])), '落盘往返后高程不一致'
    print('  ok: worldspec 文件契约往返一致（与服务契约并存的离线路径）')


def test_m2_anengine_hosts_gameplay_world():
    """M2：an-engine 的玩法世界被**托管**（不是替换）进组合上下文。"""
    c = ctx()
    wb, ae = c.worldbuilder, c.anengine
    # 托管容器是 an-engine 自己的 Context（零第三方依赖，不 import cordis）
    hosted = ae.hosted
    assert type(hosted).__name__ == 'Context', type(hosted).__name__
    world = wb.generate_complete(64, 64, seed=7)
    d = tempfile.mkdtemp()
    wb.save(world, d, tile_m=2.0)
    assert 'graph.json' in os.listdir(d), '完整世界应产出 graph.json（POI + 路网）'
    graph = ae.mapgraph_from_worldspec(d)
    nodes = getattr(graph, 'nodes', {})
    assert len(nodes) >= 2, f'玩法图节点过少：{len(nodes)}'
    ids = list(nodes)[:2]
    path = ae.route(graph, ids[0], ids[1])
    assert path and path[0] == ids[0] and path[-1] == ids[1], path
    print(f'  ok: M2 托管 —— 玩法图 {len(nodes)} 节点，寻路 {ids[0]}→{ids[1]} 命中 {len(path)} 段')


def test_m2_provides_mapgraph_into_hosted_context():
    """MapGraph 挂进托管 Context 后可按 key 取回（effect/dispose 归 an-engine 自己管）。"""
    c = ctx()
    wb, ae = c.worldbuilder, c.anengine
    world = wb.generate_complete(48, 48, seed=5)
    d = tempfile.mkdtemp()
    wb.save(world, d, tile_m=2.0)
    h = ae.world_from(wb, d)
    assert h.get('mapgraph') is not None, '托管 Context 里取不到 mapgraph'
    print('  ok: MapGraph 已挂进托管 Context 且可取回')


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
    print(f'[test_pipeline] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_PIPELINE_TESTS_FAILED')
        return 1
    print('ALL_PIPELINE_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
