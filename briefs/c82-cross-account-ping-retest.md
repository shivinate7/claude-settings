# c82: re-run the cross-account ping test

Paste the block below, whole, into the sending session: the one on the account where your ping was
blocked. Written by the local liaison, Oct 27, against claude-settings main 2ad85de6 (batch #649,
which carries PR #645).

```
Re-run the cross-account ping test for c82 (an override pass lifts the SendMessage wording judge). Do nothing else.
1. Pull claude-settings to 2ad85de6 or later and reinstall. Then confirm ~/.claude/settings.json has no "Judge this SendMessage" prompt hook, and that the SendMessage command hook's timeout is 50. If either check fails, stop and report.
2. Wait for me to type an override (for example "override 10m"). Then send the same ping as before to the session on my other account.
3. Expect it to go through, with a guard.log line "override parallelism-no-mid-task-talk".
4. After the override ends, send one bare chatter ping with no override. Expect a deny, which shows the judge still works.
Report the guard.log lines and the verdict of each send, not the transcript. Five lines at most.
```
