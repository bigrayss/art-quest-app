# -*- coding: utf-8 -*-
"""课堂模块：一节课有课件和配套的画画任务；老师建班传课件，学生凭班级码进班交作业。"""
import os
import shutil
import unittest
from pathlib import Path

from .env import ADMIN, TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

os.environ["ARTQUEST_TEACHER_CODE"] = "code-777"

from fastapi.testclient import TestClient  # noqa: E402

from artquest import classroom  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.quests import QUESTS, QUESTS_BY_ID  # noqa: E402

from .test_teacher import _png  # noqa: E402

LESSON = "zj5a_bridge"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class Classroom(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _account(self, name, role="student"):
        body = {"name": name, "pin": "2468", "age": 11, "anon_id": "dev-" + name}
        if role == "teacher":
            body.update(role="teacher", teacher_code="code-777")
        r = self.c.post("/api/accounts/register", json=body)
        if r.status_code == 409:
            r = self.c.post("/api/accounts/login", json={"name": name, "pin": "2468", "anon_id": "dev-" + name})
        return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]

    def _class(self, teacher="桥老师", name="五（2）班"):
        t, _ = self._account(teacher, "teacher")
        r = self.c.post("/api/classroom/classes", headers=t, json={"name": name})
        self.assertEqual(r.status_code, 201, r.text)
        return t, r.json()

    def test_a_lesson_has_courseware_and_drawing_tasks_to_go_with_it(self):
        cards = self.c.get("/api/classroom/lessons").json()
        self.assertIn(LESSON, [c["id"] for c in cards])
        lesson = self.c.get(f"/api/classroom/lessons/{LESSON}").json()
        self.assertEqual(lesson["title"], "家乡的桥")
        self.assertGreaterEqual(len(lesson["slides"]), 6)
        for s in lesson["slides"]:
            self.assertTrue(s["title"] and s["lines"], s)
            for fig in s["figures"]:
                self.assertTrue(fig.startswith("<svg"), "课件的图是自己画的线稿，不是外面的图片")
        kinds = [t["kind"] for t in lesson["tasks"]]
        self.assertIn("practice", kinds)
        self.assertIn("homework", kinds)
        for t in lesson["tasks"]:
            q = t["quest"]                      # 任务库的形状：前端拿它直接开画
            self.assertEqual(q["id"], t["task_id"])
            self.assertIn("要做到", q["prompt"])
            self.assertTrue(q["rubric"])
        self.assertEqual(self.c.get("/api/classroom/lessons/nope").status_code, 404)

    def test_every_reference_lesson_comes_with_a_cover_tasks_and_a_pdf(self):
        cards = [c for c in self.c.get("/api/classroom/lessons").json() if c["builtin"] and not c["public"]]
        self.assertEqual([c["title"] for c in cards], ["家乡的桥", "皮影戏", "田园村舍", "藏书票"])
        for card in cards:
            self.assertTrue(card["cover"].startswith("<svg"), card["id"])
            lesson = self.c.get(f"/api/classroom/lessons/{card['id']}").json()
            self.assertEqual({"practice", "homework"}, {t["kind"] for t in lesson["tasks"]})
            pdf = [f for f in lesson["files"] if f["filename"].endswith(".pdf")]
            self.assertEqual(len(pdf), 1, "参考课例各配一份整份的 PDF 课件")
            r = self.c.get(pdf[0]["url"])
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content.startswith(b"%PDF"))
        # 公开课：不用班级码人人看得到；配的是仓库里的名画（公有领域），挂不到班上也不用挂
        pub = [c for c in self.c.get("/api/classroom/lessons").json() if c["public"]]
        self.assertEqual([c["title"] for c in pub], ["美术欣赏", "素描入门", "油画入门"])
        for card in pub:
            self.assertTrue(card["cover_url"].startswith("/static/classroom/img/"), card)
            lesson = self.c.get(f"/api/classroom/lessons/{card['id']}").json()
            self.assertGreaterEqual(len(lesson["tasks"]), 3)
            pics = [sl for sl in lesson["slides"] if sl.get("image_url")]
            self.assertGreaterEqual(len(pics), 4)
            for sl in pics:
                self.assertTrue(sl["credit"], sl["title"])
                self.assertEqual(self.c.get(sl["image_url"]).status_code, 200, sl["image_url"])
        t0, cls0 = self._class(teacher="公开课老师", name="五（9）班")
        r = self.c.post(f"/api/classroom/classes/{cls0['code']}/lessons", headers=t0, json={"lesson_ids": [LESSON, pub[0]["id"]]})
        self.assertEqual([l["id"] for l in r.json()["lessons"]], [LESSON])
        # 新建的班默认只挂第一节，别的课老师自己勾
        _, cls = self._class(teacher="参考课例老师", name="五（8）班")
        self.assertEqual([l["id"] for l in cls["lessons"]], [LESSON])

    def test_classroom_tasks_stay_off_the_map(self):
        """课堂任务能建 session，但不在地图、选题、研究协议遍历的那张表里。"""
        ids = [classroom.task_id(LESSON, t["key"]) for t in classroom.LESSONS_BY_ID[LESSON]["tasks"]]
        for tid in ids:
            self.assertIn(tid, QUESTS_BY_ID)
        self.assertFalse(set(ids) & {q["id"] for q in QUESTS})
        self.assertFalse(set(ids) & {q["id"] for q in self.c.get("/api/quests").json()})

    def test_only_a_teacher_opens_a_class_and_the_code_lets_students_in(self):
        s, _ = self._account("课堂学生乙")
        self.assertEqual(self.c.post("/api/classroom/classes", headers=s, json={"name": "x"}).status_code, 403)
        self.assertEqual(self.c.post("/api/classroom/classes", json={"name": "x"}).status_code, 401)
        t, cls = self._class()
        code = cls["code"]
        self.assertRegex(code, r"^[A-HJ-KM-NP-Z2-9]{6}$")          # 没有 0/O/1/I/L
        self.assertEqual(self.c.post("/api/classroom/classes", headers=t, json={"name": "  "}).status_code, 422)

        # 抄在黑板上的码：小写、带空格也认
        r = self.c.post(f"/api/classroom/classes/{code.lower()}/join", headers=s, json={"anon_id": "dev-课堂学生乙"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], "五（2）班")
        self.assertEqual([l["id"] for l in r.json()["lessons"]], [LESSON])
        self.assertNotIn("members", r.json(), "学生看不到名单")
        self.c.post(f"/api/classroom/classes/{code}/join", headers=s, json={"anon_id": "dev-课堂学生乙"})   # 进两次算一次
        self.c.post(f"/api/classroom/classes/{code}/join", json={"anon_id": "dev-guest", "name": "没登录的"})
        self.assertEqual(self.c.post("/api/classroom/classes/ZZZZZZ/join", json={"anon_id": "d"}).status_code, 404)

        mine = self.c.get("/api/classroom/classes", headers=t).json()["classes"]
        self.assertEqual([(c["code"], c["n_members"]) for c in mine if c["code"] == code], [(code, 2)])
        other, _ = self._account("课堂别的老师", "teacher")
        self.assertNotIn(code, [c["code"] for c in self.c.get("/api/classroom/classes", headers=other).json()["classes"]])
        self.assertEqual(self.c.get(f"/api/classroom/classes/{code}/work", headers=other).status_code, 403)
        self.assertEqual(self.c.get(f"/api/classroom/classes/{code}/work", headers=ADMIN).status_code, 200)

    def test_a_teacher_uploads_courseware_and_the_class_can_open_it(self):
        t, cls = self._class(name="传课件的班")
        code = cls["code"]
        up = f"/api/classroom/classes/{code}/courseware"
        r = self.c.post(up, headers=t, params={"filename": "家乡的桥.pdf", "lesson_id": LESSON}, content=PDF)
        self.assertEqual(r.status_code, 201, r.text)
        row = r.json()
        self.assertTrue(row["viewable"])
        got = self.c.get(row["url"])                                   # 学生不带令牌也能翻：有班级码就行
        self.assertEqual(got.content, PDF)
        self.assertEqual(got.headers["content-type"], "application/pdf")
        self.assertTrue(got.headers["content-disposition"].startswith("inline"))

        r = self.c.post(up, headers=t, params={"filename": "讲稿.pptx"}, content=b"PK\x03\x04fake")
        self.assertFalse(r.json()["viewable"])
        self.assertTrue(self.c.get(r.json()["url"]).headers["content-disposition"].startswith("attachment"))

        self.assertEqual(self.c.post(up, headers=t, params={"filename": "脚本.html"}, content=b"<script>").status_code, 422)
        self.assertEqual(self.c.post(up, headers=t, params={"filename": "空.pdf"}, content=b"").status_code, 422)
        self.assertEqual(self.c.post(up, headers=t, params={"filename": "../../etc/x.pdf"}, content=PDF).json()["filename"], "x.pdf")
        s, _ = self._account("课堂学生丙")
        self.assertEqual(self.c.post(up, headers=s, params={"filename": "a.pdf"}, content=PDF).status_code, 403)

        names = [u["filename"] for u in self.c.get(f"/api/classroom/classes/{code}").json()["uploads"]]
        self.assertEqual(names, ["家乡的桥.pdf", "讲稿.pptx", "x.pdf"])
        self.assertEqual(self.c.delete(row["url"], headers=s).status_code, 403)
        self.assertEqual(self.c.delete(row["url"], headers=t).status_code, 200)
        self.assertEqual(self.c.get(row["url"]).status_code, 404)

    def test_homework_is_an_ordinary_drawing_that_says_which_class_it_was_for(self):
        t, cls = self._class(name="交作业的班")
        code = cls["code"]
        s, acc = self._account("课堂学生丁")
        tid = classroom.task_id(LESSON, "h1")
        r = self.c.post("/api/sessions", headers=s, json={
            "quest_id": tid, "intent": {"emotion": "", "text": ""},
            "participant": {"anon_id": "dev-课堂学生丁", "account_id": acc["account_id"]},
            # 哪节课、练习还是作业由任务说了算：客户端乱写的不算
            "routing": {"classroom": {"class_code": code.lower(), "lesson_id": "made-up", "task_kind": "practice"}}})
        self.assertEqual(r.status_code, 201, r.text[:300])
        sid = r.json()["session_id"]
        self.c.post(f"/api/sessions/{sid}/submit", headers=s, json={"image": _png(), "elapsed_ms": 60000, "phase": "before"})
        self.c.post(f"/api/sessions/{sid}/finalize", headers=s, json={"elapsed_ms": 62000})

        meta = self.c.get(f"/api/sessions/{sid}", headers=ADMIN).json()
        self.assertEqual(meta["routing"]["classroom"],
                         {"lesson_id": LESSON, "task_kind": "homework", "task_key": "h1", "class_code": code})
        self.assertEqual(meta["task"]["title"], "我家乡的桥")
        self.assertEqual(meta["status"], "done")

        # 没进班、自己点开课件画的：照样是课堂任务，班级码是空的
        r = self.c.post("/api/sessions", headers=s, json={
            "quest_id": classroom.task_id(LESSON, "p1"), "intent": {"emotion": "", "text": ""},
            "participant": {"anon_id": "dev-课堂学生丁", "account_id": acc["account_id"]},
            "routing": {"classroom": {"class_code": "NOSUCH"}}})
        loose = self.c.get(f"/api/sessions/{r.json()['session_id']}", headers=ADMIN).json()
        self.assertEqual(loose["routing"]["classroom"]["class_code"], "")
        self.assertEqual(loose["routing"]["classroom"]["task_kind"], "practice")

        work = self.c.get(f"/api/classroom/classes/{code}/work", headers=t).json()["work"]
        self.assertEqual([(w["session_id"], w["student"], w["task_kind"], w["status"]) for w in work],
                         [(sid, "课堂学生丁", "homework", "done")])
        self.assertTrue(work[0]["image"])
        # 画完的作业进了老师平时评分的那个池子
        pool = self.c.get("/api/teacher/sessions", headers=t).json()["sessions"]
        self.assertIn(sid, [p["session_id"] for p in pool])

        # 平时在地图上画的不带课堂标签
        r = self.c.post("/api/sessions", headers=s, json={
            "quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
            "participant": {"anon_id": "dev-课堂学生丁", "account_id": acc["account_id"]},
            "routing": {"classroom": {"class_code": code}}})
        plain = self.c.get(f"/api/sessions/{r.json()['session_id']}", headers=ADMIN).json()
        self.assertNotIn("classroom", plain["routing"])


