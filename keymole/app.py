"""入口：把 core / render / display 三层接起来跑。"""
from __future__ import annotations

import argparse
import os
import random
import sys


def _ensure_stdio() -> None:
    # 打包成 --windowed 的 exe 时 stdout/stderr 是 None，print 会炸
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
from collections import deque
import time
import tkinter as tk

from . import detect
from .audio import SoundBank
from .core.game import Game, Mole
from .core.layout import HAND_LABEL, HAND_SETS, HOLE_CODES, code_from_keysym
from .display.base import Fanout, Tier
from . import wininput
from .display.screen import BG, ScreenDisplay
from .render import build_frame

FRAME_MS = 16


def _log(msg: str) -> None:
    try:
        with open(".keymole.log", "a", encoding="utf-8") as fh:
            fh.write(("%.2f %s" + chr(10)) % (time.time() % 100000, msg))
    except Exception:
        pass


def _capture(root: tk.Tk, path: str) -> bool:
    """调试用：把窗口截图存盘（需要 Pillow）。优先问窗口自己要素材。"""
    try:
        from ._winshot import capture
        size = capture(int(root.winfo_id()), path)
        if size:
            return True
    except Exception:
        pass
    try:
        from PIL import ImageGrab
    except Exception as exc:
        print("[shot] 没装 Pillow，跳过截图: %r" % (exc,))
        return False
    try:
        root.update_idletasks()
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
        return True
    except Exception as exc:
        print("[shot] 截图失败: %r" % (exc,))
        return False


def _demo_moles(game: Game, now: float) -> None:
    """截图/演示用：摆三只年龄错开的地鼠，好看出「快跑了」的红色渐变。"""
    game.next_spawn = now + 600.0
    for code, age in (("e", 0.25), ("s", 1.00), ("b", 1.40)):
        game.moles[code] = Mole(code, now - age, 1.55)


