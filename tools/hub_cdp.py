"""通过 Chrome DevTools 协议操作 MCHOSE HUB 的渲染层。

前提：用 `--remote-debugging-port=9222` 启动过 HUB（单独的 user-data-dir，
不会动到原有安装文件）。用途：把 HUB 实际发给键盘的 HID 报文抓出来。

用法：
  python -m tools.hub_cdp hook          # 装上 HID 记录钩子
  python -m tools.hub_cdp dump          # 打印已记录的报文
  python -m tools.hub_cdp eval "1+1"    # 在页面里执行一段 JS
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

import websocket

PORT = 9222


def targets():
    with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=3) as r:
        return json.loads(r.read())


def page_target():
    for t in targets():
        if t.get("type") == "page" and "index.html" in (t.get("url") or ""):
            return t
    for t in targets():
        if t.get("type") == "page":
            return t
    raise SystemExit("没有可用的 page 目标")


class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=20, suppress_origin=True)
        self.id = 0

    def call(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def eval(self, expr, await_promise=False):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise, userGesture=True)
        if "exceptionDetails" in r:
            return {"error": str(r["exceptionDetails"])[:400]}
        return r.get("result", {}).get("value")


HOOK = r"""
(() => {
  if (window.__hidHooked) return 'already';
  window.__hidHooked = true;
  window.__hidlog = [];
  const push = (kind, rid, data) => {
    try {
      const bytes = Array.from(new Uint8Array(data));
      window.__hidlog.push([Date.now(), kind, rid, bytes.length, bytes.slice(0, 64)]);
      if (window.__hidlog.length > 4000) window.__hidlog.shift();
    } catch (e) {}
  };
  for (const name of ['sendReport', 'sendFeatureReport', 'sendOutputReport']) {
    const proto = (window.HIDDevice && HIDDevice.prototype) || null;
    if (!proto || !proto[name]) continue;
    const orig = proto[name];
    proto[name] = function (rid, data) { push(name, rid, data); return orig.apply(this, arguments); };
  }
  // 输入报文也记一份
  try {
    if (window.HIDDevice) {
      const origAdd = HIDDevice.prototype.addEventListener;
      HIDDevice.prototype.addEventListener = function (ev, cb, opts) {
        if (ev === 'inputreport') {
          this.__onInput = true;
          const wrap = (e) => {
            try { push('input', e.reportId, e.data.buffer || new Uint8Array(0)); } catch (err) {}
            return cb.call(this, e);
          };
          return origAdd.call(this, ev, wrap, opts);
        }
        return origAdd.call(this, ev, cb, opts);
      };
      const origOpen = HIDDevice.prototype.open;
      HIDDevice.prototype.open = function () { window.__hidopened = (window.__hidopened || 0) + 1; return origOpen.apply(this, arguments); };
    }
  } catch (e) {}
  return 'hooked';
})()
"""


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    cmd = argv[0]
    c = CDP(page_target()["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    if cmd == "hook":
        print(c.eval(HOOK))
    elif cmd == "dump":
        log = c.eval("JSON.stringify(window.__hidlog || [])") or "[]"
        rows = json.loads(log)
        print("记录 %d 条" % len(rows))
        for ts, kind, rid, n, head in rows[:80]:
            print("  %-16s rid=0x%02X len=%3d %s" % (kind, rid or 0, n,
                  " ".join("%02X" % b for b in head[:28])))
    elif cmd == "eval":
        print(c.eval(argv[1]))
    else:
        raise SystemExit("未知命令 %s" % cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
