# Triage handoff: claude-settings

Written by triage 5 (session_013NEJL1qEunLpTi68de3Jrv), Nov 2 2026 12:40 CST, at the owner's 12:31 CST wind-down; updated 13:15 and 13:06 CST after the coordinator's last pass. Coordinator: session_013NEJL2pASwRjgJDnsvnpNe.

## Role

- Triage is the only writer of the Queue page and of this branch (roadmap). It routes owner answers to the owning session, files each ruling and task in its home, and answers the coordinator's check-ins ("none" or item ids with picks).
- Queue page: artifact:queue. Database collections: items/<id>, answers/<id> (owner writes), receipts/<id>. Route an answer in one batch: update the item (status, pick, lastAnswer, reply), delete the answer pinned to its version, set receipts/<id> {n, read, filed}; then tell the owning session.
- Page HTML republished as v88 at 13:12 CST, with the roadmap block at 190bab8b spliced in; the items database is current. Republish the page as "claude-settings Cockpit" once step page-title-cockpit (PR #1100) merges (owner ruling 11:12 CST).
- Roadmap head at writing: 190bab8b (before this update's commit). Steps: roadmap/data/steps/<slug>.json, json indent 1, ensure_ascii False, trailing newline. Pull before each write.

## Standing rulings triage applies

- Every turn that pushes the roadmap ends with the full report (Done, Deviations, Input Needed, Next) in one blockquote; each RECORDED or BUILT line names its own commit or PR (owner, Nov 1 16:23 CST).
- Every owner question goes on the Queue page in the same turn it is asked; an owner chat answer closes its item; no 5-minute wait (owner, Nov 1 23:31 CST, page item 158, step questions-reach-page).
- No rotation limit: standing sessions run through autocompact (owner, page item 109 b, Nov 1 17:56 CST; step rotation-text-current fixes the stale template text).
- Do not ask what a ruling already answers or an undoable implementation pick; withdraw and tell the lane (rule questions-go-to-owner).
- An option that widens what a shared tool accepts carries "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo" and is never recommended.
- Owner item 31 e (Oct 27 12:07 CDT, step c95), verbatim: "trust first, then cut in steps, each only past its measured bar, stepping back on a miss; step 3 milestone runs". "A red run blocks the next merge" is a coordinator application, process-only; never quote it as the owner's.
- Never reply in an artifact comment thread; answers go on the items or to the coordinator.
- Route every saved answer at once, also on lane-owned items.
- Roster (owner Nov 1 21:34 CST): the coordinator never merges; batch runners run every merge.

## Open page items

### 91 apple-ids-account-file: Put your Apple account ids in the Mac account file

- Title: Put your Apple account ids in the Mac account file
- Owner: Coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: r1. Kind: task.

### 130 3d-first-target: First 3D target

- Title: What should your first 3D work be built in?
- Owner: Lane 3d-tools-survey (session_013NEJL1nELFhJD5Rm3xiUS3). Home: 3d-tools-survey. Kind: decision.
- a) Browser 3D (three.js and glTF): gain Free, and cloud sessions can build and check it. Lose: No game-engine extras such as a scene editor or physics tools.
- b) Godot: gain A full engine at no cost. Lose: Cloud checks cover only the file structure; checking how a scene looks is not proven.
- c) Unity or Unreal: gain The largest asset stores and tooling. Lose: Licence cost, and the work runs only on your computer.

### 131 3d-asset-storage: Where 3D files live

- Title: Where should big 3D files live?
- Owner: Lane 3d-tools-survey (session_013NEJL1nELFhJD5Rm3xiUS3). Home: 3d-tools-survey. Kind: decision.
- a) Shipped files in Git LFS, source files in cloud storage: gain Code and the files a site ships stay together, and big source files use no GitHub allowance. Lose: Two places to look for files.
- b) Everything in Git LFS: gain One place for everything. Lose: The allowance runs out; past it you pay $0.07 per GiB stored a month and $0.0875 per GiB downloaded.
- c) Everything in cloud storage: gain No GitHub allowance used. Lose: Git keeps no history of file versions.

