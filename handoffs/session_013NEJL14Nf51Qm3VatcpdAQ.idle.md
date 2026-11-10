# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL14Nf51Qm3VatcpdAQ

## Reply at 2026-11-10T17:25:55Z UTC

IDLE (B). Handoff for lane notes-fix-large-2 (session_013NEJL14Nf51Qm3VatcpdAQ):
Goal: fix rows 7-12 of docs/plans/notes-sort/fix-large.tsv, plus each gap found on the way. Each PR gets a red test first, rounds 1-3 (net value for a guard or check), a merge-tool review record, lane lint, then a hand-off to runner 8.
Merged: #2216, #2290, #2278, #2319 (and earlier 1574, 1663, 1802, 1899, 2090).
Open, reviewed, released to runner 8 and waiting for merge (PR head): 1456 53bb4e3ab; 1462 475d3f095; 1472 f785eff83; 1512 84fd525bb; 1615 ce85afc97 (on 1462); 1625 5a545b6e5 (on 1456); 1806 fd3032ec1 (on 1512); 1875 428890e36; 1882 1dcf9ae5f (on 1875); 2019 72b78f21b; 2096 4b4650eb1; 2188 cdd53f954 (after 2096).
Left:
- A merge-fix lane for whichever of 1456 and 1462 merges second; the stacked 1625 or 1615 is then rebased.
- Queued notes, to file once their PRs merge: map11 shell idioms (1625); a T11o last-wins twin and a T11r uses-side pin (1472); tested-by.test.mjs:885 overstates (1615); mutate_shared.py in MUTATION_TEST_NAMES, decision builders-cannot-edit-tests omits the mutate step, guard.py says "gates", a removed-side swap pin, and the author path refuses `env: MUTATE_SHARD` (1899/2019).
- Unstarted, each needs a design pass:
  - run check_comment_narration before a test-author pushes (dated comments reached lane lint on 2278 and 1615);
  - a guard that a Co-Authored-By trailer names the model that ran;
  - docs/debts/notes.md on main repeats slugs (touched-tests-command-flags-dropped twice).
Files: handoff /root/.claude/handoffs/180a4e83-a2cd-5b87-a71f-a63fff9ac464.md. Records are comments on each PR. No unpushed commits, no servers.

