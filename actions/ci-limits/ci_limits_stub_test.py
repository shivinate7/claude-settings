"""A stand-in for ci_limits.py: the same names and no logic. Each case that expects a value fails on it, some on an
assert and some on an error. The empty-window case passes, since it expects none. Load it with CI_LIMITS_UNDER_TEST;
it shows only that those cases can go red.
"""


def job_limits(jobs_by_run, caps, kinds=None, window=30):
    return {}, []


def deadline_minutes(jobs_by_run, limits, window=30):
    return 0


def read_limits(fetch, caps, kinds=None, window=30):
    return {}, [], []


def main(argv, fetch, caps, kinds=None, out=None, err=None):
    return 0
