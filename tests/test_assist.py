"""创作**进行中**那扇窗：彩点在孩子画到一半时说的话。

守三件事：

1. `dialogue_mode` 是冻结在 session 上的条件，它必须**真的决定点什么**。
   声明了却不执行是最坏的情况——元数据说「这一臂没有陪伴」，孩子照样收到了，
   整条臂的数据就废了。所以对照组在接口层直接 403。
2. 点击要落盘。「他什么时候点、点了几次」是这个功能存在的全部理由，
   事件丢了等于什么都没采到。
3. 过程中的话**不评价质量**。这是项目一贯的那条原则（不给孩子下判决）的
   延伸：创作途中听到「画得不太像」，孩子接下来画的就不是他想画的。
   评价属于交卷之后的 /submit。

Run:  python3 -m unittest -v
"""
import base64
import io
import unittest

from .env import TMP as _TMP  # sets the offline backends and the test data dir

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.main import app  # noqa: E402
from artquest.assist.template_assist import TemplateAssist  # noqa: E402
from artquest.config import SESSIONS_DIR  # noqa: E402
from artquest.storage import session_events  # noqa: E402


def _data_url():
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class TheWindowDuringDrawing(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.img = _data_url()

    def _session(self, **condition):
        body = {"quest_id": "imagine_animal",
                "intent": {"emotion": "开心", "text": "一只在树上睡觉的猫"}}
        if condition:
            body["condition"] = condition
        return self.c.post("/api/sessions", json=body).json()["session_id"]

    def test_the_control_arm_really_gets_nothing(self):
        """`dialogue_mode: none` 不是个装饰性的标签。"""
        sid = self._session(dialogue_mode="none")
        r = self.c.post(f"/api/sessions/{sid}/assist", json={"image": self.img, "nth": 1})
        self.assertEqual(r.status_code, 403, r.text)

    def test_opening_the_window_is_recorded(self):
        """点开这个动作本身就是数据——它说明他这会儿卡住了。"""
        sid = self._session()
        for n in (1, 2):
            r = self.c.post(f"/api/sessions/{sid}/assist", json={
                "image": self.img, "elapsed_ms": n * 12000, "nth": n,
                "events": [{"seq": n, "t_ms": n * 12000, "type": "ASSIST_OPEN",
                            "payload": {"nth": n, "cached": False, "phase": "before"}}]})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["text"].strip())

        opens = [e for e in session_events(SESSIONS_DIR / sid) if e.get("type") == "ASSIST_OPEN"]
        self.assertEqual(len(opens), 2, opens)
        # 时间点要留着：第一次点在创作进行到多久，是「什么时候需要帮忙」的直接证据
        self.assertEqual([e["t_ms"] for e in opens], [12000, 24000])
        self.assertEqual([e["payload"]["nth"] for e in opens], [1, 2])

    def test_it_does_not_repeat_the_intent_it_was_just_told(self):
        """窗口第一行已经把孩子写的意图摆出来了，引擎再说一遍就是复读。"""
        intent = {"text": "一只在树上睡觉的猫", "emotion": "开心"}
        first = TemplateAssist().assist(b"", {"title": "x", "prompt": "y"}, intent, nth=1)["text"]
        self.assertNotIn(intent["text"], first, f"第一句复读了意图：{first}")

    def test_it_does_not_echo_the_child_s_own_lead_in(self):
        """孩子写心愿几乎都从「我想画」起头，模板句又要把意图嵌进句子里。

        直接拼出来是「你说你想画我想画一个安静的房间。」——真机上看到过。
        嵌进去的必须是他那句话的**内容**，起头和句号都得剥掉。
        """
        intent = {"text": "我想画一个安静的房间。", "emotion": "平静"}
        eng = TemplateAssist()
        texts = [eng.assist(b"", {"title": "x", "prompt": "y"}, intent, nth=n)["text"] for n in range(1, 13)]
        quoted = [t for t in texts if "安静的房间" in t]
        self.assertTrue(quoted, "意图从来没有被还给孩子")
        for t in quoted:
            self.assertNotIn("我想画", t, f"复读了孩子自己的起头：{t}")
            self.assertNotIn("。」", t, f"把他的句号也嵌进去了：{t}")

    def test_it_never_judges_the_work_in_progress(self):
        """过程中只鼓励和发问。评价留到交卷之后。"""
        # 说出来就越界的词：它们要么在打分，要么在给「标准答案」
        forbidden = ("构图", "比例", "透视", "明暗", "饱和度", "不够", "应该", "建议",
                     "画得好", "真棒", "不太", "可以再")
        eng = TemplateAssist()
        for n in range(1, 13):
            text = eng.assist(b"", {"title": "x", "prompt": "y"},
                              {"text": "一只猫", "emotion": "开心"}, nth=n)["text"]
            for w in forbidden:
                self.assertNotIn(w, text, f"第 {n} 句越界了（{w}）：{text}")

    def test_a_broken_engine_never_blocks_drawing(self):
        """陪伴是锦上添花，它挂了也不能让孩子画不下去。"""
        import artquest.main as m
        orig = m.get_assist_engine
        m.get_assist_engine = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            sid = self._session()
            r = self.c.post(f"/api/sessions/{sid}/assist", json={"image": self.img, "nth": 1})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["text"].strip())
            self.assertEqual(r.json()["backend"], "error")
        finally:
            m.get_assist_engine = orig


if __name__ == "__main__":
    unittest.main()
