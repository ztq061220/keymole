"""打包入口：PyInstaller / 桌面快捷方式都跑这个。"""
import sys

from keymole.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