### 150 shivpedia-plan-signoff: shivpedia plan sign-off

- Title: Sign off the shivpedia plan as written, or name changes?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: craft-book. Kind: decision.
- a) Sign off as written: gain Building starts now. No cross-repo PRs, less report noise, and no new code for a page registry. Lose: Lessons from roles other than builders may slip, and triage reads one more thing per repo.
- b) Sign off with changes: gain The plan matches what you want before anything is built. Lose: Building waits for the revision.

### 152 grant-plan-signoff: grant plan sign-off

- Title: Sign off the plan for grants that reach another session, as written or with changes?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: grant-reaches-lanes. Kind: decision.
- a) Sign off as written: gain One grant reaches the session it names; no free-text grant can widen by a misread. Lose: Only the listed grant wordings work; a new kind of grant needs a plan change.
- b) Sign off with changes: gain The plan matches what you want before anything is built. Lose: Building waits for the revision.

### 153 local-reach-plan: local reach plan

- Title: How cloud sessions answer your computer's sessions, and whether to take the trust card more widely
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: local-session-reach. Kind: decision.
- Last answer: b at 2026-11-02T06:56:26.205Z
- a) Read path, keep the guard: gain No session is limited for good; coordinators, lanes and runners keep taking messages. Lose: The local session hears only at its own wake; board rows are data, never grants.
- b) Other picks: gain Direct two-way messages, or a measured answer on why trust blocked messages. Lose: Each trusted session is limited to trusted devices for good, which cannot be undone.

### 154 qmax-1011-batch: q_max #1011 batch

- Title: q_max #1011: run main's browser tests once first, or merge now past the unknown result?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: git-never-merge-failing-ci. Kind: decision.
- Last answer: none at 2026-11-02T06:56:26.205Z
- a) Run main's browser tests once: gain main's browser state is known before #1011 lands. Lose: One full browser run of GitHub minutes, and #1011 waits for it; the last two such runs never finished, so this one may hang too.
- b) Merge now: gain #1011 lands now. Lose: A browser break already on main can hide under the merge.

### 155 banchi-codex-rules: banchi Codex rules

- Title: banchi: when CLAUDE.md is split by folder, how should Codex read the moved rules?
- Owner: banchi lane (session_013NEJL3SffaYSu5tzgYVhAv). Home: banchi D135. Kind: decision.
- Last answer: none at 2026-11-02T06:56:26.205Z
- a) Links in each folder: gain Codex reads the same rules by construction, as your ruling asks; no script; each file stays under Codex's limit. Lose: Codex sees a folder's rules only when it runs in or under that folder, not from the root.
- b) Generated file, raised limit: gain Codex reads every rule from the root. Lose: It is the sync script your ruling rules out, and it needs a Codex settings change.
- c) Drop the split: gain Nothing changes in how Codex reads rules. Lose: CLAUDE.md stays at 37.6 KB and misses its size target.

### 161 joyous-68-base-red: joyous #68 merge (reopened)

- Title: joyous #68: type the override now that only main's real build red blocks it?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: git-never-merge-failing-ci. Kind: decision.
- Last answer: b at 2026-11-02T06:56:26.205Z
- a) Type the override now: gain joyous main builds again. Lose: One merge onto a red main, which the rule allows for a fix.
- b) Leave #68 unmerged: gain None. Lose: joyous main stays red, and every joyous merge stays blocked.

### 163 mutation-ci-job: test-strength CI job

- Title: Should CI check test strength on each batch, and should a weak result block the merge?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: test-practices-first-principles. Kind: decision.
- a) Report only: gain Each batch shows its untested lines, with no risk to merges. Lose: About one extra job per batch, cost not yet measured; weak tests still merge.
- b) Block below a floor: gain Weak tests stop merging. Lose: GitHub minutes on every batch, and false reds in banchi until it can run tests per file.
- c) By hand only: gain No CI cost. Lose: Nothing watches test strength between hand runs.

