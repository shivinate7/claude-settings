# section 43518
FAMILY = "paths"

# THE PLAIN TEST RUN. A builder runs a test script by name, and the guard reads that script from disk. A script
# that writes scratch files under a run folder from lint/_test_temp.py joins that folder to a test path such as
# hooks/test_guard.py. The guard cannot read the run folder's head, so the join reads as a repo test path, and
# the plain run is refused: a false alarm. These cases name the real script files and read them from the checkout
# (REPO). A fixture copy would pass with no script to read, so a missing file stops the run instead.
CULL_RUN_FILES = [os.path.join(REPO, "lint", "test_rule_audit.py"),
                  os.path.join(REPO, "tests", "guard", "s23264-builder-refuse.py")]
_missing = [path for path in CULL_RUN_FILES if not os.path.isfile(path)]
if _missing:
    sys.exit("fixture setup failed: %s is missing, so a builder run of it has no script to read" % _missing[0])

# The builder payload is B from s20369-paths.py (loaded first, in section order). Its cwd is the real checkout.
CULL_BUILDER = dict(B, cwd=REPO)

sh("builder run: verdict python3 lint/test_rule_audit.py, a plain test run, is allowed",
   "verdict python3 lint/test_rule_audit.py", "allow", **CULL_BUILDER)
sh("builder run: verdict python3 tests/guard/s23264-builder-refuse.py, a plain test run, is allowed",
   "verdict python3 tests/guard/s23264-builder-refuse.py", "allow", **CULL_BUILDER)

# Green controls: the same builder in the same checkout, each a real write or removal of a test path. Still refused.
sh("builder-test: sed -i on lint/test_rule_audit.py is refused",
   "sed -i 's/a/b/' lint/test_rule_audit.py", "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
sh("builder-test: a redirect onto lint/test_rule_audit.py is refused",
   "echo x > lint/test_rule_audit.py", "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
sh("builder-test: rm of hooks/test_guard.py is refused",
   "rm hooks/test_guard.py", "deny", rule=BT, carries=("test-author",), **CULL_BUILDER)
