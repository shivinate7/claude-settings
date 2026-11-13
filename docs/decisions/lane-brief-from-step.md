# A lane brief is built from its step and checked against the step's rulings

## The ruling

Owner, 2026-11-13 13:37 CST, relayed by the retrospective and sent to the coordinator at 13:40 CST (step brief-from-step, the roadmap step that builds the brief tool; field why): "we need briefs to be improved then, greatly, that cna be a huge lift"

- Unverified: "yes briefs need to be templatized and token efficient and good" reached the lane only by relay (coordinator, 13:44 CST). It came from the retrospective's report, not typed to the lane.
- Owner, 13:53 CST (relayed): ruling own-747-role-layout (the role-layout ruling) covers the agent rows of `agent-model-cap` (the model-per-role table). (paraphrase, no owner quote)
- Owner, 14:05 CST (relayed by the retrospective): the spawn marker rule. (paraphrase, no owner quote)

Part 1, the brief tool `brief_from_step`. It builds one fixed template from a roadmap step. The template holds the Grant line, the Lane brief line, Task with Fences (Fences are the files the agent may not touch), Files, Rulings, Failure classes, Done-check, Report cap, then the block "Agent spawn brief head". The template follows rule roles-brief-contents (the rule for what a brief carries).

- Rulings come from the step whose slug matches, open or closed, plus the ids or aliases that the step's note names. Each ruling is quoted verbatim, with its time and source. A ruling with no quote prints "(paraphrase, no owner quote)".
- A step has no files, Done-check or failure-class field. Those print as coordinator markers, which the coordinator fills in. The tool invents nothing.
- Size, in words. Five steps: brief-matches-rulings (brief matching) 496, brief-from-step (the brief tool itself) 506, lane-brief-template-gaps (template gaps) 476, close-replaced-at-open (close at open) 557, past-ruling-on-send (the page-question judge) 470. With the same rulings, the old output ran 821-915 words. The old template alone was 821 words; the new template is 417. Hand-written lane briefs today run 198-484 words.

Part 2, the brief check `brief_rulings`. It reads a finished lane brief beside the governing rulings of its step, and flags a drop or a narrowing of a ruling. It makes one model call per brief. Its verdicts are ok, flag, unvetted and skipped.

- A store that is absent or unreadable, a model error, or a reason that cites a ruling the check did not show gives unvetted, never ok.
- The command exits 0 for ok and skipped, 1 for flag, 2 for unvetted.
- The check reuses the reader and helpers of past-ruling-on-send.
- Probe, real model, round-1 reviewer (the first review round):
  - A brief that dropped the Nov 9 close-after-replacer ruling: flagged 3/3.
  - A clean brief: ok 3/3.
  - A brief that omitted the scope add: flagged 3/3.
  - A brief with a markdown-led header: flagged 2/2 after the fix.

Covered by earlier steps. Their homes stay as they are.

- past-ruling-on-send: the page-question judge. Part 2 reuses its reader and helpers.
- brief-reads-owner-rulings: checks agent spawn briefs against the rulings of the decisions a brief names. Its lane-brief entry in the call judge belongs to that step. This step adds no entry there.
- lane-brief-cites-grant: the Grant line goes first.
- lane-brief-template-gaps: four gaps. Two are kept as lines. The rest are carried by role files and guard remedies.

Cost:

- Part 1: git reads of the step and the store. No model call, no file written, no process kept.
- Part 2: one model call per judged brief, plus git reads of the store (one list, one batch read). No file, no timer.

Known limits:

- Matching is by step slug, id and alias only. A ruling filed under another step (example: pr-close-by-batch-runner) is missed.
- A mistyped step slug reads "skipped" and exits 0.
- A step with no topic field prints a topic placeholder that the coordinator fills.
- The spawn guard (the guard that checks agent spawns) counts a marker on any line, not only the first (found by test case 22). So the block's own listing can lift a spawn refusal.
- The builder commits of both parts edited the CI workflow wiring (test config).

Incidents:

- None. The ruling above is the trigger.

Kind: process
Home: rule:roles-brief-contents
