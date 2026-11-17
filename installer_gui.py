"""键盘打地鼠 安装程序（单文件 exe，支持自定义安装路径）。"""
import os
import shutil
import subprocess
import sys
import tkinter as tk
import traceback
from tkinter import filedialog
from tkinter import font as tkfont

APP = "键盘打地鼠"
EXE = "KeyMole.exe"
LINK = APP + ".lnk"
DEFAULT_DEST = os.environ.get("KEYMOLE_INSTALL_DIR") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "KeyMole")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
START_MENU = os.path.join(os.environ.get("APPDATA", ""),
                          "Microsoft", "Windows", "Start Menu", "Programs")
BG, CARD, FG, DIM, ACCENT = "#0b0e14", "#141a26", "#e8edf6", "#7c8798", "#48ff78"
W, H = 720, 460


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def payload_dir():
    for cand in (os.path.join(base_dir(), "pkg"),
                 os.path.join(base_dir(), "dist", "package")):
        if os.path.isfile(os.path.join(cand, "KeyMole", EXE)):
            return cand
    raise RuntimeError("安装包内的程序文件缺失")


def shortcut(path, target, icon=None):
    sys.path.insert(0, payload_dir())
    from shortcut import create_shortcut
    create_shortcut(path, target, workdir=os.path.dirname(target),
                    icon=icon or (target + ",0"), description="用键盘灯打地鼠")


def do_install(log, dest):
    src = os.path.join(payload_dir(), "KeyMole")
    log("正在复制程序文件到 " + dest)
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(src, dest)
    target = os.path.join(dest, EXE)
    icon = os.path.join(dest, "KeyMole.ico")
    if not os.path.isfile(icon):
        bundled = os.path.join(base_dir(), "keymole.ico")
        if os.path.isfile(bundled):
            shutil.copyfile(bundled, icon)
    icon_arg = (icon + ",0") if os.path.isfile(icon) else (target + ",0")
    for folder in (DESKTOP, START_MENU):
        if folder and os.path.isdir(folder):
            log("正在创建快捷方式：" + folder)
            shortcut(os.path.join(folder, LINK), target, icon_arg)
    log("安装完成：" + target)


def do_uninstall(log, dest):
    for folder in (DESKTOP, START_MENU):
        p = os.path.join(folder, LINK) if folder else ""
        if p and os.path.isfile(p):
            os.remove(p)
    if os.path.isdir(dest):
        log("正在删除 " + dest)
        shutil.rmtree(dest, ignore_errors=True)
    log("已卸载")


def _safe_log(msg):
    try:
        print(msg)
    except Exception:
        pass
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                            "KeyMole-Setup.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(str(msg) + chr(10))
    except Exception:
        pass


