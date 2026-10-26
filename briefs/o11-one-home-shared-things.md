# o11: one home for each shared thing; exceptions build on it, never copy it

Cloud build thread brief. Build advisor (3), Oct 26. Base: main after batch #614 merges (it
carries o2's lint/layout.json); the dispatcher names the commit. Never rebase onto main after
review. Push roadmap edits to the branch only; only "Triage the roadmap (3)" republishes the
roadmap page.

## Task

CLAUDE.md already holds the rule (building-one-home-per-capability). Do not add a second rule.
Make it reachable and checkable:
1. agents/builder.md: before building a shared piece, search for its home; extend it with a
   variant; a copy needs a stated reason in the commit. Keep it to a few lines that point at
   the CLAUDE.md anchor.
2. How a variant extends a shared piece, with one example each, in the home that already fits
   (ux/ for CSS and Swift, testing/ or the test-author agent for tests): CSS (a modifier class
   or a custom property on the shared component), Swift (a parameter or a style), tests (a
   shared fixture or step that a test extends).
3. A copy finder: a small read-only tool in lint/ that lists, for a child repo, (a) vendored
   copies of claude-settings skills (compare against skills/), and (b) files byte-equal or
   near-equal to a claude-settings file. Worked examples it must catch: q_max's copied map
   skill (the drift that failed q_max PR 969), q_max's verbatim copy of a claude-settings test,
   and the three impeccable copies in ios-adblock, joyous and degen, which differ from each
   other.
4. Add a "Copies" probe file to skills/compliance-check that calls the tool. o4 (rework
   compliance-check) runs at the same time and leaves a "Copies" heading for you; touch
   SKILL.md only to point at your probe file.

## Fences

- Never push to child repos; read them under /home/user only.
- Shared skills are pinned, never vendored: the tool reports copies, it fixes none.
- Any new record: put it at the decisions path lint/layout.json names on your base.

## Failure classes and proof

- The finder goes red on the three worked examples and stays quiet on a repo with no copy.
- Scanner rule building-scanner-respects-strings applies if the tool scans source text.
- This adds a check and changes the builder agent: a fresh Sonnet reviewer reads the diff.
- Run ste-changed and the new tool's tests through `verdict`.

## Report

Add one line, "Port to other repos: yes or no, and why" (shiv's ruling on c52, Oct 26). Cap 20 lines: Done, Deviations, Next, and what the finder found per child repo, one line each.
Send the green, reviewed head and branch to "Advise the claude-settings build (3)". Do not
merge, and do not rebase onto main. No question for shiv: park any in the PR body.
