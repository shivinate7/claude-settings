# Install copies from main, not links into the clone

**What waits.** On a local install, each file under `~/.claude` is a symlink into the clone.
PR #164 made the guard freeze a config path by its literal path or its resolved path. So an
edit through `~/.claude/...` is refused. The clone itself stays unfrozen on purpose, so a
broken hook can be fixed (decision recovery-must-not-gate-on-its-own-state, a recovery
control must not depend on the state it recovers). Because of the links, an edit to
`<clone>/hooks/guard.py` is live at once, with no pull request. A session can still grant
itself powers through the clone.

**The idea.** Both installers copy files instead of linking them, and they copy from
`origin/main`, not from the clone's checked-out branch. The live config then changes only
through a merged pull request. The SessionStart hook already runs the installer each
session. A manual install from a named branch stays possible, as the deliberate recovery
path.

**What it costs.**
- A merged change goes live at the next session, not at once.
- The installers must prune stale copies. That needs a record of what the last run landed,
  kept outside the landed folders (install.sh names this gap in its cloud-mode comment).
- Both installers change, with tests on macOS and Windows.

**Why it waits.** The owner ruled on 2026-09-28 to build it later.

**Trigger that brings it back.** The next change to either installer. Also any sign that a
session edited the clone's hooks, settings, or CLAUDE.md without a pull request.

**Owner.** The claude-settings orchestrator that takes the next installer change.
