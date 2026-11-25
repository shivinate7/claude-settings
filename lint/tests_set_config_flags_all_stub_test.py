"""A stand-in for lint/check_tests_set_config.py that flags every test_*.py under root.

lint/test_tests_set_config.py runs against it through TESTS_SET_CONFIG_UNDER_TEST. Each clean case then fails on its assert: a
behavioural red (the checker over-flags), not a missing module.
"""
import os


def problems(root):
    found = []
    for folder, _, names in os.walk(root):
        for name in sorted(names):
            if name.startswith("test_") and name.endswith(".py"):
                rel = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                found.append(rel + ":1: flagged by the stand-in")
    return found
