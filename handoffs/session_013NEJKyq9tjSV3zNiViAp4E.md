# lane: shell-could-write-linear (session_013NEJKyq9tjSV3zNiViAp4E), received 09:43 CST 2026-11-10, kind B

Handoff (B), lane shell-could-write-linear, topic guard-speed:
1. Task: make `_shell_could_write` linear (roadmap step shell-could-write-linear, order 924).
2. Repo shivinate7/claude-settings. No branch, no PR, no commits, nothing to push.
3. State: I stopped before building. The function is not on origin/main 8bc28980b. It exists only in unmerged PR #1971 (lane revive-1042, round 3 at a7a3a67ac).
4. Your earlier ruling: wait for #1971 to reach main, then build on top of it. I never saw it land and did not re-check.
5. Left: confirm #1971 is on main, then run the lane. The test-author writes a timing case (5000 words under a set bound) and verdict cases, red on main. The builder makes the scan linear. Review owes round 3 with the net-value test.
