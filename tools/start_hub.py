"""用「可被外部读取」的方式启动 MCHOSE HUB（带 CDP 调试端口）。

KeyMole 退出时靠这个端口把键盘灯效交还给 HUB；不这样启动 HUB，
游戏照样能玩，只是退出后灯会停在最后一帧。

用法：python -m tools.start_hub
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
import time

EXE = r"D:\下载\MCHOSE HUB\MCHOSE HUB.exe"
PROFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_hubprofile")
PORT = 9222


def alive() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=1.0):
            return True
    except Exception:
        return False


def main() -> int:
    if alive():
        print("调试端口已经在监听：%d" % PORT)
        return 0
    if not os.path.exists(EXE):
        print("找不到 HUB：%s" % EXE)
        return 1
    os.makedirs(PROFILE, exist_ok=True)
    subprocess.Popen([EXE, "--remote-debugging-port=%d" % PORT,
                      "--user-data-dir=%s" % PROFILE])
    for _ in range(40):
        time.sleep(0.5)
        if alive():
            print("HUB 已启动，调试端口 %d 就绪（profile: %s）" % (PORT, PROFILE))
            return 0
    print("HUB 起来了，但调试端口没开；灯效交还可能不可用")
    return 1


if __name__ == "__main__":
    sys.exit(main())
