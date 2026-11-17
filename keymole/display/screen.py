"""L0 后端：用 tkinter 在屏幕上画一块键盘。

它同时也是「真机灯效的预览器」—— 因为吃的是同一帧颜色，你在屏幕上看到的
地鼠位置/颜色，和插上真键盘后灯亮的样子是一致的。
"""
from __future__ import annotations

import tkinter as tk
from typing import Dict, Mapping, Tuple

from ..core.game import Game
from ..core.layout import KEYBOARD, HEIGHT_U, WIDTH_U
from ..render import OFF
from .base import Display, Tier

Rgb = Tuple[int, int, int]

BG          = "#0b0e14"
HUD_DIM     = "#5b6478"
HUD_TEXT    = "#e8ecf4"
HUD_ACCENT  = "#ffb020"
HEART_ON    = "#ff5a6e"
HEART_OFF   = "#252b39"
CARD        = "#11151e"

UNIT = 52          # 1U 的像素宽度
GAP = 5            # 键与键之间的缝
MARGIN = 22
HUD_H = 92

FONT_KEY = ("Segoe UI Semibold", 13)
FONT_HUD_LABEL = ("Microsoft YaHei UI", 9)
FONT_HUD_BIG = ("Segoe UI Semibold", 27)
FONT_HUD_MID = ("Segoe UI Semibold", 13)
FONT_OVER = ("Segoe UI Semibold", 30)
HEARTS = 7         # 与 Config.lives_max 对齐：空槽位常驻，玩家看得到回血空间
FONT_OVER_SUB = ("Microsoft YaHei UI", 12)


def _lum(rgb: Rgb) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _hex(rgb: Rgb) -> str:
    return "#%02x%02x%02x" % rgb


def _brighten(rgb: Rgb, k: float = 1.45) -> str:
    return _hex(tuple(min(255, int(c * k + 18)) for c in rgb))


