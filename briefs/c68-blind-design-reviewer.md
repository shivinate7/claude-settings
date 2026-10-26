# c68: the blind design reviewer stays blind to the repo's design spec

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main 853b512.
Base: main 853b512; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Finding (unmeasured)

`skills/design-review` step 2 says Reviewer B never sees the design spec. But Reviewer B runs
impeccable, whose SKILL.md Setup step 1 runs `impeccable context`. The guard rule
impeccable-review-only refuses that, and impeccable's fallback then reads the repo's
PRODUCT.md and DESIGN.md directly. So in a repo with a DESIGN.md, Reviewer B likely reads the
spec, and every run hits one guard refusal.

## Task

1. Red first: in a scratch fixture repo with a DESIGN.md and one screenshot, run the design
   review as written and record what Reviewer B reads (file reads, the guard refusal). If it
   does not read the spec, stop and report: the finding is false.
2. Fix (a), triage's pick: Reviewer B's brief in design-review skips impeccable's Setup and
   fallback and judges only the screenshots. Fix (b), a scratch folder holding only the
   screenshots, only if (a) cannot hold.
3. Green: the same run reads no spec file and draws no guard refusal.

## Fences

- In scope: skills/design-review and its tests. Do not edit vendored skills/impeccable; the
  fix lives in the brief design-review gives Reviewer B.
- Do not change guard rule impeccable-review-only.
- d7 (#611) adds one pointer line to skills/design-review/SKILL.md; keep clear of it.

## Failure classes and proof

- This changes a review's behaviour: a fresh Sonnet reviewer reads the diff.
- Report the red and green runs in the PR body; run checks through `verdict`.

## Report

Cap 15 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (3)". Do not merge, and do not rebase onto main. No
question for shiv: park any in the PR body.
