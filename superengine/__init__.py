# -*- coding: utf-8 -*-
"""superengine —— 基于 cordis 的三仓组合仓（超级引擎骨架）。

三仓（worldbuilder 生成 / an-engine 玩法 / 3dworld 表现）**互不引用**；
本仓只做四件事：**契约**、**桥接**、**装配**、**门禁** —— 不含任何算法。

    from superengine import boot
    result = boot('configs/cordis.super.yml')

四条核心纪律
------------
1. **独立仓**：三仓平等，天然阻断「某一仓吞并另两仓」的耦合倾向；
2. **契约独立版本化**：`contracts.CONTRACT_VERSIONS` 不跟随任何一仓发版，
   各仓用 `SUPPORTED_CONTRACTS` 声明**兼容区间**，装配期校验；
3. **文件契约与服务契约并存**：worldspec v1 管离线/跨进程/独立发布，
   cordis 服务契约管同进程在线装配 —— 两者不互相替代；
4. **唯一 import 三仓的地方是 `bridges/`**，且只经各仓的 ``bridge`` 友好接口。
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__", "boot"]
