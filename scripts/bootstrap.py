#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""superengine 一键引导：把「干净机」变成「能跑本仓」的状态。

为什么需要这个脚本
------------------
本仓是**组合仓**：它自己只做契约 / 桥接 / 装配 / 门禁，但要跑起来必须同时满足
四件事——① Python 依赖齐全 ② 三个兄弟仓源码就位 ③ cordis 可定位 ④ 契约层自检通过。
缺任何一件，症状都长得不一样，而且**报错信息会误导**：

* 缺 `pyglet` ⇒ `RepoNotFound: 仓 '3dworld' 缺少 bridge 接口模块`
  （真实原因是 3dworld 侧 pyglet 的**两个并列顶层入口**之一在 import 期失败：
  `world3d/engine/mathkit.py:19` 的 `from pyglet.math import Mat4, Vec3`（首个失败点），
  以及 `world3d/engine/timeline.py:21` 的 `from pyglet.math import Quaternion, Vec3`；
  两者都挂在 `world3d/engine/__init__.py` 的无条件导入下 —— 只改一处摘不掉 pyglet。
  详见 `docs/architecture/ADR-004-依赖声明单一事实来源与锁版.md`
  与 `docs/architecture/已知风险与缓解.md §1`。
  这个真实原因被 `_locate.py` 的 `ImportError` 兜底包成了「找不到仓」）。
* 缺 `numpy` ⇒ 同样被报成「仓 'worldbuilder' 缺少 bridge 接口模块」。
* 少了某个兄弟仓 ⇒ fiber 停在 PENDING，cordis 不报错、只一直等，进程可能静默退出。

这正是 3dworld `_cordis_locate.py` 已经踩过的「把依赖缺失误报成没找到包」的坑。
本脚本把**四类前置条件逐个显式探测并给出可执行的修复指令**，不把诊断权交给
运行期那条会吞异常的路径。

用法（从任意目录执行，路径一律相对本文件解析，不依赖当前工作目录）
-------------------------------------------------------------------
    python scripts/bootstrap.py               # 建 .venv + 装依赖 + 校验四仓 + 自检
    python scripts/bootstrap.py --check-only  # 只体检，不装东西（CI / 排障用）
    python scripts/bootstrap.py --test        # 自检之外再跑 `tests.run_tests` 全量回归
    python scripts/bootstrap.py --python PY   # 指定建 venv 用的解释器

设计约束
--------
* **铁律 5**：路径不写死盘符。仓内一律相对 `REPO_ROOT`，跨仓用环境变量或
  「与本仓并排」的约定父目录；文档里的绝对路径用去符盘形式。
* 文本 I/O 显式 `encoding="utf-8"`；路径字面量用 `Path` 而非字符串拼接，
  避免 Windows 下 `\\a` `\\t` 被解释成控制字符。
* 退出码：0 = 全部通过；1 = 有阻断项；2 = 参数 / 环境错误。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"

#: 仓名 → (内部包名, 环境变量, 自动定位时的并排目录名)
REPOS = {
    "worldbuilder": ("worldbuilder", "WORLDBUILDER_SRC", "worldbuilder"),
    "an-engine": ("allin_engine", "ANENGINE_SRC", "an-engine"),
    "3dworld": ("world3d", "TDWORLD_SRC", "3dworld"),
}

#: 装完后必须能 import 的模块（对应 pyproject.toml 的 dependencies）
REQUIRED_MODULES = (
    ("PyYAML", "yaml"),
    ("watchdog", "watchdog"),
    ("numpy", "numpy"),
    ("pyglet", "pyglet.math"),
)

OK = "[ ok ]"
BAD = "[BAD ]"
WARN = "[warn]"


def _say(tag: str, msg: str) -> None:
    print(f"{tag} {msg}", flush=True)


def venv_python(venv_dir: Path) -> Path:
    """跨平台定位 venv 里的解释器。"""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(cmd: list[str]) -> int:
    """跑子进程并透传输出；cwd 固定为仓根，保证包与 configs/ 可定位。"""
    _say("    $", " ".join(str(c) for c in cmd))
    return subprocess.run(
        [str(c) for c in cmd], cwd=str(REPO_ROOT), check=False
    ).returncode


# ------------------------------------------------------------- 前置探测 ----
def check_repos() -> bool:
    """三仓是否就位。返回是否有阻断项。"""
    _say(OK, "检查三个兄弟仓源码（组合仓跑起来的前提）")
    blocked = False
    for name, (pkg, env, sibling) in REPOS.items():
        env_root = os.environ.get(env)
        candidates = []
        if env_root:
            candidates.append((f"${env}", Path(env_root)))
        candidates.append(("并排目录", REPO_ROOT.parent / sibling))
        found = None
        for source, root in candidates:
            if (root / pkg).is_dir():
                found = (source, root)
                break
        if found:
            source, root = found
            _say(OK, f"  {name:<13} 就位（{source}: {root.name}/，内部包 {pkg}）")
        else:
            blocked = True
            _say(BAD, f"  {name:<13} 未找到")
            _say("     ", f"设 {env}=<该仓根目录>，或把仓库目录 `{sibling}/` "
                         f"放在与本仓同一父目录下。")
            _say("     ", f"注意目录名 ≠ 包名：目录叫 `{sibling}`，内部包叫 `{pkg}`。")
    return not blocked


