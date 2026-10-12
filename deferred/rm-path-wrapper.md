# An rm wrapper on PATH, active only in Claude sessions

**What waits.** A shell wrapper named `rm`, ahead of the real `rm` on PATH, that refuses a
recursive delete whose real target is `/`, the home folder, the current folder, or a parent of
either. It runs the real `rm` for every other call. It is the last stop behind the `rm-var`
guard rule and the prompt-answer hook (decision rm-on-a-variable-needs-a-guard): those read
the command text, this reads the resolved path at run time.

**Owner ruling, 2026-10-11.** "Yes, only for Claude sessions." Outside a Claude session the
wrapper must do nothing.

**The gate.** MEASURED on this machine, 2026-10-12: a Claude Code session sets `CLAUDECODE=1`
in every Bash tool process, with `CLAUDE_CODE_ENTRYPOINT` naming the host (`claude-desktop`
here). The wrapper reads `CLAUDECODE`; unset means pass through to the real `rm` untouched.

**Why it waits.** The guard rule and the hook land first (brief step 7). The wrapper needs its
own red cases: the four critical targets, a relative path that resolves to one, a symlink to
one, and a call with `CLAUDECODE` unset that must reach the real `rm`. It also needs an install
step per OS (`install.sh`, `install.ps1`), and `_rm_target_bad` in hooks/guard.py is the one
home for the critical-path reading, so the wrapper calls it rather than copying it.

**What keeps it from being lost.** This file.

**Trigger.** The hook merges, or a session reports an `rm` that both the rule and the hook let
through.
