"""陪伴与画面关联（agent 级数据计划 PR 2，2026-10-14）。

守四件事：
1. 真调模型的点击：画面存进 frames/（按内容 hash），calls.jsonl 那条的输入图指向它；click 记录里 call_id = 响应的 call_id；
   客户端笔画数和服务器当时已入库的笔画数都在。
2. 冷却期 / 离线的点击走 /assist/click：存画面和账、带 source_call_id，**不**多一条调用记录；同一张图只存一份；同一个 click_id 重放不记第二条。
3. 删掉的 session：/assist/click 404、目录不重建。
4. before/after 记录带 sha256 + n_strokes_server；导出有 assist_clicks.csv。

Run:  python3 -m unittest -v tests.test_assist_clicks
"""
import base64
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from .env import TMP as _TMP  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.main import app  # noqa: E402
from artquest.storage import SessionStore  # noqa: E402


def _png(seed=0) -> bytes:
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40 + seed, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _stroke(i):
    return {"seq": i, "stroke_id": f"s{i:05d}", "phase": "before", "tool": "pen", "color": "#000000", "size": 4,
            "opacity": 1.0, "erase": False, "pointer_type": "pen", "t0_ms": 100 * i,
            "points": [[10 + i, 10, 0, None, None, None], [40 + i, 40, 30, None, None, None]]}


