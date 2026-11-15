# section 43405
FAMILY = "red-run"  # the push check on test commits (rule red-run, decision red-run-trailer-on-test-commits)

# A commit made earlier in the same call that reverts another is not judged at push time, as a landed revert is not:
# decision red-run-trailer-on-test-commits, item 7. The revert carries git's `This reverts commit <sha>.` line, and
# the push below sends it as a pending commit. The control is the same chain with a plain message, which is refused.
RR_REVERT_CHAIN = (VCS + " add " + RR_TEST + " && " + VCS + ' commit -m "Revert x" -m "This reverts commit abc1234."'
                   + " && " + VCS + " push origin topic")
RR_PLAIN_CHAIN = VCS + " add " + RR_TEST + " && " + VCS + ' commit -m "add test" && ' + VCS + " push origin topic"

rr_allow("a pending revert in one call: git add hooks/test_x.py, a commit -m with the This reverts commit line, then a push",
         RR_REVERT_CHAIN, RR_HEREDOC)
rr_refuse("a pending plain test commit in one call: git add hooks/test_x.py, a commit -m with no trailer, then a push",
          RR_PLAIN_CHAIN, RR_HEREDOC)

# The same revert line on a lone commit, with no push after it and no revert in progress. The plain lone commit of
# hooks/test_x.py on this fixture is refused in section 43410, the control for this case.
sh("red-run: a lone commit -m with the This reverts commit line, staging hooks/test_x.py, is allowed",
   VCS + ' commit -m "Revert x" -m "This reverts commit abc1234."', "allow", cwd=RR_HEREDOC)