### 170 branch-delete-list: delete 136 old branches from your Mac

- Title: Run the branch delete list from a Claude Code session on your Mac
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: branch-cleanup. Kind: task, with command {mac, powershell}.
- Task: a session on the owner's computer runs 136 leased branch deletes under the standing grant 'acts the cloud refuses'. List: branch branch-cleanup, docs/plans/briefs/branch-cleanup-mac-deletes.md, d9a3e8f5. Checked 12:55 CST: every tip matches origin, every archive copy exists at the same tip. Item 164 (start a Mac session) closed into it.

### 166 newer-run-clears-red: newer green run clears a red

- Title: Which jobs must a newer green run on main repeat to clear an older red run?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: no-merge-onto-red-main. Kind: decision.
- a) Change nothing: gain No loosening of the merge tool. Lose: banchi pull request #1003 waits until tomorrow's nightly run passes, unless you type the override; each red nightly anywhere waits the same way.
- b) Repeat every job that did not pass (widens): gain banchi pull request #1003 merges now; a job the red run cancelled must still pass in the newer run. Lose: A job that passed in the red run is not checked again, in every repo. Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo.
- c) Repeat only the failed jobs (widens): gain The same clear for banchi pull request #1003. Lose: A job the red run cancelled needs no newer pass; looser than b. Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo.

### 167 no-undo-check-scope: how wide the no-undo check reads

- Title: Should the no-undo check flag any deleted line a lane added, or only the two shapes real undos take?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: no-undo-lane-commits. Kind: decision.
- a) Narrow to the two undo shapes: gain Catches both of this morning's undos, with far fewer false alarms. Lose: A lane can still drop its own non-test lines without an excuse line.
- b) Any line: gain Nothing a lane added is dropped without a named reason. Lose: Most batches go red today, so builders learn to ignore the check.

### 168 page-answer-starts-lane: page answer starts its lane

- Title: How should one page answer start the lane it approves, with no second click and on the right branch?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: session-tiers. Kind: decision.
- a) Agent on the Mac, session in the cloud: gain No card and the right branch, on the Mac and in the cloud. Lose: On the Mac a lane ends when the coordinator's session ends, and it shares the Mac's load brake.
- b) Idle lane sessions at run start: gain Lanes outlive the coordinator. Lose: The coordinator must guess how many lanes to start; idle sessions wait; a card still drops the branch unless each brief creates its branch.
- c) Ask for the start in chat: gain No new tool. Lose: It works only when you answer in chat, not on the page.
- d) Fix the page read across accounts only: gain No relay of answers. Lose: The account limit is outside the repo; the waiting-data copy in each repo already lets the owning session read answers from git; it does not remove the click.

### 169 standing-tally-drop: drop the self-reported use tally

- Title: Should standing sessions stop reporting their own use to the coordinator?
- Owner: coordinator (session_013NEJL2pASwRjgJDnsvnpNe). Home: rotation-text-current. Kind: decision.
- a) Drop the tally: gain One less report per standing session, and no rule that nothing reads. Lose: The coordinator must read use itself if it ever needs it.
- b) Keep the tally: gain The coordinator sees each session's use without reading it. Lose: A report that nothing reads stays in every standing session's routine.

## Steps in doing

Ten lanes wound down at 12:31 CST went back to todo (13:10 CST); each lane's branch and handoff hold its state.

