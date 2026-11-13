# A review log body held in a shell variable is not read

- **What.** The guard reads the body of a `gh pr comment` or `gh issue comment` post from `--body`, `--body-file`, a heredoc or a `cat FILE` pipe. A body held in a shell variable (`BODY=...; gh pr comment 5 --body "$BODY"`) is not read, so a malformed review log, or one with a hand-typed head, is allowed on that route. `merge --reviewed` then cannot read it.
- **Where.** `review_post_hit` in `hooks/guard.py`, and the judges `review_log_hit` and `review_form_hit` in `hooks/guard_merge.py`.
- **Decision.** `pr-review-record` (a review log names the head it reviewed and must parse). It lists this route as a limit under "The guard".
- **Retire.** Read the variable's assignment earlier in the same command, or refuse a marked post whose body the guard cannot read. Then the `review-log` cases in `hooks/test_guard.py` hold a case for the `BODY=...; gh pr comment 5 --body "$BODY"` form that is refused when the body is malformed and allowed when it parses. Remove the "held in a shell variable" bullet from the decision's limits in the same PR.
