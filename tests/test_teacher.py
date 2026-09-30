# -*- coding: utf-8 -*-
"""教师端：老师注册要邀请码；只有老师（或研究员）能看全部作品、打分；打分追加不覆盖。"""
import base64
import io
import os
import unittest

from .env import ADMIN, TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

os.environ["ARTQUEST_TEACHER_CODE"] = "code-777"
# 别的测试不关心池子：每件要 99 份 = 永远评不满、谁都看得见。池子规则在 test_a_work_leaves_the_queue 里单独把 K 调到 2。
os.environ["ARTQUEST_RATINGS_PER_WORK"] = "99"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.main import app  # noqa: E402


def _png(color=(200, 40, 40)):
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((50, 50, 250, 250), fill=color, outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class TeacherSide(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _finished_session(self, name="小画家", pin="1111", revise=True):
        r = self.c.post("/api/accounts/register", json={"name": name, "pin": pin, "anon_id": "dev-" + name})
        if r.status_code == 409:
            r = self.c.post("/api/accounts/login", json={"name": name, "pin": pin, "anon_id": "dev-" + name})
        tok, acc = r.json()["token"], r.json()["account"]
        h = {"Authorization": f"Bearer {tok}"}
        r = self.c.post("/api/sessions", headers=h, json={
            "quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "一只飞鱼"},
            "participant": {"anon_id": "dev-" + name, "account_id": acc["account_id"]}})
        sid = r.json()["session_id"]
        self.c.post(f"/api/sessions/{sid}/snapshot", json={"image": _png(), "elapsed_ms": 30000, "events": []})
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 60000, "phase": "before"})
        if revise:
            self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png((40, 200, 90)), "elapsed_ms": 120000, "phase": "after"})
        else:
            self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 61000})
        return sid

    def _teacher(self, name="王老师", code="code-777"):
        r = self.c.post("/api/accounts/register", json={"name": name, "pin": "2222", "role": "teacher", "teacher_code": code})
        if r.status_code == 409:      # 数据目录跨进程复用时（ARTQUEST_DATA_DIR 指定了）名字会撞：登录就行
            r = self.c.post("/api/accounts/login", json={"name": name, "pin": "2222"})
        return r

    def test_a_teacher_needs_the_invite_code_and_a_student_cannot_enter(self):
        self.assertEqual(self._teacher("冒充", code="wrong").status_code, 403)
        r = self._teacher("李老师")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["account"]["role"], "teacher")
        teacher = {"Authorization": f"Bearer {r.json()['token']}"}
        student = self.c.post("/api/accounts/register", json={"name": "学生甲", "pin": "3333"}).json()
        self.assertEqual(student["account"]["role"], "student")
        self.assertEqual(self.c.get("/api/teacher/sessions", headers={"Authorization": f"Bearer {student['token']}"}).status_code, 403)
        self.assertEqual(self.c.get("/api/teacher/sessions").status_code, 401)
        self.assertEqual(self.c.get("/api/teacher/sessions", headers=teacher).status_code, 200)
        self.assertEqual(self.c.get("/api/teacher/sessions", headers=ADMIN).status_code, 200)

    def test_the_queue_shows_finished_work_and_grading_moves_it_to_done(self):
        sid = self._finished_session("小画家A")
        teacher = {"Authorization": f"Bearer {self._teacher('张老师').json()['token']}"}
        todo = self.c.get("/api/teacher/sessions?status=todo", headers=teacher).json()
        row = next(r for r in todo["sessions"] if r["session_id"] == sid)
        self.assertEqual(row["student"], "小画家A")
        self.assertTrue(row["revised"]); self.assertFalse(row["graded_by_me"]); self.assertEqual(row["n_snapshots"], 1)

        detail = self.c.get(f"/api/teacher/sessions/{sid}", headers=teacher).json()
        kinds = [i["kind"] for i in detail["images"]]
        self.assertEqual(kinds, ["snapshot", "before", "final"], "过程图在前，最终图最后")
        self.assertEqual(len(detail["dimensions"]), 9)
        self.assertIsNone(detail["my_rating"])
        self.assertNotIn("scores", detail, "不给老师看模型的分")

        grade = {"dims": {"imagination": 4, "color_richness": 3}, "comment": "构图很稳。",
                 "image_notes": {detail["images"][0]["key"]: "先画了轮廓", "before": "颜色还没上"}}
        r = self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=teacher, json=grade)
        self.assertEqual(r.status_code, 200, r.text)
        done = self.c.get("/api/teacher/sessions?status=done", headers=teacher).json()["sessions"]
        self.assertIn(sid, [r["session_id"] for r in done])
        todo = self.c.get("/api/teacher/sessions?status=todo", headers=teacher).json()["sessions"]
        self.assertNotIn(sid, [r["session_id"] for r in todo])
        detail = self.c.get(f"/api/teacher/sessions/{sid}", headers=teacher).json()
        self.assertEqual(detail["my_rating"]["dims"]["imagination"], 4)
        self.assertEqual(detail["my_rating"]["comment"], "构图很稳。")
        self.assertEqual(detail["my_rating"]["image_notes"]["before"], "颜色还没上")

    def test_many_snapshots_are_sampled_down_to_three_for_the_teacher(self):
        sid = self._finished_session("小画家C", revise=False)
        for ms in (45000, 50000, 55000, 58000):      # 加到 5 张快照
            self.c.post(f"/api/sessions/{sid}/snapshot", json={"image": _png(), "elapsed_ms": ms, "events": []})
        t = {"Authorization": f"Bearer {self._teacher('孙老师').json()['token']}"}
        detail = self.c.get(f"/api/teacher/sessions/{sid}", headers=t).json()
        snaps = [i for i in detail["images"] if i["kind"] == "snapshot"]
        self.assertEqual(len(snaps), 3, "老师只看开头、中间、快结束三张")
        self.assertEqual([s["elapsed_ms"] for s in snaps], [30000, 50000, 58000])
        row = next(r for r in self.c.get("/api/teacher/sessions", headers=t).json()["sessions"] if r["session_id"] == sid)
        self.assertEqual(row["n_snapshots"], 5, "服务器上全部快照都在，只是界面抽样")

    def test_two_teachers_are_two_ratings_and_bad_input_is_refused(self):
        sid = self._finished_session("小画家B", revise=False)
        t1 = {"Authorization": f"Bearer {self._teacher('赵老师').json()['token']}"}
        t2 = {"Authorization": f"Bearer {self._teacher('钱老师').json()['token']}"}
        first = self.c.get(f"/api/teacher/sessions/{sid}", headers=t1).json()["images"][0]["key"]
        self.assertEqual(self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=t1, json={"dims": {"imagination": 5}, "image_notes": {first: "一笔起头"}}).status_code, 200)
        # 有过程图就至少写一条过程短评：只写评语不行，写在任一张过程图上才行
        self.assertEqual(self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=t2, json={"comment": "只写评语"}).status_code, 422)
        snap_key = self.c.get(f"/api/teacher/sessions/{sid}", headers=t2).json()["images"][0]["key"]
        self.assertEqual(self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=t2, json={"comment": "只写评语", "image_notes": {snap_key: "先画了轮廓"}}).status_code, 200)
        detail = self.c.get(f"/api/teacher/sessions/{sid}", headers=t1).json()
        self.assertEqual(detail["n_graders"], 2)
        self.assertEqual([i["kind"] for i in detail["images"]], ["snapshot", "final"], "没改过就没有 before 那张")
        self.assertEqual(self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=t1, json={}).status_code, 422)
        self.assertEqual(self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=t1, json={"dims": {"imagination": 9}}).status_code, 422)
        self.assertEqual(self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=t1, json={"dims": {"nope": 3}}).status_code, 422)


    def test_the_rubric_reference_is_for_teachers_and_carries_all_nine_dimensions_in_both_languages(self):
        student = self.c.post("/api/accounts/register", json={"name": "学生乙", "pin": "3333"}).json()
        self.assertEqual(self.c.get("/api/teacher/rubric", headers={"Authorization": f"Bearer {student['token']}"}).status_code, 403)
        self.assertEqual(self.c.get("/api/teacher/rubric").status_code, 401)
        teacher = {"Authorization": f"Bearer {self._teacher('孙老师').json()['token']}"}
        r = self.c.get("/api/teacher/rubric", headers=teacher)
        self.assertEqual(r.status_code, 200, r.text)
        rb = r.json()
        from artquest.scoring.base import DIM_KEYS
        self.assertEqual(sorted(rb["dimensions"]), sorted(DIM_KEYS))
        self.assertEqual([k for c in rb["categories"] for k in c["dims"]], DIM_KEYS)   # 四组连起来正好是九维、同一顺序
        for k, d in rb["dimensions"].items():
            self.assertEqual([l["score"] for l in d["levels"]], [5, 4, 3, 2, 1], k)
            for l in d["levels"]:
                self.assertTrue(l["zh"] and l["en"], (k, l["score"]))
            self.assertTrue(d["criterion"]["zh"] and d["criterion"]["en"], k)
            self.assertNotIn("reference", d, "不给老师看数据集的分布，免得先入为主")
        self.assertNotIn("source", rb, "界面上不引用论文")
        self.assertTrue(rb["examples"] and all(e["comment"]["zh"] and e["comment"]["en"] for e in rb["examples"]))
        # 示范图是仓库自带的静态文件
        self.assertEqual(self.c.get(rb["examples"][0]["image"]).status_code, 200)

    def test_a_work_leaves_the_queue_once_it_has_enough_ratings(self):
        t = [self._teacher(n) for n in ("池子甲", "池子乙", "池子丙")]
        hs = [{"Authorization": f"Bearer {r.json()['token']}"} for r in t]
        self.assertEqual(self.c.post("/api/teacher/progress", headers=hs[0], json={"ratings_per_work": 1}).status_code, 401, "老师不能改")
        self.assertEqual(self.c.post("/api/teacher/progress", headers=ADMIN, json={"ratings_per_work": 2}).status_code, 200)
        try:
            a = self._finished_session("池子学生A", revise=False)
            b = self._finished_session("池子学生B", revise=False)
            todo = lambda h: [r["session_id"] for r in self.c.get("/api/teacher/sessions?status=todo", headers=h).json()["sessions"]]
            done = lambda h: [r["session_id"] for r in self.c.get("/api/teacher/sessions?status=done", headers=h).json()["sessions"]]
            for h in hs:
                self.assertTrue({a, b} <= set(todo(h)), "没评满、没评过：谁都看得见")
            key = lambda sid, h: self.c.get(f"/api/teacher/sessions/{sid}", headers=h).json()["images"][0]["key"]
            grade = lambda sid, h: self.c.post(f"/api/teacher/sessions/{sid}/grade", headers=h,
                                               json={"dims": {"imagination": 4}, "image_notes": {key(sid, h): "起头"}}).status_code
            self.assertEqual(grade(b, hs[0]), 200)
            self.assertNotIn(b, todo(hs[0])); self.assertIn(b, done(hs[0]))
            self.assertIn(b, todo(hs[1]), "别人还看得见")
            # 评得少的在前：a（0 次）排在 b（1 次）前面
            order = [sid for sid in todo(hs[1]) if sid in (a, b)]
            self.assertEqual(order, [a, b])
            self.assertEqual(grade(b, hs[1]), 200)
            self.assertNotIn(b, todo(hs[2]), "评满 2 次：从没评过的人的待评里也消失")
            self.assertIn(b, done(hs[0]), "评过的人在「已评」里还看得到")
            self.assertEqual(grade(b, hs[2]), 200, "按 id 打开照样能评，第 3 份不是坏事")
            p = self.c.get("/api/teacher/progress", headers=ADMIN).json()
            wb = next(w for w in p["works"] if w["session_id"] == b)
            self.assertEqual((wb["n_ratings"], wb["full"]), (3, True))
            self.assertEqual(next(w for w in p["works"] if w["session_id"] == a)["full"], False)
            names = {x["name"]: x["n_graded"] for x in p["teachers"]}
            self.assertEqual((names["池子甲"], names["池子乙"], names["池子丙"]), (1, 1, 1))
            # 研究员的列表带 full，全都看得到
            rows = {r["session_id"]: r for r in self.c.get("/api/teacher/sessions?status=todo", headers=ADMIN).json()["sessions"]}
            self.assertTrue(rows[b]["full"] and not rows[a]["full"])
        finally:
            self.c.post("/api/teacher/progress", headers=ADMIN, json={"ratings_per_work": 99})

class TeacherEntrance(unittest.TestCase):
    """/teacher 是同一份 app 的另一个入口，不是第二个网站。"""

    def test_the_teacher_path_serves_the_same_shell_with_no_cache(self):
        c = TestClient(app)
        for path in ("/teacher", "/teacher/"):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("view-welcome", r.text)
            self.assertIn("no-cache", r.headers.get("cache-control", ""), "外壳一律 no-cache，/teacher 也是外壳")
        self.assertEqual(c.get("/").text, c.get("/teacher").text)

if __name__ == "__main__":
    unittest.main()
