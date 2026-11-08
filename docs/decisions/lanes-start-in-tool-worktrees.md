# Lanes start only in the tool's own worktrees

## The ruling

Owner, 2026-10-21: refuse the hand-made worktree fully, and record which layer refused isolation. A worktree comes only from the Agent tool's `isolation: 'worktree'` or the EnterWorktree tool. `hooks/guard.py` rule `hand-made-worktree` refuses the workaround.

- **The act.** A shell call (Bash or PowerShell) that holds a real `git worktree add`, read with `git_calls`, whose new tree resolves outside `<primary>/.claude/worktrees/`. `<primary>` is the primary checkout of the repo the call runs in: its last `cd`, its `-C`, or the payload cwd. A relative path resolves against that folder. A Windows path counts.
- **Passes.** A new tree under `.claude/worktrees/`. A repo under the temp folder, such as a test fixture: the rule judges the repo, not the target, so a real repo that adds a tree into a scratchpad is refused. Every other `worktree` subcommand, `--help`, and text that only mentions the command. A non-git folder or an unreadable primary is unknown, and allows (`verification-report-unknown-reads`).
- **Not read.** Brief prose. An Agent or Task spawn with no isolation passes, whatever paths its prompt names: a read-only Explore spawn needs no tree, and a guard that reads prose cries wolf (`verification-cry-wolf-guard-is-spent`).
- **The refusal** names the two tools, never the refused path or command (`git-remedy-never-names-target`). It tells the session, when the tool's isolation was refused, to make no tree by hand and to report which layer refused and its exact message: a guard refusal names its rule and holds `Rule (`; any other refusal is the harness's.
- **The pointer remedy** (`pointer-head`) names the EnterWorktree tool, not a hand-made worktree, so the two rules never contradict.
- **An owner override lifts it** (`owner-override`).

Why: an agent spawned with no isolation starts in the main clone, and no hook payload field ties it to a hand-made tree, so `worktree-home` (`an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop) cannot fence it. Without the hand-made tree, the workaround has nothing to brief the agent into.

Named limits, each a form Claude rarely writes:

- A tree that already exists outside `.claude/worktrees/` (the owner's own, or one made before this rule) can still be named in a brief.
- A `git worktree add` inside `bash -c`, `sh -c`, `eval` or `powershell -c` passes: the guard leaves those strings unparsed, a known gap.
- A repo named only by `--git-dir`, and a target that holds a variable (`$HOME/wt`), read as unknown and pass.
- A hand-typed read-only checkout (a review or a "before" image) is refused. EnterWorktree serves that need too.

Which layer refused on 2026-10-19, by reading, unmeasured live: the harness. That day `hooks/guard.py` judged an orchestrator's Agent call by model rules only, and each of their refusals names a model; `worktree-home` reads only an agent's call. The Agent prompt hook in `settings.json` judges brief contents, and its refusal names a rule id. This repo had no `WorktreeCreate` hook. The harness's message was not recorded. The next refusal's layer and message are still owed: the refusal text asks the session to report both.

Risk kind: incident, per `building-guard-needs-incident`: 2026-10-20 16:53 CDT, two agents wrote into the main clone. Landed 2026-10-26.

Cost, per `outcomes-mechanize-rules`: process starts, one `git` read per `git worktree add` call, none on any other call (unmeasured). Files written: none on an allowed call; a refusal adds one line to `guard.log` (not pinned here), which `lint/guard_log_report.py` reads.

### A fix round

The orchestrator starts each fix round as a fresh agent spawn with `isolation: 'worktree'`. The new worktree starts from the lane branch head.

The orchestrator resumes an agent by name only when that agent died mid-round (`roles-resume-by-name`: resume a dead agent by name, never fresh). A resumed agent keeps its old worktree. `worktree-home` (an agent stays in its recorded home) keeps it there.

Why: a test-author worktree, resumed for a fix round, held staged copies of four files. The copies equal the old branch base, because the branch ref had moved under the index. Committing them would have undone a merged PR.

Each agent runs `git diff --cached --stat` before each commit. The list names only the files that the agent changed this round. Any other file means the branch moved under the worktree. The agent commits nothing and reports it.

`COMMON`, the standing-rules list in `hooks/agent_brief.py` (the SubagentStart hook), carries the staged-diff step (`git diff --cached --stat`) to each agent type that commits, meaning each type not in `READ_ONLY`. A test in `hooks/test_agent_brief.py` checks that each committing agent in `agents/` gets it. Still, no hook or check stops a commit that skips the step.

- The orchestrator never `cd`s into an agent's worktree. It reads that tree with `git -C <path>`.
- The cloud platform's Stop hook (`~/.claude/stop-hook-git-check.sh`) is written by the platform, not this repo. It checks git in the shell's current folder. A `cd` by the main session persists.
- Incident: the hook read a worktree of base copies. It asked to commit and push them. That push would have undone a merged PR.
- Orchestrator's call, 2026-11-01 23:39 CST: no patch to the platform's script.
- Orchestrator's call, same time: a tree that holds only base copies can be removed. See the worktree-removal decision, `when-a-worktree-may-be-removed`.

Risk kind: incident, 2026-11-01 22:41 CST, worktree of lane `merge-lock-record-drift`.

Kind: build
Plan: docs/decisions/lanes-start-in-tool-worktrees.md#the-ruling (all)
