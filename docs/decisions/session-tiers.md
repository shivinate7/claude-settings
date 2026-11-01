# Session tiers

## The ruling

Owner rulings, 2026-10-28 CDT unless dated. They name the session tiers and how they talk.

- **Session shape** (owner, 15:18). A new session in a repo reads what the owner asks, and picks one shape.
  - Solo. It builds the change itself.
  - One lane. It runs one line of work, and it orchestrates its own agents.
  - Coordinator. It runs a standing build. It starts triage and the batch runner, then lane sessions.
  - The owner's ask (15:04): revise the solo-versus-orchestrate rules to match these tiers, with an Opus review. The roles rules in `CLAUDE.md` now carry the shapes.
  - The shape stays dynamic. A session may grow to a larger shape (`roles-solo-grows-switch-to-orchestrate`). It says so in one line.
- **Orchestrator, the catch-all word** (owner, 15:18). Any session that spawns agents is an orchestrator. Coordinator, triage, batch runner, arbiter and lane session are kinds of orchestrator. Analogy: a square is a rectangle.
- **A coordinator in another repo** (owner, 2026-10-30 13:22 and 13:25 CDT: "i entirely meant compliance"; 16:09 CDT: "anything that brings something into how claude-settings wants our repos to work is compliance, something like doing ui ux features for a screen of an app is not compliance"). A coordinator's work in another repo is compliance only, by hand-off or by its own lane PR there. Compliance is any change that brings a repo into how claude-settings wants repos to work (its rules, checks, layout, CI, skills, map, glossary, prose, branch protection and shared tools). Product features, such as UI or UX work on an app screen, are not compliance. It may also finish an item that is near landing, a small last step. It never does that repo's in-flight feature engineering. No hard block applies. Before it acts, it checks whether that repo has an active coordinator. If one is active, it coordinates with that coordinator. If none is active, it proceeds. It does not hold back for lack of a reply.
- **Who starts which session** (owner, 15:18). The coordinator is the one session that starts other sessions. It starts triage and the batch runner together, as a trio, before any lane session. This refines the triage-first ruling below.
- **Rotation of standing sessions** (owner, 15:23; the arbiter joins them, owner, 2026-10-29 16:42 CDT, waiting item 81, pick a). Triage, the batch runner and the arbiter each report a tally of their own use, in turns or context, to the coordinator. When a tally nears its limit, the coordinator has that session write its handoff, archives it, and starts a fresh one from the handoff. The coordinator writes its own handoffs and compacts as today.
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
  - The helpers it starts, such as a builder or a designer, keep today's model and effort table in `agent-model-cap` (owner, 17:50, waiting item 59, pick a). This holds until step-down cost and quality are measured (see the todo line). The Measured part of that record has their token cost. Their quality against one step down is unmeasured.
- **Overlapping files.** No coded guard and no file-ownership record covers lanes that touch the same file. A good brief is enough. Orchestrators resolve overlapping edits. The owner wants better file splitting (owner, 15:01). A false "done" is already covered. The shared merge tool, `merge/merge.py`, reads the head and CI from GitHub.
- **Batch runner.** A third standing role (owner, 15:11): "B for sure actually". The batch runner owns:
  - the integration batch,
  - the CI waits,
  - the merge tool runs,
  - archiving finished lanes.
  The coordinator holds only lane state and talks with the owner. The batch runner runs the merge tool under the coordinator's merge grant (the Merge grant bullet). It holds no grant of its own.
