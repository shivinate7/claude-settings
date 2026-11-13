# A lane brief is built from its step and checked against the step's rulings

## The ruling

Owner, 2026-11-13 13:37 CST (step brief-from-step, the roadmap step that builds the brief tool). The step's source field reads "owner 13:37 CST Nov 13, via retrospective and coordinator 13:39 CST". Quote, from field why: "we need briefs to be improved then, greatly, that cna be a huge lift"

- Unverified: "yes briefs need to be templatized and token efficient and good" reached the lane only by relay (coordinator, 13:44 CST). It came from the retrospective's report, not typed to the lane.
- Owner, 13:53 CST Nov 13 (relayed by the retrospective), on ruling own-747-role-layout (the role-layout ruling, typed 13:51 CST): "for the sessions and not the subagents that sessions can have". The layout sets session rows only (coordinator, arbiter, consultant, triage, lane kinds). Agents keep their `agent-model-cap` rows (the model-per-role table) unchanged. <!-- glossary-ok: verbatim owner quote -->
- Owner, 14:05 CST Nov 13, relayed by the retrospective: the rule on the round, audit and fix verifier markers. Ruling own-r3-reviewer-sonnet-high (the round-3 reviewer ruling) holds the quote, verbatim, in three parts. Part one: "i shuld never be prompted we shd change this -- no opus round 3 here just sonnnet high". Part two: "case 2: that should be part of our brief fixes". Part three, 14:07 CST: "i mean, it shouldn't even try, the prose shouldn't say it can have round 3 opus and get it confused.."
- Owner, 14:30 CST (relayed by the coordinator at 14:46 CST; unverified): a check that only batch CI can prove is written "proved at batch CI", and the lane is not failed on it. The template carries no ruling id or measured figure. (paraphrase, no owner quote)

Part 1, the brief tool `brief_from_step`, on this head. It builds one fixed template from a roadmap step. The template holds the Grant line, the Lane brief line, Task with Fences (Fences are the files the agent may not touch), Files, Rulings, Failure classes, Done-check, Report cap, then the block "Agent spawn brief head". The template follows rule roles-brief-contents (the rule for what a brief carries). It restores three lines no role file or guard carries: a fix round is a fresh isolated spawn; never rebase onto main after review; only triage publishes the page.

- Rulings come from the step whose slug matches, open or closed, plus the ids or aliases that the step's note names. Each ruling is quoted verbatim, with its time and source. A ruling with no quote prints "(paraphrase, no owner quote)". The id and alias match is case-insensitive and whole-token at this head; 199 step files write ids in capitals (count unverified here).
- The step has no files or topic field. It may carry an optional `done_check` text and an optional `ci_only` flag. A missing field prints a marker that the coordinator fills in. The tool invents nothing.
- With `ci_only`, the Done-check line ends "(proved at batch CI)", and a template line says the lane does not fail on that check.
- Size, at head 075aa670d2. Words, and characters with chars/4 as an estimate:
  - Template: 821 words before the rewrite (pre-rewrite head of PR 3237, commit efc87b0c0; 5121 characters, estimate 1280). Now 439 words (2703 characters, estimate 676).
  - Probe: `git show efc87b0c0:` on the project-ops brief template, then `wc -w` -> 821. The current template, `wc -w` -> 439.
  - Tool output for five steps: brief-matches-rulings (brief matching) 497 words, 3061 characters (estimate 765); brief-from-step (the brief tool itself) 572 words, 3470 characters (estimate 868). Also lane-brief-template-gaps (template gaps) 477 words, 3004 characters (estimate 751). Also close-replaced-at-open (close at open) 558 words, 3442 characters (estimate 861); past-ruling-on-send (the page-question judge) 471 words, 2895 characters (estimate 724).
  - Probe: the tool run on each slug against the main checkout, then `wc -w` and `wc -c` on each output.
  - Carried from the earlier measure, not re-measured at this head: the same rulings ran 821-915 words before the rewrite, and hand-written lane briefs run 198-484 words.

Part 2, the brief check `brief_rulings`, is not on this head. It is built in the part 2 PR (PR 3262). That branch forks at fccff95e6, not at this head, so the check is true once that PR merges first or in the same batch.

- Probe: `git merge-base` of the part 2 branch and this head -> fccff95e6. The part 2 branch does not contain this head.
- The check reads a finished lane brief beside the governing rulings of its step, and flags a drop or a narrowing of a ruling. It makes one model call per brief. Its verdicts are ok, flag, unvetted and skipped.
- A store that is absent or unreadable, a model error, or a reason that cites a ruling the check did not show gives unvetted, never ok.
- The command exits 0 for ok and skipped, 1 for flag, 2 for unvetted.
- It matches rulings by step slug only. Id and alias matching is in part 1.
- Probe counts below are the PR 3262 reviewer's, unverified here. Round-1 reviewer (the first review round):
  - A brief that dropped the Nov 9 close-after-replacer ruling: flagged 3/3.
  - A clean brief: ok 3/3.
  - A brief that omitted the scope add: flagged 3/3.
  - A brief with a markdown-led header: flagged 2/2 after the fix.

Covered by earlier steps. Their homes stay as they are.

- past-ruling-on-send: the page-question judge. The part 2 check reuses its reader and helpers.
- brief-reads-owner-rulings: checks agent spawn briefs against the rulings of the decisions a brief names. Its lane-brief entry in the call judge belongs to that step. This step adds no entry there.
- lane-brief-cites-grant: the Grant line goes first.
- lane-brief-template-gaps: four gaps. Two are kept as lines. The rest are carried by role files and guard remedies.

Cost:

- Part 1: git reads of the step and the store. No model call, no file written, no process kept.
- Part 2: one model call per judged brief, plus git reads of the store (one list, one batch read). No file, no timer (part 2 fact, not on this head).

Known limits:

- Part 1 matches by step slug, id and alias. Part 2 matches by step slug only. A ruling filed under another step (example: pr-close-by-batch-runner) is missed.
- A mistyped step slug reads "skipped" and exits 0 (part 2).
- A step with no topic field prints a topic placeholder that the coordinator fills.
- The spawn guard (the guard that checks agent spawns) reads a marker on any line of a brief, outside fenced text, not only the first. So the block's own listing can lift a spawn refusal.
- The builder commits of both parts edited the CI workflow wiring (test config; part 2 fact, not on this head).

Incidents:

- None. The ruling above is the trigger.

Kind: process
Home: rule:roles-brief-contents
