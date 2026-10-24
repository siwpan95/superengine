# -*- coding: utf-8 -*-
"""headless 装配验证入口。

延续 3dworld 既有纪律：**「demo 怎么挂的 = headless 验证怎么挂的」，接线只有这一份**
（同一个 `configs/cordis.super.yml` 既给运行时也给验证用）。

    python -m superengine.cli.boot            # 装配三仓 + 门禁
    python -m superengine.cli.boot --report   # 额外打印契约版本与兼容区间
"""

from __future__ import annotations

import argparse
import sys

from ..assembly import boot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="超级引擎 cordis 装配验证（headless）")
    ap.add_argument("--config", default=None, help="配置树路径（默认 configs/cordis.super.yml）")
    ap.add_argument("--report", action="store_true", help="打印契约版本与兼容区间")
    args = ap.parse_args(argv)

    try:
        ctx, diag = boot(args.config)
    except Exception as exc:                                    # noqa: BLE001
        print(f"[boot] 装配失败: {type(exc).__name__}: {exc}")
        print("SUPERENGINE_BOOT_FAILED")
        return 1

    print("[boot] 装配完成，fiber 状态：")
    for f in diag["fibers"]:
        print(f"  ok: {f['name']} {f['state']} inject={f['inject']}")
    if args.report:
        print("[boot] 契约版本 → 兼容区间：")
        for svc, rep in diag["contracts"].items():
            for k, v in rep.items():
                print(f"  {svc}: {k} {v}")
    print("SUPERENGINE_BOOT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
