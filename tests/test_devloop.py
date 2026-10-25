# -*- coding: utf-8 -*-
"""开发循环门禁 —— M3（热重载）与 M4（多实现替换）在**实际开发循环**里真的联动。

钉三件事：
1. 会话能起来并构建出地形；
2. **改配置** ⇒ 走 M4 换实现（clipmap ⇄ flat，产出真的变）；
3. **改三仓源码** ⇒ 走 M3 热重载（底层模块被重导 + entry fiber 被换，registry 不增长）。

另加：同一参数重复构建结果一致（开发循环不能引入随机漂移）。
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine.devloop import (DEFAULT_PARAMS, DevLoop, boot,  # noqa: E402
                                 load_params, save_params)

TMP = None


def _cfg(name='dev.json'):
    global TMP
    if TMP is None:
        TMP = tempfile.mkdtemp()
    return os.path.join(TMP, name)


def _fresh(params=None):
    """起一个会话（配置落在临时目录，不污染 configs/dev.json）。"""
    cfg = _cfg()
    save_params(dict(params or DEFAULT_PARAMS), cfg)
    return boot(config_path=cfg), cfg


def test_session_boots_and_builds():
    loop, _ = _fresh()
    try:
        rep = loop.build()
        assert rep['backend'] == 'clipmap', rep
        assert rep['vertex_count'] > 0, rep
        assert abs(rep['height_max'] - rep['height_min']) > 1e-6, \
            f"高度无起伏（上游没接通）: {rep}"
    finally:
        loop.close()
    print(f"  ok: 会话启动并构建（clipmap / {rep['vertex_count']} 顶点）")


def test_config_backend_change_swaps_implementation():
    """**M4 接进开发循环**：改配置的 backend ⇒ 换实现，产出真的不同。"""
    loop, cfg = _fresh()
    try:
        before = loop.build()
        p = dict(DEFAULT_PARAMS)
        p['backend'] = 'flat'
        save_params(p, cfg)
        events = loop.tick()
        after = loop.last_report
        assert any('backend→flat' in e for e in events), events
        assert after['backend'] == 'flat', after
        assert after['vertex_count'] != before['vertex_count'], \
            f"换了实现但顶点数没变（没真换）: {before} → {after}"
        assert abs(after['height_max'] - after['height_min']) < 1e-9, 'flat 后端应恒高'
    finally:
        loop.close()
    print(f"  ok: 改配置换实现 clipmap({before['vertex_count']}) → "
          f"flat({after['vertex_count']})")


def test_source_change_triggers_hot_reload():
    """**M3 接进开发循环**：改三仓 bridge 源码 ⇒ 重导底层 + 换 entry fiber。"""
    loop, _ = _fresh()
    try:
        loop.build()
        base = loop.last_report['registry']
        # 只推后 mtime，不改内容（测试不写源码）
        mod = importlib.import_module('worldbuilder.bridge')
        st = os.stat(mod.__file__)
        os.utime(mod.__file__, (st.st_atime, st.st_mtime + 1.0))
        events = loop.tick()
        assert any('reimport:worldbuilder.bridge' in e for e in events), events
        assert any('reload:' in e for e in events), events
        assert 'rebuild' in events, events
        after = loop.last_report['registry']
        assert after <= base, f'热重载后 registry 从 {base} 涨到 {after}（旧 fiber 没清）'
    finally:
        loop.close()
    print(f'  ok: 改源码触发热重载（registry {base} → {after}，无泄漏）')


def test_rebuild_is_deterministic():
    """同参数重复构建结果一致 —— 开发循环不能引入随机漂移。"""
    loop, _ = _fresh()
    try:
        a = loop.build()
        b = loop.build()
        assert a['vertex_count'] == b['vertex_count'], (a, b)
        assert abs(a['height_max'] - b['height_max']) < 1e-12, (a, b)
    finally:
        loop.close()
    print(f"  ok: 同参数重复构建一致（{a['vertex_count']} 顶点）")


def test_params_roundtrip_and_defaults():
    cfg = _cfg('rt.json')
    save_params({'seed': 42, 'backend': 'flat'}, cfg)
    p = load_params(cfg)
    assert p['seed'] == 42 and p['backend'] == 'flat', p
    # 缺失键由默认值补齐
    assert p['tile_m'] == DEFAULT_PARAMS['tile_m'], p
    print('  ok: 开发配置读写与默认值补齐正常')


def test_seed_change_changes_terrain():
    """改 seed ⇒ 地形真的变了（否则"参数生效"只是说说）。"""
    loop, cfg = _fresh()
    try:
        a = loop.build()
        p = dict(DEFAULT_PARAMS)
        p['seed'] = 1234
        save_params(p, cfg)
        loop.tick()
        b = loop.last_report
        assert abs(a['height_max'] - b['height_max']) > 1e-9, (a, b)
    finally:
        loop.close()
    print(f"  ok: 改 seed 地形随之变化（h_max {a['height_max']:.4f} → {b['height_max']:.4f}）")


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
    print(f'[test_devloop] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_DEVLOOP_TESTS_FAILED')
        return 1
    print('ALL_DEVLOOP_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
