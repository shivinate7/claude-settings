"""The one home of the test-run commit-signing opt-out (roadmap step test-runs-skip-signing).

A test suite or test helper that commits, merges or tags in a fixture repo imports this module once,
near the top. The import appends commit.gpgsign=false and tag.gpgsign=false to os.environ through
GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n, so every git the suite starts skips the
signing service. Keys already set stay. A second import adds nothing.

A subprocess that gets a fresh env (not a copy of os.environ) and commits passes it through
`apply(env)`. Product code never imports this module: its real commits still sign.

Twins with the same keys and the same append rule: lint/_test_git.sh (sourced) and
lint/_test_git.mjs (imported). lint/test_test_git.py proves all three.
"""
import os

# The twins copy these two pairs: a sourced shell file and a JS module cannot read a Python
# constant, and a sourced POSIX shell file cannot find its own path to read a shared data file.
OPT_OUT = (("commit.gpgsign", "false"), ("tag.gpgsign", "false"))


def apply(environ):
    """Append each OPT_OUT pair to `environ` that its git config entries do not already end with.
    Returns `environ`, the same object."""
    try:
        count = int(environ.get("GIT_CONFIG_COUNT") or 0)
    except ValueError:
        count = 0
    last = {}  # git applies entries in order, so the last value for a key wins
    for index in range(count):
        key = environ.get("GIT_CONFIG_KEY_%d" % index, "")
        last[key.lower()] = environ.get("GIT_CONFIG_VALUE_%d" % index, "")
    for key, value in OPT_OUT:
        if last.get(key) == value:
            continue
        environ["GIT_CONFIG_KEY_%d" % count] = key
        environ["GIT_CONFIG_VALUE_%d" % count] = value
        count += 1
    environ["GIT_CONFIG_COUNT"] = str(count)
    return environ


apply(os.environ)
