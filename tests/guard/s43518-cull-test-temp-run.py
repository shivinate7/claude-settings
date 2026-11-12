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

# THE SHADOW FORMS. hooks/guard_frozen.py reads a bare `run_folder()` as lint/_test_temp.py's helper only while the
# script binds that name nowhere else. Each script below imports run_folder, then rebinds the name a different way: a
# nested def, a global assignment, a try/except fallback, a lambda argument, a walrus. Its join on run_folder() to a
# test path is then the script's own folder, so the run is refused. Each form has its own clause in
# _py_run_folder_is_helper, and each case below pins that clause. The control keeps the plain import and no rebind,
# with the call inside a function, and stays allowed.
CULL_SHADOW_DIR = os.path.join(ROOT, "cull-43518-shadow")
write(os.path.join(CULL_SHADOW_DIR, "nested_def.py"), '''import os

from _test_temp import run_folder


def f():
    def run_folder():
        return os.getcwd()

    with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
        handle.write("pass\\n")


f()
''')
write(os.path.join(CULL_SHADOW_DIR, "global_assign.py"), '''import os

from _test_temp import run_folder


def f():
    global run_folder
    run_folder = lambda: os.getcwd()


f()
with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_SHADOW_DIR, "try_fallback.py"), '''import os

try:
    from _test_temp import run_folder
except ImportError:
    run_folder = lambda: os.getcwd()

with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_SHADOW_DIR, "lambda_arg.py"), '''import os

from _test_temp import run_folder

pick = lambda run_folder: os.getcwd()

with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_SHADOW_DIR, "walrus.py"), '''import os

from _test_temp import run_folder

(run_folder := lambda: os.getcwd())

with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
    handle.write("pass\\n")
''')
write(os.path.join(CULL_SHADOW_DIR, "control_inner.py"), '''import os

from _test_temp import run_folder


def f():
    with open(os.path.join(run_folder(), "hooks/test_guard.py"), "w") as handle:
        handle.write("pass\\n")


f()
''')
for _cull_script, _cull_why in (
        ("nested_def.py", "a nested def of run_folder"),
        ("global_assign.py", "a global run_folder with an assignment"),
        ("try_fallback.py", "a try/except fallback that assigns run_folder"),
        ("lambda_arg.py", "a lambda argument named run_folder"),
        ("walrus.py", "a walrus that binds run_folder")):
    sh("builder run: shadowed run_folder, %s, is refused" % _cull_why,
       "verdict python3 " + os.path.join(CULL_SHADOW_DIR, _cull_script).replace(os.sep, "/"), "deny",
       rule=BT, carries=("test-author",), **CULL_BUILDER)
sh("builder run: shadowed run_folder control, a helper call inside a function with no rebind, is allowed",
   "verdict python3 " + os.path.join(CULL_SHADOW_DIR, "control_inner.py").replace(os.sep, "/"), "allow",
   **CULL_BUILDER)

# THE PYTHON 3.9 FLOOR. _py_run_folder_is_helper (hooks/guard_frozen.py) names ast.MatchAs and ast.MatchStar in an
# isinstance tuple, and ast.MatchMapping, on each node that is none of the kinds before it. Python 3.9 has no match
# statement, so those names are absent there. The helper then raises on every script, and interpreter_write_hit reads
# the crash as no hit, so a heredoc write to a test path is allowed. No CI job runs the guard on 3.9: the 3.9 job
# (checks.yml, "Python 3.9 floor check") reads the source only. The guard runs as a child process, so the three names
# are hidden there by a sitecustomize.py on PYTHONPATH, the shim s10425 uses.
CULL_PY39_DIR = os.path.join(ROOT, "cull-43518-py39")
write(os.path.join(CULL_PY39_DIR, "sitecustomize.py"), '''import ast

for _name in ("MatchAs", "MatchStar", "MatchMapping"):
    if hasattr(ast, _name):
        delattr(ast, _name)
''')
CULL_PY39_ENV = {"PYTHONPATH": os.pathsep.join(filter(None, (CULL_PY39_DIR, os.environ.get("PYTHONPATH"))))}

# THE HELPER FAILS FOR ANOTHER REASON. The verdict must stay a refusal whatever the helper's exception is: the same
# crash reads as no hit. The shim raises a RuntimeError from ast.walk only while the helper is on the stack, so the
# raise sits in the helper's own walk, and a sub-helper that the helper calls raises too. A fix that stops walking
# inside the helper leaves nothing to raise, so this case then passes without showing the fail-closed rule.
CULL_RAISE_DIR = os.path.join(ROOT, "cull-43518-raise")
write(os.path.join(CULL_RAISE_DIR, "sitecustomize.py"), '''import ast
import sys

_walk = ast.walk


def _walk_that_fails_in_the_helper(tree):
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_name == "_py_run_folder_is_helper":
            raise RuntimeError("injected: _py_run_folder_is_helper fails for another reason")
        frame = frame.f_back
    return _walk(tree)


ast.walk = _walk_that_fails_in_the_helper
''')
CULL_RAISE_ENV = {"PYTHONPATH": os.pathsep.join(filter(None, (CULL_RAISE_DIR, os.environ.get("PYTHONPATH"))))}

# The heredoc both cases judge: a plain `python3 -` heredoc that writes a test path, with no run_folder call. The
# control runs it with no shim, where the helper works, so it is refused on the head.
CULL_HEREDOC = "python3 - <<'EOF'\nopen('tests/guard/x.py', 'w').write('x')\nEOF"
sh("builder run: a heredoc write of tests/guard/x.py is refused (control, the helper works)",
   CULL_HEREDOC, "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
sh("builder run: a heredoc write of tests/guard/x.py is refused on Python 3.9, where the match names are absent",
   CULL_HEREDOC, "deny", rule=BT, carries=("test-author",), env=CULL_PY39_ENV, **CULL_BUILDER)
sh("builder run: a heredoc write of tests/guard/x.py is refused when _py_run_folder_is_helper fails for another reason",
   CULL_HEREDOC, "deny", rule=BT, carries=("test-author",), env=CULL_RAISE_ENV, **CULL_BUILDER)
# The shim alone must not stop the guard: a shell edit the helper never reads is still refused under it.
sh("builder-test: sed -i on lint/test_rule_audit.py is still refused under the 3.9 shim",
   "sed -i 's/a/b/' lint/test_rule_audit.py", "deny", rule=BT, carries=("test-author",), env=CULL_PY39_ENV,
   **CULL_BUILDER)
