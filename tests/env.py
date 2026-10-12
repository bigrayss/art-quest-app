"""Shared test environment: offline backends, one throwaway data dir.

Imported first by every test module so `artquest.config` is reloaded before any
other package module reads it.
"""
import importlib
import os
import tempfile

os.environ.setdefault("ARTQUEST_SCORER", "heuristic")
os.environ.setdefault("ARTQUEST_FEEDBACK", "template")
TMP = os.environ.setdefault("ARTQUEST_DATA_DIR", tempfile.mkdtemp(prefix="artquest-test-"))
# 研究员令牌。全量列表、打分、标注、策展都要它；测试里研究员视角的 client 带着它。
ADMIN_TOKEN = os.environ.setdefault("ARTQUEST_ADMIN_TOKEN", "test-admin-token")
# 首访任务库（2026-10-12）默认开着：第一次来的孩子看到的是年龄门 + 五道固定的题，不是十个家族的地图。
# 既有的浏览器用例走的都是老地图，所以测试里统一关掉；test_bank 自己把开关打开再测。
os.environ.setdefault("ARTQUEST_FIRST_VISIT", "off")
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

import artquest.config  # noqa: E402

importlib.reload(artquest.config)