def run_gui(args) -> int:
    root = tk.Tk()
    root.title("键盘打地鼠 · KeyMole")
    root.configure(bg=BG)
    root.resizable(False, False)

    screen = ScreenDisplay(root)

    # 中文输入法会把按键吃掉（进候选框），先把这个窗口的 IME 摘掉；
    # 再加一层 GetAsyncKeyState 轮询兜底，IME 怎么折腾都不影响判定。
    hwnd = wininput.root_hwnd(root.winfo_id())
    wininput.disable_ime(hwnd)
    poller = wininput.KeyPoller(list(HAND_SETS["both"]) + ["1", "2", "3"])
    edge = {"enter": False}
    hardware = []
    mock_server = None
    if args.mock:
        from .display.mock import MockServer
        from .display.openrgb import OpenRGBDisplay
        mock_server = MockServer(detect.OPENRGB_PORT)
        mock_server.start()
        candidates = [OpenRGBDisplay()]
    else:
        candidates = detect.hardware_displays(args.tier)
    # 快照必须在我们打开设备之前取：一旦被我们占用，HUB 就读不到配置了
    try:
        from . import hubbridge
        hub_snap = hubbridge.snapshot()
    except Exception:
        hub_snap = None
    if hub_snap:
        print("[KeyMole] 已记住 HUB 灯效，退出时自动还原")

    def status_text() -> str:
        forced = os.environ.get("KEYMOLE_STATUS")
        if forced:                    # 出图/演示用：强制显示某个通道名
            return forced
        if not hardware:
            return "灯效：只有屏幕（没找到可控制的键盘）　F5 重新连接"
        best = hardware[0]
        label = getattr(best, "device_label", "") or best.name
        return "灯效：%s（%s）　F5 重新连接" % (label, detect.TIER_LABEL[best.tier])

    def connect_hardware(reason: str) -> None:
        """关掉现有设备、重新扫描并打开。启动时和按 F5 时都走这里。"""
        for d in hardware:
            try:
                d.close()
            except Exception:
                pass
        hardware.clear()
        if args.mock:
            from .display.openrgb import OpenRGBDisplay
            cands = [OpenRGBDisplay()]
        else:
            cands = detect.hardware_displays(args.tier)
        try:
            for b in detect.scan():
                _log("  %s ok=%s %s" % (b.key, b.ok, str(b.detail)[:120]))
        except Exception as exc:
            _log("scan detail fail %r" % exc)
        _log("scan %s backends=%d" % (reason, len(cands)))
        for d in cands:
            try:
                d.open()
                hardware.append(d)
                label = getattr(d, "device_label", "") or d.name
                _log("open ok %s" % label)
                print("[KeyMole] 已点亮：%s（%s）" % (label, detect.TIER_LABEL[d.tier]))
            except Exception as exc:
                _log("open fail %s %r" % (d.name, exc))
                print("[%s] 启用失败: %r" % (d.name, exc))
        for d in hardware:
            if hasattr(d, "invalidate"):
                d.invalidate()
        if hardware:
            try:                      # 亮 0.35 秒的绿闪：肉眼确认「通道通了」
                for d in hardware:
                    d.flush({code: (0, 255, 120) for code in HAND_SETS["both"]})
                time.sleep(0.35)
                for d in hardware:
                    d.flush({code: (0, 0, 0) for code in HAND_SETS["both"]})
            except Exception as exc:
                _log("selftest fail %r" % exc)
        if screen is not None:
            screen.set_menu_status(status_text())

    connect_hardware("startup")

    displays = {"obj": Fanout([screen] + hardware)}
    # 键盘的 HID 周转有 ~20ms，屏幕是即时的；把屏幕这一帧往后压一点，
    # 两边就能「同时」看到地鼠（游戏逻辑和判定仍然用真实时间，不受影响）。
    sync_s = float(os.environ.get("KEYMOLE_SYNC_MS", "25")) / 1000.0
    history = deque()
    print("[KeyMole] 显示层 = %s，能力 = %s"
          % (displays["obj"].name, detect.TIER_LABEL[displays["obj"].tier]))
    if not hardware:
        print("[KeyMole] 这次只有屏幕版。跑 `python -m keymole.probe` 看为什么。")

    audio = SoundBank(enabled=not args.mute)
    hand = getattr(args, "hand", "left")
    game = Game(list(HAND_SETS[hand]), rng=random.Random(args.seed))

    def apply_mode(kind: str) -> None:
        nonlocal hand
        hand = kind
        game.holes = list(HAND_SETS[kind])
        game.reset(time.perf_counter())
        for d in hardware:
            if hasattr(d, "invalidate"):
                d.invalidate()
        screen.set_mode("模式：%s　1 左手 / 2 右手 / 3 双手" % HAND_LABEL[kind])

    screen.set_mode("模式：%s　1 左手 / 2 右手 / 3 双手" % HAND_LABEL[hand])
    pressed = set()
    paused = {"since": 0.0}          # 非 0 = 窗口失焦，整局时间轴冻着
    state = {"level": 1, "t0": time.perf_counter()}

    start = time.perf_counter()
    game.reset(start)
    game.running = False

    scene = {"name": "menu"}
    selected = {"mode": hand}

    def menu_preview(now: float):
        # 菜单里只静态预览洞位：颜色不变 → 不发包，键盘零负担
        return {code: (255, 140, 0) for code in HAND_SETS[selected["mode"]]}

    def toggle_pause() -> None:
        if paused["since"]:
            game.shift(time.perf_counter() - paused["since"])
            paused["since"] = 0.0
            screen.set_paused(False)
            audio.play("spawn")
        elif game.running:
            paused["since"] = time.perf_counter()
            screen.set_paused(True)
            audio.play("miss")

    def enter_menu() -> None:
        if paused["since"]:
            paused["since"] = 0.0
            screen.set_paused(False)
        scene["name"] = "menu"
        game.running = False
        game.over = False
        game.moles.clear()
        for d in hardware:
            if hasattr(d, "invalidate"):
                d.invalidate()
        screen.show_menu(selected["mode"])
        screen.set_menu_status(status_text())
        screen.set_menu_best("上一个模式：%s　最高分 %d"
                             % (HAND_LABEL[selected["mode"]], game.score))

    def start_game() -> None:
        _log("start mode=%s" % selected["mode"])
        scene["name"] = "play"
        screen.hide_menu()
        apply_mode(selected["mode"])

    def tick() -> None:
        if paused["since"]:
            screen.set_paused(True)
            poll_input()
            root.after(FRAME_MS, tick)
            return
        now = time.perf_counter()
        if hardware and now - state.get("lastlog", 0.0) >= 2.0:
            state["lastlog"] = now
            d0 = hardware[0]
            _log("frames_sent=%s applied=%s todo=%d"
                 % (getattr(d0, "frames_sent", "-"),
                    "set" if getattr(d0, "_applied", None) is not None else "none",
                    len(getattr(d0, "_todo", ()))))
        if scene["name"] == "menu":
            frame = menu_preview(now)
            for d in hardware:
                d.offer(frame, now)
            screen.offer(frame, now)
            poll_input()
            if args.duration and now - state["t0"] >= args.duration:
                quit_app()
                return
            root.after(FRAME_MS, tick)
            return
        for ev in game.update(now):
            if ev.kind in ("hit", "miss", "wrong", "spawn", "levelup"):
                audio.play(ev.kind)

        poll_input()

        frame = build_frame(game, now)
        for d in hardware:
            d.offer(frame, now)
        if sync_s > 0:
            history.append((now, frame))
            cut = now - sync_s
            while len(history) > 1 and history[1][0] <= cut:
                history.popleft()
            frame_shown = history[0][1]
        else:
            frame_shown = frame
        screen.offer(frame_shown, now)
        screen.update_hud(game, now)

        if args.duration and now - state["t0"] >= args.duration:
            quit_app()
            return
        root.after(FRAME_MS, tick)

    def restart() -> None:
        _log("restart frames_sent=%s" % getattr(hardware[0], "frames_sent", "-") if hardware else "restart")
        game.reset(time.perf_counter())
        for d in hardware:                      # 换局必须整帧重发，否则残留上一局的颜色
            if hasattr(d, "invalidate"):
                d.invalidate()
        history.clear()
        state["level"] = 1
        poller.clear()
        pressed.clear()
        audio.play("levelup")

    def fire(code) -> None:
        if code in ("1", "2", "3"):
            kind = {"1": "left", "2": "right", "3": "both"}[code]
            if scene["name"] == "menu":
                selected["mode"] = kind
                screen.set_menu_selection(kind)
                audio.play("spawn")
            else:
                apply_mode(kind)
            return
        if not code or code in pressed:
            return            # 按住不放产生的重复事件不算
        pressed.add(code)
        now = time.perf_counter()
        for e in game.press(code, now):
            audio.play(e.kind)
        screen.update_hud(game, now)

    def poll_input() -> None:
        # F5 用系统级按键状态，窗口没焦点也能重新连接设备
        if wininput.key_down(wininput.VK_F5) and not edge.get("f5"):
            edge["f5"] = True
            _log("hotkey F5 reconnect (global)")
            connect_hardware("hotkey")
            history.clear()
        elif not wininput.key_down(wininput.VK_F5):
            edge["f5"] = False
        # 只有本窗口在前台时才算数，别在别的程序里打字也被打地鼠
        if wininput.foreground() != hwnd:
            poller.clear()
            edge["enter"] = False
            return
        if poller.f5():
            _log("hotkey F5 reconnect")
            connect_hardware("hotkey")
            history.clear()
            return
        if poller.escape():
            if scene["name"] == "menu":
                quit_app()
            else:
                enter_menu()
            return
        if scene["name"] == "play" and not game.over:
            if poller.space():
                toggle_pause()
        ent = poller.enter()
        if ent and not edge["enter"]:
            edge["enter"] = True
            if scene["name"] == "menu":
                start_game()
            elif game.over:
                enter_menu()
        elif not ent:
            edge["enter"] = False
        for code in poller.poll():
            fire(code)

    def on_press(ev) -> None:
        if ev.keysym == "Escape":
            if scene["name"] == "menu":
                quit_app()
            else:
                enter_menu()
            return
        if ev.keysym == "space" and scene["name"] == "play":
            toggle_pause()
            return
        if ev.keysym in ("Return", "KP_Enter"):
            if scene["name"] == "menu":
                start_game()
            elif game.over:
                enter_menu()
            return
        fire(code_from_keysym(ev.keysym))

    def on_release(ev) -> None:
        code = code_from_keysym(ev.keysym)
        if code:
            pressed.discard(code)

    def on_focus_out(_ev=None) -> None:
        if game.running and not paused["since"]:
            paused["since"] = time.perf_counter()

    def on_focus_in(_ev=None) -> None:
        if paused["since"]:
            now = time.perf_counter()
            game.shift(now - paused["since"])   # 冻结多久就平移多久
            paused["since"] = 0.0
            screen.set_paused(False)

    done = {"flag": False}

    def quit_app() -> None:
        '''唯一的退出路径：关灯、把键盘交还 HUB、销毁窗口。'''
        if done["flag"]:
            return
        done["flag"] = True
        audio.stop()
        try:
            displays["obj"].close()
        finally:
            # 退出时把灯光交还给 HUB，别让键盘停在游戏最后一帧
            try:
                from . import hubbridge
                print("[KeyMole] " + hubbridge.restore(hub_snap))
            except Exception:
                pass
            root.destroy()

    def on_close() -> None:
        quit_app()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<KeyPress>", on_press)
    root.bind("<KeyRelease>", on_release)
    root.bind("<FocusOut>", on_focus_out)
    root.bind("<FocusIn>", on_focus_in)

    def on_click(ev) -> None:
        if scene["name"] != "menu":
            return
        hit = screen.menu_hit(ev.x, ev.y)
        if hit:
            selected["mode"] = hit
            screen.set_menu_selection(hit)
            audio.play("spawn")

    screen.canvas.bind("<Button-1>", on_click)
    root.focus_force()
    root.after(FRAME_MS, tick)

    if args.shot:
        def _do_shot() -> None:
            now = time.perf_counter()
            if os.environ.get("KEYMOLE_SHOT_PLAY"):
                start_game()
                now = time.perf_counter()
            _demo_moles(game, now)
            if os.environ.get("KEYMOLE_SHOT_OVER"):  # 出图用：伪造一局结束的画面
                game.lives = 0
                game.running = False
                game.over = True
            displays["obj"].flush(build_frame(game, now))
            screen.update_hud(game, now)
            root.attributes("-topmost", True)
            root.lift()
            root.update()
            if _capture(root, args.shot):
                print("[shot] 已保存:", args.shot)
            root.destroy()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry("+%d+%d" % (max(0, (sw - screen.w) // 2),
                                  max(0, sh - screen.h - 140)))
        root.after(800, _do_shot)

    enter_menu()
    root.after(FRAME_MS, tick)
    root.mainloop()
    return 0


def simulate(args) -> int:
    """无头模拟：用一个「人类水平」的机器人跑一遍，用来校准难度曲线。"""
    rng = random.Random(args.seed)
    game = Game(HOLE_CODES, rng=rng)
    game.reset(0.0)
    t = 0.0
    dt = 1.0 / 120.0
    pending = []
    while game.running and t < args.simulate:
        t += dt
        for ev in game.update(t):
            if ev.kind == "spawn" and rng.random() < 0.90:
                pending.append((t + rng.uniform(0.16, 0.34), ev.code))
        for item in list(pending):
            when, code = item
            if t >= when:
                pending.remove(item)
                if code in game.moles:
                    game.press(code, t)

    print("模拟结果（机器人：反应 160-340ms，命中率 90%）")
    print("  存活时间 : %.1f s%s" % (t, "" if not game.running else "  (跑满窗口，难度可能偏低)"))
    print("  得分     : %d" % game.score)
    print("  命中/漏掉/误按 : %d / %d / %d" % (game.hits, game.misses, game.wrongs))
    print("  命中率   : %.0f%%" % (game.accuracy * 100))
    print("  最高连击 : %d" % game.best_combo)
    print("  到达等级 : %d" % game.level)
    return 0


def main(argv=None) -> int:
    _ensure_stdio()
    p = argparse.ArgumentParser(prog="keymole", description="键盘打地鼠")
    p.add_argument("--tier", default="auto",
                   choices=["auto", "screen", "whole", "zones", "perkey"],
                   help="限定显示后端；默认 auto 自动挑能力最高的")
    p.add_argument("--mute", action="store_true", help="静音")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--simulate", type=float, default=0.0, metavar="SECONDS",
                   help="无头模拟跑 N 秒（校准难度用）")
    p.add_argument("--duration", type=float, default=0.0, help=argparse.SUPPRESS)
    p.add_argument("--shot", default="", help=argparse.SUPPRESS)
    p.add_argument("--mock", action="store_true",
                   help="用内置的假键盘验证逐键灯效（不需要任何硬件）")
    p.add_argument("--hand", default="left", choices=["left", "right", "both"],
                   help="洞位布局：left 左手（默认）/ right 右手 / both 双手")
    args = p.parse_args(argv)

    if args.simulate > 0:
        return simulate(args)
    return run_gui(args)
