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

# THE NAME IS NOT THE HEAD. hooks/guard_frozen.py reads a call named `run_folder` as lint/_test_temp.py's run
# folder by its name alone. So a `run_folder` the script defines itself (a lambda), or one reached through an
# attribute chain, reads as that folder, and its join to a test path is allowed. Each script below has a join
# head that is not that function, so its join to a test path is refused. The argument forms (positional,
# keyword, starred) are refused on this head already: these cases pin that, so a rule that loosens them goes red.
# A bare `run_folder()` imported from lint/_test_temp.py, and `_test_temp.run_folder()`, stay allowed.
CULL_NAME_DIR = os.path.join(ROOT, "cull-43518-names")
write(os.path.join(CULL_NAME_DIR, "own_lambda.py"), '''import os

run_folder = lambda: os.path.join(os.getcwd(), "tests")

with open(os.path.join(run_folder(), "test_x.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_NAME_DIR, "attr_chain.py"), '''import os

import a

with open(os.path.join(a.b.run_folder(), "test_x.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_NAME_DIR, "arg_positional.py"), '''import os

import _test_temp

with open(os.path.join(_test_temp.run_folder(os.getcwd()), "test_x.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_NAME_DIR, "arg_keyword.py"), '''import os

import _test_temp

with open(os.path.join(_test_temp.run_folder(temp_root="hooks"), "test_x.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_NAME_DIR, "arg_starred.py"), '''import os

import _test_temp

args = ("hooks",)

with open(os.path.join(_test_temp.run_folder(*args), "test_x.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_NAME_DIR, "import_attr.py"), '''import os

import _test_temp

with open(os.path.join(_test_temp.run_folder(), "hooks/test_guard.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_NAME_DIR, "import_bare.py"), '''import os

from _test_temp import run_folder

with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
    handle.write("pass\\n")
''')
for _cull_script, _cull_why in (
        ("own_lambda.py", "a lambda the script defines as run_folder"),
        ("attr_chain.py", "an attribute chain, a.b.run_folder()"),
        ("arg_positional.py", "run_folder given a positional argument"),
        ("arg_keyword.py", "run_folder given a keyword argument"),
        ("arg_starred.py", "run_folder given a starred argument")):
    sh("builder run: a join on %s is refused" % _cull_why,
       "verdict python3 " + os.path.join(CULL_NAME_DIR, _cull_script).replace(os.sep, "/"), "deny",
       rule=BT, carries=("test-author",), **CULL_BUILDER)
for _cull_script, _cull_why in (
        ("import_attr.py", "_test_temp.run_folder() after import _test_temp"),
        ("import_bare.py", "a bare run_folder() after from _test_temp import run_folder")):
    sh("builder run: a join on %s is allowed" % _cull_why,
       "verdict python3 " + os.path.join(CULL_NAME_DIR, _cull_script).replace(os.sep, "/"), "allow",
       **CULL_BUILDER)