- **Arbiter** (owner, 2026-10-29 14:55 CDT, waiting item 72, a question on the waiting page, pick b). The arbiter is a separate role. It holds a repo's ruling voice. Batch checks go to the batch runner, not to it. The coordinator starts it, only on demand (see "On demand" below). The coordinator holds only lane state and talks with the owner.
  - q_max's decision D-748 on browser checks: batch checks go to the batch runner. The ruling voice goes to the arbiter.
  - On demand (owner, 2026-10-29 16:42 CDT, waiting item 81, pick a): the arbiter does not start with triage and the batch runner. It starts later, when the owner tells the coordinator "spawn arbiter". It is for long runs the owner does not want to sit through.
  - Effort (owner, 2026-10-29 16:42 CDT, waiting item 81, pick a): by default the arbiter runs at high effort for its model.
  - Ruling (same item): an arbiter's answer counts as a ruling inside its own repo. It ranks below the owner, and the owner can overturn it.
  - Home (lane default, not an owner ruling; rule `output-answer-has-a-home`, an answer has a home): an arbiter's ruling lands where an owner's would, in its question's record in that repo.
  - On the page (owner, 2026-10-30 12:44 CDT, waiting item 86, pick a): each ruling the arbiter makes adds a closed item to the waiting page, with an Overturn choice. The arbiter hands the ruling to the page's writer, which writes the item (skill `waiting-page`). An Overturn reopens the question to the item's owning session.
  - Which repos (same item): not every repo gets an arbiter, only a repo that asks. Today that is q_max.
  - Kind (same item): the arbiter is a standing session and an orchestrator, and runs Opus. It is rotated before it goes stale, like triage.
