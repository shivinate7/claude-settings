# o12: bring every skill up to date with the current rules

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main 853b512.
Base: main 853b512; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Task

One pass over five skills in `skills/`: ci-hygiene, design-review, fresh-prose, impeccable,
plain-english-map. Leave compliance-check alone; o4 (rework compliance-check) owns it.

Per skill, answer three questions, then fix, merge or cull:
1. Does it still match CLAUDE.md, GLOSSARY.md and `decisions/` as they are on main now?
   Name each sentence that disagrees, and the rule or decision it disagrees with.
2. Is it still used? Grep CLAUDE.md, agents/, hooks/, other skills and the child repos
   (read only; never push to them). A skill nothing names and no rule needs is a cull
   candidate: say so in the PR body, with the grep you ran.
3. Does it start processes or load files it never uses (c26, watching costs less than what
   it watches)? Name each one.

impeccable is vendored. Update it to the newest upstream version that passes its checks
(rule verification-newest-that-passes): read the changelog first, use the existing
impeccable-sync workflow's source, and say which version you took and why.

## Fences

- In scope: files under `skills/` for these five, and the tests or lints that read them.
- Out of scope: compliance-check (o4); the copies vendored in ios-adblock, joyous and degen
  (o11 owns the copy check); o2 lane 2's folder move. Batch #608 adds `lint/layout.json`;
  do not touch `lint/` or `hooks/guard.py`.
- A cull deletes the skill and every pointer to it in one commit.

## Failure classes and proof

- A rule sentence in a skill that contradicts CLAUDE.md is the defect; CLAUDE.md wins unless
  the sentence names a stale rule, then use outcomes-stale-decision-protocol and park it.
- Run ste-changed and the skill's own tests through `verdict`.
- A change that alters a rule's behaviour goes to a fresh Sonnet reviewer; wording-only
  changes merge on green.

## Report

Cap 20 lines: Done, Deviations, Next, one line per skill (kept, fixed, merged or culled).
Send the green, reviewed head and branch to "Advise the claude-settings build (3)". Do not
merge, and do not rebase onto main. No question for shiv: park any in the PR body.
