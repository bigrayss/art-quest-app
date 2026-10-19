"""纸面 session（2026-10-19）：画在纸上，app 只当会话中枢。

`condition.medium = ipad | paper`，建 session 时冻结，默认 ipad。paper 的 session 屏上没有笔画：

- 可以 0 笔结束（`POST /sessions/{id}/end`），开始、结束都在同一条时间线上；
- 作品是上传的照片或扫描件（`POST /sessions/{id}/artifacts`）：终稿必传，阶段照可选、可多张，
  每张记 sha256、拍摄时间、上传者。原图按内容 hash 存进 `artifacts/`，只追加、不改写；
  换一张终稿是**标记**旧的被取代，不删；
- QC 换一组项：有终稿图、有开始和结束、有同步标记。0 笔不算失败。

iPad session 的 QC 一项不变。

Run:  python3 -m unittest tests.test_paper_session -v
"""
import base64
import csv
import hashlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from .env import ADMIN, TMP

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from artquest import events as ev  # noqa: E402
from artquest import study as study_mod  # noqa: E402
from artquest.main import app, store  # noqa: E402
from tools.export_dataset import export  # noqa: E402

from .test_browser import _chrome_available, _free_port  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

WALL0 = 1_760_000_000_000

# 改动之前 iPad session 跑的那一组检查，原样、按顺序。paper 的改动不许动它。
IPAD_CHECKS = ["task_known", "condition_frozen", "stimulus_ready", "events_nonempty", "strokes_nonempty",
               "stroke_count_plausible", "canvas_recorded", "reference_available", "log_checksum",
               "artwork_nonblank", "final_image_saved", "times_monotonic", "duration_plausible",
               "strokes_replayable", "uploads_flushed", "log_streams_agree", "replay_matches_final"]


def png_bytes(shade=40, size=(64, 48)) -> bytes:
    img = Image.new("RGB", size, "white")
    img.paste((shade, shade, shade), (8, 8, 40, 30))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def jpeg_bytes(when="2026:12:29 10:15:00", offset="+08:00") -> bytes:
    """一张带 EXIF 拍摄时间的 JPEG，像手机拍的那样。"""
    img = Image.new("RGB", (80, 60), (200, 180, 160))
    exif = Image.Exif()
    sub = exif.get_ifd(0x8769)           # Exif IFD
    sub[0x9003] = when                   # DateTimeOriginal
    sub[0x9011] = offset                 # OffsetTimeOriginal
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def data_url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def anchor(seq=1, t_ms=3):
    return {"seq": seq, "t_ms": t_ms, "type": "SYNC_MARK",
            "payload": {"n": 0, "source": "clock", "visible": False, "wall_ms": WALL0 + t_ms}}


def mark(n, t_ms, seq, source):
    return {"seq": seq, "t_ms": t_ms, "type": "SYNC_MARK", "payload": {"n": n, "source": source, "visible": True}}


class PaperClient:
    """建 paper session、记标记、结束、上传——测试里反复要走的那几步。"""

    def __init__(self, test: unittest.TestCase):
        self.t = test
        self.c = TestClient(app, headers=ADMIN)

    def create(self, condition=None, pid="P201"):
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                "participant": {"anon_id": "anon-paper", "participant_id": pid},
                "condition": {"medium": "paper", "sync_marks": True, **(condition or {})}, "canvas": {}}
        r = self.c.post("/api/sessions", json=body)
        self.t.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def log(self, sid, events):
        r = self.c.post(f"/api/sessions/{sid}/log", json={"events": events})
        self.t.assertEqual(r.status_code, 200, r.text)

    def end(self, sid, elapsed_ms=600_000, events=None):
        return self.c.post(f"/api/sessions/{sid}/end", json={"elapsed_ms": elapsed_ms, "events": events or []})

    def upload(self, sid, kind, raw, mime="image/png", **extra):
        body = {"kind": kind, "image": data_url(raw, mime), "uploaded_by": "R01",
                "captured_at_ms": WALL0 + 590_000, "captured_at_source": "file_mtime", "t_ms": 601_000}
        body.update(extra)
        return self.c.post(f"/api/sessions/{sid}/artifacts", json=body)

    def run(self, sid, final=None, stages=1):
        """开始（锚点 + 开始闪）→ 研究员补一次 → 结束（交卷闪）→ 阶段照 → 终稿。"""
        self.log(sid, [anchor(), mark(1, 40, 2, "start"), mark(2, 300_000, 3, "researcher")])
        r = self.end(sid, events=[mark(3, 600_000, 4, "submit")])
        self.t.assertEqual(r.status_code, 200, r.text)
        for i in range(stages):
            self.t.assertEqual(self.upload(sid, "stage", png_bytes(60 + i), label=f"stage {i + 1}").status_code, 200)
        r = self.upload(sid, "final", final or jpeg_bytes(), mime="image/jpeg")
        self.t.assertEqual(r.status_code, 200, r.text)
        return r.json()


