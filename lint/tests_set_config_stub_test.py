"""A stand-in for lint/check_tests_set_config.py that finds nothing.

lint/test_tests_set_config.py runs against it with --stand-in lint/tests_set_config_stub_test.py. Each case that expects a problem then fails on
its assert: a behavioural red, not a missing module.
"""


def problems(root):
    return []
