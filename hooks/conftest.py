"""pytest fixtures for the spawn grant tests (hooks/test_grant_word.py, hooks/test_grant_gate.py).

One run folder per pytest run, from the repo's shared test temp root (decision test-temp-standard, lint/_test_temp.py).
The first request of the run sweeps sibling run folders older than a day. The session removes this run's folder at its end.
"""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint"))
import _test_temp  # noqa: E402  the one home of the run-folder standard


@pytest.fixture(scope="session")
def run_dir():
    folder = _test_temp.run_folder()
    yield folder
    shutil.rmtree(folder, ignore_errors=True)
