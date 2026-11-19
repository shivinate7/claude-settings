# Handoff: lane dead-host-lock-form-off-linux

- Slug: dead-host-lock-form (step dead-host-lock-form-off-linux)
- Started 2026-11-13 18:33 CST by the claude-settings coordinator (session_013NEJL1gw6EdrSyvHkTUEx6). This session: session_013NEJL1gw6EdrSyvHkTUEx6's child, id in the Claude-Session trailer.
- Branch: none for work. This archive branch holds only this file. Head of origin/main read at start: 2a388ccd927102fdb9bb97e49c638d6c1b4bbe48 (checkout head).
- Open PRs: none from this lane. Sibling PR #3303 (lane sweep-mutants-windows-skip, head fe470abfcd9ebfa47269f9d6af6ad27363686757) is untouched.
- Agents: none started.

## Done
- Read the lock form. The harness writes the agent lock as a git worktree lock reason `claude agent agent-<id> (pid N start S)`. The repo only reads it: `janitor/sweep.py` `AGENT_LOCK_RE`, `_ticks_lock_stale`, `stale_agent_lock_verdict`. A lock file lives at `<git-common-dir>/worktrees/<name>/locked`. No writer is in the repo.
- Part (a) not measured. `list_computer_folders` returned no folders (empty `folders` and `cannot_be_used`) at 2026-11-13 18:34 CST.

## Unfinished
- (a) measure the lock form a dead host leaves on Windows and on Mac.
- (b) if the ticks form occurs there: build the process-start read in `_ticks_lock_stale`, tests first (red then green, `Red-run:` trailers), tests not skipped on that platform's CI job.
- (c) if it never occurs: document the measured source in the docstring and keep the Windows/macOS keep-path test.

## Next step
Owner shares the repo checkout folder of one computer (Claude desktop app, Settings, Claude Code, Remote Control). Restart this lane, then `request_computer_folder`, then list lock files read-only and print each start field. One lane per computer; Windows first.

## Refused acts
None. No act was tried past the empty folder list.

## Owner rulings held
None filed by this lane. The lane brief grant (owner flywheel, 2026-11-11 22:38 CST) is a standing brief, filed in the inbox as step:dead-host-lock-form-off-linux, handoff, not-a-grant.