def _rrect(canvas: tk.Canvas, x0, y0, x1, y1, r, **kw):
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0,
        x1, y0 + r, x1, y1 - r, x1, y1,
        x1 - r, y1, x0 + r, y1, x0, y1,
        x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class ScreenDisplay(Display):
    name = "screen"
    tier = Tier.OFF
    refresh_hz = 60.0

    def __init__(self, root: tk.Tk, unit: int = UNIT) -> None:
        super().__init__()
        self.root = root
        self.unit = unit
        self.w = int(MARGIN * 2 + WIDTH_U * unit)
        self.h = int(HUD_H + MARGIN * 2 + HEIGHT_U * unit)
        self.canvas = tk.Canvas(root, width=self.w, height=self.h,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()
        self._key_items: Dict[str, list] = {}
        self._last: Dict[str, Rgb] = {}
        self._hud: Dict[str, object] = {}
        self._build_keys()
        self._build_hud()

    # ---------- 画布 ----------

    def _build_keys(self) -> None:
        u, g = self.unit, GAP
        for key in KEYBOARD:
            x0 = MARGIN + key.x * u + g / 2
            y0 = HUD_H + MARGIN + key.y * u + g / 2
            x1 = x0 + key.w * u - g
            y1 = y0 + u - g
            rect = _rrect(self.canvas, x0, y0, x1, y1, 7,
                          fill=_hex(self._last.get(key.code, OFF)),
                          outline="#1c2231", width=1)
            txt = self.canvas.create_text(
                (x0 + x1) / 2, (y0 + y1) / 2 + (0 if key.label else 0),
                text=key.label, fill="#6a7386", font=FONT_KEY,
            )
            self._key_items[key.code] = [rect, txt]

    def _build_hud(self) -> None:
        c = self.canvas
        # 分数
        self._hud["lbl_score"] = c.create_text(MARGIN, 20, text="分数", anchor="nw",
                                               fill=HUD_DIM, font=FONT_HUD_LABEL)
        self._hud["score"] = c.create_text(MARGIN, 38, text="0", anchor="nw",
                                           fill=HUD_TEXT, font=FONT_HUD_BIG)
        # 连击
        self._hud["combo"] = c.create_text(MARGIN + 150, 52, text="", anchor="nw",
                                           fill=HUD_ACCENT, font=FONT_HUD_MID)
        # 等级
        self._hud["lbl_level"] = c.create_text(self.w / 2 - 30, 20, text="等级", anchor="nw",
                                               fill=HUD_DIM, font=FONT_HUD_LABEL)
        self._hud["level"] = c.create_text(self.w / 2 - 30, 38, text="1", anchor="nw",
                                           fill=HUD_TEXT, font=FONT_HUD_BIG)
        # 命
        self._hud["lbl_hearts"] = c.create_text(self.w - MARGIN, 20, text="命", anchor="ne",
                                                fill=HUD_DIM, font=FONT_HUD_LABEL)
        self._hud["hearts"] = [
            c.create_text(self.w - MARGIN - i * 24, 40, text="♥", anchor="ne",
                          fill=HEART_ON, font=("Segoe UI Symbol", 19))
            for i in range(HEARTS)
        ]
        # 结束遮罩（平时隐藏）
        cw, cy0, cy1 = 470.0, self.h / 2 - 84, self.h / 2 + 78
        self._hud["veil"] = _rrect(c, self.w / 2 - cw / 2, cy0,
                                   self.w / 2 + cw / 2, cy1, 18,
                                   fill="#0c0f16", outline="#2b3447", width=1)
        self._hud["over"] = c.create_text(self.w / 2, self.h / 2 - 22,
                                          text="GAME OVER", fill="#ff6a7a",
                                          font=FONT_OVER)
        self._hud["over_sub"] = c.create_text(self.w / 2, self.h / 2 + 20,
                                              text="", fill=HUD_TEXT, font=FONT_OVER_SUB)
        self._hud["over_hint"] = c.create_text(self.w / 2, self.h / 2 + 50,
                                               text="按 Enter 重来 · Esc 退出",
                                               fill=HUD_DIM, font=FONT_OVER_SUB)
        self._hud["mode"] = c.create_text(
            MARGIN, self.h - 14, text="", anchor="w",
            fill=HUD_DIM, font=FONT_HUD_LABEL)
        self._hud["paused"] = c.create_text(
            self.w / 2, self.h - 14, text="已暂停 · 空格继续 · Esc 回菜单",
            fill=HUD_DIM, font=FONT_HUD_LABEL, state="hidden")
        for name in ("veil", "over", "over_sub", "over_hint"):
            c.itemconfigure(self._hud[name], state="hidden")
        self._build_menu()


    # ---------- 开始菜单 ----------

    def _build_menu(self) -> None:
        c = self.canvas
        cx = self.w / 2
        self._menu = {"btns": {}}
        self._menu["backdrop"] = c.create_rectangle(
            0, 0, self.w, self.h, fill="#080a10", outline="")
        self._menu["title"] = c.create_text(
            cx, 62, text="键盘打地鼠",
            fill="#e8ecf5", font=("Microsoft YaHei UI", 38, "bold"))
        self._menu["sub"] = c.create_text(
            cx, 104, text="先选一个模式，然后按 Enter 开始",
            fill=HUD_DIM, font=FONT_HUD_MID)

        modes = [("left", "左手", "Q W E R T / A S D F G / Z X C V B"),
                 ("right", "右手", "Y U I O P / H J K L ; / N M , . /"),
                 ("both", "双手", "左右各 15 个洞，共 30 个")]
        bw, bh, gap = 250, 124, 26
        total = len(modes) * bw + (len(modes) - 1) * gap
        x0 = cx - total / 2
        y0 = 140
        for i, (key, label, desc) in enumerate(modes):
            x = x0 + i * (bw + gap)
            rect = _rrect(c, x, y0, x + bw, y0 + bh, 16,
                          fill="#141a25", outline="#2b3447", width=2)
            num = c.create_text(x + bw / 2, y0 + 30, text=str(i + 1),
                                fill="#6a7386", font=FONT_HUD_BIG)
            name = c.create_text(x + bw / 2, y0 + 74, text=label,
                                 fill="#e8ecf5",
                                 font=("Microsoft YaHei UI", 22, "bold"))
            desc_item = c.create_text(x + bw / 2, y0 + 104, text=desc,
                                      fill=HUD_DIM, font=FONT_HUD_LABEL)
            self._menu["btns"][key] = (x, y0, x + bw, y0 + bh,
                                       rect, num, name, desc_item)
        self._menu["hint"] = c.create_text(
            cx, y0 + bh + 34, text="1 / 2 / 3 或点击选择    Enter 开始    Esc 退出",
            fill=HUD_DIM, font=FONT_HUD_LABEL)
        self._menu["best"] = c.create_text(
            cx, self.h - 38, text="", fill=HUD_ACCENT, font=FONT_HUD_LABEL)
        self._menu["status"] = c.create_text(
            cx, self.h - 64, text="", fill=HUD_DIM, font=FONT_HUD_LABEL)
        self.hide_menu()

    def _menu_items(self) -> list:
        items = [self._menu["backdrop"], self._menu["title"], self._menu["sub"],
                 self._menu["hint"], self._menu["best"], self._menu["status"]]
        for _x0, _y0, _x1, _y1, rect, num, name, desc in self._menu["btns"].values():
            items += [rect, num, name, desc]
        return items

    def show_menu(self, selected: str = "left") -> None:
        for item in self._menu_items():
            self.canvas.itemconfigure(item, state="normal")
        for name in ("score", "level", "combo", "mode",
                     "lbl_score", "lbl_level", "lbl_hearts"):
            self.canvas.itemconfigure(self._hud[name], state="hidden")
        for item in self._hud["hearts"]:
            self.canvas.itemconfigure(item, state="hidden")
        self.set_menu_selection(selected)

    def hide_menu(self) -> None:
        for item in self._menu_items():
            self.canvas.itemconfigure(item, state="hidden")
        for name in ("score", "level", "combo", "mode",
                     "lbl_score", "lbl_level", "lbl_hearts"):
            self.canvas.itemconfigure(self._hud[name], state="normal")
        for item in self._hud["hearts"]:
            self.canvas.itemconfigure(item, state="normal")

    def set_menu_selection(self, selected: str) -> None:
        for key, (_x0, _y0, _x1, _y1, rect, num, name, desc) in self._menu["btns"].items():
            on = key == selected
            self.canvas.itemconfigure(rect, fill="#1d3a2e" if on else "#141a25",
                                      outline="#48ff78" if on else "#2b3447",
                                      width=3 if on else 2)
            self.canvas.itemconfigure(name, fill="#48ff78" if on else "#e8ecf5")

    def set_menu_status(self, text: str) -> None:
        self.canvas.itemconfigure(self._menu["status"], text=text)

    def set_menu_best(self, text: str) -> None:
        self.canvas.itemconfigure(self._menu["best"], text=text)

    def menu_hit(self, x: float, y: float):
        for key, (x0, y0, x1, y1, *_rest) in self._menu["btns"].items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return key
        return None

    # ---------- 刷新 ----------

    def _commit(self, frame: Mapping[str, Rgb]) -> None:
        for code, rgb in frame.items():
            if self._last.get(code) == rgb:
                continue
            self._last[code] = rgb
            items = self._key_items.get(code)
            if items is None:
                continue
            rect, txt = items
            lum = _lum(rgb)
            self.canvas.itemconfigure(rect, fill=_hex(rgb),
                                      outline=_brighten(rgb) if lum > 90 else "#1c2231",
                                      width=2 if lum > 90 else 1)
            self.canvas.itemconfigure(txt, fill="#0a0c11" if lum > 120 else "#6a7386")

    def set_mode(self, text: str) -> None:
        if self._hud.get("_mode") != text:
            self._hud["_mode"] = text
            self.canvas.itemconfigure(self._hud["mode"], text=text)

    def set_paused(self, flag: bool) -> None:
        if self._hud.get("_paused") != flag:
            self._hud["_paused"] = flag
            self.canvas.itemconfigure(self._hud["paused"],
                                      state="normal" if flag else "hidden")

    def update_hud(self, game: Game, now: float) -> None:
        c = self.canvas
        score = str(game.score)
        if self._hud.get("_score") != score:
            self._hud["_score"] = score
            c.itemconfigure(self._hud["score"], text=score)

        level = f"{game.level}"
        if self._hud.get("_level") != level:
            self._hud["_level"] = level
            c.itemconfigure(self._hud["level"], text=level)

        combo = f"连击 ×{game.combo}" if game.combo >= 2 else ""
        if self._hud.get("_combo") != combo:
            self._hud["_combo"] = combo
            c.itemconfigure(self._hud["combo"], text=combo)

        if self._hud.get("_lives") != game.lives:
            self._hud["_lives"] = game.lives
            for i, item in enumerate(self._hud["hearts"]):
                c.itemconfigure(item, fill=HEART_ON if i < game.lives else HEART_OFF)

        over = game.over
        if self._hud.get("_over") != over:
            self._hud["_over"] = over
            state = "normal" if over else "hidden"
            for name in ("veil", "over", "over_sub", "over_hint"):
                c.itemconfigure(self._hud[name], state=state)
            if over:
                c.itemconfigure(
                    self._hud["over_sub"],
                    text=f"得分 {game.score} · 最高连击 {game.best_combo} · "
                         + ("命中率 —" if game.hits + game.misses + game.wrongs == 0
                            else f"命中率 {game.accuracy:.0%}"),
                )
