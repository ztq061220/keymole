"""整局跑在「假键盘」上：游戏 → 渲染 → OpenRGB 协议 → LED。

没有真机也能验证 L3 链路是否通：起了假服务器后，把一整局打地鼠的帧发过去，
再回头检查假键盘上确实收到过「命中绿」。

    python -m tools.test_orgb_game
"""
from __future__ import annotations

import random
import time

from keymole.core.game import Game
from keymole.core.layout import HOLE_CODES
from keymole.display.openrgb import OpenRGBDisplay
from keymole.render import HIT, build_frame
from keymole.display.mock import MockServer

PORT = 6743
DURATION = 6.0


def main() -> int:
    srv = MockServer(PORT)
    srv.start()
    time.sleep(0.2)

    disp = OpenRGBDisplay(port=PORT)
    disp.open()
    ctrl = srv.controller
    index = {code: ctrl.codes.index(code) for code in ctrl.codes}
    print("假键盘：%s（%d 个 LED）" % (disp.device_label, len(ctrl.leds)))

    game = Game(HOLE_CODES, rng=random.Random(7))
    t0 = time.perf_counter()
    game.reset(t0)
    seen_hit = 0
    seen_mole = 0
    next_shot = t0
    while True:
        now = time.perf_counter()
        if now - t0 > DURATION:
            break
        game.update(now)
        if now >= next_shot:                 # 30Hz 提交，模拟真实刷新率
            next_shot = now + 1 / 30.0
            frame = build_frame(game, now)
            disp.offer(frame, now)
            live = sum(1 for c in ctrl.codes if ctrl.colors[index[c]] != (0, 0, 0))
            seen_mole = max(seen_mole, live)
        for mole in list(game.moles.values()):
            if now - mole.born > 0.25:       # 简单机器人：看到地鼠 250ms 后出手
                game.press(mole.code, now)
        time.sleep(0.005)

    disp.flush(build_frame(game, time.perf_counter()))
    time.sleep(0.2)

    greens = sum(1 for c in ctrl.codes if ctrl.colors[index[c]] == HIT)
    lit = sum(1 for c in ctrl.codes if ctrl.colors[index[c]] != (0, 0, 0))
    print("得分 %d，命中 %d，错按 %d" % (game.score, game.hits, game.wrongs))
    print("假键盘收到 %d 帧，当前亮着 %d 个键，其中命中绿 %d 个" % (ctrl.updates, lit, greens))
    print("过程中最多同时亮 %d 个键（地鼠 + 闪光）" % seen_mole)
    assert ctrl.updates > 50, "帧没真正发过去"
    assert lit > 0 or greens > 0, "灯一个都没亮"
    assert game.hits > 0, "机器人一只都没打中，链路有问题"
    disp.close()
    srv.stop()
    print("OK：游戏 → 渲染 → OpenRGB → LED 全链路通")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