def main() -> int:
    root = tk.Tk()
    root.title(APP + " 安装程序")
    root.configure(bg=BG)
    root.resizable(False, False)
    x = (root.winfo_screenwidth() - W) // 2
    y = (root.winfo_screenheight() - H) // 3
    root.geometry("%dx%d+%d+%d" % (W, H, x, y))
    try:
        root.iconbitmap(os.path.join(base_dir(), "keymole.ico"))
    except Exception:
        pass

    title_font = tkfont.Font(family="Microsoft YaHei UI", size=22, weight="bold")
    mid_font = tkfont.Font(family="Microsoft YaHei UI", size=10)
    small_font = tkfont.Font(family="Microsoft YaHei UI", size=9)

    card = tk.Frame(root, bg=CARD, bd=0)
    card.place(x=24, y=24, width=W - 48, height=H - 48)

    tk.Label(card, text=APP, bg=CARD, fg=FG, font=title_font).place(x=26, y=20)
    tk.Label(card, text="用键盘的灯当屏幕，在 QWERTY 主区打地鼠",
             bg=CARD, fg=DIM, font=mid_font).place(x=28, y=60)

    tk.Label(card, text="安装位置（可修改，或点右侧浏览选择文件夹）",
             bg=CARD, fg=DIM, font=small_font, anchor="w").place(x=28, y=96)
    var_path = tk.StringVar(value=DEFAULT_DEST)
    entry = tk.Entry(card, textvariable=var_path, bg="#0d1320", fg=FG, bd=0,
                     insertbackground=ACCENT, font=mid_font,
                     highlightthickness=1, highlightbackground="#2b3447",
                     highlightcolor=ACCENT)
    entry.place(x=28, y=118, width=W - 96 - 140, height=32)

    def browse():
        start = var_path.get() or os.path.expanduser("~")
        if os.path.isfile(start):
            start = os.path.dirname(start)
        chosen = filedialog.askdirectory(parent=root, title="选择安装位置",
                                         initialdir=start, mustexist=False)
        if chosen:
            var_path.set(os.path.join(os.path.normpath(chosen), "KeyMole"))

    tk.Button(card, text="浏览…", font=mid_font, bd=0, bg="#20283a", fg=FG,
              activebackground="#2b3447", command=browse).place(
        x=W - 96 - 100, y=118, width=92, height=32)

    status = tk.Label(card, text="准备就绪", bg=CARD, fg=ACCENT,
                      font=mid_font, anchor="w", justify="left")
    status.place(x=28, y=166, width=W - 96, height=24)
    tk.Label(card, text="装到用户目录不需要管理员权限；换到别的盘时请确保有写权限。",
             bg=CARD, fg=DIM, font=small_font, anchor="w").place(
        x=28, y=192, width=W - 96)

    state = {"busy": False}

    def current_dest():
        dest = var_path.get().strip().strip('"')
        if not dest:
            raise RuntimeError("安装位置不能为空")
        if not os.path.isabs(dest):
            raise RuntimeError("请填写完整路径，例如 D:/Games/KeyMole")
        return dest

    def log(msg):
        status.configure(text=msg)
        root.update_idletasks()

    def run(fn, after):
        if state["busy"]:
            return
        try:
            dest = current_dest()
        except Exception as exc:
            status.configure(text=str(exc))
            return
        state["busy"] = True
        btn_install.configure(state="disabled")
        btn_uninstall.configure(state="disabled")
        entry.configure(state="disabled")
        try:
            fn(log, dest)
        except Exception as exc:
            status.configure(text="出错：" + str(exc))
            _safe_log(traceback.format_exc())
            state["busy"] = False
            btn_install.configure(state="normal")
            entry.configure(state="normal")
            return
        state["busy"] = False
        after()

    def finish_install():
        status.configure(text="安装完成，桌面和开始菜单都有快捷方式了")
        btn_install.configure(text="开始游戏", state="normal", command=launch)
        btn_uninstall.configure(state="normal")
        btn_cancel.configure(text="关闭")

    def finish_uninstall():
        status.configure(text="已卸载")
        btn_install.configure(text="安装", state="normal",
                              command=lambda: run(do_install, finish_install))
        btn_uninstall.configure(state="disabled")
        entry.configure(state="normal")

    def launch():
        target = os.path.join(var_path.get().strip(), EXE)
        if os.path.isfile(target):
            subprocess.Popen([target])
        root.destroy()

    btn_install = tk.Button(card, text="安装", font=mid_font, bd=0, bg=ACCENT,
                            fg="#04140a", activebackground="#39d967",
                            command=lambda: run(do_install, finish_install))
    btn_uninstall = tk.Button(card, text="卸载", font=mid_font, bd=0, bg="#20283a",
                              fg=FG, activebackground="#2b3447",
                              command=lambda: run(do_uninstall, finish_uninstall))
    btn_cancel = tk.Button(card, text="取消", font=mid_font, bd=0, bg="#20283a",
                           fg=FG, activebackground="#2b3447", command=root.destroy)

    by = H - 48 - 88
    btn_install.place(x=28, y=by, width=190, height=44)
    btn_uninstall.place(x=232, y=by, width=140, height=44)
    btn_cancel.place(x=W - 48 - 140, y=by, width=128, height=44)

    if not os.path.isfile(os.path.join(var_path.get(), EXE)):
        btn_uninstall.configure(state="disabled")
    else:
        status.configure(text="检测到已安装，可以直接覆盖安装或卸载")

    root.mainloop()
    return 0


if __name__ == "__main__":
    if "--silent" in sys.argv:
        try:
            dest = os.environ.get("KEYMOLE_INSTALL_DIR") or DEFAULT_DEST
            if "--uninstall" in sys.argv:
                do_uninstall(_safe_log, dest)
            else:
                do_install(_safe_log, dest)
            sys.exit(0)
        except Exception as exc:
            _safe_log("失败：%r" % exc)
            _safe_log(traceback.format_exc())
            sys.exit(1)
    sys.exit(main())
