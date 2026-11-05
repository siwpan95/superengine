# -*- coding: utf-8 -*-
"""回归基线：把「不该悄悄变掉的东西」固化成断言。

为什么单独一个模块
------------------
6 个既有测试模块测的是**运行期行为**（装配 / 流水线 / 热重载 / 换实现 / 开发循环）。
本模块测的是**声明面与契约面的基线**，而且刻意做成**不依赖 cordis、不依赖三仓**
—— 与 `selfcheck.py` 同一定位，可以在干净机上只装完依赖就跑。

这批断言的由来（2026-11-04 事故驱动）：
`requirements.txt` 与 `pyproject.toml` 两份清单**都漏了 pyglet**，而装配路径
  tdworld_bridge → world3d.bridge → world3d/engine/{mathkit,timeline}.py → pyglet.math
是硬依赖。pyglet 在 3dworld 侧有**两个并列的顶层入口**：
`mathkit.py:19` 的 `from pyglet.math import Mat4, Vec3`（首个失败点）与
`timeline.py:21` 的 `from pyglet.math import Quaternion, Vec3`，两者都挂在
`world3d/engine/__init__.py` 的无条件导入下 —— 只改一处摘不掉 pyglet。
详见 `docs/architecture/ADR-004-依赖声明单一事实来源与锁版.md`
与 `docs/architecture/已知风险与缓解.md §1`。
干净机按 README 装完依赖后 `boot` 直接
`ModuleNotFoundError: No module named 'pyglet'`，6 个测试模块只有 1 个能过。
本机 venv 里装着 pyglet 时全绿 —— **本机跑绿发现不了这类缺陷**。

所以这里把「依赖声明是否完整」变成机械断言：
清单里写的每个包必须真的能 import，且 pyglet 必须在清单里。
"""

from __future__ import annotations

import importlib
import inspect
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from superengine.contracts import CONTRACT_VERSIONS, CONTRACTS  # noqa: E402

#: 契约注册表基线。加新契约 / 升版本时**必须同步改这里** —— 这正是本模块的意义：
#: 让「悄悄改了契约面」变成一个需要显式确认的动作，而不是无声漂移。
EXPECTED_CONTRACTS = {
    "worldspec_source": "1.0.0",
    "terrain_source": "1.0.0",
    "mapgraph_source": "1.0.0",
    "gameplay_world": "1.0.0",
    "terrain_sink": "1.0.0",
    "render_sink": "1.0.0",
    "dungeon_source": "1.0.0",
    "rules_kernel": "1.0.0",
}

#: 每个契约 Protocol 的**方法名集合快照**。
#: 加方法 / 改方法名 / 删方法都必须同步改这里 —— 让「悄悄改了契约形状」变成一个
#: 需要显式确认的动作（详见 测试覆盖审计.md G6 / 已知风险与缓解.md §3）。
#: 第一道机械闸门：单边给 Protocol 加 / 删 / 改名方法（却不改快照、不升 CONTRACT_VERSIONS）
#: 会立刻红。协同加方法（Protocol + 提供方同步加、但忘升版本）由装配期 `check_all`
#: 的「版本不在区间」拦截，不归本快照管。
EXPECTED_METHODS = {
    "worldspec_source": {"generate", "save", "load", "validate_spec", "meta"},
    "terrain_source": {"heightfield", "make_height_sampler"},
    "mapgraph_source": {"mapgraph_from_worldspec", "route", "nearest"},
    "gameplay_world": {"new_context", "provide_mapgraph"},
    "terrain_sink": {"clipmap_config", "terrain_mesh"},
    "render_sink": {"terrain_from_heightfield"},
    "dungeon_source": {"generate_dungeon", "dungeon_graph", "grammar_names"},
    "rules_kernel": {"roll_dice", "roll_d20", "roll_3d6", "success_chance"},
}

#: 发行名 → 实际 import 名（PyYAML 是唯一的例外）
MODULE_OF = {
    "PyYAML": "yaml",
    "watchdog": "watchdog",
    "numpy": "numpy",
    "pyglet": "pyglet",
}

