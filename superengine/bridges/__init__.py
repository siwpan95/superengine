# -*- coding: utf-8 -*-
"""bridges —— **唯一允许 import 三仓**的地方。

纪律：三仓之间互不引用（由 `tests/test_no_cross_import.py` 机器保证）；
组合仓里也只有本包可以 import 它们，且一律通过各仓的 ``bridge`` 友好接口，
不碰任何仓的内部模块 —— 某个仓重构时，只需要改它自己的 bridge 文件。
"""

from __future__ import annotations

__all__ = ["WorldbuilderBridge", "TdworldBridge", "AnengineBridge", "BRIDGES"]
