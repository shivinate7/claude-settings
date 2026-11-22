---
id: pending
slug: mutant-anchor-census
---

# Each mutant anchor sits exactly once, and CI reads the table

## The ruling

A mutant in `MUTATIONS` of `hooks/mutate_guard.py` names an anchor: the exact text it replaces. The census, `lint/check_mutant_anchors.py`, fails when an anchor is gone, sits more than once, or names an unknown target.

- It imports the table and keeps no copy.
- A "guard" or "audit" mutant is found across the guard modules by `find_anchor` in `hooks/mutate_shared.py`. No match is stale. Two or more are ambiguous.
- Any other target is read in its own file (`TARGETS`). The anchor must occur there once.
- It prints one `FAIL` line for each bad mutant. The line names the label and the target. It also names the file or folder searched, when it searched one. The run then exits 1. With no bad mutant it prints `PASS mutant anchor census: N mutants` and exits 0.
- It does not check the required-case name or the mutant file names. The mutation run does.
- CI runs it as step "Mutant anchor census" of the checks job. The step runs on a pull request that changes code, and on every run that is not a pull request. The step is also in `merge.readyChecks` of `.github/stamp.json`, so a lane runs it before it goes ready.
- The fixture suite `lint/test_check_mutant_anchors.py` runs as the step "Mutant anchor census fixture suite". Each case builds its own guard folder, target file and table. Each fail case holds a clean mutant in the same table and checks that the clean one is not reported.

## Why and harm

Mistake: note `guard-env-return-named-anchor`. The anchor `        return named` in `hooks/guard_env.py` also matched `return named, every, folders`. It was ambiguous, so no mutant could target that function. Pull request #3782 (the census pull request) adds the census so the next such anchor shows in the checks job.

Harm: an anchor that matches nothing makes a mutant that mutates nothing. An anchor that matches twice makes a mutant that mutates the wrong spot. The mutation run reads each anchor too. For a guard or audit target it stops on a stale or ambiguous anchor. For any other target it stops on a stale anchor only, and `replace(old, new, 1)` then changes the first match, which may be the wrong spot. The census reads the ambiguity of every target.

Cost: it runs once in each pull request run that changes code, and once in each ready check of a draft step (unmeasured: no test counts the runs). It reads each target file and the guard modules, starts no child process, and writes no log and no file, so no log has a reader to name (a probe on 2026-11-22 in a cloud worktree saw no child process started, and the real table of 934 mutants passed in about 1.2 s). The fixture suite `lint/test_check_mutant_anchors.py` builds its cases in its run folder and removes that folder at teardown.

## Known limits

- The census reads anchors only. A mutant whose anchor sits once can still survive every case. The mutation run judges that.
- The fixture suite builds its own tables. The census step itself reads the real table.

Kind: process
Home: lint/check_mutant_anchors.py
