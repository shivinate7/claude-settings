"""A stand-in for isolated_config() in lint/_test_temp.py that points CLAUDE_CONFIG_DIR and HOME at a fresh folder under the run
folder and never puts either back.

lint/test_test_temp.py runs against it through TEST_TEMP_UNDER_TEST. Its restore cases and its HOME case then fail on their
asserts: a behavioural red, not a missing name.
"""
import contextlib
import os
import tempfile


@contextlib.contextmanager
def isolated_config(run):
    folder = tempfile.mkdtemp(prefix="config-", dir=run)
    os.environ["CLAUDE_CONFIG_DIR"] = folder
    os.environ["HOME"] = folder
    yield folder
