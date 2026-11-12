"""A stand-in for ci_limits.py: the same names, and no logic. test_ci_limits.py runs against it through
CI_LIMITS_UNDER_TEST for the red record. Each case then fails on its own assert, not on a missing module.
"""


def job_limits(jobs_by_run, caps, kinds=None, window=30):
    return {}, []


def deadline_minutes(jobs_by_run, limits, window=30):
    return 0


def read_limits(fetch, caps, kinds=None, window=30):
    return {}, [], []


def main(argv, fetch, caps, kinds=None, out=None, err=None):
    return 0
