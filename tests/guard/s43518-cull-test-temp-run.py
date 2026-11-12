# section 43518
FAMILY = "paths"

# THE PLAIN TEST RUN. A builder runs a test script by name, and the guard reads that script from disk. A script
# that writes scratch files under a run folder from lint/_test_temp.py joins that folder to a test path such as
# hooks/test_guard.py. The guard cannot read the run folder's head, so the join reads as a repo test path, and
# the plain run is refused: a false alarm. The case names the real script file and reads it from the checkout
# (REPO). A fixture copy would pass with no script to read, so a missing file stops the run instead.
CULL_RUN_FILES = [os.path.join(REPO, "lint", "test_rule_audit.py")]
_missing = [path for path in CULL_RUN_FILES if not os.path.isfile(path)]
if _missing:
    sys.exit("fixture setup failed: %s is missing, so a builder run of it has no script to read" % _missing[0])

# The builder payload is B from s20369-paths.py (loaded first, in section order). Its cwd is the real checkout.
CULL_BUILDER = dict(B, cwd=REPO)

sh("builder run: verdict python3 lint/test_rule_audit.py, a plain test run, is allowed",
   "verdict python3 lint/test_rule_audit.py", "allow", **CULL_BUILDER)

# A join whose head is unknown stays refused. A function parameter or sys.argv names a folder the guard cannot read,
# so a script that joins one to a test path is refused as a direct write to that path would be. Allowing it would
# widen the plain run to a form that writes a test path. Each script is a fixture in the run folder, outside every
# repository, and the command names it by its absolute path.
CULL_HEAD_DIR = os.path.join(ROOT, "cull-43518-heads")
write(os.path.join(CULL_HEAD_DIR, "param_head.py"), '''import os


def _incident(w):
    with open(os.path.join(w, "tests/test_cull.py"), "w") as handle:
        handle.write("pass\\n")


_incident(os.getcwd())
''')
write(os.path.join(CULL_HEAD_DIR, "argv_head.py"), '''import os
import sys

with open(os.path.join(sys.argv[1], "tests/test_cull.py"), "w") as handle:
    handle.write("pass\\n")
''')
for _cull_script, _cull_head in (("param_head.py", "a function parameter"), ("argv_head.py", "sys.argv")):
    sh("builder run: a script whose join head is %s stays refused" % _cull_head,
       "verdict python3 " + os.path.join(CULL_HEAD_DIR, _cull_script).replace(os.sep, "/"), "deny",
       rule=BT, carries=("test-author",), **CULL_BUILDER)

# Green controls: the same builder in the same checkout, each a real write or removal of a test path. Still refused.
sh("builder-test: sed -i on lint/test_rule_audit.py is refused",
   "sed -i 's/a/b/' lint/test_rule_audit.py", "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
sh("builder-test: a redirect onto lint/test_rule_audit.py is refused",
   "echo x > lint/test_rule_audit.py", "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
sh("builder-test: rm of hooks/test_guard.py is refused",
   "rm hooks/test_guard.py", "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
