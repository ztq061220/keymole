"""创建 Windows 快捷方式（不依赖 pywin32 / PowerShell）。

实现：生成一个临时 .vbs 交给 cscript 执行。
用 ctypes 直接调 IShellLink::SetIconLocation 在本机写不进图标路径
（生成的 lnk 里既没有 .ico 引用也没有图标信息），
而 WScript.Shell.CreateShortcut 可靠，故改用这条路径。
.vbs 必须按 ANSI（本机 GBK）落盘，否则中文描述会让 cscript 解析失败。
"""

import io as _io
import os
import subprocess
import tempfile

NEWLINE = chr(13) + chr(10)


def _quote(text):
    return '"' + str(text).replace('"', '""') + '"'


def _open_ansi(path):
    try:
        return _io.open(path, "w", encoding="mbcs")
    except LookupError:  # 非 Windows 上的兜底
        return _io.open(path, "w", encoding="latin-1", errors="replace")


def create_shortcut(lnk_path, target, workdir=None, icon=None, description=None):
    """在 lnk_path 建一个指向 target 的快捷方式。icon 可传 "a.ico" 或 "a.exe,0"。"""
    lnk_path = os.path.abspath(lnk_path)
    target = os.path.abspath(target)
    workdir = os.path.abspath(workdir or os.path.dirname(target))

    lines = [
        'Set sh = CreateObject("WScript.Shell")',
        "Set lnk = sh.CreateShortcut(%s)" % _quote(lnk_path),
        "lnk.TargetPath = %s" % _quote(target),
        "lnk.WorkingDirectory = %s" % _quote(workdir),
    ]
    if icon:
        icon_path, _, icon_idx = str(icon).rpartition(",")
        if not icon_path:
            icon_path, icon_idx = str(icon), "0"
        icon_idx = icon_idx.strip()
        if not icon_idx.isdigit():
            icon_path, icon_idx = str(icon), "0"
        lines.append("lnk.IconLocation = %s"
                     % _quote("%s,%s" % (os.path.abspath(icon_path), icon_idx)))
    if description:
        lines.append("lnk.Description = %s" % _quote(description))
    lines.append("lnk.Save")

    fd, vbs = tempfile.mkstemp(suffix=".vbs", prefix="keymole_lnk_")
    os.close(fd)
    try:
        with _open_ansi(vbs) as fh:
            fh.write(NEWLINE.join(lines) + NEWLINE)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(["cscript", "//nologo", vbs],
                              capture_output=True, creationflags=flags)
        if proc.returncode != 0:
            raw = proc.stdout + proc.stderr
            text = raw.decode("mbcs", "ignore") if os.name == "nt" else raw.decode("utf-8", "ignore")
            raise RuntimeError("创建快捷方式失败：" + (text.strip() or ("cscript 返回 %d" % proc.returncode)))
    finally:
        try:
            os.remove(vbs)
        except OSError:
            pass
    return lnk_path


def remove_shortcut(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False
