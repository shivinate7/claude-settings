"""A stand-in for isolated_config() in lint/_test_temp.py that changes nothing and yields the run folder.

lint/test_test_temp.py runs against it through TEST_TEMP_UNDER_TEST. Its cases that need CLAUDE_CONFIG_DIR inside the run folder
then fail on their asserts: a behavioural red, not a missing name.
"""
import contextlib


@contextlib.contextmanager
def isolated_config(run):
    yield run
