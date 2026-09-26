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
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

import artquest.config  # noqa: E402

importlib.reload(artquest.config)
