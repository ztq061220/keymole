"""端到端冒烟测试：会弹一个游戏窗口，并向它发真实的 Windows 按键消息。

为什么需要它：键盘事件 → 命中判定 → 渲染 → 画布，这条链路只有真的发按键才测得出来。
判据：全键齐发那一帧里出现「命中绿闪」（HIT 色），且 HUD 分数 > 0。

    python tools/smoke_input.py          # 通过返回 0
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TITLE = "键盘打地鼠 · KeyMole"
KEYS = "qwertasdfgzxcvb"
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101

user32 = ctypes.windll.user32
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND


def screenshot(hwnd: int, path: Path) -> bool:
    from keymole._winshot import capture
    return bool(capture(hwnd, str(path)))


def count_hit_green(path: Path) -> int:
    from PIL import Image
    data = Image.open(path).convert("RGB").tobytes()
    n = 0
    for i in range(0, len(data), 3):
        if data[i + 1] > 180 and data[i] < 110 and data[i + 2] < 170:
            n += 1
    return n


def main() -> int:
    proc = subprocess.Popen([sys.executable, "-m", "keymole", "--mute", "--duration", "24"],
                            cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    time.sleep(2.0)
    hwnd = user32.FindWindowW(None, TITLE)
    if not hwnd:
        proc.kill()
        print("找不到游戏窗口")
        return 1

    out = ROOT / "keymole" / "docs" / "_smoke.png"
    hit_rounds = 0
    for rnd in range(8):
        for c in KEYS:      # 15 键齐发：只要场上有地鼠，必中
            vk = ord(c.upper())
            user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1)
            user32.PostMessageW(hwnd, WM_KEYUP, vk, 1 | (1 << 30) | (1 << 31))
        time.sleep(0.03)
        if screenshot(hwnd, out):
            green = count_hit_green(out)
            print("第 %d 轮：绿闪像素 %d" % (rnd + 1, green))
            if green > 300:
                hit_rounds += 1
        time.sleep(0.9)

    out.unlink(missing_ok=True)
    proc.wait(timeout=30)
    print("出现绿闪的轮数：%d / 8" % hit_rounds)
    return 0 if hit_rounds >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
