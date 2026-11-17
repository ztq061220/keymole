"""KeyMole 安装脚本：复制到用户目录，建桌面/开始菜单快捷方式。

用法：双击 安装.bat，或  python install.py
卸载：python install.py --uninstall
"""
import os
import shutil
import sys

APP_NAME = "键盘打地鼠"
EXE_NAME = "KeyMole.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
def _find_src() -> str:
    for cand in (os.path.join(HERE, "dist", "KeyMole"),
                 os.path.join(HERE, "KeyMole"),
                 HERE):
        if os.path.isfile(os.path.join(cand, EXE_NAME)):
            return cand
    return os.path.join(HERE, "dist", "KeyMole")


SRC = _find_src()
DEST = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                    "Programs", "KeyMole")
LINK_NAME = APP_NAME + ".lnk"
START_MENU = os.path.join(os.environ.get("APPDATA", ""),
                          "Microsoft", "Windows", "Start Menu", "Programs")


def desktop_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _ensure_icon() -> str:
    """把 ico 放到安装目录，快捷方式指向它（直接指向 exe 时图标常被系统缓存吃掉）。"""
    icon = os.path.join(DEST, "KeyMole.ico")
    if os.path.isfile(icon):
        return icon
    src = os.path.join(HERE, "keymole", "docs", "keymole.ico")
    if os.path.isfile(src):
        shutil.copyfile(src, icon)
        return icon
    return ""


def shortcut(path: str, target: str) -> None:
    from shortcut import create_shortcut
    icon = _ensure_icon()
    create_shortcut(path, target, workdir=os.path.dirname(target),
                    icon=(icon + ",0") if icon else (target + ",0"),
                    description="用键盘灯打地鼠")


def install() -> int:
    exe = os.path.join(SRC, EXE_NAME)
    if not os.path.isfile(exe):
        print("找不到 %s，请先在源码目录执行打包（python -m PyInstaller ...）" % exe)
        return 1
    if os.path.isdir(DEST):
        shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    shutil.copytree(SRC, DEST)
    target = os.path.join(DEST, EXE_NAME)
    made = []
    for folder in (desktop_dir(), START_MENU):
        if folder and os.path.isdir(folder):
            p = os.path.join(folder, LINK_NAME)
            shortcut(p, target)
            made.append(p)
    print("[OK] 已安装到 %s" % DEST)
    for p in made:
        print("[OK] 快捷方式 %s" % p)
    print("双击桌面的「%s」就能玩；Esc 回菜单，菜单里 Esc 退出。" % APP_NAME)
    return 0


def uninstall() -> int:
    for folder in (desktop_dir(), START_MENU):
        p = os.path.join(folder, LINK_NAME) if folder else ""
        if p and os.path.isfile(p):
            os.remove(p)
            print("[OK] 删除快捷方式 %s" % p)
    if os.path.isdir(DEST):
        shutil.rmtree(DEST, ignore_errors=True)
        print("[OK] 已删除 %s" % DEST)
    return 0


if __name__ == "__main__":
    sys.exit(uninstall() if "--uninstall" in sys.argv else install())
