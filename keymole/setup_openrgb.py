"""一键装 OpenRGB —— 这是「适配大多数键盘」真正的那条腿。

为什么不自己写驱动：OpenRGB 已经把上百个品牌、六百多个型号的私有灯效协议
逆向好了（罗技/雷蛇/海盗船/华硕/微星/技嘉/金士顿/雷柏/达尔优/各种白牌…）。
自己逆向永远追不上，正确做法是站在它肩膀上，并且把「装它」这件事做到一条命令。

    python -m keymole.setup_openrgb          # 下载 + 解压到用户目录
    python -m keymole.setup_openrgb --start  # 顺手用 SDK Server 模式启动
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

RELEASE_API = "https://api.github.com/repos/CalcProgrammer1/OpenRGB/releases/latest"
# GitHub API 会限流（403 rate limit exceeded）；限流时退回这个已知版本的直链。
FALLBACK_ZIP = (
    "OpenRGB_1.1_Windows_64_8e16de2.zip",
    "https://github.com/CalcProgrammer1/OpenRGB/releases/download/release_1.1/"
    "OpenRGB_1.1_Windows_64_8e16de2.zip",
)
DEST = Path(os.environ.get("KEYMOLE_OPENRGB_DIR") or
           (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "KeyMole" / "OpenRGB"))


def _search_dirs():
    yield DEST
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            yield Path(base) / "OpenRGB"
    yield Path(r"C:\OpenRGB")


def find_exe() -> Optional[Path]:
    for d in _search_dirs():
        for name in ("OpenRGB.exe", "OpenRGB Windows.exe"):
            p = d / name
            try:
                if p.is_file():
                    return p
            except OSError:
                continue
        try:
            for p in d.rglob("OpenRGB.exe"):
                return p
        except OSError:
            continue
    found = shutil.which("OpenRGB")
    return Path(found) if found else None


def _latest_windows_zip() -> tuple[str, str]:
    try:
        req = urllib.request.Request(RELEASE_API, headers={"User-Agent": "KeyMole"})
        data = json.load(urllib.request.urlopen(req, timeout=30))
        for asset in data.get("assets", []):
            name = asset["name"]
            if "Windows_64" in name and name.endswith(".zip"):
                return name, asset["browser_download_url"]
    except Exception as exc:
        print("（GitHub API 不可用：%s，改用已知版本）" % exc)
    return FALLBACK_ZIP


def download(force: bool = False) -> Path:
    exe = find_exe()
    if exe and not force:
        print("已经装好了：%s" % exe)
        return exe

    name, url = _latest_windows_zip()
    DEST.mkdir(parents=True, exist_ok=True)
    zip_path = DEST / name
    print("下载 %s ..." % name)
    req = urllib.request.Request(url, headers={"User-Agent": "KeyMole"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(zip_path, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                sys.stdout.write("\r  %d%%  %.1f / %.1f MB" % (pct, done / 1e6, total / 1e6))
                sys.stdout.flush()
    print("\n解压到 %s" % DEST)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(DEST)
    zip_path.unlink(missing_ok=True)
    exe = find_exe()
    if exe is None:
        raise RuntimeError("解压完了但没找到 OpenRGB.exe")
    return exe


def start(exe: Optional[Path] = None) -> subprocess.Popen:
    """以 SDK Server 模式启动：--server 开 6742 端口，--startminimized 不挡游戏。"""
    exe = exe or find_exe()
    if exe is None:
        raise RuntimeError("没找到 OpenRGB.exe，先跑 python -m keymole.setup_openrgb")
    print("启动 OpenRGB SDK Server：%s" % exe)
    return subprocess.Popen([str(exe), "--server", "--startminimized"],
                            cwd=str(exe.parent), close_fds=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="keymole.setup_openrgb",
                                 description="安装/启动 OpenRGB（KeyMole 的通用灯效引擎）")
    ap.add_argument("--start", action="store_true", help="装好后立刻以 SDK Server 模式启动")
    ap.add_argument("--force", action="store_true", help="即使已存在也重新下载")
    args = ap.parse_args(argv)
    try:
        exe = download(force=args.force)
    except Exception as exc:
        print("下载失败：%r" % (exc,))
        print("手动方案：到 https://openrgb.org 下载 Windows 64 版，解压后随意放，KeyMole 会自动找到。")
        return 1
    if args.start:
        start(exe)
    else:
        print("下一步：python -m keymole.setup_openrgb --start（或手动打开 OpenRGB 并勾选 SDK Server）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
