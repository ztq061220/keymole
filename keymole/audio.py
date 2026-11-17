"""用标准库现场合成音效，不依赖 pygame / 任何外部音频库。

音效是这个游戏的关键：视觉反馈在键盘上，眼睛往往来不及看，
「地鼠出现了」只能靠耳朵知道。
"""
from __future__ import annotations

import math
import struct
import tempfile
import wave
from pathlib import Path
from typing import Dict, Optional

try:
    import winsound
except ImportError:  # 非 Windows
    winsound = None  # type: ignore

RATE = 44100
_FLAGS = 0
if winsound is not None:
    _FLAGS = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT


def _envelope(i: int, n: int, attack: float = 0.004, release: float = 0.030) -> float:
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    e = 1.0
    if i < a:
        e = i / a
    if n - i < r:
        e = min(e, (n - i) / r)
    return max(0.0, e)


def _tone(f0: float, f1: Optional[float], dur: float, vol: float,
          shape: str = "sine") -> bytes:
    n = max(1, int(RATE * dur))
    f1 = f0 if f1 is None else f1
    phase = 0.0
    buf = bytearray()
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.0
        f = f0 + (f1 - f0) * t
        phase += 2.0 * math.pi * f / RATE
        s = math.sin(phase)
        if shape == "square":
            s = 0.55 if s >= 0 else -0.55
        elif shape == "tri":
            s = (2.0 / math.pi) * math.asin(max(-1.0, min(1.0, s)))
        s *= _envelope(i, n) * vol
        buf += struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
    return bytes(buf)


# 每个音效 = 若干段 (f0, f1, dur, vol, shape) 拼起来
_SOUNDS = {
    "spawn":   [(1046, None, 0.055, 0.26, "sine")],
    "hit":     [(1319, 1976, 0.085, 0.30, "sine")],
    "miss":    [(240, 150, 0.200, 0.30, "tri")],
    "wrong":   [(150, 120, 0.110, 0.22, "square")],
    "levelup": [(659, None, 0.060, 0.24, "sine"),
                (880, None, 0.060, 0.24, "sine"),
                (1319, None, 0.090, 0.24, "sine")],
}


def _build_wav(path: Path, segments) -> None:
    frames = b"".join(_tone(*seg) for seg in segments)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(frames)


class SoundBank:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = bool(enabled and winsound is not None)
        self.dir = Path(tempfile.gettempdir()) / "keymole_sfx"
        self.paths: Dict[str, Path] = {}
        if not self.enabled:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            for name, segments in _SOUNDS.items():
                p = self.dir / f"{name}.wav"
                if not p.exists() or p.stat().st_size < 100:
                    _build_wav(p, segments)
                self.paths[name] = p
        except Exception as exc:
            print(f"[audio] 初始化失败，静音运行: {exc!r}")
            self.enabled = False

    def play(self, name: str) -> None:
        if not self.enabled or winsound is None:
            return
        path = self.paths.get(name)
        if path is None:
            return
        try:
            # 单通道：新的声音会打断旧的，这正是我们要的（连击时只听到最新一记）
            winsound.PlaySound(str(path), _FLAGS)
        except Exception:
            pass

    def stop(self) -> None:
        if self.enabled and winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
