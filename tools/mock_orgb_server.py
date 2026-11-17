"""单独跑假 OpenRGB 服务器的入口（真正实现在 keymole/display/mock.py）。

    python -m tools.mock_orgb_server --port 6742
"""
from __future__ import annotations

import argparse

from keymole.display.mock import MockServer


def main() -> None:
    ap = argparse.ArgumentParser(description="假的 OpenRGB SDK Server（开发用）")
    ap.add_argument("--port", type=int, default=6742)
    args = ap.parse_args()
    srv = MockServer(args.port)
    srv.start()
    print("mock OpenRGB server 监听 127.0.0.1:%d，Ctrl+C 结束" % args.port)
    try:
        while True:
            srv.join(1.0)
    except KeyboardInterrupt:
        srv.stop()


if __name__ == "__main__":
    main()
