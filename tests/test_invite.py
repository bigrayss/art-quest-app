"""精灵的邀请：最终作品平均分过 3 分，邀请上大家的画廊（用户 2026-10-05）。

守四件事：
1. 平均分 > 3 且画前同意过分享、这一臂有那面墙 → 结束时 featured 变成 pending，by 是精灵，不是老师。
   平均分 ≤ 3、或没同意分享 → 什么都不发。
2. 邀请只是邀请：答应之前墙上没有；答应了才上墙，墙上的卡带名字和题目。
3. 谁的画谁才能答复 / 撤下：别人用自己的身份来，是 404（和不存在一样，不透露这张画在）。
4. 本人撤下之后墙上立刻没有。

Run:  python3 -m unittest -v
"""
import base64
import io
import unittest
from unittest import mock

from .env import TMP as _TMP, ADMIN  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.main import app  # noqa: E402
from artquest import main as main_mod  # noqa: E402


def _data_url():
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class _FixedScorer:
    name = "fixed"
    def __init__(self, score): self.score_v = score
    def score(self, png, quest, intent):
        return {"backend": self.name, "scale": [1, 5], "summary": "",
                "dims": {k: {"score": self.score_v, "note": ""} for k in ("imagination", "color_richness", "line_combination")}}


class BuddyInvite(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _finish(self, anon, score, *, consent=True, wall="always"):
        with mock.patch.object(main_mod, "get_scorer", lambda: _FixedScorer(score)):
            r = self.c.post("/api/sessions", json={
                "quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "一只猫"},
                "participant": {"anon_id": anon},
                "condition": {"share_consent": consent, "gallery_display": wall, "feedback_source": "none"}})
            self.assertEqual(r.status_code, 201, r.text)
            sid = r.json()["session_id"]
            r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 9000, "phase": "before"})
            self.assertEqual(r.status_code, 200, r.text)
            r = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 12000})
            self.assertEqual(r.status_code, 200, r.text)
        return sid, r.json()["session"]

    def _wall_ids(self):
        return [c["session_id"] for c in self.c.get("/api/gallery/featured?k=24").json()["examples"]]

    def test_a_good_final_artwork_gets_an_invitation_from_the_buddy_not_a_teacher(self):
        sid, session = self._finish("anon-invite-1", 4)
        fe = session.get("featured") or {}
        self.assertEqual(fe.get("state"), "pending")
        self.assertTrue(fe.get("by", "").startswith("buddy/"), fe)
        self.assertNotIn(sid, self._wall_ids(), "邀请不等于上墙：本人没答应之前墙上没有")

    def test_average_at_or_below_three_or_no_consent_means_no_invitation(self):
        _, s1 = self._finish("anon-invite-2", 3)
        self.assertIsNone(s1.get("featured"))
        _, s2 = self._finish("anon-invite-3", 5, consent=False)
        self.assertIsNone(s2.get("featured"))
        _, s3 = self._finish("anon-invite-4", 5, wall="none")
        self.assertIsNone(s3.get("featured"), "这一臂没有那面墙，就不请孩子上一面看不见的墙")

    def test_only_the_owner_can_answer_and_the_wall_shows_name_and_title(self):
        sid, _ = self._finish("anon-invite-5", 4)
        # 别人来答：和不存在一样
        r = self.c.post(f"/api/sessions/{sid}/featured?anon_id=someone-else", json={"accept": True})
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(sid, self._wall_ids())
        # 本人答应
        r = self.c.post(f"/api/sessions/{sid}/featured?anon_id=anon-invite-5", json={"accept": True})
        self.assertEqual(r.status_code, 200, r.text)
        cards = {c["session_id"]: c for c in self.c.get("/api/gallery/featured?k=24").json()["examples"]}
        self.assertIn(sid, cards)
        self.assertEqual(cards[sid]["name"], "小画家", "没有账号也没有研究代号：不露设备 id")
        self.assertTrue(cards[sid]["title"])
        self.assertTrue(cards[sid]["featured_by"].startswith("buddy/"))
        # 本人撤下
        r = self.c.post(f"/api/sessions/{sid}/featured?anon_id=anon-invite-5", json={"accept": False})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(sid, self._wall_ids())
        # 别人想撤别人的：还是 404
        sid2, _ = self._finish("anon-invite-6", 4)
        self.c.post(f"/api/sessions/{sid2}/featured?anon_id=anon-invite-6", json={"accept": True})
        r = self.c.post(f"/api/sessions/{sid2}/featured?anon_id=anon-invite-5", json={"accept": False})
        self.assertEqual(r.status_code, 404)
        self.assertIn(sid2, self._wall_ids())

    def test_researcher_code_is_the_name_when_there_is_no_account(self):
        with mock.patch.object(main_mod, "get_scorer", lambda: _FixedScorer(4)):
            r = self.c.post("/api/sessions", json={
                "quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": ""},
                "participant": {"anon_id": "anon-invite-7", "participant_id": "P-07"},
                "condition": {"share_consent": True, "gallery_display": "always", "feedback_source": "none"}})
            sid = r.json()["session_id"]
            self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 9000, "phase": "before"})
            self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 12000})
        self.c.post(f"/api/sessions/{sid}/featured?anon_id=anon-invite-7&participant_id=P-07", json={"accept": True})
        cards = {c["session_id"]: c for c in self.c.get("/api/gallery/featured?k=24").json()["examples"]}
        self.assertEqual(cards[sid]["name"], "P-07")
