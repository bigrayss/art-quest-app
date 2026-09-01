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

import artquest.config  # noqa: E402

importlib.reload(artquest.config)