class TeacherWritesALesson(unittest.TestCase):
    """课由老师录入：从空白写，或者把样板课复制一份来改；挂到班上，学生凭班级码看到。"""

    def setUp(self):
        self.c = TestClient(app)
        self.h = Classroom._account(self, "录课的老师", "teacher")[0]

    def _new(self, **body):
        r = self.c.post("/api/classroom/lessons", headers=self.h, json=body)
        self.assertEqual(r.status_code, 201, r.text[:300])
        return r.json()

    def test_a_lesson_written_from_scratch_gets_pages_and_tasks(self):
        lesson = self._new()
        lid = lesson["id"]
        r = self.c.put(f"/api/classroom/lessons/{lid}", headers=self.h, json={
            "title": "线的旅行", "subject": "美术", "minutes": 35, "summary": "认识线条",
            "slides": [{"title": "线会走路", "lines": ["直线", "", "曲线"], "ask": "你见过什么线？"},
                       {"title": "", "lines": []}],                                     # 空的一页不留
            "tasks": [{"kind": "practice", "title": "十种线", "instruction": "画出十种不一样的线。", "minutes": 8},
                      {"kind": "homework", "title": "线的画", "instruction": "只用线画一幅画。", "requirements": "至少三种线", "optional": True},
                      {"title": "", "instruction": ""}]})                               # 空的任务不留
        self.assertEqual(r.status_code, 200, r.text[:300])
        got = r.json()
        self.assertEqual((got["title"], got["minutes"], got["builtin"]), ("线的旅行", 35, False))
        self.assertEqual([(s["title"], s["lines"]) for s in got["slides"]], [("线会走路", ["直线", "曲线"])])
        self.assertEqual([(t["key"], t["kind"], t["optional"]) for t in got["tasks"]], [("t1", "practice", False), ("t2", "homework", True)])
        self.assertIn("要做到：至少三种线", got["tasks"][1]["quest"]["prompt"])
        self.assertNotIn("要做到", got["tasks"][0]["quest"]["prompt"])

        # 改一次：留着的任务 key 不变（已经交上来的画靠它认题），新加的拿新 key，删掉的撤下
        t1 = dict(got["tasks"][0], title="十二种线")
        r = self.c.put(f"/api/classroom/lessons/{lid}", headers=self.h, json=dict(got, tasks=[
            {"title": "新任务", "instruction": "画一条最长的线。"}, t1]))
        self.assertEqual([(t["key"], t["title"]) for t in r.json()["tasks"]], [("t3", "新任务"), ("t1", "十二种线")])
        self.assertIn(f"CL_{lid}_t1", QUESTS_BY_ID)
        self.assertNotIn(f"CL_{lid}_t2", QUESTS_BY_ID)
        self.assertEqual(QUESTS_BY_ID[f"CL_{lid}_t1"]["title"], "十二种线")

        self.assertEqual(self.c.put(f"/api/classroom/lessons/{lid}", headers=self.h, json={"title": " "}).status_code, 422)
        self.assertEqual(self.c.put(f"/api/classroom/lessons/{lid}", headers=self.h,
                                    json={"title": "x", "tasks": [{"title": "只有题目"}]}).status_code, 422)

    def test_only_its_author_changes_a_lesson_and_the_sample_is_copied_not_edited(self):
        lid = self._new()["id"]
        other = Classroom._account(self, "路过的老师", "teacher")[0]
        student = Classroom._account(self, "课堂学生戊")[0]
        for who, code in ((other, 403), (student, 403), ({}, 401)):
            self.assertEqual(self.c.put(f"/api/classroom/lessons/{lid}", headers=who, json={"title": "抢"}).status_code, code)
            self.assertEqual(self.c.delete(f"/api/classroom/lessons/{lid}", headers=who).status_code, code)
        self.assertEqual(self.c.post("/api/classroom/lessons", headers=student, json={}).status_code, 403)
        self.assertEqual(self.c.put(f"/api/classroom/lessons/{LESSON}", headers=self.h, json={"title": "改样板"}).status_code, 403)
        self.assertEqual(self.c.post("/api/classroom/lessons", headers=other, json={"copy_of": lid}).status_code, 404)   # 别人的课不能复制

        copy = self._new(copy_of=LESSON)
        self.assertNotEqual(copy["id"], LESSON)
        self.assertEqual((copy["title"], len(copy["slides"]), len(copy["tasks"])), ("家乡的桥", 8, 4))
        self.assertEqual(len(copy["slides"][2]["figures"]), 4, "样板课的示意图跟着复制过来")
        # 原样存回去，示意图还在
        saved = self.c.put(f"/api/classroom/lessons/{copy['id']}", headers=self.h, json=dict(copy, title="我们这儿的桥")).json()
        self.assertEqual(len(saved["slides"][2]["figures"]), 4)
        self.assertEqual(self.c.get(f"/api/classroom/lessons/{LESSON}").json()["title"], "家乡的桥")   # 样板没动

        mine = [l["id"] for l in self.c.get("/api/classroom/lessons", headers=self.h).json()]
        self.assertTrue({LESSON, lid, copy["id"]} <= set(mine))
        self.assertNotIn(lid, [l["id"] for l in self.c.get("/api/classroom/lessons", headers=other).json()])
        self.assertEqual([l["id"] for l in self.c.get("/api/classroom/lessons").json()], [l["id"] for l in classroom.LESSONS])

    def test_a_page_can_carry_a_picture_and_a_lesson_an_attachment(self):
        lid = self._new()["id"]
        up = f"/api/classroom/lessons/{lid}/files"
        png = __import__("base64").b64decode(_png().split(",", 1)[1])
        img = self.c.post(up, headers=self.h, params={"filename": "桥.png"}, content=png).json()
        pdf = self.c.post(up, headers=self.h, params={"filename": "讲稿.pdf"}, content=PDF).json()
        self.assertTrue(img["image"])
        self.assertEqual(self.c.post(up, headers=self.h, params={"filename": "x.exe"}, content=b"MZ").status_code, 422)
        got = self.c.put(f"/api/classroom/lessons/{lid}", headers=self.h, json={
            "title": "带图的课", "slides": [{"title": "看图", "lines": ["这是一座桥"], "image": img["id"]},
                                         {"title": "不能拿 PDF 当配图", "image": pdf["id"]},
                                         {"title": "乱写的图", "image": "lf-nope"}]}).json()
        self.assertEqual(got["slides"][0]["image_url"], img["url"])
        self.assertNotIn("image_url", got["slides"][1])
        self.assertNotIn("image_url", got["slides"][2])
        self.assertEqual([f["filename"] for f in got["files"]], ["讲稿.pdf"], "没被当配图用的才是附件")
        self.assertEqual(self.c.get(img["url"]).content, png)                              # 学生不带令牌也看得到图
        self.assertEqual(self.c.delete(img["url"], headers=self.h).status_code, 200)
        self.assertNotIn("image_url", self.c.get(f"/api/classroom/lessons/{lid}").json()["slides"][0])

    def test_the_class_code_shows_the_lessons_the_teacher_picked(self):
        lid = self._new()["id"]
        self.c.put(f"/api/classroom/lessons/{lid}", headers=self.h, json={
            "title": "我录的课", "tasks": [{"title": "试一试", "instruction": "画一个圆。"}]})
        code = self.c.post("/api/classroom/classes", headers=self.h, json={"name": "选课的班"}).json()["code"]
        other = Classroom._account(self, "路过的老师", "teacher")[0]
        theirs = self.c.post("/api/classroom/lessons", headers=other, json={}).json()["id"]
        self.assertEqual(self.c.post(f"/api/classroom/classes/{code}/lessons", headers=other, json={"lesson_ids": [lid]}).status_code, 403)
        r = self.c.post(f"/api/classroom/classes/{code}/lessons", headers=self.h, json={"lesson_ids": [lid, theirs, "nope", lid]})
        self.assertEqual([l["id"] for l in r.json()["lessons"]], [lid], "别人的课、不存在的课挂不上")
        self.assertEqual([l["title"] for l in self.c.get(f"/api/classroom/classes/{code}").json()["lessons"]], ["我录的课"])

        # 学生画老师录的任务：和样板课一样是一条普通的 session
        s, acc = Classroom._account(self, "课堂学生己")
        r = self.c.post("/api/sessions", headers=s, json={
            "quest_id": f"CL_{lid}_t1", "intent": {"emotion": "", "text": ""},
            "participant": {"anon_id": "dev-课堂学生己", "account_id": acc["account_id"]},
            "routing": {"classroom": {"class_code": code}}})
        self.assertEqual(r.status_code, 201, r.text[:300])
        meta = self.c.get(f"/api/sessions/{r.json()['session_id']}", headers=ADMIN).json()
        self.assertEqual(meta["routing"]["classroom"], {"lesson_id": lid, "task_kind": "practice", "task_key": "t1", "class_code": code})
        self.assertEqual(meta["task"]["instruction"], "画一个圆。")

        # 课删了：班里不再有它，新的画开不出来，已经画的那张还在、题面还在
        self.assertEqual(self.c.delete(f"/api/classroom/lessons/{lid}", headers=self.h).status_code, 200)
        self.assertEqual(self.c.get(f"/api/classroom/classes/{code}").json()["lessons"], [])
        self.assertEqual(self.c.get(f"/api/classroom/lessons/{lid}").status_code, 404)
        again = self.c.get(f"/api/sessions/{r.json()['session_id']}", headers=ADMIN).json()
        self.assertEqual(again["task"]["title"], "试一试")