#: contracts/ 层允许的标准库根模块（零依赖边界，见 docs/architecture/ADR-001）
ALLOWED_STDLIB = {
    "__future__", "typing", "re", "abc", "collections", "dataclasses",
    "math", "warnings", "sys", "os", "enum", "itertools", "functools",
}


def _dep_names(spec: str) -> str:
    """`PyYAML>=6.0,<7` → `PyYAML`；`numpy[extra]>=2` → `numpy`。"""
    return re.split(r"[<>=!~\[ ;]", spec, maxsplit=1)[0].strip()


# --------------------------------------------------------------- 契约基线 ----
def test_contract_registry_snapshot():
    """8 个契约名 + 版本号不得悄悄变化。"""
    assert dict(CONTRACT_VERSIONS) == EXPECTED_CONTRACTS, (
        f"契约注册表漂移：\n  实际 {dict(CONTRACT_VERSIONS)}\n"
        f"  基线 {EXPECTED_CONTRACTS}\n"
        "若是有意加契约 / 升版本，同步更新 tests/test_baseline.py 的 EXPECTED_CONTRACTS，"
        "并按 docs/design/新增契约流程.md 走完整流程。")
    print(f"  ok: 契约注册表基线一致（{len(EXPECTED_CONTRACTS)} 个契约，全 1.0.0）")


def test_contract_protocol_registry_aligned():
    """CONTRACTS（结构校验用）与 CONTRACT_VERSIONS（版本校验用）必须同键。"""
    assert set(CONTRACTS) == set(CONTRACT_VERSIONS), (
        f"两个注册表键不一致：CONTRACTS={sorted(CONTRACTS)}, "
        f"CONTRACT_VERSIONS={sorted(CONTRACT_VERSIONS)}")
    print(f"  ok: CONTRACTS / CONTRACT_VERSIONS 同键（{len(CONTRACTS)} 项）")


def test_protocols_are_runtime_checkable_and_methods_only():
    """@runtime_checkable 的 Protocol 若带非方法成员，issubclass() 会直接抛错。"""
    for name, proto in CONTRACTS.items():
        assert getattr(proto, "_is_runtime_protocol", False), \
            f"契约 {name} 未标 @runtime_checkable"
        non_methods = [
            k for k, v in vars(proto).items()
            if not k.startswith("_") and not callable(v)
        ]
        assert not non_methods, \
            f"契约 {name} 含非方法成员 {non_methods}（会让 issubclass() 抛错）"
    print(f"  ok: {len(CONTRACTS)} 个 Protocol 均可运行时检查且只含方法")


def test_protocol_methods_are_declared():
    """每个契约的方法名集合必须与 EXPECTED_METHODS 快照**逐字节一致**。

    这是「形状真空」的第一道机械闸门：单边给 Protocol 加 / 删 / 改名方法
    （却不改快照、不升 CONTRACT_VERSIONS）会立刻红。协同加方法
    （Protocol + 提供方同步加、但忘升版本）仍由装配期 check_all 的
    「版本不在区间」拦截，不归本断言管 —— 见 测试覆盖审计.md G6。
    """
    for name, proto in CONTRACTS.items():
        methods = {
            k for k, v in vars(proto).items()
            if not k.startswith("_") and callable(v)
        }
        assert name in EXPECTED_METHODS, (
            f"契约 {name} 未在 EXPECTED_METHODS 登记；"
            "新增契约时同步在 tests/test_baseline.py 登记方法名集合。")
        assert methods == EXPECTED_METHODS[name], (
            f"契约 {name} 方法名集合与快照不一致：\n"
            f"  实际 {sorted(methods)}\n"
            f"  快照 {sorted(EXPECTED_METHODS[name])}\n"
            "若是有意改形状，同步更新 EXPECTED_METHODS 并按新增契约流程升版本。")
    print(f"  ok: {len(EXPECTED_METHODS)} 个契约方法名集合与快照一致（形状真空已锁）")