class AssistClicks(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.store = SessionStore()
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": "一只猫"},
                                                 "participant": {"anon_id": "anon-clicks"}})
        self.sid = r.json()["session_id"]
        # 两笔先到服务器，第三笔还在客户端队列里（客户端说 3，服务器只见 2）
        self.c.post(f"/api/sessions/{self.sid}/log", json={"events": [], "strokes": [_stroke(1), _stroke(2)]})

    def test_a_generated_reply_is_tied_to_the_frame_the_model_saw(self):
        png = _png()
        sha = hashlib.sha256(png).hexdigest()
        r = self.c.post(f"/api/sessions/{self.sid}/assist",
                        json={"image": _url(png), "nth": 1, "click_id": "clk_a", "n_strokes": 3, "phase": "before", "elapsed_ms": 4200})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["click_id"], "clk_a")
        self.assertEqual(body["frame_sha256"], sha)
        self.assertEqual(body["n_strokes_server"], 2)
        self.assertTrue(body["call_id"].startswith("call_"))

        clicks = self.store.assist_clicks(self.sid)
        self.assertEqual(len(clicks), 1)
        k = clicks[0]
        self.assertEqual((k["click_id"], k["nth"], k["t_ms"], k["phase"]), ("clk_a", 1, 4200, "before"))
        self.assertEqual((k["cached"], k["offline"], k["deferred"]), (False, False, False))
        self.assertEqual((k["n_strokes_client"], k["n_strokes_server"], k["server_count_at"]), (3, 2, "receipt"))
        self.assertEqual(k["call_id"], body["call_id"])
        self.assertEqual(k["text"], body["text"])
        self.assertEqual(k["frame"]["sha256"], sha)
        frame = self.store.dir(self.sid) / k["frame"]["file"]
        self.assertTrue(frame.exists() and frame.parent.name == "frames")
        self.assertEqual(hashlib.sha256(frame.read_bytes()).hexdigest(), sha)   # 服务端按实际字节算的

        call = [c for c in self.store.calls(self.sid) if c["purpose"] == "assist"][0]
        self.assertEqual(call["call_id"], body["call_id"])
        self.assertEqual(call["input"]["images"], [{"sha256": sha, "file": k["frame"]["file"]}])
        self.assertEqual(call["stage"], "before")

    def test_a_cached_click_keeps_its_own_frame_and_adds_no_call(self):
        first = self.c.post(f"/api/sessions/{self.sid}/assist",
                            json={"image": _url(_png()), "nth": 1, "click_id": "clk_1", "n_strokes": 3}).json()
        n_calls = len(self.store.calls(self.sid))
        png2 = _png(seed=7)                          # 又画了几笔再点：显示的还是上一句，画面已经不同
        r = self.c.post(f"/api/sessions/{self.sid}/assist/click",
                        json={"image": _url(png2), "click_id": "clk_2", "nth": 2, "n_strokes": 5, "phase": "before",
                              "cached": True, "source_call_id": first["call_id"], "elapsed_ms": 9000})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.store.calls(self.sid)), n_calls)          # 没有新的模型/引擎执行
        clicks = self.store.assist_clicks(self.sid)
        self.assertEqual([c["click_id"] for c in clicks], ["clk_1", "clk_2"])
        k = clicks[1]
        self.assertTrue(k["cached"])
        self.assertEqual(k["source_call_id"], first["call_id"])
        self.assertIsNone(k["call_id"])
        self.assertIsNone(k["text"])
        self.assertNotEqual(k["frame"]["sha256"], clicks[0]["frame"]["sha256"])   # 两张不同的图，各存各的
        self.assertTrue((self.store.dir(self.sid) / k["frame"]["file"]).exists())
        self.assertEqual(self.store.load(self.sid)["counts"]["assist_clicks"], 2)

        # 发件箱重放同一个 click_id：原样返回，不记第二条
        r2 = self.c.post(f"/api/sessions/{self.sid}/assist/click",
                         json={"image": _url(png2), "click_id": "clk_2", "nth": 2, "cached": True,
                               "source_call_id": first["call_id"], "deferred": True})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(self.store.assist_clicks(self.sid)), 2)
        # 同一张图再来一次只存一份
        before = sorted(p.name for p in (self.store.dir(self.sid) / "frames").iterdir())
        self.c.post(f"/api/sessions/{self.sid}/assist/click",
                    json={"image": _url(png2), "click_id": "clk_3", "nth": 3, "cached": True, "source_call_id": first["call_id"]})
        after = sorted(p.name for p in (self.store.dir(self.sid) / "frames").iterdir())
        self.assertEqual(before, after)
        self.assertEqual(len(self.store.assist_clicks(self.sid)), 3)

    def test_an_offline_click_is_a_click_with_nothing_shown(self):
        r = self.c.post(f"/api/sessions/{self.sid}/assist/click",
                        json={"image": _url(_png()), "click_id": "clk_off", "nth": 1, "n_strokes": 3,
                              "cached": False, "offline": True, "deferred": True, "source_call_id": None})
        self.assertEqual(r.status_code, 200, r.text)
        k = self.store.assist_clicks(self.sid)[0]
        self.assertEqual((k["cached"], k["offline"], k["deferred"], k["source_call_id"], k["text"]),
                         (False, True, True, None, None))

    def test_the_control_arm_gets_no_click_endpoint_either(self):
        sid = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                                                 "condition": {"dialogue_mode": "none"}}).json()["session_id"]
        r = self.c.post(f"/api/sessions/{sid}/assist/click", json={"image": _url(_png()), "click_id": "x", "cached": True})
        self.assertEqual(r.status_code, 403)

    def test_a_deleted_session_does_not_grow_a_frames_dir(self):
        d = self.store.dir(self.sid)
        self.store.delete(self.sid)
        r = self.c.post(f"/api/sessions/{self.sid}/assist/click", json={"image": _url(_png()), "click_id": "late", "cached": True})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(d.exists())
        with self.assertRaises(KeyError):
            self.store.save_frame(self.sid, _png())
        self.assertFalse(d.exists())

    def test_phase_records_carry_content_hash_and_server_stroke_count(self):
        png = _png()
        self.c.post(f"/api/sessions/{self.sid}/submit",
                    json={"image": _url(png), "elapsed_ms": 60000, "phase": "before", "strokes": [_stroke(3)]})
        m = self.store.load(self.sid)
        self.assertEqual(m["before"]["sha256"], hashlib.sha256(png).hexdigest())
        self.assertEqual(m["before"]["n_strokes_server"], 3)          # submit 带来的那一笔已经入库
        self.assertEqual(m["before"]["calls"]["group_id"], [c for c in self.store.calls(self.sid)
                                                             if c["purpose"] == "score"][0]["group_id"])

    def test_export_has_assist_clicks(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools import export_dataset
        first = self.c.post(f"/api/sessions/{self.sid}/assist",
                            json={"image": _url(_png()), "nth": 1, "click_id": "clk_e1", "n_strokes": 3}).json()
        self.c.post(f"/api/sessions/{self.sid}/assist/click",
                    json={"image": _url(_png(3)), "click_id": "clk_e2", "nth": 2, "cached": True, "source_call_id": first["call_id"]})
        out = Path(tempfile.mkdtemp(prefix="artquest-export-"))
        counts = export_dataset.export(out)
        self.assertGreaterEqual(counts["assist_clicks"], 2)
        rows = [r for r in csv.DictReader((out / "assist_clicks.csv").open(encoding="utf-8")) if r["session_id"] == self.sid]
        self.assertEqual([r["click_id"] for r in rows], ["clk_e1", "clk_e2"])
        self.assertEqual(rows[0]["call_id"], first["call_id"])
        self.assertEqual(rows[1]["source_call_id"], first["call_id"])
        self.assertEqual(rows[1]["cached"], "True")
        self.assertTrue(rows[0]["frame_file"].startswith("frames/"))


if __name__ == "__main__":
    unittest.main()
