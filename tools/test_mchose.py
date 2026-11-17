"""离线自检：迈从包结构 / 分片 / 校验，不碰硬件。"""
from keymole.display.vendor import mchose

GREEN = (0, 255, 0)
RED = (255, 0, 0)

payload = mchose.build_payload({"q": GREEN, "a": RED, "b": (0, 0, 255)})
assert len(payload) == 360, len(payload)
assert payload[0] == mchose.CMD_SET_LIGHT
assert payload[32:35] == bytes(GREEN), payload[32:35]
assert payload[35:38] == bytes(RED), payload[35:38]
assert payload[110:113] == bytes((0, 0, 255))
assert payload[8:11] == b"\x00\x00\x00", "未点亮的键必须是黑的"
assert payload[-28:-14] == bytes(14), "empty15 应该是 14 个 0"
assert payload[-14:-10] == bytes([0, 0, 0x5A, 0xA5])

frames = mchose.split_frames(payload)
assert len(frames[0]) == 20, len(frames[0])
total = len(frames)
assert total == 26, total
for seq, f in enumerate(frames):
    assert f[0] == mchose.REPORT_ID
    assert f[1] == mchose.CMD_SET_LIGHT
    assert f[2] == total and f[3] == seq, (f[2], f[3], total, seq)
    assert (mchose.REPORT_ID + sum(f[1:-1])) & 0xFF == f[-1], "校验和不对"
assert 0 <= frames[-1][4] <= 14, "yy 应是 0..14"

joined = b"".join(f[5:19] for f in frames)
assert joined[:len(payload) - 1] == payload[1:]
print("offline ok: payload 360 字节，%d 片，每片 20 字节" % total)
