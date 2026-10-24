# -*- coding: utf-8 -*-
"""superengine 全量测试聚合 runner。

    python -m tests.run_tests

按各模块的 ``ALL_*_TESTS_PASSED`` 尾标记判定，打印每模块通过/失败。
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODULES = [
    ('tests.test_assembly', 'ALL_ASSEMBLY_TESTS_PASSED', '装配门禁（契约版本 / fiber 终态 / 依赖图）'),
    ('tests.test_no_cross_import', 'ALL_NO_CROSS_IMPORT_TESTS_PASSED', '三仓互不引用门禁'),
    ('tests.test_pipeline', 'ALL_PIPELINE_TESTS_PASSED', '三仓流水线（M1 表现腿 / M2 玩法托管）'),
    ('tests.test_live', 'ALL_LIVE_TESTS_PASSED', 'M3 cordis Hmr 热重载'),
    ('tests.test_backends', 'ALL_BACKENDS_TESTS_PASSED', 'M4 reflect.Impl 多实现可替换'),
]


def main() -> int:
    env = dict(os.environ)
    env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
    failed = []
    for mod, marker, desc in MODULES:
        proc = subprocess.run(
            [sys.executable, '-m', mod], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace')
        out = proc.stdout or ''
        cases = sum(1 for line in out.splitlines() if line.strip().startswith('ok:'))
        if proc.returncode == 0 and marker in out:
            print(f'  [PASS] {mod}  {cases} 项  ({desc})')
        else:
            failed.append(mod)
            print(f'  [FAIL] {mod}  ({desc})')
            print('\n'.join('        ' + ln for ln in out.splitlines()[-12:]))
    print('=' * 70)
    print(f'[run_tests] 模块 {len(MODULES) - len(failed)}/{len(MODULES)} 通过')
    if failed:
        print('ALL_TESTS_FAILED')
        return 1
    print('ALL_TESTS_PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
