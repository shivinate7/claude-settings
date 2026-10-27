# c119: does a Mac session pick up merged claude-settings work with no manual reinstall?

Local liaison, Oct 27, against claude-settings main d4e1b86b. Mac session, measurement only: no
reinstall by hand, no settings edit, no ask to the owner.

Today: the SessionStart (startup|resume) hook fetches origin/main, fast-forwards local main, and runs
merge/install_from_main.sh in the background when the pin is behind. It exits at once when
CLAUDE_CODE_REMOTE is set. It logs failures to ~/.claude/claude-settings-install.log.

1. Read the pin: the path in the first `@<path>/CLAUDE.md` line of ~/.claude/CLAUDE.md. Record
   `git -C <pin> rev-parse HEAD` and `git -C <pin> rev-parse origin/main` after a fetch, plus the
   last 10 lines of the install log.
2. Record whether CLAUDE_CODE_REMOTE is set in this session's environment, and to what. If it is
   set, Remote Control sessions never auto-pull: say so.
3. Start one fresh headless session from $HOME: `claude -p "reply ok" --max-turns 1`. Wait 3 min,
   then read the pin HEAD and the log again. If auto mode refuses the start, give the exact refusal.
4. Report in 8 lines: pin before and after, whether it reached origin/main, new log lines,
   CLAUDE_CODE_REMOTE, and any refusal text.
