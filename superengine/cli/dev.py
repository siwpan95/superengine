# -*- coding: utf-8 -*-
"""实际开发循环入口 —— 把 M3（热重载）与 M4（多实现可替换）接到日常开发。

    python -m superengine.cli.dev                # 常驻：监听配置 + 三仓源码，自动重建
    python -m superengine.cli.dev --once         # 只构建一次并打印报告
    python -m superengine.cli.dev --iterations 20 --interval 0.2
    python -m superengine.cli.dev --set backend flat     # 改配置（下一轮生效）
    python -m superengine.cli.dev --status               # 打印当前会话状态

**改配置**里 `backend` 走 M4 的实现热替换（clipmap ⇄ flat，消费方代码不动）；
**改三仓源码**走 M3 的 cordis Hmr（旧 fiber 完整回滚，registry 规模不增长）。
"""

from __future__ import annotations

import argparse
import json
import sys

from ..devloop import DEV_CONFIG, DEFAULT_PARAMS, boot, load_params, save_params


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="superengine 开发循环（M3 热重载 + M4 多实现替换）")
    ap.add_argument("--config", default=None, help=f"开发配置路径（默认 {DEV_CONFIG}）")
    ap.add_argument("--once", action="store_true", help="只构建一次并打印报告后退出")
    ap.add_argument("--iterations", type=int, default=None, help="轮询多少轮（默认一直跑）")
    ap.add_argument("--interval", type=float, default=0.5, help="轮询间隔秒（默认 0.5）")
    ap.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), action="append",
                    default=[], help="写一条配置（如 --set backend flat）")
    ap.add_argument("--status", action="store_true", help="打印当前配置与默认值的差异")
    args = ap.parse_args(argv)

    if args.set:
        params = load_params(args.config)
        for key, value in args.set:
            if key not in DEFAULT_PARAMS:
                print(f"[dev] 未知配置键 {key!r}（可用：{sorted(DEFAULT_PARAMS)}）")
                return 2
            if key == "backend" and value not in ("clipmap", "flat"):
                print(f"[dev] 未知后端 {value!r}（可用：clipmap / flat）")
                return 2
            params[key] = type(DEFAULT_PARAMS[key])(value) if key != "backend" else value
        save_params(params, args.config)
        print(f"[dev] 已写入 {args.config or DEV_CONFIG}: {json.dumps(params, ensure_ascii=False)}")
        if args.once:
            args.once = False

    if args.status:
        params = load_params(args.config)
        print(f"[dev] 配置 {args.config or DEV_CONFIG}:")
        for k in sorted(DEFAULT_PARAMS):
            mark = "" if params.get(k) == DEFAULT_PARAMS[k] else "  (改过)"
            print(f"  {k} = {params.get(k)!r}{mark}")
        return 0

    try:
        loop = boot(config_path=args.config)
    except Exception as exc:                                    # noqa: BLE001
        print(f"[dev] 启动失败: {type(exc).__name__}: {exc}")
        print("SUPERENGINE_DEV_FAILED")
        return 1

    if args.once:
        rep = loop.build()
        print(f"[dev] backend={rep['backend']} seed={rep['seed']} "
              f"verts={rep['vertex_count']} "
              f"h={rep['height_min']:.3f}~{rep['height_max']:.3f} "
              f"registry={rep['registry']}")
        print("SUPERENGINE_DEV_OK")
        return 0

    print(f"[dev] 监听中：配置 {args.config or DEV_CONFIG} + 三仓 bridge 源码"
          f"（interval={args.interval}s，Ctrl-C 退出）")
    loop.run(iterations=args.iterations, interval=args.interval)
    print("SUPERENGINE_DEV_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