- **Merge grant** (owner, 2026-10-29 16:47 CDT). The coordinator holds a standing merge grant in claude-settings and in the owner's other repos, until the owner withdraws it. The switch `merge.standingGrant` in each repo's `.github/stamp.json` turns it off there (owner, 2026-10-30 15:06 CDT). It never asks the owner to merge. The grant covers the merge act only and lifts no check: green CI, no merge during a batch CI run, fresh review and the net-value hold still apply. Record `standing-merge-grant` (the coordinator's standing merge grant) holds the words, the repos and the limits.
- **Wrong tier.** When the owner names the wrong tier, or brings work that belongs to another tier, the session says so in one line (owner, 15:12).
  - Owner, 15:12: "i also may improperly use my setup, ie miscall something coordinator/orchestrator ..."
  - "... and want it so that u push back on me somehow being like by the way, im coordinator ..."
  - "... you should really be messaging triage for this part to save context, etc, it's a learning experience for me."
  - The line names the session's own tier, the right tier, and why, such as saving context.
  - The session then still handles the message, or routes it.
- **Tier guards** (owner, 2026-10-31 15:31 and 15:32 CDT). A coordinator stays in its tier, and a guard enforces it.
  - Owner's words: the coordinator did other tiers' work and asked him too many questions. That goes against the ruling that sessions "kindly point me in the right direction". "It needs to be like an actual fix." Of the refused merge handoff: "also sounds like a fault".
  - Risk kind (rule `building-guard-needs-incident`, a guard needs an incident): incident. A coordinator session, 2026-10-31 14:49-15:31 CDT:
    - It asked the owner questions in chat. It never pointed him to triage.
    - It ran merges in banchi and q_max.
    - It edited banchi's `CLAUDE.md` and banchi decision records D042 and D307. It ran review agents itself.
  - Second incident, 15:31 CDT: the auto-mode classifier refused the coordinator's `send_message` that handed banchi pull request #1002 to the batch runner, as "Merge Without Review". The message named neither review round.
  - Guard `coordinator-scope` (`hooks/guard.py`, lands with lane tier-boundaries-enforced): a cloud coordinator's own writes (no agent) go only to records, its scratchpad, or paths outside a repo. A record home is a kind of `COORDINATOR_KINDS` at the path `lint/layout.py` gives for that repo (its `legacy-repos` path included). It is also a `roadmap`, `briefs` or `handoffs` folder of a checkout on the record branch. The guard reads the tier from `~/.claude/state/merge-role.json`. `merge --role <tier>` writes that file. The tier is proven, not self-declared: guard rule `merge-role-proof` allows `merge --role <tier>` only when the session's own newest `get_session` result lists the tag `cs-build:<tier>` (section "Merge role" below). The file only holds a tier that call already passed.
  - A shell call is judged on its write words (a `cp` by its destination, an `mv` by both ends), on python (`-c` or a heredoc, read with the `ast` parser), `perl -i` and `dd of=`. A `git commit` is judged on its pathspecs, else on the index plus the paths of each `git add` earlier in the same call.
  - Cost: the role file is read first, once per write or shell call by a cloud session (once the call has no agent and `CLAUDE_CODE_REMOTE` is `true`). Nothing else is read unless the session is a coordinator and the call names a repo path. Then: `lint/layout.json`, the repo's extras file and git config, the `~/.claude/CLAUDE.md` pointer, and for a checkout with `roadmap/data` one `git symbolic-ref`. A coordinator `git commit` adds one `git rev-parse` and one `git diff --cached` (one more `git diff` with `-a`). Each `git add` before it adds one `git rev-parse` and one `git ls-files`. On a refusal, no file is written but the normal `guard.log` line. A test counts the opens.
  - Limits: cloud only (a local coordinator has no role file). Its own agents' writes pass. A path in any repo outside the record homes is refused, another repo's `CLAUDE.md` included. Another repo's record paths pass, because the kinds are the same layout paths. The role file is matched to the environment's `CLAUDE_CODE_REMOTE_SESSION_ID`, never to the hook payload's `session_id`. The reader is `read_merge_role` in `hooks/shared_names.py`, the one home that `merge` imports too. A symlink in a target path, a python path built at run time and a `sh -c` script are not read (debt notes `coordinator-scope-symlinks` and `coordinator-kinds-hand-listed`; `coordinator-scope-cloud-env-unmeasured` for the env id). These write forms are missed: `touch`, `curl -o`, `tar -C`, `rsync`, `patch`, `git apply`, `node -e`, `os.remove`, `shutil.*`, a path from an f-string or `os.path.join`, `cat x | python3`, an add in a subshell, and a `<<-` heredoc (note `coordinator-scope-missed-writes`). A sed script is code, not a path. A wrapped or nested sed with a flag cluster such as `-Ei` is missed (debt `sed-wrapped-inplace-missed`). The rule is marked a guard for `roles-orchestrator-never-builds`, and it judges one tier only (debt `orchestrator-rule-half-guarded`).
  - Open: which questions a coordinator may ask in chat, how strong the guards are, and the merge-handoff route wait on the owner. Waiting-page items pending, sent to triage 2026-10-31. The fixed merge handoff form is in `skills/project-ops/templates/operating-model.md` (section "Autopilot").
- **Triage feeds the lanes** (owner, 2026-10-29 13:45 CDT): "a role that's whole job is to be pushing stuff from triage into more lanes to work ie identify parallelism opportunities and push to you to start them ie a flywheel of sorts".
  - At each wake and each check-in, triage sends the coordinator a ready list. A step is ready when every question it has is answered and its files do not clash with a running lane.
  - The list also names each step that waits only on order, and what it waits on.
  - The coordinator starts each ready step in the same turn.
- **No owner step for work he signed off** (owner, 2026-10-29 13:44 CDT): "I shouldn't be expected to be around to do something I'd already signed off for".
  - Triage asks nothing that a past ruling answers. The coordinator does the act, or finds who can.
- **Opus grants live on the roadmap step** (owner, 2026-10-29 13:44 CDT, pick a): "Grants living in roadmap actually does make a lot of sense -- i lean towards that route."
  - Triage writes each Opus grant on the step it covers, with the owner's words and time. A lane's guard reads the grant of its own step. Lane opus-grant-on-step builds this; decision agent-model-cap gets the lift when it lands.
- **Merge role** (owner, 2026-10-29 16:54 CDT): the merge tool's confirm runs with no owner step per session. Only a coordinator or batch runner gains a way to merge: guard rule `merge-role-proof` (the guard that proves the tier from the session's own tag) denies every other session's `merge --role`.
  - Ruling fb-1541-1 (the owner's ruling on who may run `merge --role`, 2026-10-30 15:41 CDT): the real coordinator and batch runner run `merge --role <tier>` with no prompt. A lane's mistaken `--role` is refused or asked, and the guard denies it. A deliberate forger is out of scope (rule `guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker). A refused session is steered to the working route, never left retrying.
  - Problem (16:39 CDT): the auto-mode classifier refused the batch runner's merge tool confirm. That session never saw the owner's merge grant.
  - Cloud settings only: `install.sh` adds `merge/cloud_allow.json` to the cloud settings. It reads the file from the source checkout, never from origin/main: `merge/launch.py` runs the checkout's own `merge.py` when it cannot prove fresh code, and on `--dev`, and the file landed in the same commit as that `merge.py`'s role gate. A checkout without the file gets no rules, and the install log says so with the checkout's commit. At each cloud start and resume, `install.sh` moves a clean, detached session checkout whose commit main holds to origin/main, so its rules follow main (coordinator, 2026-10-29 23:37 CDT). A branch, a dirty tree or a commit main lacks stays as it is, with a WARN. Its four narrow allow rules cover two commands through `~/.claude/bin/merge` only, so the classifier does not judge them: the confirm (two rules: `merge * --confirm` and `merge * --confirm *`) and the role record (two exact rules, one per merge tier: `merge --role coordinator` and `merge --role batch-runner`). Guard rule `merge-role-proof` still judges each `--role` call, below. The role rules bend ruling t18 (the owner's one-home-then-variants topic; decision `uniform-over-variants`, one form per shared tool): the owner, 2026-10-30 15:05 CDT, picked a second merge command form on the shared allow list, because the batch runner merges each batch with no wait for the coordinator. No rule names bare `merge`: it is not on a cloud PATH. No rule names `bin/merge`: that form matches any repo's own script in the working directory. A narrow allow rule stays in effect in auto mode, and PreToolUse hooks still run (Claude Code docs, permission-modes and auto-mode-config pages, read 2026-10-29). No rule names `merge/merge.py`: that form runs the checkout's own copy, and an old lane branch's copy has no role check.
  - The merge tool refuses a cloud confirm unless `~/.claude/state/merge-role.json` names `coordinator` or `batch-runner` for this session's id. The refusal hands the PR number and head to the batch runner. A missing, unreadable or foreign file fails closed.
  - A coordinator or batch runner records its role with `~/.claude/bin/merge --role <tier>` at session start and again after each resume. The tier line in `hooks/session_start.sh` says so. The merge tool refuses any other tier, and the refusal lists no tier.
  - Proof: guard rule `merge-role-proof` in `hooks/guard_merge.py` allows `merge --role T` only when the session's own newest `get_session` result, read from its log, lists the tag `cs-build:T`. Anything else is denied, an unreadable log too. So the session runs `get_session` in a turn of its own before the `--role` call.
  - Risk kind: likely risk (rule `building-guard-needs-incident`: guards need a named incident, a measured risk or a likely risk). A lane's mistaken `merge --role`, under the exact allow rules above, is one Claude can write in normal work. Landed 2026-10-30.
  - Tags: a coordinator the owner starts tags itself `cs-build:coordinator` (`set_session_tags` on its own id), then runs `get_session`, before its first merge. The coordinator tags each batch runner `cs-build:batch-runner` at spawn (coordinator, 2026-10-30 15:48 CDT).
  - Steer: the deny reason says to run `get_session` in its own turn first, else to hand the branch, head and PR to the batch runner, found through `list_sessions`. A lane that reads it hands off, and never retries.
  - Local sessions: unchanged. No allow rule and no role check apply, so the classifier or a permission prompt judges each confirm, as before. The guard also denies `merge --role` there, because no cloud session id is set. That is harmless: `merge.py` already refuses `--role` outside the cloud.
  - Not covered: raw `gh pr merge` and the GitHub MCP merge tool. `hooks/guard_merge.py` judges both on CI only, as before.
  - Cost: one small file read per cloud confirm, one file write per role record, one log read per `--role` call, inside processes already running. No new process, timer or log. Checks: `merge/test_merge.py` (MergeRoleCheck, CloudAllow), `hooks/test_guard.py` (section "the merge role record") and `hooks/test_session_start.py`.

## How it works

Mechanics that carry out the rulings above. They are not owner rulings.

- **Tier tags** (coordinator, 2026-10-28). Each session the coordinator starts carries these two tags, beside any others such as `cs-step:<step>`.
  - `cs-build:<tier>`, one of `coordinator`, `triage`, `batch-runner`, `arbiter`, `lane`.
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
