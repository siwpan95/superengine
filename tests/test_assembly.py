# -*- coding: utf-8 -*-
"""门禁二：装配期门禁 —— 契约版本兼容、fiber 终态 ACTIVE、依赖图顺序。

治的正是 cordis 两个已记录的坑：
* **PENDING 静默**：依赖名拼错不报错、一直等 ⇒ 用「终态必须 ACTIVE」硬断言；
* **FAILED 不重试且被 Loader 吞异常** ⇒ 装配层已先手工 import，这里再断言无 FAILED。

G6（契约形状 ↔ 三仓区间联动）
-----------------------------
`test_contract_versions_within_declared_intervals` 走的是**提供方 → 注册表**方向
（逐个 `svc.supported` 查版本）。反向没有门禁：把 `CONTRACT_VERSIONS` 里某个契约
从 `1.0.0` 升到 `2.0.0`、三仓 `SUPPORTED_CONTRACTS` 仍写 `>=1.0,<2.0` 时，
装配期 `check_provider()` **会**拒，但那要等真装配；而「注册表里有个契约
三仓谁都没声明」这类幽灵契约，装配期压根不会报错（`check_all` 只查提供方声明的键）。

所以这里补**注册表 → 三仓声明**方向的机械联动：复用 `_version.py` 的
`version_in_interval` / `parse_interval`，不另写一套版本算术。

「三仓缺失时 skip」的边界要说清：skip 只在 `repo_root()` 定位不到源码时发生，
且打印具体仓名与修复指引。仓**能定位到**但 bridge 导入失败（依赖缺失 / 接口变动）
一律当**失败**报，绝不 skip —— 这正是 `_locate.py` 注释里记过的坑：
把「依赖缺失」误报成「没找到包」，排障方向会被带偏（2026-11-04 pyglet 事故同款）。
CI 四仓并排布局下三仓必然可定位，因此不得 skip。

**skip 不是通过**：2026-11-05 QA 实测指出，若三条 G6 断言全被跳过而 `main()`
仍打印 `ALL_ASSEMBLY_TESTS_PASSED` 且返回 0，`run_tests.py`（只看退出码 + 尾标记）
会把它判成 `[PASS]` —— 联动断言一条没跑却报绿。所以只要有 skip，模块级判定就
改为 `ALL_ASSEMBLY_TESTS_INCOMPLETE` 并返回 1，**测试函数本身仍然 skip**（不是
FAIL，不伪造断言结果），但模块不宣称通过。CI 布局下不 skip，不受影响。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine._locate import (REPO_PACKAGES, RepoNotFound,  # noqa: E402
                                 import_bridge, repo_root)
from superengine.assembly import boot, config_path, fiber_report  # noqa: E402
from superengine.contracts import CONTRACT_VERSIONS  # noqa: E402
from superengine.contracts._version import (version_in_interval,  # noqa: E402
                                            ContractVersionError, parse_interval)

WANT = ('worldbuilder', 'tdworld', 'anengine')


class _SkipTest(Exception):
    """三仓源码未全部就位，联动断言本轮无法执行（**不是通过**）。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _three_repo_supported():
    """返回 ``{仓名: SUPPORTED_CONTRACTS}``；任一仓定位不到则抛 `_SkipTest`。

    分两步是刻意的：先用 `repo_root()` 只做**路径定位**（不 import），
    全齐了才 `import_bridge()`。这样「仓没找到」与「仓在但依赖缺失」不会混淆 ——
    `import_bridge` 会把 ImportError 统一包成 `RepoNotFound`，若不看定位结果就把
    它当 skip，缺 pyglet 也会被静默跳过，等于把 P0 事故重新埋回去。
    """
    missing = []
    for name in REPO_PACKAGES:
        try:
            repo_root(name)
        except RepoNotFound as exc:
            missing.append(f'{name}: {exc}')
    if missing:
        raise _SkipTest(
            '三仓源码未全部就位，跳过联动断言：' + ' | '.join(missing) +
            '（并排放置或设 *_SRC 环境变量后重跑；CI 四仓并排布局不应出现本行）')
    out = {}
    for name in REPO_PACKAGES:
        try:
            mod = import_bridge(name)
        except RepoNotFound as exc:
            raise AssertionError(
                f'仓 {name!r} 根目录已定位，但 bridge 导入失败 —— 这是依赖缺失或接口变动，'
                f'不是仓没找到。原始错误：{exc}') from exc
        supported = getattr(mod, 'SUPPORTED_CONTRACTS', None)
        assert isinstance(supported, dict) and supported, \
            f'仓 {name!r} 的 SUPPORTED_CONTRACTS 缺失或为空，联动断言会退化成空转'
        out[name] = dict(supported)
    return out


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


