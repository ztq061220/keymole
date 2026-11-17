"""`python -m keymole.probe`：先看清这台机器能玩到哪一级、插了哪些键盘。"""
from . import detect
from .devices import format_devices


def main() -> int:
    print("\n".join(detect.report()))
    print()
    print("\n".join(format_devices()))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