def check_cordis() -> bool:
    """cordis 是否能定位（无 pip 发行，必须靠 vendored 源码或环境变量）。"""
    _say(OK, "检查 cordis（无 pip 发行，随 3dworld vendored）")
    if importlib.util.find_spec("cordis") is not None:
        _say(OK, "  cordis 已可直接 import")
        return True
    env_src = os.environ.get("CORDIS_SRC")
    sibling = REPO_ROOT.parent / "3dworld" / "vendor" / "cordis" / "src"
    for source, path in (("$CORDIS_SRC", Path(env_src) if env_src else None),
                         ("并排 3dworld/vendor", sibling)):
        if path and (path / "cordis").is_dir():
            _say(OK, f"  已定位（{source}）")
            return True
    _say(BAD, "  未找到 cordis 源码")
    _say("     ", "设 CORDIS_SRC=<3dworld>/vendor/cordis/src，或让 3dworld 与本仓并排放置。")
    _say("     ", "别用 pip install cordis —— 上游无官方发行，装到的会是同名无关包。")
    return False


def check_deps(python: Path) -> bool:
    """依赖是否真的可 import（不重复安装，只断言 `-r requirements.txt` 的成果）。"""
    _say(OK, "断言运行时依赖可导入（对照 pyproject.toml 的 dependencies）")
    code = (
        "import importlib, sys\n"
        "mods = " + repr([m for _, m in REQUIRED_MODULES]) + "\n"
        "bad = []\n"
        "for m in mods:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "    except Exception as e:\n"
        "        bad.append(f'{m}: {type(e).__name__}: {e}')\n"
        "print('\\n'.join(bad) if bad else 'ALL_DEPS_IMPORTABLE')\n"
        "sys.exit(1 if bad else 0)\n"
    )
    result = subprocess.run(
        [str(python), "-c", code], cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode == 0:
        for label, _mod in REQUIRED_MODULES:
            _say(OK, f"  {label}")
        return True
    _say(BAD, "  依赖缺失：")
    for line in (result.stdout or "").strip().splitlines():
        _say("     ", line)
    for line in (result.stderr or "").strip().splitlines()[-5:]:
        _say("     ", line)
    _say("     ", "先跑 `python scripts/bootstrap.py` 装依赖；若已装过，"
                  "检查是不是用错了解释器（系统 python vs .venv）。")
    return False


# ----------------------------------------------------------------- 动作 ----
def ensure_venv(base_python: str) -> Path:
    venv_dir = VENV_DIR
    py = venv_python(venv_dir)
    if not py.is_file():
        _say(OK, f"创建虚拟环境：{venv_dir.name}/")
        if run([base_python, "-m", "venv", str(venv_dir)]) != 0:
            raise RuntimeError("创建 venv 失败")
    else:
        _say(OK, f"复用已有虚拟环境：{venv_dir.name}/")
    return py


def install_deps(py: Path) -> bool:
    _say(OK, "安装依赖（requirements.txt → -e . → pyproject.toml 单一事实来源）")
    if run([py, "-m", "pip", "install", "--upgrade", "pip", "-q"]) != 0:
        _say(WARN, "  pip 自升级失败，继续尝试安装（通常不影响）")
    if run([py, "-m", "pip", "install", "-r", "requirements.txt"]) != 0:
        _say(BAD, "  依赖安装失败")
        return False
    return True


def selfcheck(py: Path) -> bool:
    """契约层无头自检：不依赖 cordis / 三仓，是最便宜的前置闸门。"""
    _say(OK, "契约层无头自检（selfcheck.py）")
    rc = run([py, "selfcheck.py"])
    if rc != 0:
        _say(BAD, "  selfcheck 失败 —— 契约层自身有问题，先别往上查三仓")
        return False
    return True


def full_tests(py: Path) -> bool:
    _say(OK, "全量回归（tests.run_tests）")
    rc = run([py, "-m", "tests.run_tests"])
    if rc != 0:
        _say(BAD, "  回归失败")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="superengine 一键引导与体检")
    parser.add_argument("--check-only", action="store_true",
                        help="只体检，不创建 venv / 不装依赖")
    parser.add_argument("--test", action="store_true",
                        help="自检之外再跑全量测试")
    parser.add_argument("--python", default=sys.executable,
                        help="建 venv 用的解释器（默认当前 python）")
    args = parser.parse_args()

    print("=" * 68)
    print("superengine bootstrap — 四仓组合流水线环境引导")
    print(f"仓根：{REPO_ROOT}")
    print("=" * 68)

    repos_ok = check_repos()
    cordis_ok = check_cordis()

    py = venv_python(VENV_DIR) if VENV_DIR.is_dir() else Path(args.python)
    if args.check_only:
        deps_ok = check_deps(py) if py.is_file() else False
        if not py.is_file():
            _say(BAD, "  虚拟环境不存在（体检模式下不自动创建）")
        print("-" * 68)
        if repos_ok and cordis_ok and deps_ok:
            _say(OK, "体检通过：四仓 / cordis / 依赖 全部就位")
            return 0
        _say(BAD, "体检有阻断项，按上面的提示逐条修复")
        return 1

    if not py.is_file():
        try:
            py = ensure_venv(args.python)
        except RuntimeError as exc:
            _say(BAD, str(exc))
            return 2

    if not install_deps(py):
        return 1
    if not check_deps(py):
        return 1
    if not selfcheck(py):
        return 1
    if args.test and not full_tests(py):
        return 1

    print("-" * 68)
    if not repos_ok or not cordis_ok:
        _say(WARN, "Python 侧已就绪，但四仓 / cordis 仍有阻断项 —— 装配跑不起来。")
        _say("     ", "按上面的提示补齐后再跑 `python -m superengine.cli.boot --report`。")
        return 1
    _say(OK, "引导完成。下一步：")
    print("       python -m superengine.cli.boot --report   # 装配 + 门禁 + 契约版本报告")
    print("       python -m tests.run_tests                 # 全量回归")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n中断。", file=sys.stderr)
        sys.exit(130)
