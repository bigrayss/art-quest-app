"""速写格式导出里的时间（2026-10-19）。

笔画在入库时就折成了当前的字段名（`t_start_ms` → `t0_ms`，`t_end_ms` 丢掉，见
`events.canonical_stroke`），转换器却还在读 `t_start_ms` / `t_end_ms`：每一笔都读成 0，
DifferSketching 的 s_time / e_time 和 QuickDraw 的逐点时间全挤在零点上。
现在按 `events.stroke_start_ms` / `stroke_end_ms` 取；墙钟起点优先用客户端锚点
（`events.client_clock_anchor`），没有锚点的老 session 退回服务端的 `started_at`，
并在 `artquest.clock` 里写明用的是哪只钟。

Run:  python3 -m unittest tests.test_export_sketches -v
"""
import unittest
from datetime import datetime

from .env import ADMIN

from fastapi.testclient import TestClient  # noqa: E402

from artquest.main import app  # noqa: E402
from tools.export_sketches import to_differsketching, to_quickdraw  # noqa: E402

from .test_research import _strokes, _timeline  # noqa: E402

WALL0 = 1_760_000_000_000


class SketchTimes(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)

    def _session(self, with_anchor):
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                                               "canvas": {"width": 1024, "height": 704}})
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session_id"]
        st = _strokes(3)
        evs = _timeline(st)
        if with_anchor:
            evs.append({"seq": len(evs) + 1, "t_ms": 2, "type": "SYNC_MARK",
                        "payload": {"n": 0, "source": "clock", "visible": False, "wall_ms": WALL0 + 2}})
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/log", json={"strokes": st, "events": evs}).status_code, 200)
        return sid, st

    def test_each_stroke_keeps_its_own_time_on_the_client_clock(self):
        sid, st = self._session(with_anchor=True)
        d = to_differsketching(sid)
        self.assertEqual([x["s_time"] for x in d["strokes"]], [WALL0 + s["t_start_ms"] for s in st])
        self.assertEqual([x["e_time"] for x in d["strokes"]], [WALL0 + s["t_end_ms"] for s in st])
        self.assertEqual(d["artquest"]["clock"], "client_anchor")

    def test_without_an_anchor_it_falls_back_to_the_server_clock_and_says_so(self):
        sid, st = self._session(with_anchor=False)
        d = to_differsketching(sid)
        started = self.c.get(f"/api/sessions/{sid}").json()["times"]["started_at"]
        base = int(datetime.fromisoformat(started).timestamp() * 1000)
        self.assertEqual([x["s_time"] for x in d["strokes"]], [base + s["t_start_ms"] for s in st])
        self.assertEqual(d["artquest"]["clock"], "server_started_at")

    def test_quickdraw_points_carry_their_stroke_start(self):
        sid, st = self._session(with_anchor=True)
        q = to_quickdraw(sid)
        self.assertEqual([s[2][0] for s in q["drawing"]], [s["t_start_ms"] for s in st])
        self.assertEqual([s[2][-1] for s in q["drawing"]], [s["t_end_ms"] for s in st])


if __name__ == "__main__":
    unittest.main()
