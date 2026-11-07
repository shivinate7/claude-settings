# The cloud classifier refuses a test-author's cd into its red-run checkout

- **What.** `agents/test-author.md` tells each test-author to `cd` into its own `agent-<id>-red` checkout. The guard allows that act. The cloud auto-mode classifier refused it four times in lane page-dup-helpers (2026-11-07 14:30 to 15:05 CST, two test-authors), for example `cd /home/user/claude-settings/.claude/worktrees/agent-ade37b30f41b8a907-red && git status --short`, as a git act in a "shared checkout".
- **Where.** `settings.json` `autoMode.allow`, and the red-run step in `agents/test-author.md`.
- **Decision.** `auto-mode-owner-acts` (which acts auto mode allows with no ask). A new entry needs the owner's grant.
- **Retire.** The owner grants a narrow allow entry for the caller's own red-run checkout, or the test-author step changes to a form the classifier allows. `hooks/test_auto_mode_allow.py` pins the entry.
