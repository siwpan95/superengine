# -*- coding: utf-8 -*-
"""外部依赖定位：cordis 与三仓源码（**唯一处理路径的地方**）。

为什么集中在这里
----------------
组合仓要明确区分两件事：
* **cordis**：框架本身。3dworld 已 vendor 了一份纯 Python 移植（MIT，commit `a3d0c17`）；
* **三仓源码**：被整合的能力源，各自独立发版。

把路径解析收在一个文件里，好处是：桥接插件只写业务，不复制 try/except 兜底；
换部署形态（pip 安装 / 目录并排 / CI）只改本文件。

解析优先级（cordis）：``import cordis`` → 环境变量 ``CORDIS_SRC`` → 并排的
``3dworld/vendor/cordis/src``。
解析优先级（三仓）：环境变量 ``<REPO>_SRC`` → 并排目录。
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Optional

__all__ = ["ensure_cordis", "repo_root", "import_bridge", "REPO_PACKAGES", "RepoNotFound"]

#: 仓名 → (包名, 环境变量)
REPO_PACKAGES = {
    "worldbuilder": ("worldbuilder", "WORLDBUILDER_SRC"),
    "3dworld": ("world3d", "TDWORLD_SRC"),
    "an-engine": ("allin_engine", "ANENGINE_SRC"),
}


class RepoNotFound(ImportError):
    """找不到某个仓的源码（未装、也未用环境变量/并排目录指到）。"""


def _sibling(name: str) -> Optional[str]:
    """并排目录约定：``<superengine>/../<name>``。"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cand = os.path.join(os.path.dirname(here), name)
    return cand if os.path.isdir(os.path.join(cand, REPO_PACKAGES[name][0])) else None


def ensure_cordis():
    """确保 ``import cordis`` 可用，返回 cordis 模块。

    失败时给出**可执行的**修复指令（不要吞掉真实根因 —— 这是 3dworld
    `_cordis_locate.py` 已经踩过的坑：把「依赖缺失」误报成「没找到包」）。
    """
    try:
        import cordis  # noqa: F401
        return cordis
    except ImportError:
        pass
    for cand in (os.environ.get("CORDIS_SRC"),
                 os.path.join(_sibling("3dworld") or "", "vendor", "cordis", "src")):
        if cand and os.path.isdir(cand):
            sys.path.insert(0, cand)
            try:
                import cordis  # noqa: F401
                return cordis
            except ImportError as exc:
                raise ImportError(
                    f"cordis 源码已定位到 {cand}，但导入失败 —— 几乎总是它自身的依赖缺失"
                    f"（PyYAML / watchdog）。请 pip install -r requirements.txt。原始错误：{exc}"
                ) from exc
    raise ImportError(
        "未找到 cordis：pip 安装它，或设 CORDIS_SRC 指向源码目录"
        "（本机可指向 3dworld/vendor/cordis/src）。"
    )


def repo_root(name: str) -> str:
    """返回某个仓的根目录；找不到就抛 `RepoNotFound`（带可执行修复指令）。"""
    if name not in REPO_PACKAGES:
        raise RepoNotFound(f"未知仓名 {name!r}，已知：{sorted(REPO_PACKAGES)}")
    _pkg, env = REPO_PACKAGES[name]
    for cand in (os.environ.get(env), _sibling(name)):
        if cand and os.path.isdir(os.path.join(cand, _pkg)):
            return os.path.abspath(cand)
    raise RepoNotFound(
        f"找不到仓 {name!r}：设环境变量 {env} 指向该仓根目录，"
        f"或把它与本仓并排放置（<superengine>/../{name}）。"
    )


def import_bridge(name: str):
    """导入某个仓的 bridge 接口模块（``<pkg>.bridge``）。"""
    _pkg, _env = REPO_PACKAGES[name]
    root = repo_root(name)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(f"{_pkg}.bridge")
    except ImportError as exc:
        raise RepoNotFound(
            f"仓 {name!r} 缺少 bridge 接口模块（{_pkg}.bridge）—— "
            f"整合要求三仓各提供一个 bridge 友好接口。原始错误：{exc}"
        ) from exc