# ---------------------------------------------- G6 注册表 → 三仓声明联动 ----
def test_three_repo_declared_contract_names_are_registered():
    """G6(b)：三仓 `SUPPORTED_CONTRACTS` 的每个契约名都必须存在于注册表。

    防的是拼错与「幽灵契约」：某仓声明 `terain_sink`，`check_all()` 在装配期
    会因「该仓声明了未知契约」而拒 —— 但那要等真装配。这里在测试期直接对照，
    报错里直接给出拼错的键与注册表全量键。
    """
    declared = _three_repo_supported()
    seen = 0
    for repo, supported in declared.items():
        unknown = set(supported) - set(CONTRACT_VERSIONS)
        assert not unknown, (
            f'仓 {repo!r} 声明了注册表里没有的契约 {sorted(unknown)}；'
            f'注册表为 {sorted(CONTRACT_VERSIONS)}。'
            '是拼错，还是忘了在 contracts/__init__.py 登记 CONTRACT_VERSIONS？'
            '（加契约是跨仓四步动作，见 docs/design/新增契约流程.md）')
        seen += len(supported)
    print(f'  ok: 三仓声明的 {seen} 项契约名全部已在注册表（无幽灵契约）')


def test_registry_versions_fit_three_repo_intervals():
    """G6(a)：注册表每个契约的当前版本，必须落在**声明它的**三仓区间内。

    与既有的 `test_contract_versions_within_declared_intervals` 方向相反：
    那个从「提供方声明」出发，这个从「权威注册表」出发。后者才能抓住
    「把 terrain_sink 升到 2.0.0 却没让 3dworld 改 SUPPORTED_CONTRACTS」
    —— 装配期会拒，但测试期就红更早、且不必依赖 cordis 装配成功。
    """
    declared = _three_repo_supported()
    checked = 0
    for contract, version in CONTRACT_VERSIONS.items():
        providers = {repo: spec for repo, sup in declared.items()
                     for name, spec in sup.items() if name == contract}
        assert providers, (
            f'契约 {contract!r}（版本 {version}）没有任何兄弟仓声明 —— '
            '这是幽灵契约或漏了跨仓声明步骤。'
            'check_all() 只查「提供方声明了什么」，不会替你发现「谁都没声明」。')
        for repo, spec in providers.items():
            assert version_in_interval(version, spec), (
                f'契约 {contract!r} 版本 {version} 不在 {repo!r} 声明的区间 {spec!r} 内。'
                ' 升契约版本时须同步三仓 SUPPORTED_CONTRACTS（跨仓单独提 PR）。')
            checked += 1
    print(f'  ok: 注册表 {len(CONTRACT_VERSIONS)} 个契约 → {checked} 条区间声明全部命中')


def test_all_registry_contracts_have_a_provider():
    """G6 补强：注册表不得出现「三仓谁都没声明」的契约。

    `check_all(versions, supported)` 的方向是「supported 的键 → versions」，
    天然查不出注册表多出来的键。这条断言把方向补齐，也让「新增契约但三仓
    一个都没接」在测试期立刻可见，而不是等到有人问「这契约谁实现的」。
    """
    declared = _three_repo_supported()
    all_declared = {name for sup in declared.values() for name in sup}
    orphan = set(CONTRACT_VERSIONS) - all_declared
    assert not orphan, (
        f'注册表里有 {sorted(orphan)} 无提供方声明；'
        f'三仓合计声明 {sorted(all_declared)}。'
        ' 按 docs/design/新增契约流程.md 补齐跨仓声明，或从注册表移除。')
    print(f'  ok: 注册表 {len(CONTRACT_VERSIONS)} 个契约均有提供方声明（无孤儿契约）')


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and callable(f)]
    failed = []
    skipped = []
    for name, fn in tests:
        try:
            fn()
            print(f'  ok: {name}')
        except _SkipTest as exc:
            skipped.append(name)
            print(f'  SKIP: {name}: {exc.reason}')
        except AssertionError as exc:
            failed.append((name, exc))
            print(f'  FAIL: {name}: {exc}')
        except Exception as exc:                            # noqa: BLE001
            failed.append((name, exc))
            print(f'  ERROR: {type(exc).__name__}: {exc}')
    print('=' * 60)
    if skipped:
        print(f'[test_assembly] 跳过 {len(skipped)} 项（三仓未就位，非通过）：'
              f'{sorted(skipped)}')
    print(f'[test_assembly] {len(tests) - len(failed) - len(skipped)}/{len(tests)} 通过')
    if failed:
        print('ALL_ASSEMBLY_TESTS_FAILED')
        return 1
    if skipped:
        # 联动断言一条没跑，绝不能让 run_tests.py 的「退出码 0 + 尾标记」判据报绿。
        # 测试函数本身仍 skip（不伪造断言结果），但模块级不宣称通过。
        # 修复：把三仓与本仓并排放置，或设 <REPO>_SRC 环境变量后重跑。
        print('ALL_ASSEMBLY_TESTS_INCOMPLETE')
        return 1
    print('ALL_ASSEMBLY_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
