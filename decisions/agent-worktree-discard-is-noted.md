# An agent's discard in its own worktree is noted, not asked

## The question

The shared-tree rule asks the owner before a discarding git command
runs. The commands are `git reset --hard`, `git checkout -- <path>`,
and `git restore`. The ask fires inside any linked worktree. Is that
ask earned when the worktree is one the harness made for an agent, not
a person?

## Measured facts

18 shared-tree asks sit in `~/.claude/guard.log` since 2026-09-16. The
owner reports the prompt is frequent in agent-heavy repos. There, it
carries nothing to judge. The lane is the agent's own. The agent's
commits already sit on its own branch. They sit in its own reflog too,
before any discard runs.

## Ruling (owner, 2026-10-03)

Take a linked worktree. Its resolved path sits under
`<main repo root>/.claude/worktrees/`. Call that an agent-owned
worktree. Inside it, a discard is ALLOWED. It is logged as a note, with
no prompt. A linked worktree anywhere else keeps "ask". The main
checkout keeps "deny". Four things stay unchanged: branch-delete deny,
worktree-remove deny, worktree-prune ask, and every stash deny.

**What the old ask protected.** A person's own uncommitted work in a
worktree they made by hand. There, a discard has no other copy.

**What protects it now.** The ask stays for every worktree outside
`.claude/worktrees/`. A person's own lane keeps the prompt there. Inside
an agent's own worktree, the story differs. The agent's commits are the
copy. They sit on the agent's own branch. They sit in its own reflog.
A discard there loses nothing the clone does not already hold
elsewhere.

## The rule

hooks/guard.py, rule 1, beside `is_worktree`, holds the check:
`agent_owned_worktree(root)`. It resolves `root` with a real path. It
resolves the primary checkout's `.claude/worktrees/` the same way. The
reads are `primary_checkout` and `path_is_inside`. `agent_worktree_home`
already uses both. This keeps three near misses out: a `..`-spelled
path, a decoy main checkout nested under a look-alike folder, and a
symlink that climbs back out. Each is judged on where it really sits,
never on a "worktrees" segment in its spelling. A hit logs
`record(tool, "noted", "shared-tree", matched)` and allows. A miss keeps
the existing ask.

## Lint

This record changes the gate's verdict for a real class of commands.
A reviewer reads this diff.
