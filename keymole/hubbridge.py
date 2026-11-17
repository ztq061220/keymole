"""把键盘灯光在「游戏开始/结束」之间和 MCHOSE HUB 交接。

流程：
  1. 开局前 snapshot()：从 HUB 的活实例里读出当前灯效配置（getLightConfig +
     getSelectedLightEffect），存下来。必须在游戏开始写灯之前取，否则设备里的
     配置已经被我们的帧覆盖。
  2. 退出时 restore(snap)：把这份配置原样推回去，键盘就回到驱动里的灯效。

HUB 必须是带 --remote-debugging-port=9222 启动的那个实例；没开就安静跳过。
"""
from __future__ import annotations

import json
import time
import urllib.request

PORT = 9222
ACCEPT_VID = 16868          # Ace68 系列（HUB 内部用它判 CZ 家族）

def _pick_js() -> str:
    return """
const _pick = () => {
  const S = window.ALL_CZ_STATE;
  if (!S || !S.deviceStateMap) return null;
  for (const v of S.deviceStateMap.values()) {
    const st = v && v.state;
    if (st && st.sdk && st.sdk.hidDevice && st.sdk.hidDevice.vendorId === __VID__) return st.sdk;
  }
  return null;
};
"""

_JS_SNAPSHOT = "(() => {" + _pick_js() + """
  window.__km = {done: false};
  (async () => {
    try {
      const sdk = _pick();
      if (!sdk) { window.__km = {done: true, err: 'no sdk'}; return; }
      const cfg = await sdk.getLightConfig();
      const eff = await sdk.getSelectedLightEffect();
      window.__km = {done: true, cfg: cfg, eff: eff};
    } catch (e) { window.__km = {done: true, err: String(e)}; }
  })();
  return 'started';
})()"""

_JS_RESTORE = "(() => {" + _pick_js() + """
  const snap = __SNAP__;
  window.__kmr = {done: false};
  (async () => {
    const steps = [];
    try {
      const sdk = _pick();
      if (!sdk) { window.__kmr = {done: true, err: 'no sdk'}; return; }
      if (snap && snap.cfg) {
        await sdk.setLightConfig(snap.cfg); steps.push('config');
      }
      if (snap && snap.eff) {
        await sdk.setSelectedLightEffect(snap.eff); steps.push('effect');
      }
      if (!steps.length) { window.__kmr = {done: true, err: 'empty snapshot'}; return; }
      window.__kmr = {done: true, steps: steps};
    } catch (e) { window.__kmr = {done: true, err: String(e), steps: steps}; }
  })();
  return 'started';
})()"""


def _target():
    with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=1.5) as r:
        for t in json.loads(r.read()):
            if t.get("type") == "page" and "index.html" in (t.get("url") or ""):
                return t
    return None


class _Session:
    def __init__(self, url):
        import websocket
        self.ws = websocket.create_connection(url, timeout=8, suppress_origin=True)
        self._id = 0

    def eval(self, expr):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "returnByValue": True,
                                            "userGesture": True}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                res = msg.get("result", {})
                if "exceptionDetails" in res:
                    raise RuntimeError(str(res["exceptionDetails"])[:200])
                return res.get("result", {}).get("value")

    def wait(self, expr, timeout):
        end = time.time() + timeout
        while time.time() < end:
            val = self.eval(expr)
            if val:
                return val
            time.sleep(0.15)
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def _open():
    t = _target()
    if not t or not t.get("webSocketDebuggerUrl"):
        return None
    try:
        return _Session(t["webSocketDebuggerUrl"])
    except Exception:
        return None


def snapshot(timeout: float = 4.0):
    """开局前调用：拿到 HUB 当前的灯效配置。拿不到就返回 None。"""
    ses = _open()
    if not ses:
        return None
    try:
        ses.eval(_JS_SNAPSHOT.replace("__VID__", str(ACCEPT_VID)))
        val = ses.wait("window.__km && window.__km.done ? window.__km : null", timeout)
    except Exception:
        return None
    finally:
        ses.close()
    if not val or val.get("err"):
        return None
    return {"cfg": val.get("cfg"), "eff": val.get("eff")}


def restore(snap, timeout: float = 6.0) -> str:
    """退出时调用：把 snapshot() 拿到的配置推回去。"""
    if not snap:
        return "没有 HUB 灯效快照，灯光停在最后一帧"
    ses = _open()
    if not ses:
        return "没找到带调试端口的 HUB，灯光停在最后一帧"
    try:
        ses.eval(_JS_RESTORE.replace("__VID__", str(ACCEPT_VID)).replace("__SNAP__", json.dumps(snap, ensure_ascii=False)))
        val = ses.wait("window.__kmr && window.__kmr.done ? window.__kmr : null", timeout)
    except Exception as exc:
        return "通知 HUB 失败：%s" % exc
    finally:
        ses.close()
    if not val:
        return "HUB 没回应，灯光停在最后一帧"
    if val.get("err"):
        return "HUB 还原失败：%s" % val["err"]
    return "已把键盘灯效交还给 HUB（%s）" % "+".join(val.get("steps") or [])
