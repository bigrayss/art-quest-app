# -*- coding: utf-8 -*-
"""课堂模块：一节课有课件和配套的画画任务；老师建班传课件，学生凭班级码进班交作业。"""
import os
import unittest

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


SHOTS = None     # 调试时填一个目录，课件页和老师页各存一张截图


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
            page.fill("#cl-code", "nosuch")
            page.click("#cl-join-go")
            page.wait_for_selector("#cl-msg:not(.hidden)")              # 码不对：说一句，不进班
            page.fill("#cl-code", code.lower())
            page.click("#cl-join-go")
            page.wait_for_selector(".cl-mine")
            self.assertIn("五（3）班", page.inner_text(".cl-mine"))

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
            self.assertEqual(page.eval_on_selector_all("#cl-lesson-tasks .cl-task", "e=>e.length"), 4)

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

            # 老师登录进来：课堂页上有这个班、有交上来的那张画
            tpage = browser.new_context(viewport={"width": 1280, "height": 860}).new_page()
            tpage.on("pageerror", lambda e: errors.append(str(e)))
            tpage.set_default_timeout(15000)
            # 老师用另一个浏览器环境（自己的 localStorage），像在讲台那台电脑上
            tpage.add_init_script("localStorage.setItem('artquest.token', %r); localStorage.setItem('artquest.tour/2','1')" % reg.json()["token"])
            tpage.goto(self.base + "/teacher")
            tpage.wait_for_selector("body.teacher")
            tpage.click('.tab[data-tab="class"]')
            tpage.wait_for_selector(".cl-class.on")
            self.assertIn(code, tpage.inner_text(".cl-class.on"))
            tpage.wait_for_selector(".cl-piece img")
            self.assertIn("课堂练习", tpage.inner_text(".cl-piece"))
            self.assertIn("老师的讲稿.pdf", tpage.inner_text("#cl-files"))
            if SHOTS:
                tpage.screenshot(path=SHOTS + "/teacher.png", full_page=True)
            tpage.click('.cl-lesson[data-lesson="%s"]' % LESSON)
            tpage.wait_for_selector("#class-lesson:not(.hidden) #cl-slide h2")
            self.assertTrue(tpage.is_visible("#cl-lesson-note"))
            self.assertEqual(tpage.eval_on_selector_all("#cl-lesson-tasks [data-task]", "e=>e.length"), 0, "老师这边没有「开始画」")
            browser.close()

        self.assertEqual(errors, [])
        work = c.get(f"/api/classroom/classes/{code}/work", headers=t).json()
        self.assertEqual([(w["task_kind"], w["task_key"], w["status"]) for w in work["work"]], [("practice", "p1", "done")])
        self.assertEqual(len(work["members"]), 1)


if __name__ == "__main__":
    unittest.main()
