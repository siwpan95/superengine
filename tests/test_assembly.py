# -*- coding: utf-8 -*-
"""门禁二：装配期门禁 —— 契约版本兼容、fiber 终态 ACTIVE、依赖图顺序。

治的正是 cordis 两个已记录的坑：
* **PENDING 静默**：依赖名拼错不报错、一直等 ⇒ 用「终态必须 ACTIVE」硬断言；
* **FAILED 不重试且被 Loader 吞异常** ⇒ 装配层已先手工 import，这里再断言无 FAILED。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine.assembly import boot, config_path, fiber_report  # noqa: E402
from superengine.contracts import CONTRACT_VERSIONS  # noqa: E402
from superengine.contracts._version import (version_in_interval,  # noqa: E402
                                            ContractVersionError, parse_interval)

WANT = ('worldbuilder', 'tdworld', 'anengine')


def test_config_tree_exists():
    assert os.path.isfile(config_path()), f'缺少配置树 {config_path()}'
    print('  ok: 配置树存在')


def test_boot_all_fibers_active():
    """门禁：装配后**所有** fiber 必须是 ACTIVE（治 PENDING 静默）。"""
    ctx, diag = boot()
    states = {f['name']: f['state'] for f in diag['fibers']}
    not_active = {k: v for k, v in states.items() if v != 'ACTIVE'}
    assert not not_active, f'存在非 ACTIVE 的 fiber：{not_active}'
    print(f'  ok: 装配后 {len(states)} 个 fiber 全部 ACTIVE')


def test_services_reachable():
    ctx, _ = boot()
    for name in WANT:
        svc = getattr(ctx, name, None)
        assert svc is not None, f'服务 {name} 不可达'
    print(f'  ok: {len(WANT)} 个服务全部可达（worldbuilder/tdworld/anengine）')


def test_contract_versions_within_declared_intervals():
    """契约版本必须落在各仓声明的兼容区间内（**契约独立版本化**的装配期校验）。"""
    ctx, _ = boot()
    checked = 0
    for name in WANT:
        svc = getattr(ctx, name)
        for contract, spec in svc.supported.items():
            ver = CONTRACT_VERSIONS[contract]
            assert version_in_interval(ver, spec), \
                f'{name}: 契约 {contract} 版本 {ver} 不在区间 {spec}'
            checked += 1
    print(f'  ok: {checked} 项契约版本均在声明区间内')


def test_inject_graph_orders_dependencies():
    """依赖决定顺序：tdworld / anengine 都 inject worldbuilder。"""
    ctx, _ = boot()
    rep = {f['name']: f['inject'] for f in fiber_report(ctx)}
    assert 'worldbuilder' in rep.get('TdworldBridge', []), rep
    assert 'worldbuilder' in rep.get('AnengineBridge', []), rep
    print('  ok: 依赖图正确（两个消费方都 inject worldbuilder）')


def test_bad_interval_is_rejected():
    """兼容区间机制本身要有效：越界必须被拒（否则版本化形同虚设）。"""
    assert version_in_interval('1.5.0', '>=1.0,<2.0')
    assert not version_in_interval('2.0.0', '>=1.0,<2.0')
    assert not version_in_interval('0.9.0', '>=1.0,<2.0')
    assert version_in_interval('1.2.3', '==1.2.3')
    try:
        parse_interval('not-a-range')
    except ContractVersionError:
        pass
    else:
        raise AssertionError('非法区间串应被拒绝')
    print('  ok: 兼容区间判定与非法串拒绝均正确')


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
    print(f'[test_assembly] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_ASSEMBLY_TESTS_FAILED')
        return 1
    print('ALL_ASSEMBLY_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
