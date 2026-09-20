# claude-settings

One source of truth for my user-level Claude Code config, read by local sessions and by cloud
sessions started from the desktop app / claude.ai/code.

| File            | Becomes                                              |
| --------------- | ---------------------------------------------------- |
| `CLAUDE.md`     | `~/.claude/CLAUDE.md` (through a one-line `@` import) |
| `settings.json` | `~/.claude/settings.json` (symlink locally, generated copy in the cloud) |
| `agents/*.md`   | `~/.claude/agents/*.md` (symlink per file locally, copies in the cloud) |
| `lint/*`        | `~/.claude/lint/*` STE linter and hook gate (same treatment)          |
| `hooks/*`       | `~/.claude/hooks/*` guard and session-start line (same treatment)     |
| `install.sh`    | Wiring for Linux/macOS and for the cloud setup script |
| `install.ps1`   | Wiring for Windows                                   |
| `.github/`      | The `gates.yml` workflow. Runs in this repository only, never installed |
| `actions/`      | Composite actions this repository publishes. Callers pin them at `@main` |

`settings.json` sets `outputStyle: "Concise"` (built-in style, needs Claude Code v2.1.237+),
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, and
`worktree.baseRef: "head"`.

## Local machine (Windows)

```powershell
git clone https://github.com/shivinate7/claude-settings C:\src\claude-settings
cd C:\src\claude-settings
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Result:

* `~\.claude\CLAUDE.md` contains one line, `@C:/src/claude-settings/CLAUDE.md`. Claude Code
  resolves `@` imports at session start, so after `git pull` the next session reads the new file.
  Nothing to re-run.
* `~\.claude\settings.json` is a symlink to the clone's `settings.json`, and each
  `~\.claude\agents\<role>.md` is a symlink to the clone's `agents\<role>.md`. Symlinks need
  Windows Developer Mode (Settings > System > For developers) or an admin shell. Without it the
  script copies the files instead, and installs a git `post-merge` hook in the clone. The loop
  is then: a merge lands on main, the next local session start pulls the clone, and the hook
  copies `settings.json`, `agents\*`, and `lint\*`. The hook copies only when the checked-out
  branch is `main`, so merging an unreviewed branch elsewhere never pushes its settings live.
  The hook also re-runs `install.ps1` when the pull changed it. A new landed folder or a changed
  hook body then needs no manual run. Both the hook and `install.ps1` log one dated line per run
  to `~\.claude\claude-settings-install.log`.
  The hook is a bandaid. When Developer Mode is on, re-run `install.ps1` once to get the real
  symlinks.
* Any existing `~\.claude\CLAUDE.md` or `settings.json` is backed up as `*.bak.<timestamp>`
  first. Merge keys you want to keep (for example a `permissions.allow` list Claude Code built up
  from "always allow") into the repo's `settings.json`, then commit.

Verify in a session: `/context` lists `~/.claude/CLAUDE.md` and the imported file under
**Memory files**. `/status` shows the Concise output style.

## Local machine (macOS, Linux)

```bash
mkdir -p ~/Developer
git clone https://github.com/shivinate7/claude-settings ~/Developer/claude-settings
cd ~/Developer/claude-settings
bash install.sh
```

Result:

* `~/.claude/CLAUDE.md` contains one line, `@~/Developer/claude-settings/CLAUDE.md`.
* `~/.claude/settings.json` is a real symlink to the clone. The same is true for each file
  under `agents/`, `lint/`, and `hooks/`. A `git pull` in the clone is the whole update, and
  the `SessionStart` auto-pull below runs that pull for you.
* Any existing `~/.claude/CLAUDE.md` or `settings.json` is backed up as `*.bak.<timestamp>`
  first. Fold keys you want to keep into the repo `settings.json`, then commit.
* Re-run `bash install.sh` only when a new file lands under `agents/`, `lint/`, or `hooks/`.
  A symlink needs no re-run for a change to a file it already points at.

macOS has Python 3 through the Command Line Tools, so the STE and guard hooks run. Check with
`python3 -V`. Install the tools with `xcode-select --install` if the command is missing.

## Cloud sessions (desktop app, claude.ai/code, `claude --cloud`)

Cloud VMs never see your machine's `~/.claude`, so the environment's **setup script** has to
recreate it. In claude.ai/code > environment settings, set the setup script to:

```bash
curl -fsSL https://raw.githubusercontent.com/shivinate7/claude-settings/main/install.sh | bash -s -- --cloud
```

Leave network access at **Trusted** (or add `raw.githubusercontent.com`, `github.com`, and
`codeload.github.com` to a Custom list).
This runs as root before Claude starts and writes:

* `/root/.claude/CLAUDE.md` = `@~/claude-settings/CLAUDE.md`
* `/root/.claude/agents/builder.md` and `reviewer.md` = copies of the repo files
* `/root/.claude/settings.json` = repo `settings.json` plus a `SessionStart` hook that re-runs
  the same one-liner, so each new or resumed session re-fetches both files.

Why the hook: Anthropic snapshots the VM after the setup script and reuses it for about 7 days.
The setup script alone would pin whatever was on `main` at snapshot time. The hook keeps it
fresh. Claude Code reads CLAUDE.md after SessionStart hooks finish, so the fetched files are live
in that same session. Editing the setup script text (any character) forces a fresh snapshot.

To make cloud sessions change only when you say so, pin a commit instead of `main`. Replace
`/main/` in the URL with `/<sha>/`. Set `CLAUDE_SETTINGS_REF=<sha>` as an environment variable on
the environment.

Verify in a cloud session: `/context` for the memory file, and ask Claude to run
`echo $CLAUDE_CODE_SUBAGENT_MODEL` (expect `sonnet`).

## Local auto-pull

`settings.json` carries a `SessionStart` hook that runs at every local session start. It reads
the `@` pointer in `~/.claude/CLAUDE.md` to find the clone, then runs a quiet `git pull --ff-only`
there. It exits at once in cloud sessions (`CLAUDE_CODE_REMOTE` is set). It prints nothing and
never blocks a session. No network, no clone, or a diverged branch all fall through silently. Claude
Code reads CLAUDE.md after SessionStart hooks finish (measured: a hook that rewrote CLAUDE.md
changed the same session's first answer), so a pulled change is live in that very session. The
cloud installer replaces this hook with its own refresh hook, so it never runs in the cloud.

## Subagent model gate

`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` is only a default: a model Claude passes when it spawns a
subagent, or a `model` field in an agent definition, outranks it. A `PreToolUse` hook on the
`Agent` tool closes the first gap. When the spawn names a model other than Sonnet or Haiku, the
hook returns `ask`. A permission prompt appears, in auto mode too, and you decide. CLAUDE.md
tells the orchestrator to make its case in one line before such a spawn. The hook does not catch
a `model` field in an agent file. Set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` to pin those to Sonnet
as well, at the cost of removing the ask path.

