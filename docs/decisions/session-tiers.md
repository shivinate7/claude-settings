# Session tiers

## The ruling

Owner rulings, all 2026-10-28 CDT. They name the session tiers and how they talk.

- **Session shape** (owner, 15:18). A new session in a repo reads what the owner asks, and picks one shape.
  - Solo. It builds the change itself.
  - One lane. It runs one line of work, and it orchestrates its own agents.
  - Coordinator. It runs a standing build. It starts triage and the batch runner, then lane sessions.
  - The owner's ask (15:04): revise the solo-versus-orchestrate rules to match these tiers, with an Opus review. The roles rules in `CLAUDE.md` now carry the shapes.
  - The shape stays dynamic. A session may grow to a larger shape (`roles-solo-grows-switch-to-orchestrate`). It says so in one line.
- **Orchestrator, the catch-all word** (owner, 15:18). Any session that spawns agents is an orchestrator. Coordinator, triage, batch runner and lane session are kinds of orchestrator. Analogy: a square is a rectangle.
- **A coordinator in another repo** (owner, 15:18). A coordinator may work in another repo, by hand-off or by its own lane PR there. No hard block applies. Before it acts, it checks whether that repo has an active coordinator. If one is active, it coordinates with that coordinator. If none is active, it proceeds. It does not hold back for lack of a reply.
- **Who starts which session** (owner, 15:18). The coordinator is the one session that starts other sessions. It starts triage and the batch runner together, as a trio, before any lane session. This refines the triage-first ruling below.
- **Rotation of standing sessions** (owner, 15:23). Triage and the batch runner each report a tally of their own use, in turns or context, to the coordinator. When a tally nears its limit, the coordinator has that session write its handoff, archives it, and starts a fresh one from the handoff. The coordinator writes its own handoffs and compacts as today.
  - MEASURED (coordinator, 2026-10-28; the second reading at 17:53 CDT, the first's time not given): `get_session` on a child session returns `external_metadata.context_usage` (`used_tokens`, `max_tokens`) and `autocompact_state` (`threshold`, `effective_window`). The q_max lane read 171216 of 500000, threshold 384000. A lane in the owner's environment "lane test" read `max_tokens` 200000, so a per-environment context window works for a cloud lane.
  - So the coordinator can read each standing session's tally itself. Dropping the self-report needs the owner's grant.
- **No coordinator succession** (owner, 15:24). Handing children to a new coordinator failed in the owner's runs, in two ways.
  - A child refused the new coordinator as not its parent. That was a safety reflex.
  - A child missed a message while busy, after the old coordinator archived itself.
  So a coordinator never hands its children to a successor. It writes its own handoffs and compacts in place.
- **Coordinator.** One coordinator runs each repo (owner, 14:59): "one coordinator per repo is exactly/indeed what i meant ... coordinators even talk to one another on my local setup if they need to share something like an iphone simulator on the pc because its under load ... coordinators can touch multiple repos if need be, but yes it's laregly to manage its own repo's lanes."
  - Coordinators may talk to one another. The reason is a shared scarce machine, such as an iPhone simulator under load.
  - A coordinator may touch several repos. Its main job is its own repo's lanes.
  - claude-settings is the special case. It touches every repo a little.
- **Triage.** Triage is a standing session (owner, 15:03).
  - Owner, 15:03: "triage should always be a standing session that if anything is the first thing a coordinator spawns before it spawns any other orchestrator sessions".
  - Triage may run agents (owner, about 14:55).
  - Triage is the only writer of the roadmap and the waiting page (owner, 2026-10-28, time not given).
- **Lane session.** A lane session runs its own lane as an orchestrator. It spawns its own builder and reviewer agents under `agent-model-cap` (the model per role). It reports up to the coordinator. Owner, about 14:52, in short: sessions that spawn under a coordinator are their own orchestrators, reporting up to it.
- **Lane session model** (owner, 16:15, waiting item 50, pick b). A lane session runs Opus. It keeps itself light, but it needs top reasoning on what it is asked.
  - The helpers it starts, such as a builder or a designer, keep today's model and effort table in `agent-model-cap` (owner, 17:50, waiting item 59, pick a), until their cost and quality are measured.
- **Overlapping files.** No coded guard and no file-ownership record covers lanes that touch the same file. A good brief is enough. Orchestrators resolve overlapping edits. The owner wants better file splitting (owner, 15:01). A false "done" is already covered. The shared merge tool, `merge/merge.py`, reads the head and CI from GitHub.
- **Batch runner.** A third standing role (owner, 15:11): "B for sure actually". The batch runner owns:
  - the integration batch,
  - the CI waits,
  - the merge tool runs,
  - archiving finished lanes.
  The coordinator holds only lane state and talks with the owner.
- **Wrong tier.** When the owner names the wrong tier, or brings work that belongs to another tier, the session says so in one line (owner, 15:12).
  - Owner, 15:12: "i also may improperly use my setup, ie miscall something coordinator/orchestrator ..."
  - "... and want it so that u push back on me somehow being like by the way, im coordinator ..."
  - "... you should really be messaging triage for this part to save context, etc, it's a learning experience for me."
  - The line names the session's own tier, the right tier, and why, such as saving context.
  - The session then still handles the message, or routes it.
- **Triage feeds the lanes** (owner, 2026-10-29 13:45 CDT): "a role that's whole job is to be pushing stuff from triage into more lanes to work ie identify parallelism opportunities and push to you to start them ie a flywheel of sorts".
  - At each wake and each check-in, triage sends the coordinator a ready list. A step is ready when every question it has is answered and its files do not clash with a running lane.
  - The list also names each step that waits only on order, and what it waits on.
  - The coordinator starts each ready step in the same turn.
- **No owner step for work he signed off** (owner, 2026-10-29 13:44 CDT): "I shouldn't be expected to be around to do something I'd already signed off for".
  - Triage asks nothing that a past ruling answers. The coordinator does the act, or finds who can.
- **Opus grants live on the roadmap step** (owner, 2026-10-29 13:44 CDT, pick a): "Grants living in roadmap actually does make a lot of sense -- i lean towards that route."
  - Triage writes each Opus grant on the step it covers, with the owner's words and time. A lane's guard reads the grant of its own step. Lane opus-grant-on-step builds this; decision agent-model-cap gets the lift when it lands.
- **Merge role** (owner, 2026-10-29 16:54 CDT): the merge tool's confirm runs with no owner step per session, and no other session gains a way to merge.
  - Problem (16:39 CDT): the auto-mode classifier refused the batch runner's merge tool confirm. That session never saw the owner's merge grant.
  - Cloud settings only: `install.sh` adds `merge/cloud_allow.json` to the cloud settings. Its two narrow allow rules cover the confirm through `~/.claude/bin/merge` only, so the classifier does not judge it. No rule names bare `merge`: it is not on a cloud PATH. No rule names `bin/merge`: that form matches any repo's own script in the working directory. A narrow allow rule stays in effect in auto mode, and PreToolUse hooks still run (Claude Code docs, permission-modes and auto-mode-config pages, read 2026-10-29). No rule names `merge/merge.py`: that form runs the checkout's own copy, and an old lane branch's copy has no role check.
  - The merge tool refuses a cloud confirm unless `~/.claude/state/merge-role.json` names `coordinator` or `batch-runner` for this session's id. The refusal hands the PR number and head to the batch runner. A missing, unreadable or foreign file fails closed.
  - A coordinator or batch runner records its role with `~/.claude/bin/merge --role <tier>`, read from its own `cs-build:<tier>` tag, at session start and again after each resume. The tier line in `hooks/session_start.sh` says so. Any other tier is refused, and the refusal lists no tier.
  - Local sessions: unchanged. No allow rule and no role check apply, so the classifier or a permission prompt judges each confirm, as before.
  - Not covered: raw `gh pr merge` and the GitHub MCP merge tool. `hooks/guard_merge.py` judges both on CI only, as before.
  - Cost: one small file read per cloud confirm, one file write per role record, inside processes already running. No new process, timer or log. Checks: `merge/test_merge.py` (MergeRoleCheck, CloudAllow) and `hooks/test_session_start.py`.

## How it works

Mechanics that carry out the rulings above. They are not owner rulings.

- **Tier tags** (coordinator, 2026-10-28). Each session the coordinator starts carries these two tags, beside any others such as `cs-step:<step>`.
  - `cs-build:<tier>`, one of `coordinator`, `triage`, `batch-runner`, `lane`.
  - `cs-repo:<owner>/<name>`, the repo it builds.
- **Live-coordinator check.** A session that would act as coordinator reads every page of `list_sessions`. It looks for one session with both tags whose `session_status` is not archived. That session is the active coordinator.
  - The `tags` filter of `list_sessions` errors inside a session, so the check filters the rows itself.
  - `list_sessions` leaves out runs a scheduled task started. The check misses a coordinator started that way.
- **Session start** (lane L3). In a cloud session (`CLAUDE_CODE_REMOTE=true`), `hooks/session_start.sh` prints one fixed line, in any working folder, git or not. The line tells the session to read its own record with `get_session`, and gives the check above.
  - The hook cannot read the tier itself. `get_session` and `list_sessions` are MCP tools only, and a hook never calls the sessions API with a token.
  - Outside the cloud the hook prints no line. The gate is that one env value.
  - Cost: one env read in the hook already running. No network, no new process, no timer, no file written. `hooks/test_session_start.py` proves the line prints once in cloud, in a git folder or not, and never outside the cloud.

## Why

- Coordinators share a scarce machine by talking to each other (14:59).
- The batch runner leaves the coordinator with lane state only. The coordinator then talks with the owner (15:11).
- A wrong-tier line saves context in the tier that should do the work. It also teaches the owner the setup (15:12).
- No coded overlap guard. A false "done" fails at merge, because the merge tool reads GitHub's head and CI (15:01).

## Open

Open: the context limit for each tier. The route works (waiting item 53, pick a, tested 17:46 and 17:53); the limit values are not ruled.

Kind: process
Home: docs/decisions/session-tiers.md
Home: rule:roles-pick-mode-from-request
Home: rule:style-wrong-tier-one-line