# --------------------------------------------------------------- 依赖基线 ----
def test_pyproject_is_single_source_of_dependencies():
    """requirements.txt 必须是 `-e .` 转发，不许维护第二份清单。"""
    req = ROOT / "requirements.txt"
    text = req.read_text(encoding="utf-8")
    forwards = [ln.strip() for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    assert forwards == ["-e ."], (
        f"requirements.txt 不是单一事实来源转发：{forwards}\n"
        "它应该只有 `-e .` 一行（其余是注释），依赖统一写在 pyproject.toml。")
    print("  ok: requirements.txt → pyproject.toml 单一事实来源")


def test_declared_dependencies_are_importable():
    """清单里声明的每个包必须真的能 import —— 防「装完依赖还是跑不起来」。"""
    with (ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    specs = data["project"]["dependencies"]
    names = {_dep_names(s) for s in specs}
    unknown = names - set(MODULE_OF)
    assert not unknown, (
        f"pyproject.toml 里出现了未在 MODULE_OF 登记的依赖 {sorted(unknown)}；"
        "新增依赖时同步在 tests/test_baseline.py 的 MODULE_OF 里补 import 名。")
    failed = []
    for dist, module in MODULE_OF.items():
        if dist not in names:
            continue
        try:
            importlib.import_module(module)
        except Exception as exc:                              # noqa: BLE001
            failed.append(f"{dist}({module}): {type(exc).__name__}: {exc}")
    assert not failed, "声明了但 import 失败：\n    " + "\n    ".join(failed)
    print(f"  ok: 声明的 {len(names)} 个依赖全部可 import")


def test_pyglet_is_declared():
    """专项回归：pyglet 漏声明曾让 6 个测试模块只有 1 个能过。"""
    with (ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    names = {_dep_names(s) for s in data["project"]["dependencies"]}
    assert "pyglet" in names, (
        "pyglet 未声明 —— 装配路径 "
        "tdworld_bridge → world3d.bridge → "
        "world3d/engine/mathkit.py:19 + world3d/engine/timeline.py:21 → pyglet.math "
        "是硬依赖（两个并列的顶层入口，都挂在 engine/__init__.py 无条件导入下，"
        "只改一处摘不掉）。漏了它，干净机 boot 直接 ModuleNotFoundError。\n"
        "详见 docs/architecture/已知风险与缓解.md §1 与 ADR-004。")
    print("  ok: pyglet 已在依赖清单中（专项回归）")


# ----------------------------------------------------------- 零依赖边界 ----
def test_contracts_layer_is_dependency_free():
    """contracts/ 只 import 标准库；零依赖边界画在这一层，不是整仓。

    整仓并非零依赖（bridges/ 会穿透到 pyglet），所以只断言 contracts/。
    见 docs/architecture/ADR-001 与 docs/design/契约体系设计.md §7。
    """
    contracts_dir = ROOT / "superengine" / "contracts"
    bad = []
    for path in sorted(contracts_dir.glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", line)
            if not m:
                continue
            mod = (m.group(1) or m.group(2)).split(".")[0]
            if line.lstrip().startswith("from ."):
                continue                      # 包内相对导入，合法
            if mod not in ALLOWED_STDLIB:
                bad.append(f"{path.name}: {line.strip()}")
    assert not bad, "contracts/ 层混入了非标准库依赖：\n    " + "\n    ".join(bad)
    print("  ok: contracts/ 层零第三方依赖（边界画在契约层）")


# ------------------------------------------------------------------ 入口 ----
def test_key_entrypoints_exist():
    """文档 / CI 里引用的入口必须真实存在，别让命令清单变成悬空引用。"""
    required = [
        "selfcheck.py",
        "scripts/bootstrap.py",
        "superengine/cli/boot.py",
        "superengine/cli/dev.py",
        "configs/cordis.super.yml",
        "configs/dev.json",
        ".github/workflows/ci.yml",
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    assert not missing, f"入口缺失：{missing}"
    print(f"  ok: {len(required)} 个入口文件全部存在")


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f) and inspect.isfunction(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok: {name}")
        except AssertionError as exc:
            failed.append((name, exc))
            print(f"  FAIL: {name}: {exc}")
        except Exception as exc:                              # noqa: BLE001
            failed.append((name, exc))
            print(f"  ERROR: {name}: {type(exc).__name__}: {exc}")
    print("=" * 60)
    print(f"[test_baseline] {len(tests) - len(failed)}/{len(tests)} 通过")
    if failed:
        print("ALL_BASELINE_TESTS_FAILED")
        return 1
    print("ALL_BASELINE_TESTS_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