## Roles

CLAUDE.md names three worker roles. Two are shipped here as user-level agent definitions. The
third is Claude Code's built-in `Explore`.

| Role       | File                 | Tools                                   | Tree                       |
| ---------- | -------------------- | --------------------------------------- | -------------------------- |
| `builder`  | `agents/builder.md`  | all                                     | own worktree, from `head`  |
| `reviewer` | `agents/reviewer.md` | all except `Edit`, `Write`, `NotebookEdit` | caller's checkout       |
| `Explore`  | built in             | read-only                               | caller's checkout          |

`worktree.baseRef: "head"` makes a builder's worktree branch from the orchestrator's current
branch instead of `main`, so a second-round builder sees the first round's commits. A worktree
holds tracked files only: a repo with heavy dependencies adds a `.worktreeinclude` for its env
files and an install step to the brief.

**Workers never spawn.** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` removes the `Agent` tool
from every subagent, so only the main conversation fans out. Reason, as of September 2026: a
nested child's completion notice goes to the main conversation or is dropped. The subagent that
launched it never hears back and waits forever
([anthropics/claude-code#75043](https://github.com/anthropics/claude-code/issues/75043),
[#86782](https://github.com/anthropics/claude-code/issues/86782),
[#88545](https://github.com/anthropics/claude-code/issues/88545)). Claude Code's cloud
environment already runs at depth 1. This setting makes local sessions match. A repo that needs
nesting sets a higher depth in its own `.claude/settings.json` and records the stall risk in its
CLAUDE.md. Re-check those issues before raising it here.

A project-level `.claude/agents/builder.md` with the same `name` shadows the user-level file, so
a repo can specialize a role and note the change in its CLAUDE.md.

## STE lint gate

CLAUDE.md asks for Simplified Technical English and a fixed report shape. Hooks in
`settings.json` enforce the parts a machine can check, at error severity only:

| Hook | Trigger | Effect |
| --- | --- | --- |
| `PreToolUse` on `Write`, `Edit`, `MultiEdit` | the target path ends in `.md` | the write is denied and the findings come back, so Claude fixes the text and writes again |
| `Stop` | this turn wrote a markdown file through any tool, Bash included | the turn is blocked once, and each file and finding is named. See Markdown sweep below |
| `Stop` | end of a turn | a warning is shown as a system message. The turn is not blocked |
| `Stop` | the turn ran `git commit`, `git push`, `git merge`, or a GitHub MCP write tool | the turn is blocked once unless the reply is one blockquote with the bold labels Done, Deviations, Input Needed, Next in order, written tight in Simplified Technical English |
| `Stop` | any project config file changed, a merge into main landed, or the guard could not read the subject of a discarding git call, this turn | a system message names each changed `.claude/settings.json`, `.claude/settings.local.json`, or `.claude/hooks/*` path, each `gh pr merge` or GitHub MCP merge call, and each command whose subject was unreadable, so the reply can name them in the report. See `hooks/config_report.py` |
| `PreToolUse` on `Bash`, `PowerShell`, `Read`, `Grep`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and the GitHub merge tool | a call matches a guard rule | the guard answers deny, ask, or nothing. See Guard below |
| `SessionStart` on `startup`, `resume` | every local session start or resume | the session-start line prints. See Guard below |

The first `Stop` hook is a Sonnet agent guardrail that checks the turn against recorded
decisions, gates, build-orders, CLAUDE.md rules, and settings values. It reports a finding as
a system message and never blocks the turn.

Errors are: a sentence over the STE budget (STE001), a semicolon (STE006), a Latin
abbreviation such as `i.e.` (STE007), a contraction (STE008). Warnings such as passive voice
and paragraph length are not gated. Fenced code and inline code are exempt. Table cells are not.

The linter is `lint/ste_lint.py`, vendored from
[DotDebian/asd-ste100-skill](https://github.com/DotDebian/asd-ste100-skill) at commit
`e71a969`, MIT, license in `lint/LICENSE-ste_lint`. It is Python 3.9+ with no dependencies.
It carries one local patch: a closing `**`, `*`, or `_` after a sentence end also ends the
sentence, so `**Bold.** Next.` reads as two sentences.
The STE gate is `lint/ste_gate.py`. The report gate is `lint/report_gate.py`. It checks the
shape only, not the wording, and it fires only after a landed commit, push, or merge. Both
gates share one fixture suite, `lint/test_gates.py`. Its cases are the check that proves each
gate goes red on the defect it guards. The hook command exits silently when the files or
Python are missing, so a machine without Python runs without the gates. The cloud image has
Python 3.11. On Windows, install Python and make sure `python3` or `python` is on the PATH of
Git Bash.

Run it by hand:

```bash
python3 ~/.claude/lint/ste_lint.py CLAUDE.md            # all severities
python3 ~/.claude/lint/ste_lint.py --fail-on error docs/  # what the gate checks
python3 ~/.claude/lint/ste_lint.py --explain STE006
```

The linter is an approximation of ASD-STE100, whose dictionary is not open. Verified before
merge: the old Roles paragraph with its semicolon goes red, the current CLAUDE.md is clean at
error level.

## Guard

`hooks/guard.py` is a `PreToolUse` hook on `Bash`, `PowerShell`, `Read`, `Grep`,
`Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and the GitHub merge tool. It answers
deny, ask, or nothing. It fails open on bad input.

| Rule | Tools | Decision | Remedy |
| --- | --- | --- | --- |
| Shared trees, with a subject to take: `git stash push`/`save`/bare, `stash drop`, `stash clear`, `git reset --hard`, `git restore` with neither flag or with `--worktree`, `git clean -f`, `git checkout <path>` | `Bash`, `PowerShell` | deny in a shared checkout, ask in a git worktree | mutation-test with a `.bak` copy, commit work you must set aside on your own branch, or work in a worktree of your own |
| Reads and safe restores in the same trees: `git stash list`/`show`/`apply`/`pop`, `git reset` with no flag, `--soft`, `--mixed`, `--keep`, `--merge`, or a path, `git restore --staged` alone | `Bash`, `PowerShell` | allow | nothing to do. Each one reads, or puts work back, or touches only the index, and git itself refuses to overwrite a modified file |
| An empty subject: the same commands when `git status --porcelain` is empty, or empty for the paths they name, or holds no untracked entry for a `clean -f`, or when `git stash list` is empty for a `stash drop` or `stash clear`. For `git reset --hard` the target must also be `HEAD` or absent | `Bash`, `PowerShell` | allow | nothing to do. The command takes nothing, so it destroys nothing |
| `git reset --hard <any other commit>`: a branch, a tag, a raw sha, `HEAD~1` | `Bash`, `PowerShell` | deny in a shared checkout, ask in a git worktree, whatever the tree holds | the branch moves, so another session in that checkout lands on rewritten history. Reset your own worktree, or name the commit in a new commit on your own branch |
| An unreadable subject: git gives no answer to the status read or the stack read | `Bash`, `PowerShell` | allow, logged `noted`/`subject-unread`, and named in a system message at turn end | name it under Deviations in the report. A refusal whose ground could not be read is a guess |
| This session's own scratchpad: a tree whose real path lies under the session scratchpad the hook payload names | `Bash`, `PowerShell` | allow | nothing to do. No other session and no editor holds that tree |
| A directory that is no git tree | `Bash`, `PowerShell` | deny in a shared checkout, ask in a git worktree | nothing was read there, so the refusal stands |
| Conflict side: `git checkout --ours`, `--theirs`, `--merge`, with a merge, rebase, cherry-pick, or revert in progress | `Bash`, `PowerShell` | allow, logged `noted`/`conflict-resolve` | nothing to do. The call picks a side, it discards no uncommitted work |
| Silent write: `commit`, `push`, `merge`, `tag`, `rebase`, or `cherry-pick` with a redirect of either stream to `/dev/null`, `NUL`, or `$null`, or `push`, `merge`, or `rebase` (MEASURED) with `-q`/`--quiet` alone | `Bash`, `PowerShell` | deny | run the same write without silencing either stream, and read what it prints. `commit -q`, `tag -q`, `cherry-pick -q`/`--quiet` alone, `merge --abort`, `fetch`, and every read subcommand pass |
| Machine-wide kills: `pkill`, `killall`, `lsof -t`, `taskkill /IM`, `Stop-Process -Name`, in command position only | `Bash`, `PowerShell` | deny | name one PID this session started |
| Force push: `--force`, `-f`, `--force-with-lease` | `Bash`, `PowerShell` | ask | the click in the prompt is the grant |
| Recursive delete at `/`, `~`, `.`, `*`, or a drive root | `Bash`, `PowerShell` | deny | name the folder |
| Environment files: any `.env*` except `.env.example` | `Read`, `Grep`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and shell text | deny | ask the user for the value. Loader flags such as `--env-file` and existence checks with `ls` or `test` pass |
| Merge into main: `gh pr merge`, and every `mcp__github__merge_pull_request` call | `Bash`, `PowerShell`, MCP | allow, logged `noted`/`merge-main` when the base is `main` or unreadable, and always for the MCP tool, and named in a system message at turn end | name it under Done in the report |
| Frozen paths: `settings.json`, `CLAUDE.md`, `hooks/*`, `lint/*`, `agents/*` under `~/.claude` | `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and shell writes | deny | edit the clone of claude-settings and open a PR |
| Project config: a project's own `.claude/settings.json`, `.claude/settings.local.json`, `.claude/hooks/*` | `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and shell writes | allow, logged `noted`/`config-edit`, and named in a system message at turn end | name it under Deviations in the report |
| Live streams: `tail -f`, `tail -F`, `--follow`, `Get-Content -Wait` | `Bash`, `PowerShell` | deny | run it in the foreground with a timeout, or in the background and wait for the completion notice |
| Waiter loops: a segment whose command word is `sleep`, `Start-Sleep`, or `timeout /t` | `Bash`, `PowerShell` | deny | run the long command in the background and wait for its completion notice, or use a tool that waits once, such as `gh run watch <id> --exit-status` (avoid `gh pr checks --watch`, which serves a cached status) |

The harness watcher tool `Monitor` is removed through `permissions.deny` in `settings.json`. It
errors often, and a background command with a completion notice does the same job.

### Decisions

1. Discards and force push: **ask or deny, no tokens.** Deny `git stash`, `git reset`, `git restore`, `git clean -f`, and a `git checkout` that names a path when the cwd is a shared checkout. Answer `ask` for the same commands when the cwd is a git worktree, and `ask` for `git push --force` or `-f` anywhere. The user's click in the permission prompt is the grant. Reason: q_max's `GIT_DISCARD_OK=1` and `DESTRUCTIVE_OK=1` tokens pass silently and are typed by the agent, so nothing proves the user was asked.
2. Merge into main: **ask always.** `gh pr merge` whose PR base is `main` (read with `gh pr view <n> --json baseRefName`, and `ask` when unreadable), and every call of the `mcp__github__merge_pull_request` tool. A merge into any other base passes. No `OWNER_MERGE=1` token. Superseded by Decision 8.
3. Composite action pin for callers: **`@main`.**
4. STE in CI, refined: **changed lines only** against the PR base by default. A finding counts only when its line sits in an added or changed hunk of the diff. Findings on untouched lines of a changed file show in the step summary and never fail the build. A `scope: all` input runs the whole tree in report mode and never fails the build, for manual audits from the Actions tab. Reason, measured on q_max: whole-file scope made the first branch to touch an old document pay that document's whole backlog.
5. Stamping of decision records: **stays local** in each repo. Formats differ (`D100_<slug>.md` per kind by date in job-cost-reporting, `<slug>.md` with `id: pending` in first-parent order in q_max). Do not touch it.
6. Extras: add the SessionStart checkout line. No scheduled audit, dispatch only. No stamp work.
7. Project config edits: **allow and report.** An edit to a project's `.claude/hooks/*`, `.claude/settings.json`, or `.claude/settings.local.json` is allowed in any checkout. It is logged in `guard.log`, listed in a system message at the end of the turn, and named under Deviations in the report. Paths under `~/.claude` stay denied, the clone of claude-settings is the way. Reason: the owner is often away from the desk. The work is not sensitive enough for a hard wall, and a change seen at turn end is enough.
8. Merge into main: **allow and report.** Supersedes 2. `gh pr merge` into `main` and the `mcp__github__merge_pull_request` tool are allowed, logged in `guard.log` as `noted merge-main`. Both are listed in the system message at turn end and named under Done in the report. `Bash(gh pr merge:*)` sits in `permissions.allow` so the harness does not prompt either. CLAUDE.md's "merged only when I name the act" stays the model's rule. Reason: the owner says merge in chat and the guard cannot read chat. The prompt only repeats a decision already made.

9. Command resolution: **resolve the act, never match the spelling.** A rule that names a program fires only when that program sits in command position in a segment. Segments come from `split_segments`, which tracks quotes. Tokens come from `shlex`. Wrappers such as `sudo`, `env`, `xargs`, and `nohup` are unwrapped, so `xargs pkill` still denies. A command the tokenizer cannot parse fails open. Reason, measured: a bare `\bpkill\b` over the whole command string denied `grep -n -i "...|make reap|pkill..." CLAUDE.md`, a search for the word. The file already held the right standard in its flag-aware helper. That helper told `lsof -ti` from `lsof -i :3000`. The four regexes above it skipped the step.

10. The conflict side of a merge: **allow and log.** `git checkout --ours`, `--theirs`, or `--merge` is allowed when git reports a merge, rebase, cherry-pick, or revert in progress in the tree the command acts on. The state comes from `MERGE_HEAD`, `REBASE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, and the rebase directories, never from the command text. Unknown state keeps the old decision. Reason: that call picks a conflict side. It discards no uncommitted work, and git does not let a tree leave a conflict silently. Every other path-naming checkout keeps Decision 1.

11. Late markdown check: **block the turn once.** The `PreToolUse` gate sees `Write`, `Edit`, and `MultiEdit` only. `lint/md_sweep.py` runs at `Stop`, lints each markdown file this turn wrote through any tool, and blocks once at error severity. Scope is this turn only, read from the transcript, so an old document is not this turn's debt. `MD_SWEEP_DISABLE` turns it off and `MD_SWEEP_EXCLUDE` takes globs for generated markdown. The sweep reads a literal path only. A path held in a shell variable stays out of scope, a limit written down rather than left silent. Reason, measured: an 830-line CLAUDE.md landed through a Bash heredoc with no check. The operating instructions for a session prefer Bash, so the default path skirted the gate. A gate a lane can skip by picking another tool is not a gate.

12. Shared trees, `stash`/`reset`/`restore`: **judge the act, not the subcommand name.** `git stash list` and `git stash show` read and always allow. `git stash apply` and `git stash pop` allow: they put work back, and git refuses to overwrite a modified file rather than clobber it (MEASURED against a real conflicting change, 2026-09-17). `git stash`, `stash push`, and `stash save` keep the deny-or-ask split, because git does not refuse them and the moved work leaves the working tree. `stash drop` and `stash clear` keep deny-or-ask: they destroy stashed work with no way back. `git reset` allows with no flag, `--soft`, `--mixed`, `--keep`, `--merge`, or a pathspec. None of these can lose an uncommitted change. MEASURED the same day. A bare reset and `--soft` leave the working tree file untouched. `--keep` and `--merge` abort with "Entry not up to date" against a modified file, rather than overwrite it. A path-scoped reset touches only the index, and git itself refuses to combine `--hard` with a path. `git reset --hard` keeps deny-or-ask: it rewrites the working tree unconditionally. MEASURED: an uncommitted line was gone after it. `git restore --staged` alone allows: it writes only the index (MEASURED: an uncommitted line survived). `git restore` with neither flag, with `--worktree`, or with both, keeps deny-or-ask: the working tree is the default write target, and MEASURED runs of each form lost the uncommitted line. Reason: the guard denied `git stash list`, a read, and the owner's `git stash apply stash@{0} 2>&1 | tail -10`, which puts work back, because `shared_tree_hit` matched the subcommand name alone. The same defect, one name standing in for every act under it, had already produced the `pkill` false positive and the conflict-side checkout fix (Decision 9, Decision 10). This closes the third instance for `stash`, `reset`, and `restore` together, table above.

13. The orchestrator and product code: **judge the act, not the file.** This session writes records, docs, and briefs. Building goes to a lane, with one exception: a small fix, under 10 lines, named in the report. Reason, measured here: "It never edits product code" read as a file test. It blocked a decision entry, which is orchestration, and charged a whole lane for one comment.
14. Setting work aside: **commit it, never stash it.** A lane that must park uncommitted work makes a commit on its own branch. Reason: a stash entry belongs to no branch. Only the session that holds the tag can find it again, and that session can die. The work is then unreachable in a tree where the next reader sees an empty stack. A commit survives the session, pushes with the branch, and any reader of the branch can see it. This states the remedy the guard already owed: `git stash push` is denied in a shared checkout (Decision 12), and the refusal now names the commit as the way out.

15. Shared trees, the subject: **read it before you refuse over
it.** This extends Decision 12 one level up. Decision 12 judged the subcommand name. This
judges what the command would take.

MEASURED on `6e179ae` with the real hook. `git reset --hard HEAD` in a clean tree
answered deny. Nothing was uncommitted, so nothing could be lost. `git reset --hard HEAD`
and `git stash push -u -m t` in a fresh `git init` repository under the session scratchpad
answered deny too. No other session can reach that repository.

`git reset --hard` passes on a clean tree only at `HEAD`, or with no target at all. A
`reset --hard` that names any other commit keeps the deny-or-ask split, whatever the tree
holds. The reason: that form MOVES THE BRANCH. Another session in the same checkout then
lands on rewritten history. The reflog that recovers the commit belongs to the tree that
ran the reset, not to theirs. The outcome this rule protects is the other session's tree.

The guard now makes the two reads git itself makes. `git status --porcelain` is the
subject of five arms. They are `reset --hard`, `restore` in the forms that write the
worktree, `stash push`/`save`/bare, `checkout <path>`, and `clean -f`. `git stash list` is the
subject of `stash drop` and `stash clear`. An empty subject allows.

For `checkout <path>` and `restore <path>` the pathspec goes to `git status --porcelain --
<paths>`. The pass is then per path, and git resolves the path, the directory and the
glob. For `clean -f` the subject is the untracked part of that output. `-x` or `-X` widens
it to the ignored part.

A subject git cannot answer for allows. The guard logs `noted`/`subject-unread`, and the
system message at turn end names it. A refusal that cannot read its own ground is a guess.
A directory that is no git tree is NOT an unreadable subject. git answers "no tree"
there, so that deny stands.

A tree whose real path lies under the scratchpad of the session the hook payload names
allows. The test is the path alone, and it resolves symlinks on both sides. No token and
no override: the deny-or-ask split and the permission click stay the grant (Decision 1).

MEASURED after the change, on the same probes, with a real uncommitted line added for the
dirty rows. A clean tree allows `git reset --hard HEAD`. A dirty tree denies it. The dirty
scratchpad repository allows for this session's id, and denies for another session's id.
In the clean tree, `git reset --hard HEAD~1`, `origin/main`, and a raw sha each deny.

- **silent-write-leaves-a-trace**: **deny a discarding redirect always. Deny the
  quiet flag only where it measures the same way.** `commit`, `push`, `merge`,
  `tag`, `rebase`, and `cherry-pick` deny on a redirect that sends either stream
  to a null device. The shell throws the stream away before git gets a say. A
  refusal and a proof of landing are both gone, on any of the six. git's own
  `-q`/`--quiet` flag is judged per subcommand instead of by name. MEASURED
  2026-09-19 and 2026-09-20, in throwaway repos, never a shared checkout, all
  six. Each was checked across a write that succeeds, one a hook or a real
  conflict refuses, and a no-op.

  `push`, `merge`, and `rebase` deny on the flag alone. Each one's success and
  its own no-op are both silent at exit 0. Without the flag they already
  differ, by a line such as "Everything up-to-date" or "Successfully
  rebased". The flag erases that line. A session cannot read whether the
  write it just ran moved anything.

  `commit`, `tag`, and `cherry-pick` carve out. `commit -q` leaves a hook's
  refusal on stderr and a no-op's message on stdout, both at a nonzero exit.
  A silent exit-0 commit is already unambiguous. `tag` has no `-q` or
  `--quiet` at all. Both spellings exit 129 with an unknown-option error,
  before git reads the tag name or the repository state. Every state
  measures the same. `cherry-pick`'s short form fails the same way. Its long
  form still prints a full commit summary, a full conflict, or a full
  "nothing to commit" in every state, so nothing is silenced either way.

  A discarding redirect still denies any of the six, carve-out or not.
  `merge --abort` passes, because it lands nothing. `fetch`, `rev-parse`, and
  every other read subcommand pass too. Reason: CLAUDE.md says never discard
  a command's output. pkmnscan's `scripts/silent-write-guard.py` carries the
  measurement this rule ports. A coordinator reported work as landed twice
  in one session, when it had not. Once, a refusal was discarded. Once, a
  proof of landing was discarded. The bare flag turned out to be a narrower
  claim than the redirect, and a different claim for each subcommand. Only
  the measurement above told them apart. No number is claimed here. The
  entry is a slug, and the number waits for merge (CLAUDE.md: never allocate
  a numbered record on a branch).

Every deny or ask appends one line to `~/.claude/guard.log`: timestamp, tool,
decision, rule, and the matched text cut at 120 characters. Allows are never
logged. This is how a false positive gets measured later.

Both job-cost-reporting and q_max keep their own guards until a week of clean
`guard.log` on both machines. After that, each repo trims to what only it
owns. That is a later task.

`hooks/session_start.sh` prints `checkout <toplevel> on <branch>, <n> dirty
files` at local session start and resume. It stays silent outside a git tree.
The cloud install replaces the `SessionStart` list, so this line is local
only.

Run the fixture suite with `python3 ~/.claude/hooks/test_guard.py`. Each case
is the check that proves a rule goes red on the defect it guards.

`hooks/mutate_guard.py` breaks one rule at a time in a copy of `guard.py`. It
expects the fixture suite to go red. CI runs it on every push and pull request.

## CI

`.github/workflows/gates.yml` runs on push to `main`, on every pull request, and on manual
dispatch. Each run sets up Python 3.11. It then runs the guard suite and the guard
mutation harness. It also runs the report-gate suite, a shell check of `install.sh`, a
PowerShell parse of `install.ps1`, and the STE lint action.

Manual dispatch takes one input, `full_ste_audit`. Enable it from the Actions tab to lint
the whole tree in report mode. That run never fails the build. It only writes a summary.

`actions/ste-lint` is the composite action behind the STE step. Scope `changed` diffs
markdown against the pull request base, or the default branch on a push. It then gates only
the added or changed lines of that diff (Decision 4). A finding on an untouched line of a
changed file still shows, under "Pre-existing, not gated", and never fails the build.

Scope `all` lints every file the `paths` glob names, in report mode, and never fails the
build. Input `fail` sets whether an in-hunk error blocks the step. Input `exclude` drops
newline- or comma-separated pathspecs from both scopes, for a generated file the linter
should never see. The action always writes a step summary, with the file count, the excluded
count, both counts by group, and a findings table for each group.

A caller pins the action to `@main`:

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- uses: shivinate7/claude-settings/actions/ste-lint@main
  with:
    scope: changed
    fail: "true"
    exclude: docs/Decision_Index.md
```

The caller needs `actions/checkout` at `fetch-depth: 0`. Scope `changed` diffs against a
branch, and a shallow clone carries no history for the diff.

One manual step remains, in this repository only. Open Settings, then Actions, then
General, then Access. Set "Accessible from repositories owned by the user". That setting
applies to a private repository only. This repository is public, so any repository can
call the action today. No file sets this switch. Flip it after this pull request merges,
before the first external caller runs.

## Editing

Edit `CLAUDE.md` or `settings.json` here, commit, push. Local picks it up on `git pull`. Cloud
picks it up on the next session start.

A new role is a new `agents/<name>.md`. A linter change is a change to `lint/`. A guard change is
a change to `hooks/`. Locally, re-run the installer once so the symlink exists. In copy mode, the
post-merge hook copies `settings.json`, `agents\*`, `lint\*`, and `hooks\*` on the next pull. It
copies only when the checked-out branch is `main`, so a merge on any other branch leaves
`~\.claude` untouched. It also re-runs `install.ps1` itself when the pull changed it. So a new
landed folder or a changed hook body needs no manual run. Check
`~\.claude\claude-settings-install.log` for a dated line from each run. Cloud picks it up on the
next session start.

Hooks in `settings.json` run everywhere the file lands. Command hooks use `sh` syntax, which Git
Bash runs on Windows. Guard anything local-only with `CLAUDE_CODE_REMOTE`. The cloud install
replaces the `SessionStart` list with its own refresh hook and leaves every other event alone.
