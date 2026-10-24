# -*- coding: utf-8 -*-
"""门禁一：三仓之间**不得互相 import**（三仓互不引用纪律的机器保证）。

这是整合方案里最容易在无人注意时被破坏的一条：
某天有人图省事在 3dworld 里 `from worldbuilder import ...`，
三仓立刻从「可独立发布」退化成「一损俱损」，而且**编译期不会报错**。

扫描范围排除 `.venv` / `vendor` / `dist` / `release` 等目录（第三方与 vendored 代码不算）。
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from superengine._locate import REPO_PACKAGES, repo_root  # noqa: E402

_SKIP_DIRS = {'.venv', 'vendor', 'dist', 'release', '__pycache__', '.git',
              'build', 'node_modules', 'example', 'examples', 'docs'}

#: 仓名 → 禁止出现在其源码里的顶层包名
_FORBIDDEN = {
    'worldbuilder': {'world3d', 'allin_engine'},
    '3dworld': {'worldbuilder', 'allin_engine'},
    'an-engine': {'worldbuilder', 'world3d'},
}

_IMPORT_RE = re.compile(
    r'^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))',
    re.MULTILINE)


def _iter_py(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


def scan_violations(repo: str):
    """返回该仓违反纪律的 (文件, 行号, 语句, 被禁包名) 列表。"""
    root = repo_root(repo)
    banned = _FORBIDDEN[repo]
    out = []
    for path in _iter_py(root):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        for m in _IMPORT_RE.finditer(text):
            mod = m.group(1) or m.group(2) or ''
            top = mod.split('.')[0]
            if top in banned:
                line = text[:m.start()].count('\n') + 1
                out.append((path, line, m.group(0).strip(), top))
    return out


def test_three_repos_never_import_each_other():
    total = []
    for repo in _FORBIDDEN:
        bad = scan_violations(repo)
        total += [(repo,) + b for b in bad]
    assert not total, '发现跨仓 import（三仓必须互不引用）：\n' + '\n'.join(
        f'  {r}: {p}:{ln}  {stmt}  ← 禁止 {pkg}' for r, p, ln, stmt, pkg in total)
    print(f'  ok: 三仓源码零跨仓 import（扫描 {len(_FORBIDDEN)} 个仓）')


#: 运行时也要防：`import_bridge('3dworld')` 这类调用会绕过静态 import 扫描
_RUNTIME_IMPORT_RE = re.compile(r"""import_bridge\(\s*['"]([\w-]+)['"]""")


def test_bridges_are_the_only_importers():
    """组合仓里只有 `superengine/bridges/` 允许引用三仓（**静态 + 运行时**）。

    只扫 `import` 语句是不够的：`import_bridge('3dworld')` 是函数调用，
    静态扫描看不见，却同样把三仓拉了进来 —— 所以这里**连带扫运行时调用**。
    """
    # 只扫 **包体** superengine/（tests/ 是验证代码，不算生产引用；
    # 且扫自己会因为正则字面量自匹配而误报）
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkg = os.path.join(here, 'superengine')
    banned = {pkg_name for s in _FORBIDDEN.values() for pkg_name in s}
    bad = []
    for dirpath, dirnames, filenames in os.walk(pkg):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if os.path.basename(dirpath) == 'bridges':
            continue
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            for m in _IMPORT_RE.finditer(text):
                mod = m.group(1) or m.group(2) or ''
                if mod.split('.')[0] in banned:
                    bad.append((path, m.group(0).strip()))
            for m in _RUNTIME_IMPORT_RE.finditer(text):
                if m.group(1) in _FORBIDDEN_BY_PKG or m.group(1) in {
                        r for r in _FORBIDDEN}:
                    bad.append((path, m.group(0).strip()))
    assert not bad, 'bridges/ 之外不允许引用三仓（含运行时 import_bridge）：\n' + '\n'.join(
        f'  {p}: {s}' for p, s in bad)
    print('  ok: 组合仓内只有 bridges/ 引用三仓（静态 import + 运行时调用都扫）')


#: 仓名（import_bridge 用的是仓名，不是包名）
_FORBIDDEN_BY_PKG = {pkg: repo for repo, s in _FORBIDDEN.items() for pkg in s}


def test_repo_roots_are_resolvable():
    for repo, (pkg, _env) in REPO_PACKAGES.items():
        root = repo_root(repo)
        assert os.path.isdir(os.path.join(root, pkg)), f'{repo} 根目录里找不到包 {pkg}'
    print(f'  ok: 三仓根目录均可定位（{sorted(REPO_PACKAGES)}）')


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
    print(f'[test_no_cross_import] {len(tests) - len(failed)}/{len(tests)} 通过')
    if failed:
        print('ALL_NO_CROSS_IMPORT_TESTS_FAILED')
        return 1
    print('ALL_NO_CROSS_IMPORT_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
