# section 43420
FAMILY = "red-run"  # the commit-time check on test commits (rule red-run, decision red-run-trailer-on-test-commits)

# A lone commit is judged alone, whatever runs before it in the same call. A read-only step that is not git, such as a
# test run, must not switch the rule off for the commit that follows it. Each refused case has its trailer form allowed
# on the same fixture beside it. RR_HEREDOC holds hooks/test_x.py staged and nothing committed.
RC_TEST_RUN = "verdict python3 -m pytest hooks/test_x.py -q"

# The control for the cause: `true` is a step the chain read passes, so the commit after it is still judged. Only the
# test run, which the chain read does not pass, differs from it.
rc_refuse("a true, then a commit -m that adds hooks/test_x.py with no Red-run line, joined by ;",
          "true; " + VCS + ' commit -m "add test"', RR_HEREDOC)
rc_refuse("a test run, then a commit -m that adds hooks/test_x.py with no Red-run line, joined by ;",
          RC_TEST_RUN + "; " + VCS + ' commit -m "add test"', RR_HEREDOC)
rc_allow("a test run, then a commit -m with Red-run: none: x, joined by ;",
         RC_TEST_RUN + "; " + VCS + ' commit -m "add test" -m "%s"' % RR_NONE_LINE, RR_HEREDOC)
rc_refuse("a test run, then a commit -m that adds hooks/test_x.py with no Red-run line, joined by &&",
          RC_TEST_RUN + " && " + VCS + ' commit -m "add test"', RR_HEREDOC)
rc_allow("a test run, then a commit -m with Red-run: none: x, joined by &&",
         RC_TEST_RUN + " && " + VCS + ' commit -m "add test" -m "%s"' % RR_NONE_LINE, RR_HEREDOC)
