# c125 outbox

- c125 (lanes run the gates lint before batching): finding. `lint/test_check_silent_undo.py` errors in a cloud container with git 2.43 (`test_a_gitlink_with_an_absent_commit_is_not_unknown`, in check_silent_undo `absent`). CI's result unknown from here. Candidate debt or a fix step.
- c125: note. gates.yml runs the STE lint as a `uses:` action, so `ci-job --lint` skips it. A `bin/ste-changed` run step in gates would close the gap.