- builder-test-edit-heredoc: Guard builder-test-edit also stops a heredoc write to a test file. Why: Incident, Nov 1: lane refusal-cite-reach saw a builder change lint/test_rule_audit.py through a python heredoc before the guard refused its Edit tool call; the builder disclosed and restored it. The guard checks the Edit tool only.
- c127: A small shared set of lint and type tools covers every language in the repos. Why: Proposed and widened by you, Oct 27 (cmsg_01DoF7thf3iq2Srr1UsfXgh2RAHCgXRgVqY8FQzV1SZAPx, cmsg_01DoF7thf3iq2Srr1UsfXgh2AS65GEmZso8CawVbTFZUGD): no claude-settings step, rule or config covers type checking; c21 covered Ruff and ShellCheck only.
- c174: Banchi's guard allows notes folders and leaves the tree check to the shared rule. Why: The Banchi part of c156, from your ask (cmsg_01DoF7thf3iq2Srr1UsfXgh26MuXHQwVQFmfKrqbe6bgD9): Banchi's guard refused a write to the Claude app's side-session notes folder.
- c203: A per-session compaction window must not dirty settings.json; the handoff hook must read the window in use. Why: shiv, Oct 28 15:20 CDT (via the coordinator): running /autocompact on a session to a value other than 500k writes it into his user settings, which on his machine is the repo's tracked settings.json, leaving a stray line change.
- child-repo-gap: Check how far each child repo is from claude-settings main. Why: Child repos drift from the shared rules, and nobody has measured how far.
- child-rules-cite-records: A child repo's CLAUDE.md names records, never copies them. Why: Owner ruling in chat, Nov 2 10:41 CST (inbox fb-1041-2): a child CLAUDE.md names records and never copies them; rulings on the same question are held 30 minutes, then written in one rewrite (follow now); a lint check enforces it.
- comment-lint-every-repo: The comment check runs in every repo, not only claude-settings. Why: Owner asked, Nov 1 18:39 CST, about the lint work on code and comments. Read: lint/check_comment_narration.py (comments say what and why, never history; rule building-comments-say-why) runs only in claude-settings' own checks; the shared actions/code-check that other repos pin does not run it (git g
- compaction-carry-watch: Watch whether compaction loses rulings, to revisit the no-limit ruling. Why: Owner, Nov 1 17:56 CST (page item 109, pick b): no rotation limit, and some way to see if it should be revisited.
- craft-book: shivpedia: what a session learns in one repo, the next repo starts with. Why: Owner, Nov 1 21:02 CST: "even broader than this, it's like if i learned how to build seomthing better one way, i should be able to utilize that again some other day" Just how a carpenter gets more skilled with his experience, similarly we should too, rather than always being a new laborer in each re
- feedback-repeat-detect: New feedback is matched against old feedback, and a repeat is flagged. Why: Owner, Nov 1 17:44 CST, forwarding a home repo session's finding: the gap is in every repo, not only home.
- glossary-meets-owner-halfway: Sessions read the owner's words by meaning and answer in the glossary term. Why: The owner writes in his own words. Sessions should match those words to the glossary term by meaning, not ask him to use the exact term, and then write the glossary term themselves.
- grant-reaches-lanes: A grant typed in one session reaches the session it names. Why: Owner, chat, Nov 1 22:37 CST: "a grant here should allow for a grant there". Auto mode in each session sees only grants typed in its own chat (incident: item 149 b, step runner-merge-allow).
- guard-log-time-offset: guard.log times carry their zone, so a machine on another clock reads true. Why: Found Nov 1 (local vs cloud audit): shiv's Windows PC runs on Eastern time while the hooks speak Central, and hooks/guard_core.py record() writes datetime.now().isoformat() with no offset, so his guard.log lines read one hour ahead of Central. The batch pace numbers (rule reports-batch-pace-numbers)
- handoff-checkpoint-before-compact: The last handoff checkpoint fires before compaction starts. Why: From lane c203, Nov 1 17:43 CST: the handoff hook's last checkpoint sits at the window minus 50k (450k on 500k), but compaction may start near 384k, so that checkpoint may never fire.
- handoff-read-before-write: After compaction, a session cannot act until it has read its handoff. Why: Incident, Nov 1 17:23 CST: triage 5 rewrote its handoff and worked a turn after compaction before reading it back; the Stop hook caught it only at turn end. Owner, 17:35 CST: the slip should not be possible.
- idle-resume-compacts: A session idle for a couple of hours does not compact on the next reply. Why: Owner report, Nov 1 17:54 CST: sessions idle a couple of hours compact first thing on his reply, whatever the context used.
- install-drops-retired-files: An install removes ~/.claude files that main no longer ships. Why: Found Nov 1 (local vs cloud audit): shiv's PC still holds a skills/tile-windows link and a plain hooks/config_report.py, neither on main. install.sh says so itself (line 593-597): proving a copy stale needs a manifest of what the last run installed, so cloud mode keeps stale copies of removed files.
- install-log-offset: install.sh and install.ps1 write log times with their UTC offset. Why: The install logs write local wall time with no offset. The owner's PC runs Eastern, so an 18:40 CST run logged 19:40 (PC session, Nov 1 18:40 CST). A reader cannot tell which zone a line is in. Same defect as guard.log (PR #974).
- lane-closes-after-records: A lane does not close until its records pull request has merged. Why: Owner, Nov 1 17:44 CST, forwarding a home repo session's finding: the gap is in every repo, not only home.
- local-session-reach: What makes a session trusted, and how others reach it. Why: Owner, chat, Nov 1 22:52 CST: plan what decides a trusted device or session, reach without trust, and a message-board fallback.
- merge-ignores-superseded-runs: The merge tool judges each check by the newest run on the head. Why: The shared merge tool refused q_max PR #1003 on a duplicate run that concurrency cancelled when the PR went ready (run 41368432206), although the newer run on the same head passed (41368432483). It will recur on every child-repo integration PR opened as a draft and then marked ready.
- merge-lock-record-drift: Merge lock and env-file records match the code. Why: Lane refusal-uncited-rewrites' record-writer found four places where a record or usage line says one thing and the code does another.
- merge-undo-scan-follows-renames: The merge tool's silent-undo scan follows renamed files. Why: Incident, Nov 1 17:17 and 17:38 CST (coordinator): joyous PR #53 renamed gates.yml to checks.yml, and the merge tool refused it twice although the line moved unchanged.
- no-undo-lane-commits: Builders never undo earlier lane work, and the silent-undo scan catches it. Why: Owner ruling in chat, Nov 2 10:41 CST (inbox fb-1041-1): builders never undo earlier lane work; extend the silent-undo scan.
- none-with-note-is-direction: A "none of these" answer with a clear note closes the item and becomes a step. Why: Owner, Nov 1 17:44 CST, forwarding a home repo session's finding: the gap is in every repo, not only home.
- o3: Shrink each CLAUDE.md toward 200 lines. Why: Long files cost context and lower how well rules are followed. Keep AGENTS.md as a symlink.
- one-inbox-per-repo: Each repo has one feedback inbox that every session writes to. Why: Owner, Nov 1 17:44 CST, forwarding a home repo session's finding: the gap is in every repo, not only home.
- one-model-rule: One model rule for every agent: each role runs its table row, or one marked step up. Why: Owner asked, Nov 1 16:45 CST (page item 127, note): the model rules looked picked at random. A blind Opus review (his grant) found five layered rulings giving opposite verdicts at two edges: a plain search agent passes on Opus but is refused on Sonnet, and a bigger model jump gets a softer check.
- other-checkout-scratch-false-alarm: Guard other-checkout stops refusing a session's own scratchpad worktree. Why: Incidents: the guard refused writes in a session's own scratchpad worktree after a cd, though its record exempts that path: lane cc-update-behavior-diff at 22:00 CST, the coordinator at 23:28 CST (a commit in scratchpad/wt-notes; git -C passed), and triage 5 earlier on Nov 1 (a cd into its roadmap w
- pace-brake-cloud: In a cloud session, the brake pace number reads "n/a (cloud)", never 0. Why: Owner, Nov 1 21:34 CST: "why would there be brake refusals when you are running on the cloud? that's specific to local sesions." Rule reports-batch-pace-numbers' fourth number reads only the local guard.log, and the load brake applies to local sessions only.
- page-item-checked-at-write: A page item's mockup focus and fields are checked when it is written, not only when the page draws it. Why: Incident (shiv, Nov 1 17:06 CST, photo of another repo's waiting page, item 51, speaker sheet volume fill, lane local_3808a094): the card showed "The picture of option A shows nothing the focus names" and "This item carries a field the page does not draw" to the owner. The page caught both, but only
- page-stale-asks-sink: Inside each tier of the waiting page, newer questions rise and ones asked before and still unanswered sink, with their options folded. Why: Owner ask, Nov 1 17:16 CST (page note on item 142): "after triage here sorts questions into severity, there needs to be another sort within the subgroups where items that have been previously asked and weren't answered sink lower (and their answer choices collapse, I can be able to uncollapse it tho
- page-title-cockpit: Each repo's page is titled "<repo> Cockpit". Why: Owner ruling in chat, Nov 2 11:12 CST: each repo's page is titled just "<repo> Cockpit".
- plugin-assess-three: Assess three plugins: iceberg, ambition lenses and hypotize. Why: Owner, Nov 1 21:32 CST: "send a lane to assess whether we should add the plugin iceberg from anthropic and another called ambition lenses, and another called hypotize".
- question-checks-past-rulings: Before a question reaches the owner, past rulings on it are found and cited. Why: Owner, Nov 1 18:39 CST: so many things are misremembered. Incidents today: item 145 re-asked the Oct 28 keep-the-apps ruling; item 133 was written twice without the Oct 27 milestone-runs ruling; earlier, home's items 48 and 49 were re-asked.
- questions-reach-page: Every owner question reaches the page at once. Why: Owner, chat, Nov 1 23:31 CST, pick a: every owner question goes to the page writer in the same turn it is asked, and an owner answer in chat closes the page item. No 5-minute wait. Logged as Queue item 158.
- r2: q_max: merge its three token layers. Why: --aq-*, --f2-* and Tailwind drift apart. One layer stops it.
- r4: q_max: merge its six design homes into one DESIGN.md. Why: design/, specs/, docs/design.md, docs/rules/, src/styles.md and brand/ all hold design truth today. One home is how its agents find the look.
- r5: Each repo drops its copies of claude-settings things and reads the one home. Why: A drifted copy follows old rules while the home moves on, and nobody sees the gap.
- red-main-stale-schedule: A newer run of the same jobs clears an old scheduled red. Why: Incident, Nov 2 00:01 CST: the merge tool refused joyous #68 because an Oct 26 scheduled link-check run on an old main was red, though a newer run on today's main passed. Since PR #1013 the tool judges scheduled runs as their own group, so a stale scheduled red blocks until the next scheduled run.
- refusal-cite-reach: Every refusal cites its rule, in every hook. Why: Lane refusal-uncited-rewrites found refusals its ratchet cannot see: the guard-crash deny, 13 exempt ids that can cite now, 9 later ids, and hooks outside guard*.py, merge.py included.
- refusal-looser-fixes: Guard rules looser than their rule are tightened to the rule's outcome. Why: Follow-ups from the refusal-versus-rule sweep (step refusal-matches-rule; owner Nov 1 20:57 CST).
- refusal-matches-rule: Each guard and merge refusal matches its rule's outcome, no stricter or looser. Why: Owner, Nov 1 20:57 CST: "so that sounds more like the merge tool being more restrictive than the prose said for it, and that's where the gap was ... a lot of what this repo is is just self improvement best practices so that my next project comes in faster, better than the last".
- refusal-uncited-rewrites: Guard and merge refusals that cite no rule get a rule or record. Why: Follow-ups from the refusal-versus-rule sweep (step refusal-matches-rule; owner Nov 1 20:57 CST).
- roadmap-live-check-true: The roadmap's in-progress check sees every live lane. Why: Owner, Nov 2 00:00 CST: the roadmap and the live work must stay in step.
- roadmap-one-writer: Only triage pushes to the roadmap branch. Why: Incident, Nov 1 17:2x CST: a lane session committed step c203 to the roadmap branch (87a9d9c9) while triage 5 was the only writer.
- roles-follow-ruling: Tools follow the 21:34 roster ruling. Why: Owner 21:34 CST: the coordinator never merges; a batch runner runs every merge (decision session-tiers, PR #1038). Owner on the load brake: "that's specific to local sesions". The tools still let a coordinator merge, and the brake runs in cloud containers.
- sim-crash-loop-stop: sim-test stops a simulator that is crash-looping. Why: In home (Nov 1), a simulator crash-looped for 7 minutes before anyone stopped it. A check in sim-test would have stopped it in about 10 seconds.
- sim-machine-lock: Every simulator boot on the Mac goes through one machine-wide lock. Why: A home iOS lane reported (Nov 1 19:02 CST, relayed by the owner) that sim-test (the shared simulator tool) takes no machine-wide lock, and a lane that boots with simctl or the Simulator panel skips sim-test entirely. Two sessions can then boot and fight over simulators.
- stale-prose-standing: When a thing changes, every prose line that describes it changes in the same merge. Why: shiv, Nov 1 16:30 CST, in chat to triage: "Please make it a standing thing that stale prose never makes it anymore man when things change the prose needs to be snappy to match (i think maybe we've already addressed this and we just had a past debt of this -- unclear)". Incident the same hour: a ques
- ste-changed-shallow-clone: ste-changed says "unknown" on a shallow clone instead of a false stale-pin warning. Why: Named incident, Nov 1 21:4x CST (mailaudit lane): on a shallow claude-settings clone, ste-changed said CI pins ste-lint at 17492e5 "which this copy does not hold", though 17492e5 is an ancestor of main d8037a44. The lane opened an unneeded pin-move lane (cancelled; archived as archive/pin-claude-set
- tci-12-stale-records: The stale claude-settings test records are fixed. Why: From the test and CI plan (docs/plans/test-ci-standard.md, merged Nov 1 18:28 CST in PR #977), lane 12 of 12, ranked by harm avoided.
- tci-2-red-first-proof: A lane PR with new tests carries their red run on the old code. Why: From the test and CI plan (docs/plans/test-ci-standard.md, merged Nov 1 18:28 CST in PR #977), lane 2 of 12, ranked by harm avoided.
- tci-3-builder-test-edit-refuse: The builder's test-edit check refuses again, not only logs. Why: From the test and CI plan (docs/plans/test-ci-standard.md, merged Nov 1 18:28 CST in PR #977), lane 3 of 12, ranked by harm avoided.
- tci-4-show-skips: Skipped tests show as a count, so CI cannot look green while tests never run. Why: From the test and CI plan (docs/plans/test-ci-standard.md, merged Nov 1 18:28 CST in PR #977), lane 4 of 12, ranked by harm avoided.
- tci-6-mutation-replay: Mutation replay over the last 50 merged PRs in q_max and banchi. Why: From the test and CI plan (docs/plans/test-ci-standard.md, merged Nov 1 18:28 CST in PR #977), lane 6 of 12, ranked by harm avoided.
- test-practices-first-principles: Shared test-making practice, from first principles and evidence. Why: Owner, Nov 1 20:49 CST: "yeah again i'm not too sure on how much best practices we absorb from good tests to better replicate good tests as i think we have few guidelines now asides for outcomes based thinking, but would like to see some more shared best practices on test making from first principle
- tier-boundaries-enforced: Each session keeps to its tier, and a hook points the owner to the right one. Why: shiv, Oct 31 15:31 to 15:32 CDT, owner chat (via coordinator session_013NEJL2pASwRjgJDnsvnpNe): the coordinator took owner questions that belong to triage; sessions must point him to the right tier, and "it needs to be like an actual fix": a hook or check, not prose. Second incident the same hour: t
- time-pinned-tests-go: Tests that pass or fail on clock speed become outcome checks, then CI caps return to measured. Why: Owner, Nov 1 18:44 CST: "we have a step regarding fixing CI that eliminates time limits and instead ensures outcomes based testing". No step did this (searched c34, c39, c128, test-ci-standard, tci-7, tci-8; gap found by tci-12). Generous job caps are a stopgap until it lands (decision ci-job-caps).
- worktree-base-copies-remove: A worktree holding only base copies can be removed. Why: Incident, Nov 1 22:41 CST, raised at the owner's request by lane merge-lock-record-drift: test-author worktree agent-a7d6329a40cedecfc kept staged copies of four files, each byte for byte equal to the branch base, with no unpushed commit. The shared-tree guard refused its remove and restore; the own

## Waiting for the outbox or filing

- roadmap/outbox/child-cites-briefs.md: three child-repo briefs (home, degen, ios-adblock) from lane child-rules-cite-records (PR #1098, branch at 58a51bfa), for the owner to send once decision child-cites-not-copies and actions/claude-md-cites are on main.
- roadmap/outbox/triage.md: seven debt notes still owed to docs/debts/notes.md on main (checked Nov 2 12:58 CST); the next lane that edits notes.md lands them.
- Lane rotation-text-current owes child-repo hand-off briefs (home, degen, mailaudit) after its merge; none written yet (its handoff: branch rotation-text-current, handoffs/rotation-text-current.md, 092b733f).
- Outbox read Nov 2 13:00 CST: 21 older lane-status notes removed; each named PR is on main (checked by commit ancestry).
- Lane mockup-homes' question (mockup check scope): the coordinator ruled open steps only, Nov 2 12:49 CST; filed on step mockup-homes. No page item. Its handoff: branch mockup-homes, handoffs/mockup-homes.md, f5b8d6a7.

## Follow-ups owed

- When PR #978 merges, or the roster lands via PR #1038 (pace-brake-cloud): those rulings then have a home.
- When PR #1020 merges: add createdAt to each pull in live.json; fix a todo step's status when it has an open PR.
- When PR #981 merges: add an items list to live.json; file the 11 closed page rulings missing from their steps.
- When PR #987 merges: mark feel-fixes with feel and deviceCheck {how, at}.
- When batches 59 and 60 merge: mark c203 and merge-undo-scan-follows-renames done.
- When the coordinator settles the agent-model-cap item: mark refusal-looser-fixes done.
- Item 170: route its answer to the coordinator; after the deletes run, re-point the debt named in roadmap/outbox/triage.md. Items 161, 166: route to the coordinator and the batch runner. Item 169: route to the coordinator for lane rotation-text-current. Item 162 closed 13:05 CST: trial run gd is archived.
- trust-error-record: its owner question goes through the question check before any page item.
- c121: mark per repo as each roll-out visit closes.
- Roadmap build upkeep left at 13:10 CST (run `python3 ~/.claude/skills/roadmap/build.py --repo <roadmap checkout> --live live.json --block --out block.html`): 12 page rulings not on their step, 6 draft PRs over 12 h with no live lane, 17 notes over 250 words, 3 new top-5 steps with no placement line, 3 Step trailers naming no step (stale-note-recheck).
- Archive order (coordinator, Nov 2 12:49 CST): triage stays live and is archived last, with batch runner 7.
- Item 166 context gained a note, Nov 2 12:58 CST: banchi #1003 has no merger (runner 8 archived); the next session merges it after item 166 and the nightly.
- Trial lg's report-guard question not filed on the page: the Nov 1 16:23 CST ruling answers it (extend the guard). Note in roadmap/outbox/triage.md.
- Steps filed after the wind-down, from the owner's direct reports Nov 2 12:54-12:55 CST: option-key-guard-gap, ask-reaches-writer.
- Owner ruling Nov 2 13:10 CST (time zone on every time, 24-hour clock): home is decision local-time-central, rewritten in place by step time-zone-every-time. Follow it now in every reply.