SHOTS = os.environ.get("ARTQUEST_SHOTS")     # 调试时指一个目录，各页存一张截图


class ClassroomInTheBrowser(unittest.TestCase):
    """学生的一整节课：进班 → 翻课件 → 画课堂练习 → 交上去；老师那边看得到。"""

    @classmethod
    def setUpClass(cls):
        import threading
        import time
        import urllib.request

        import uvicorn

        from . import test_browser as tb
        cls.tb = tb
        cls.port = tb._free_port()
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

    def test_a_student_takes_the_lesson_and_the_teacher_sees_the_drawing(self):
        from playwright.sync_api import sync_playwright

        c = TestClient(app)
        reg = c.post("/api/accounts/register", json={"name": "浏览器里的老师", "pin": "2468", "role": "teacher", "teacher_code": "code-777"})
        if reg.status_code == 409:
            reg = c.post("/api/accounts/login", json={"name": "浏览器里的老师", "pin": "2468"})
        t = {"Authorization": f"Bearer {reg.json()['token']}"}
        code = c.post("/api/classroom/classes", headers=t, json={"name": "五（3）班"}).json()["code"]
        c.post(f"/api/classroom/classes/{code}/courseware", headers=t, params={"filename": "老师的讲稿.pdf", "lesson_id": LESSON}, content=PDF)

        errors = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_default_timeout(15000)
            page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")
            page.goto(self.base)
            page.wait_for_selector("#view-world:not(.hidden)", timeout=8000)
            page.click("#btn-enter-world")
            page.wait_for_selector("#quest-grid .quest-card")

            page.click('.tab[data-tab="class"]')
            page.wait_for_selector("#view-class:not(.hidden) #cl-code")
            # 没输码也有公开课
            self.assertEqual(page.eval_on_selector_all("#cl-public .cl-lesson b", "e=>e.map(x=>x.textContent)"), ["美术欣赏", "素描入门", "油画入门"])
            if SHOTS:
                page.wait_for_timeout(600)
                page.screenshot(path=SHOTS + "/student_home.png", full_page=True)
            page.fill("#cl-code", "nosuch")
            page.click("#cl-join-go")
            page.wait_for_selector("#cl-msg:not(.hidden)")              # 码不对：说一句，不进班
            page.fill("#cl-code", code.lower())
            page.click("#cl-join-go")
            # 加一个码，那个班的课就加进「我的课堂」，和公开课一样是卡片；没有「退出班级」，输码栏还在，可以再加别的班
            page.wait_for_selector("#cl-mycls .cl-lesson")
            self.assertIn("五（3）班", page.inner_text("#cl-msg"))
            self.assertEqual(page.eval_on_selector_all("#cl-leave, .cl-mine", "e=>e.length"), 0)
            self.assertTrue(page.is_visible("#cl-code"))
            self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('artquest.classes'))"), [code])
            # 再加一个班的码：两个班的课都在
            code2 = c.post("/api/classroom/classes", headers=t, json={"name": "美术社团", "lesson_ids": ["zj5a_shadow"]}).json()["code"]
            page.fill("#cl-code", code2)
            page.click("#cl-join-go")
            page.wait_for_selector('#cl-mycls .cl-lesson[data-lesson="zj5a_shadow"]')
            self.assertEqual(page.eval_on_selector_all("#cl-mycls .cl-lesson b", "e=>e.map(x=>x.textContent)"), ["家乡的桥", "皮影戏"])
            if SHOTS:
                page.wait_for_timeout(400)
                page.screenshot(path=SHOTS + "/student_home2.png", full_page=True)

            page.click('.cl-lesson[data-lesson="%s"]' % LESSON)
            page.wait_for_selector("#class-lesson:not(.hidden) #cl-slide h2")
            self.assertEqual(page.inner_text("#cl-page"), "1 / 8")
            self.assertFalse(page.is_visible("#cl-lesson-note"), "「请对照课本」那句只给老师看")
            titles = [page.inner_text("#cl-slide h2")]
            page.click("#cl-next")
            page.keyboard.press("ArrowRight")                            # 键盘也能翻
            titles.append(page.inner_text("#cl-slide h2"))
            self.assertEqual(titles, ["家乡的桥", "桥有哪几种样子"])
            self.assertEqual(page.eval_on_selector_all("#cl-slide .cl-figs svg", "e=>e.length"), 4)
            # 图要画在卡片里面，不能溢出去
            self.assertTrue(page.evaluate("""() => { const s = document.querySelector('#cl-stage').getBoundingClientRect();
                return [...document.querySelectorAll('#cl-slide svg')].every(v => { const r = v.getBoundingClientRect();
                    return r.width > 60 && r.left >= s.left && r.right <= s.right + 1; }) }"""))
            if SHOTS:
                page.screenshot(path=SHOTS + "/lesson.png", full_page=True)
            self.assertIn("老师的讲稿.pdf", page.inner_text("#cl-lesson-files"))
            self.assertNotIn("课件.pdf", page.inner_text("#cl-lesson-files"), "参考课例那份整份 PDF 只给老师")
            # 课件没看完：任务还没出来。翻到最后一页：提醒一句，任务出来，同时放进「任务」
            self.assertEqual(page.eval_on_selector_all("#cl-lesson-tasks .cl-task", "e=>e.length"), 0)
            self.assertTrue(page.is_visible(".cl-locked"))
            for _ in range(6):
                page.keyboard.press("ArrowRight")
            self.assertEqual(page.inner_text("#cl-page"), "8 / 8")
            page.wait_for_selector("#cl-lesson-done:not(.hidden)")
            self.assertIn("4", page.inner_text("#cl-lesson-done"))
            self.assertEqual(page.eval_on_selector_all("#cl-lesson-tasks .cl-task", "e=>e.length"), 4)
            self.assertTrue(page.evaluate("document.querySelector('.tab[data-tab=\"map\"]').classList.contains('has-new')"))
            if SHOTS:
                page.screenshot(path=SHOTS + "/lesson_done.png", full_page=True)

            page.click('[data-task="CL_%s_p1"]' % LESSON)
            page.wait_for_selector("#view-draw:not(.hidden)")
            self.assertIn("桥的样子", page.inner_text("#draw-quest-card"))
            screen_of, drag, stroke_from = self.tb.ZoomKeepsStrokesInCanvasSpace._canvas_tools(page)
            for i in range(4):
                stroke_from(200 + i * 120, 300, 90, 60 if i % 2 else -60)
            page.click("#btn-submit")
            page.wait_for_selector("#view-result:not(.hidden)")
            page.click("#btn-skip-revise")
            page.wait_for_selector("#view-final:not(.hidden)", timeout=20000)

            self.assertEqual(page.inner_text("#btn-again"), "回到课堂")
            page.click("#btn-again")                                     # 回到这节课，这道题标了「画过了」
            page.wait_for_selector("#class-lesson:not(.hidden) #cl-lesson-tasks .cl-tag.ok")
            self.assertEqual(page.eval_on_selector_all("#cl-lesson-tasks .cl-tag.ok", "e=>e.length"), 1)

            # 「任务」页顶上细细一条三栏：日常任务 / 课程任务 / 已完成。刚看完课件过来，落在「课程任务」
            page.click('.tab[data-tab="map"]')
            page.wait_for_selector("#class-tasks:not(.hidden) .ct-row")
            self.assertEqual(page.eval_on_selector_all("#task-tabs button", "e=>e.map(x=>x.textContent)"), ["日常任务", "课程任务3", "已完成1"])
            self.assertEqual(page.get_attribute("#task-tabs button.on", "data-pane"), "class")
            titles = page.eval_on_selector_all("#class-tasks .ct-row b", "e=>e.map(x=>x.textContent)")
            self.assertEqual(titles, ["家乡的桥 · 一座有远近的桥", "家乡的桥 · 我家乡的桥", "家乡的桥 · 未来的桥"])
            self.assertFalse(page.is_visible("#quest-grid"), "课程任务这一栏里没有地图")
            self.assertFalse(page.evaluate("document.querySelector('.tab[data-tab=\"map\"]').classList.contains('has-new')"))
            if SHOTS:
                page.wait_for_timeout(500)
                page.screenshot(path=SHOTS + "/map_tasks.png", full_page=True)
            page.click('#task-tabs [data-pane="done"]')                  # 画过的在「已完成」
            self.assertEqual(page.eval_on_selector_all("#class-tasks .ct-row b", "e=>e.map(x=>x.textContent)"), ["家乡的桥 · 桥的样子"])
            page.click('#task-tabs [data-pane="daily"]')                 # 「日常任务」就是原来那张地图
            page.wait_for_selector("#quest-grid .quest-card")
            self.assertFalse(page.is_visible("#class-tasks"))
            if SHOTS:
                page.wait_for_timeout(500)
                page.screenshot(path=SHOTS + "/map_daily.png", full_page=True)
            page.click('#task-tabs [data-pane="class"]')
            page.click("#class-tasks .ct-row")
            page.wait_for_selector("#view-draw:not(.hidden)")
            self.assertIn("一座有远近的桥", page.inner_text("#draw-quest-card"))

            # 老师登录进来：课堂页上有这个班、有交上来的那张画
            tpage = browser.new_context(viewport={"width": 1280, "height": 860}).new_page()
            tpage.on("pageerror", lambda e: errors.append(str(e)))
            tpage.set_default_timeout(15000)
            # 老师用另一个浏览器环境（自己的 localStorage），像在讲台那台电脑上
            tpage.add_init_script("localStorage.setItem('artquest.token', %r); localStorage.setItem('artquest.tour/2','1')" % reg.json()["token"])
            tpage.goto(self.base + "/teacher")
            tpage.wait_for_selector("body.teacher")
            tpage.click('.tab[data-tab="class"]')
            # 老师的课堂页两个分页：课程库（所有的课）、我的班级
            tpage.wait_for_selector("#cl-lessons .cl-lesson-wrap")
            self.assertEqual(tpage.eval_on_selector_all("#cl-lessons .cl-lesson b", "e=>e.map(x=>x.textContent)"),
                             ["美术欣赏", "素描入门", "油画入门", "家乡的桥", "皮影戏", "田园村舍", "藏书票"])
            self.assertTrue(tpage.is_visible("#cl-up-lesson"))
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/library.png", full_page=True)
            tpage.click('[data-cltab="classes"]')
            tpage.click('.cl-class[data-code="%s"]' % code)             # 这位老师现在有两个班，点开学生交了画的那个
            tpage.wait_for_selector('.cl-class.on[data-code="%s"]' % code)
            self.assertIn(code, tpage.inner_text(".cl-class.on"))
            tpage.wait_for_selector(".cl-piece img")
            self.assertIn("课堂练习", tpage.inner_text(".cl-piece"))
            self.assertIn("老师的讲稿.pdf", tpage.inner_text("#cl-files"))
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/teacher.png", full_page=True)
            tpage.click('[data-cltab="library"]')
            tpage.click('.cl-lesson[data-lesson="%s"]' % LESSON)
            tpage.wait_for_selector("#class-lesson:not(.hidden) #cl-slide h2")
            self.assertTrue(tpage.is_visible("#cl-lesson-note"))
            self.assertEqual(tpage.eval_on_selector_all("#cl-lesson-tasks [data-task]", "e=>e.length"), 0, "老师这边没有「开始画」")
            browser.close()

        self.assertEqual(errors, [])
        work = c.get(f"/api/classroom/classes/{code}/work", headers=t).json()
        self.assertEqual([(w["task_kind"], w["task_key"], w["status"]) for w in work["work"]], [("practice", "p2", "drawing"), ("practice", "p1", "done")],
                             "从「任务」页开画的那张也带着班级码")
        self.assertEqual(len(work["members"]), 1)


    def test_opening_the_class_tab_right_after_launch_is_not_pulled_back_to_the_cover(self):
        """启动时封面要等服务器（彩点长到哪了）。等的这一下人已经点去了「课堂」，回来不能把他拽回封面。"""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_context(viewport={"width": 1280, "height": 860}).new_page()
            page.set_default_timeout(30000)
            page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")

            # 慢网：封面要的那条请求晚一秒多才发出去（本机太快，那个窗口撞不上）
            page.add_init_script("""const f = window.fetch; window.fetch = (u, o) => !String(u).includes('/growth?') ? f(u, o)
                : (window.__asked = true, new Promise(r => setTimeout(r, 1200)).then(() => f(u, o)));""")
            page.goto(self.base)
            # 等到启动流程**已经停在这条请求上**再点：它回来之后就是 show("world")
            page.wait_for_function("window.__asked === true")
            page.click('.tab[data-tab="class"]')
            page.wait_for_selector("#cl-public .cl-lesson")
            page.wait_for_timeout(2500)
            self.assertTrue(page.is_visible("#view-class"), "被拽回封面了")
            self.assertTrue(page.is_visible("#cl-public .cl-lesson"))
            browser.close()

    @unittest.skipUnless(shutil.which("soffice") or shutil.which("libreoffice"), "这台机器没有 LibreOffice")
    def test_a_ppt_uploaded_by_the_teacher_plays_slide_by_slide_on_the_page(self):
        """老师传 PPT：服务器转一份放映用的 PDF，页面上一页一页放，不用下载。传 PDF 是另一个入口，往下滚。"""
        from playwright.sync_api import sync_playwright

        c = TestClient(app)
        reg = c.post("/api/accounts/register", json={"name": "传 PPT 的老师", "pin": "2468", "role": "teacher", "teacher_code": "code-777"})
        if reg.status_code == 409:
            reg = c.post("/api/accounts/login", json={"name": "传 PPT 的老师", "pin": "2468"})
        pptx = (Path(__file__).parent / "two_slides.pptx").read_bytes()
        old = os.environ.get("ARTQUEST_SOFFICE")
        os.environ["ARTQUEST_SOFFICE"] = ""              # 测试环境默认关着转换，这一条打开
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.set_default_timeout(60000)
                page.add_init_script("localStorage.setItem('artquest.token', %r); localStorage.setItem('artquest.tour/2','1')" % reg.json()["token"])
                page.goto(self.base + "/teacher")
                page.wait_for_selector("body.teacher")
                page.click('.tab[data-tab="class"]')
                page.wait_for_selector("#cl-up-ppt-btn")
                self.assertEqual(page.get_attribute("#cl-up-file", "accept"), ".pdf")
                self.assertEqual(page.get_attribute("#cl-up-ppt", "accept"), ".ppt,.pptx")
                page.set_input_files("#cl-up-ppt", {"name": "色彩的冷暖.pptx", "buffer": pptx,
                                                    "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"})
                page.wait_for_selector("#class-edit:not(.hidden) #ed-title")
                self.assertEqual(page.input_value("#ed-title"), "色彩的冷暖")
                self.assertIn("放映", page.inner_text("#ed-files"))
                page.click("#ed-back")
                card = '.cl-lesson-wrap:has-text("色彩的冷暖")'
                page.click(card + " .cl-lesson")
                page.wait_for_selector("#class-lesson:not(.hidden) .cl-deck canvas.cl-pdfpage.ready")
                self.assertEqual(page.inner_text(".cl-deck-n"), "1 / 2")
                page.keyboard.press("ArrowRight")                        # 键盘也能翻
                page.wait_for_function("document.querySelector('.cl-deck-n').textContent === '2 / 2'")
                self.assertTrue(page.is_disabled('.cl-deck [data-d="1"]'))
                if SHOTS:
                    page.screenshot(path=SHOTS + "/ppt_lesson.png", full_page=True)
                browser.close()
        finally:
            if old is None:
                os.environ.pop("ARTQUEST_SOFFICE", None)
            else:
                os.environ["ARTQUEST_SOFFICE"] = old
        self.assertEqual(errors, [])
        # 原件还是 PPT（下载用），放映的那份是 PDF；没开转换的机器上 PPT 只能下载，照样传得上去
        lesson = next(l for l in c.get("/api/classroom/lessons", headers={"Authorization": f"Bearer {reg.json()['token']}"}).json() if l["title"] == "色彩的冷暖")
        f = c.get(f"/api/classroom/lessons/{lesson['id']}").json()["files"][0]
        self.assertTrue(c.get(f["play_url"]).content.startswith(b"%PDF"))
        self.assertTrue(c.get(f["url"]).content.startswith(b"PK"))
        t = {"Authorization": f"Bearer {reg.json()['token']}"}
        r = c.post(f"/api/classroom/lessons/{lesson['id']}/files", headers=t, params={"filename": "第二份.pptx"}, content=pptx)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["play_url"], "")
        self.assertEqual(c.get(r.json()["url"] + "?as=pdf").status_code, 404)

    def test_a_teacher_writes_a_lesson_on_the_page_and_the_class_code_opens_it(self):
        from playwright.sync_api import sync_playwright

        c = TestClient(app)
        reg = c.post("/api/accounts/register", json={"name": "页面上录课的老师", "pin": "2468", "role": "teacher", "teacher_code": "code-777"})
        if reg.status_code == 409:
            reg = c.post("/api/accounts/login", json={"name": "页面上录课的老师", "pin": "2468"})
        t = {"Authorization": f"Bearer {reg.json()['token']}"}
        code = c.post("/api/classroom/classes", headers=t, json={"name": "五（4）班"}).json()["code"]

        errors = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            tpage = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
            tpage.on("pageerror", lambda e: errors.append(str(e)))
            tpage.on("dialog", lambda d: d.accept())
            tpage.set_default_timeout(15000)
            tpage.add_init_script("localStorage.setItem('artquest.token', %r); localStorage.setItem('artquest.tour/2','1')" % reg.json()["token"])
            tpage.goto(self.base + "/teacher")
            tpage.wait_for_selector("body.teacher")
            tpage.click('.tab[data-tab="class"]')
            tpage.click("#cl-new-lesson")
            tpage.wait_for_selector("#class-edit:not(.hidden) #ed-title")
            tpage.fill("#ed-title", "会跳舞的线")
            tpage.fill("#ed-summary", "用线条画出动起来的感觉。")
            tpage.click("#ed-add-slide")
            tpage.fill('.ed-slide[data-i="0"] [data-f="title"]', "线会动")
            tpage.fill('.ed-slide[data-i="0"] [data-f="lines"]', "直线很安静\n曲线像在跳舞")
            tpage.click("#ed-add-slide")                                  # 加第二页时第一页填的字不能丢
            tpage.fill('.ed-slide[data-i="1"] [data-f="title"]', "第二页")
            tpage.click('.ed-slide[data-i="1"] [data-up]')                # 挪到前面
            self.assertEqual(tpage.input_value('.ed-slide[data-i="1"] [data-f="title"]'), "线会动")
            tpage.click('.ed-slide[data-i="0"] [data-del]')               # 再删掉
            tpage.click("#ed-add-task")
            tpage.fill('.ed-task[data-i="0"] [data-f="title"]', "跳舞的人")
            tpage.fill('.ed-task[data-i="0"] [data-f="instruction"]', "只用线画一个正在跳舞的人。")
            tpage.fill('.ed-task[data-i="0"] [data-f="requirements"]', "看得出他在动")
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/editor.png", full_page=True)
            tpage.click("#ed-save")
            tpage.wait_for_selector("#class-home:not(.hidden) .cl-lesson-wrap [data-edit]")
            lid = tpage.get_attribute(".cl-lesson-wrap [data-edit]", "data-edit")
            # 样板课默认挂在班上；把它拿下来，换成自己录的这节
            tpage.click('[data-cltab="classes"]')
            tpage.uncheck('#cl-pick input[value="%s"]' % LESSON)
            tpage.wait_for_selector('#cl-pick input[value="%s"]:not(:checked)' % LESSON)
            tpage.check('#cl-pick input[value="%s"]' % lid)
            tpage.wait_for_selector('#cl-pick input[value="%s"]:checked' % lid)
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/teacher2.png", full_page=True)

            # 现成的 PDF 课件传上来就是一节课：课题先用文件名，直接进编辑页；这节课打开来 PDF 就是课件
            tpage.click('[data-cltab="library"]')
            real = (classroom.COURSEWARE_DIR / "zj5a_bridge.pdf").read_bytes()
            tpage.set_input_files("#cl-up-file", {"name": "色彩的冷暖.pdf", "mimeType": "application/pdf", "buffer": real})
            tpage.wait_for_selector("#class-edit:not(.hidden) #ed-title")
            self.assertEqual(tpage.input_value("#ed-title"), "色彩的冷暖")
            self.assertIn("色彩的冷暖.pdf", tpage.inner_text("#ed-files"))
            tpage.click("#ed-back")
            card = '.cl-lesson-wrap:has-text("色彩的冷暖")'
            tpage.wait_for_selector("#class-home:not(.hidden) " + card)
            self.assertEqual(tpage.inner_text(card + " .cl-doc"), "PDF")
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/library2.png", full_page=True)
            tpage.click(card + " .cl-lesson")
            # PDF 在页面里一页页往下滚（pdf.js），不用下载
            tpage.wait_for_selector("#class-lesson:not(.hidden) canvas.cl-pdfpage.ready")
            self.assertEqual(tpage.eval_on_selector_all("canvas.cl-pdfpage", "e=>e.length"), 9)
            self.assertFalse(tpage.is_visible("#cl-next"))
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/pdf_lesson.png", full_page=True)

            page = browser.new_context(viewport={"width": 1280, "height": 860}).new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_default_timeout(15000)
            page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")
            page.goto(self.base)
            page.wait_for_selector("#view-world:not(.hidden)", timeout=8000)
            page.click("#btn-enter-world")
            page.wait_for_selector("#quest-grid .quest-card")
            page.click('.tab[data-tab="class"]')
            page.wait_for_selector("#view-class:not(.hidden) #cl-code")
            self.assertEqual(page.eval_on_selector_all("#cl-mycls .cl-lesson", "e=>e.length"), 0, "没输码：我的课堂里只有输码那一栏")
            if SHOTS:
                page.screenshot(path=SHOTS + "/join.png", full_page=True)
            page.fill("#cl-code", code)
            page.click("#cl-join-go")
            page.wait_for_selector("#cl-mycls .cl-lesson")
            self.assertEqual(page.eval_on_selector_all("#cl-mycls .cl-lesson b", "e=>e.map(x=>x.textContent)"), ["会跳舞的线"])
            self.assertEqual(page.eval_on_selector_all("[data-edit], [data-copy], #cl-new-lesson", "e=>e.length"), 0)
            page.click("#cl-mycls .cl-lesson")
            page.wait_for_selector("#class-lesson:not(.hidden) #cl-slide h2")
            self.assertEqual(page.inner_text("#cl-slide h2"), "线会动")
            self.assertEqual(page.eval_on_selector_all("#cl-slide li", "e=>e.map(x=>x.textContent)"), ["直线很安静", "曲线像在跳舞"])
            self.assertEqual(page.inner_text("#cl-page"), "1 / 1")
            page.click("#cl-lesson-tasks [data-task]")
            page.wait_for_selector("#view-draw:not(.hidden)")
            self.assertIn("跳舞的人", page.inner_text("#draw-quest-card"))
            self.assertIn("看得出他在动", page.inner_text("#draw-quest-card"))
            browser.close()
        self.assertEqual(errors, [])
        lesson = c.get(f"/api/classroom/lessons/{lid}").json()
        self.assertEqual((lesson["title"], lesson["summary"], len(lesson["slides"]), len(lesson["tasks"])),
                         ("会跳舞的线", "用线条画出动起来的感觉。", 1, 1))


if __name__ == "__main__":
    unittest.main()
