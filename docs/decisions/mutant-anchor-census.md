---
id: pending
slug: mutant-anchor-census
---

# Each mutant anchor sits exactly once, and CI reads the tables

## The ruling

A mutant names an anchor: the exact text it replaces. Two tables hold mutants: `MUTATIONS` of `hooks/mutate_guard.py` (the guard table) and `MUTATIONS` of `janitor/mutate_sweep.py` (the sweep table). The census, `lint/check_mutant_anchors.py`, fails when an anchor is gone, sits more than once, or names an unknown target.

- It imports both tables and keeps no copy.
- A guard-table "guard" or "audit" mutant is found across the guard modules by `find_anchor` in `hooks/mutate_shared.py`. No match is stale. Two or more are ambiguous.
- Any other guard-table target is read in its own file (`TARGETS`). The anchor must occur there once.
- A sweep row names one file in `SOURCES`. Its anchor is matched in that file by `find_anchor`. A row whose target is not in `SOURCES` is unknown.
- It prints one `FAIL` line for each bad mutant. The line names the label and the target, and the file or folder searched, when it searched one. A sweep line also names `janitor/mutate_sweep.py`. A row with too few fields prints `FAIL malformed row`, naming its label or `row N` and its table, and the closing line reads `mutant anchor census failed: N of M mutants have a bad row or anchor`. The run then exits 1. With no bad mutant it prints `PASS mutant anchor census: N mutants` and exits 0.
- It does not check the required-case name or the mutant file names. The mutation runs do.
- CI runs it as step "Mutant anchor census" of the checks job. The step runs on a pull request that changes code, and on every run that is not a pull request. The step is also in `merge.readyChecks` of `.github/stamp.json`, so a lane runs it before it goes ready.
- The fixture suite `lint/test_check_mutant_anchors.py` runs as the step "Mutant anchor census fixture suite". Each case builds its own guard folder, target file and `janitor/sweep.py` in a run folder, and sets its own tables. Each fail case holds a clean mutant in the same table and checks that the clean one is not reported.

## Why and harm

Mistake: note `guard-env-return-named-anchor` (a guard anchor matched twice, so no mutant could target that function). Pull request #3782 (the census pull request) added the census so the next such anchor shows in the checks job. On 2026-11-25, two dead sweep anchors passed the ready check. The ready checks run the census, not the sweep mutation run, which is the one that stops on a dead sweep anchor.

Harm: an anchor that matches nothing makes a mutant that mutates nothing. An anchor that matches twice makes a mutant that mutates the wrong spot. The mutation runs read each anchor too. The guard run stops on a stale or ambiguous anchor for a guard or audit mutant. For any other guard target it stops on a stale anchor only. The sweep run stops on a stale sweep anchor only. Either way `replace(old, new, 1)` then changes the first match, which may be the wrong spot. The census reads the staleness and ambiguity of every row in both tables.

Cost: it runs once in each pull request run that changes code, and once in each ready check of a draft step (unmeasured: no test counts the runs). It reads each target file, each sweep source file and the guard modules, starts no child process, and writes no log and no file, so no log has a reader to name. One more import, 0.8-1.9 s per run over 9 warm runs on one Mac, 2026-11-25, against 0.8-1.1 s before (3 warm runs each, measured by the builder, not pinned by a test). The fixture suite `lint/test_check_mutant_anchors.py` builds its cases in its run folder and removes that folder at teardown.

## Known limits

- The census reads anchors only. A mutant whose anchor sits once can still survive every case. The mutation runs judge that.
- The census reads two tables, the guard and sweep tables. `lint/test_all_jobs_passed.py` holds three more anchor tables (`MUTATIONS`, `DAILY_DEFECTS`, `CHILD_MUTATIONS`), and that suite's own tests check each. `hooks/mutate_shared.py` is the helper, and `hooks/mutate_js.mjs` makes its mutants from a parse tree.

Kind: process
Home: lint/check_mutant_anchors.py