class TheCondition(unittest.TestCase):
    def setUp(self):
        self.p = PaperClient(self)

    def test_medium_defaults_to_ipad_and_is_frozen(self):
        self.assertEqual(study_mod.DEFAULT_CONDITION["medium"], "ipad")
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                "participant": {"anon_id": "anon-paper"},
                "canvas": {"width": 1024, "height": 704, "css_width": 900, "css_height": 619}}
        r = self.p.c.post("/api/sessions", json=body)
        self.assertEqual(r.json()["session"]["condition"]["medium"], "ipad")
        sid = self.p.create()
        self.assertEqual(self.p.c.get(f"/api/sessions/{sid}").json()["condition"]["medium"], "paper")

    def test_an_unknown_medium_is_refused_not_frozen(self):
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                "participant": {"anon_id": "anon-paper"}, "condition": {"medium": "Paper"}, "canvas": {}}
        self.assertEqual(self.p.c.post("/api/sessions", json=body).status_code, 422)


class Ending(unittest.TestCase):
    def setUp(self):
        self.p = PaperClient(self)

    def test_a_paper_session_ends_with_no_strokes(self):
        sid = self.p.create()
        self.p.log(sid, [anchor()])
        r = self.p.end(sid, elapsed_ms=420_000)
        self.assertEqual(r.status_code, 200, r.text)
        meta = store.load(sid)
        self.assertEqual(meta["status"], "ended")
        self.assertEqual(meta["times"]["duration_ms"], 420_000)
        self.assertTrue(meta["times"]["ended_at"])
        ends = [e for e in store.log(sid, "events").read() if e["type"] == "SESSION_END"]
        self.assertEqual(len(ends), 1)
        self.assertEqual((ends[0]["t_ms"], ends[0]["payload"]["medium"]), (420_000, "paper"))

    def test_ending_twice_is_one_end(self):
        """发件箱会重发：第二次原样返回，时间线上不多一条 SESSION_END。"""
        sid = self.p.create()
        self.assertEqual(self.p.end(sid, 1000).status_code, 200)
        self.assertEqual(self.p.end(sid, 9999).status_code, 200)
        ends = [e for e in store.log(sid, "events").read() if e["type"] == "SESSION_END"]
        self.assertEqual([e["t_ms"] for e in ends], [1000])
        self.assertEqual(store.load(sid)["times"]["duration_ms"], 1000)

    def test_an_ipad_session_cannot_be_ended_without_its_canvas(self):
        sid = self.p.create({"medium": "ipad"})
        self.assertEqual(self.p.end(sid).status_code, 409)

    def test_abandoning_a_paper_session_marks_it_instead_of_deleting_it(self):
        """iPad 上一笔没画就退出是空局，删掉；纸面 session 屏上永远 0 笔，它不是空局。"""
        sid = self.p.create()
        self.p.log(sid, [anchor()])
        r = self.p.c.post(f"/api/sessions/{sid}/abandon", json={"elapsed_ms": 5000, "reason": "wrong_task"})
        self.assertEqual(r.json()["status"], "abandoned")
        self.assertEqual(store.load(sid)["status"], "abandoned")


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.p = PaperClient(self)

    def test_each_upload_records_its_hash_capture_time_and_uploader(self):
        sid = self.p.create()
        self.p.end(sid)
        stage, final = png_bytes(90), jpeg_bytes("2026:12:29 10:15:00", "+08:00")
        a = self.p.upload(sid, "stage", stage, label="线稿").json()["artifact"]
        b = self.p.upload(sid, "final", final, mime="image/jpeg", uploaded_by="R02",
                          captured_at_ms=None, captured_at_source="").json()["artifact"]
        self.assertEqual(a["sha256"], hashlib.sha256(stage).hexdigest())
        self.assertEqual(b["sha256"], hashlib.sha256(final).hexdigest())
        # 存的是原图的字节，一个字节不改
        self.assertEqual((store.dir(sid) / a["file"]).read_bytes(), stage)
        self.assertEqual((store.dir(sid) / b["file"]).read_bytes(), final)
        self.assertEqual((a["kind"], a["uploaded_by"], a["label"]), ("stage", "R01", "线稿"))
        self.assertEqual((a["captured_at_ms"], a["captured_at_source"]), (WALL0 + 590_000, "file_mtime"))
        self.assertIsNone(a["exif_datetime_original"], "PNG 里没有 EXIF：没有就是 null")
        self.assertEqual((b["kind"], b["uploaded_by"]), ("final", "R02"))
        self.assertIsNone(b["captured_at_ms"], "客户端没报拍摄时间：存 null，不拿上传时间顶")
        self.assertEqual((b["exif_datetime_original"], b["exif_offset_time_original"]),
                         ("2026:12:29 10:15:00", "+08:00"))
        self.assertTrue(b["uploaded_at"])
        meta = store.load(sid)
        self.assertEqual([x["artifact_id"] for x in meta["artifacts"]], [a["artifact_id"], b["artifact_id"]])
        ups = [e for e in store.log(sid, "events").read() if e["type"] == "ARTIFACT_UPLOADED"]
        self.assertEqual([(e["payload"]["kind"], e["payload"]["sha256"]) for e in ups],
                         [("stage", a["sha256"]), ("final", b["sha256"])])

    def test_the_final_needs_an_ended_session_an_uploader_and_an_image(self):
        sid = self.p.create()
        self.assertEqual(self.p.upload(sid, "final", png_bytes()).status_code, 409, "先结束，再交终稿")
        self.assertEqual(self.p.upload(sid, "stage", png_bytes()).status_code, 200, "阶段照画着的时候就能传")
        self.p.end(sid)
        self.assertEqual(self.p.upload(sid, "final", png_bytes(), uploaded_by="  ").status_code, 422)
        self.assertEqual(self.p.upload(sid, "final", b"not an image").status_code, 422)
        ipad = self.p.create({"medium": "ipad"})
        self.assertEqual(self.p.upload(ipad, "stage", png_bytes()).status_code, 409)

    def test_the_same_bytes_twice_are_one_artifact(self):
        sid = self.p.create()
        self.p.end(sid)
        raw = png_bytes(33)
        a = self.p.upload(sid, "final", raw).json()["artifact"]
        b = self.p.upload(sid, "final", raw).json()["artifact"]
        self.assertEqual(a["artifact_id"], b["artifact_id"])
        self.assertEqual(len(store.load(sid)["artifacts"]), 1)
        self.assertEqual(len([e for e in store.log(sid, "events").read() if e["type"] == "ARTIFACT_UPLOADED"]), 1)

    def test_a_new_final_supersedes_the_old_one_without_deleting_it(self):
        sid = self.p.create()
        self.p.end(sid)
        old, new = png_bytes(20), jpeg_bytes()
        a = self.p.upload(sid, "final", old).json()["artifact"]
        b = self.p.upload(sid, "final", new, mime="image/jpeg").json()["artifact"]
        arts = {x["artifact_id"]: x for x in store.load(sid)["artifacts"]}
        self.assertEqual(arts[a["artifact_id"]]["superseded_by"], b["artifact_id"])
        self.assertIsNone(arts[b["artifact_id"]]["superseded_by"])
        self.assertEqual((store.dir(sid) / a["file"]).read_bytes(), old, "被取代的那张还在")
        # final 是一个「阶段」不是文件名：纸面 session 的终稿就是当前那张上传的原图
        r = self.p.c.get(f"/files/{sid}/final.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, new)
        self.assertEqual(r.headers["content-type"], "image/jpeg")


class PaperQC(unittest.TestCase):
    def setUp(self):
        self.p = PaperClient(self)

    def test_start_end_upload_questionnaire_passes_qc_and_exports_as_paper(self):
        sid = self.p.create({"questionnaire": True})
        out = self.p.run(sid, stages=1)
        qc = out["qc"]
        self.assertTrue(qc["ok"], qc["failed"])
        self.assertEqual(qc["medium"], "paper")
        names = [c["name"] for c in qc["checks"]]
        for want in ("final_artwork_uploaded", "artifacts_intact", "session_started", "session_ended",
                     "sync_marks_present", "no_canvas_strokes"):
            self.assertIn(want, names)
        for gone in ("strokes_nonempty", "strokes_replayable", "replay_matches_final", "canvas_recorded"):
            self.assertNotIn(gone, names, "0 笔不是失败，没有回放可比")
        r = self.p.c.post(f"/api/sessions/{sid}/questionnaire", json={"difficulty": 3, "confidence": 4, "t_ms": 620_000})
        self.assertEqual(r.status_code, 200)
        meta = store.load(sid)
        self.assertEqual((meta["status"], meta["lifecycle"]), ("done", "server_verified"))
        self.assertEqual(ev.unknown_types(e["type"] for e in store.log(sid, "events").read()), set())
        with tempfile.TemporaryDirectory() as tmp:
            export(Path(tmp))
            with open(Path(tmp) / "sessions.csv", encoding="utf-8") as fh:
                row = {r["session_id"]: r for r in csv.DictReader(fh)}[sid]
            with open(Path(tmp) / "artifacts.csv", encoding="utf-8") as fh:
                arts = [r for r in csv.DictReader(fh) if r["session_id"] == sid]
        self.assertEqual(row["medium"], "paper")
        self.assertEqual(row["qc_ok"], "True")
        self.assertEqual(sorted(a["kind"] for a in arts), ["final", "stage"])
        final = next(a for a in arts if a["kind"] == "final")
        self.assertEqual(final["sha256"], hashlib.sha256(jpeg_bytes()).hexdigest())
        self.assertEqual(final["uploaded_by"], "R01")

    def test_no_final_or_no_sync_marks_fails_paper_qc(self):
        sid = self.p.create()
        self.p.log(sid, [anchor(), mark(1, 40, 2, "start")])
        self.p.end(sid, events=[mark(2, 600_000, 3, "submit")])
        qc = self.p.c.post(f"/api/sessions/{sid}/qc").json()
        self.assertIn("final_artwork_uploaded", qc["failed"])
        # 没有锚点、开了 sync_marks 却一个可见标记都没有：对不上外面的钟
        bare = self.p.create()
        self.p.end(bare)
        qc = self.p.upload(bare, "final", png_bytes()).json()["qc"]
        self.assertEqual(qc["failed"], ["sync_marks_present"])

    def test_a_tampered_artifact_fails_paper_qc(self):
        sid = self.p.create()
        out = self.p.run(sid, stages=0)
        self.assertTrue(out["qc"]["ok"], out["qc"]["failed"])
        (store.dir(sid) / out["artifact"]["file"]).write_bytes(png_bytes(1))
        qc = self.p.c.post(f"/api/sessions/{sid}/qc").json()
        self.assertIn("artifacts_intact", qc["failed"])


class IPadQCUnchanged(unittest.TestCase):
    """回归护栏：这几条在改动前就是绿的，守的是「iPad session 的 QC 一项不变」。"""

    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)

    def _ipad_session(self):
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                "participant": {"anon_id": "anon-ipad"}, "condition": {"feedback_source": "none"},
                "canvas": {"width": 1024, "height": 704, "css_width": 900, "css_height": 619}}
        sid = self.c.post("/api/sessions", json=body).json()["session_id"]
        r = self.c.post(f"/api/sessions/{sid}/submit",
                        json={"image": data_url(png_bytes()), "elapsed_ms": 9000, "phase": "before"})
        self.assertEqual(r.status_code, 200, r.text)
        return sid, self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 9000}).json()["qc"]

    def test_the_ipad_battery_and_its_zero_stroke_failure_are_as_before(self):
        sid, qc = self._ipad_session()
        self.assertEqual([c["name"] for c in qc["checks"]], IPAD_CHECKS)
        self.assertNotIn("medium", qc)
        self.assertIn("strokes_nonempty", qc["failed"], "iPad 上 0 笔照旧是失败")

    def test_a_session_from_before_the_medium_condition_runs_the_ipad_battery(self):
        sid, _ = self._ipad_session()
        meta = store.load(sid)
        meta["condition"].pop("medium", None)          # 改版之前建的 session 没有这一条
        (store.dir(sid) / "session.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        qc = self.c.post(f"/api/sessions/{sid}/qc").json()
        self.assertEqual([c["name"] for c in qc["checks"]], IPAD_CHECKS)


class Vocabulary(unittest.TestCase):
    def test_artifact_uploaded_is_a_known_event(self):
        self.assertTrue(ev.is_known("ARTIFACT_UPLOADED"))


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class InTheBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn
        cls.port = _free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + "/api/config", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def _ids(self):
        req = urllib.request.Request(self.base + "/api/sessions", headers=ADMIN)
        return {r["session_id"] for r in json.load(urllib.request.urlopen(req))}

    def test_start_sync_end_upload_and_questionnaire_with_no_canvas(self):
        study = Path(TMP) / "study.json"
        study.write_text(json.dumps({"active": True, "study_id": "paper1", "tasks": ["imagine_animal"], "order": "fixed",
                                     "condition": {"medium": "paper", "sync_marks": True, "questionnaire": True,
                                                   "ui": "quiet", "feedback_source": "none"}}), encoding="utf-8")
        stages, final = [png_bytes(70), png_bytes(110)], jpeg_bytes()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                try:
                    page = browser.new_page(viewport={"width": 1180, "height": 820})
                    page.set_default_timeout(15000)
                    page.goto(self.base + "/?study=1&pid=P401")
                    page.wait_for_selector("#btn-today")
                    before = self._ids()
                    page.click("#btn-today")
                    page.click("#btn-start-draw")
                    page.wait_for_selector("#view-paper:not(.hidden)")
                    self.assertTrue(page.is_hidden("#canvas"), "纸面任务屏上没有画布")
                    page.wait_for_selector("#sync-flash:not(.hidden)")
                    self.assertEqual(page.inner_text("#sync-flash").strip(), "1")
                    page.wait_for_selector("#sync-flash.hidden", state="attached")
                    page.click("#btn-paper-sync")
                    page.wait_for_selector("#sync-flash:not(.hidden)")
                    self.assertEqual(page.inner_text("#sync-flash").strip(), "2")
                    page.wait_for_selector("#sync-flash.hidden", state="attached")
                    page.wait_for_timeout(3500)          # 比停顿门槛（3 秒）久：纸面任务不该记出停顿
                    page.click("#btn-paper-end")
                    page.wait_for_selector("#paper-upload:not(.hidden)")
                    page.fill("#paper-uploader", "R07")
                    page.set_input_files("#paper-stage-input", files=[
                        {"name": f"stage{i}.png", "mimeType": "image/png", "buffer": b} for i, b in enumerate(stages)])
                    page.wait_for_function("document.querySelectorAll('#paper-list li').length === 2")
                    self.assertTrue(page.is_disabled("#btn-paper-done"), "没有终稿不能完成")
                    page.set_input_files("#paper-final-input", files=[
                        {"name": "final.jpg", "mimeType": "image/jpeg", "buffer": final}])
                    page.wait_for_selector("#btn-paper-done:not([disabled])")
                    page.click("#btn-paper-done")
                    page.wait_for_selector("#view-survey:not(.hidden)")
                    page.click('#survey .sq[data-key="difficulty"] button[data-v="3"]')
                    page.click("#btn-survey-submit")
                    page.wait_for_selector("#paper-finish:not(.hidden)")
                    (sid,) = self._ids() - before
                    page.click("#btn-paper-next")
                    page.wait_for_selector("#view-quest:not(.hidden)")
                finally:
                    browser.close()
        finally:
            os.remove(study)
        meta = store.load(sid)
        self.assertEqual((meta["condition"]["medium"], meta["status"], meta["lifecycle"]),
                         ("paper", "done", "server_verified"))
        self.assertTrue(meta["qc"]["ok"], meta["qc"]["failed"])
        self.assertEqual(meta["canvas"].get("width", 0), 0, "没有画布就不报画布尺寸")
        arts = meta["artifacts"]
        self.assertEqual([a["kind"] for a in arts], ["stage", "stage", "final"])
        self.assertEqual([a["sha256"] for a in arts], [hashlib.sha256(b).hexdigest() for b in stages + [final]])
        self.assertEqual({a["uploaded_by"] for a in arts}, {"R07"})
        self.assertEqual(arts[2]["exif_datetime_original"], "2026:12:29 10:15:00")
        evs = store.log(sid, "events").read()
        marks = sorted((e for e in evs if e["type"] == "SYNC_MARK"), key=lambda e: e["payload"]["n"])
        self.assertEqual([(m["payload"]["n"], m["payload"]["source"]) for m in marks],
                         [(0, "clock"), (1, "start"), (2, "researcher"), (3, "submit")])
        types = [e["type"] for e in evs]
        for gone in ("STROKE_START", "STROKE_END", "PAUSE_START", "CANVAS_GEOMETRY", "COLOR_CHANGE", "MASCOT_STATE"):
            self.assertNotIn(gone, types)
        end = next(e for e in evs if e["type"] == "SESSION_END")
        self.assertEqual(end["payload"], {"medium": "paper"})
        self.assertGreaterEqual(end["t_ms"], marks[3]["t_ms"])
        self.assertIn("QUESTIONNAIRE_SUBMITTED", types)
        self.assertEqual(ev.unknown_types(types), set())


if __name__ == "__main__":
    unittest.main()
