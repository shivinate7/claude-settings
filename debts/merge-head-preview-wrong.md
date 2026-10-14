# The merge head preview disagrees with the wait

- **What.** The preview (`head_state`) prints a literal `<branch>`. The wait and the read name the real branch. The preview reads checks only. With checks `gates pass` and every run skipped, it says green. The wait and the read refuse with "skipped, no job ran".
- **Where.** `head_state` in `merge/merge.py`.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** The preview names the real branch and reads the same runs as the wait. A case with every run skipped gets the same verdict from both.
