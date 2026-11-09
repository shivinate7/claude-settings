# Merge notes: lane notes-fix-page, main 624dcc188

These notes cover five ordinary merges of origin/main 624dcc188 into lane branches. They were written by an Explore agent (sonnet, audit) and checked by applying each resolution to a scratch copy and running the suites. NEEDS RULING: none.

Do the 624dcc188 merge first, with these notes. Then do the batch 70 merge on top. Its conflicts are not covered here.

Notation: "ours" is the lane branch and "theirs" is origin/main 624dcc188. Line numbers come from `git show <tree>:<file>`, where tree = `git merge-tree --write-tree origin/<branch> origin/main`, markers included. Each hunk is rebuilt from the listed pieces in order.

## 1. nfp-undo-pr-body (#1969, head 9628a6d59), tree 3b7c6168a
- merge/merge.py hunk A, markers 2621-2644. Keep theirs 2624-2642 (refuse_unstacked_head plus its trailing blank line), then ours 2622 (`def ci_job_run(wt, *args, pr_body="", notes=None):`). Delete theirs 2643.
- merge/merge.py hunk B, markers 2695-2701. Keep theirs 2698-2699 (`if target.isdigit():` / `refuse_unstacked_head(root, head, base)`), then ours 2696 (the call with `pr_body=pr_body`). Delete theirs 2700.
- merge/test_lane_lint.py, markers 417-618. Keep ours 418-437 (the ref-target test), one blank line, then theirs 439-617 (stacked_pr_on_release and the stacked-PR tests).
- Proof: `python3 merge/test_lane_lint.py` gave 60 OK. merge/test_merge.py gave 1257 tests with 1 sandbox gh error (RestRoutes.test_a_failed_or_errored_status_is_red), which is not in a conflicted area.

## 2. nfp-push-chain-guards (#2074, head 99b4ffefc), tree 55814ec0d
- hooks/guard.py, markers 448-454. Replace the whole block with:
```
            PUSH_AGENT_REASON, PUSH_NEW_BRANCH_REASON, PUSH_REASON, PUSH_STRAY_REASON, cmd_exe_delete_hit,
            delete_text, linked_nm_hit, parent_delete_hit, push_ask_hit, push_new_branch_hit, push_verdict,
            rm_delete_hit,
```
- hooks/mutate_guard.py, markers 450-535. Line 449 stays. Keep theirs 498-534 (the re-pointed stray mutant `'if merge == current() or upstream:'` plus the 10 push-agent-branch mutants), then ours 453-496 (the 10 push-new-branch mutants). Delete ours 451-452 (the old stray mutant, whose anchor is gone from main). Main's mutants go first; merge 3 depends on this order.
- hooks/test_guard.py hunk 1, markers 772-813. Keep ours 773-774 (PUSHNEWBR, PUSHBATCH), then theirs 780-812, then ours 778 (PUSH_NEWBRANCH_RULE). Delete ours 775-777 (duplicate rules).
- hooks/test_guard.py hunk 2, markers 2722-2729. Keep theirs 2725-2727. Replace theirs 2728 with `              PUSHAGENTSHORT, PUSHAGENTEIGHT, PUSHAGENTCFG, PUSHNEWBR, PUSHBATCH],`. Delete ours 2723.
- Proof: `python3 hooks/test_guard.py` (CI shards it) and `python3 hooks/mutate_guard.py`. The scratch run of `GUARD_FAMILY=push-delete` passed 789 of 789, and the push mutants were 41 of 41 killed. The full suite and the full mutant run were not run.

## 3. nfp-pnb-reflog-pin (#2308, head eb3d981ce), after #2074's resolved head
- Merging #2074's resolved head into reflog-pin: all three files merge clean (git merge-file), byte-equal to the direct resolution.
- For a direct merge with main instead (tree e2cf73522): guard.py and test_guard.py are as in merge 2. mutate_guard.py markers 450/503/541: line 449, then theirs 504-540, then ours 453-502 (#2074's block plus the `@{` mutant). Delete ours 451-452.
- Proof: as above. The scratch run passed push-delete 791 of 791, with 42 of 42 push mutants killed.

## 4. nfp-pnb-tests (#2419, head b8e50a133, PR base reflog-pin), after #3's resolved head
- guard.py and mutate_guard.py merge clean.
- test_guard.py has one conflict in the fixture constants: the REF READER constants (PUSHPACKED to PUSHRELWT, ours) against #3's PUSHOWNREF/PUSHLOCAL/PUSHAGENT constants. Keep the REF READER lines through PUSHRELWT, then #3's lines through its "The rule ids the push asks name" comment. Delete the branch's "two new asks" comment line.
- For a direct merge with main (tree a35c588aa): test_guard.py hunk 1, markers 772-831: ours 773-792, then theirs 798-830, then ours 796; delete ours 793-795. Hunk 2, markers 2740-2747: keep theirs 2743-2745; replace theirs 2746 with the PUSHAGENTSHORT... PUSHBATCH], line above; delete ours 2741.
- Proof: as above. The scratch run passed push-delete 817 of 817, with 42 of 42 push mutants killed.

## 5. nfp-inbox-guard (#1470, head a85859468), tree 675998741
- docs/debts/inbox-send-error-counts.md: `git rm` it, taking main's deletion (coordinator 15:36).
- hooks/feedback_guard.py hunk 1, markers 638-642: keep ours 639 then theirs 641:
```
        self.session_id, self._by_id, self._pos = session_id, None, {}
        self.failed = set()
```
- hooks/feedback_guard.py hunk 2, markers 686-697 (`_uses_after`), keeping both conditions:
```
        """The tool_use blocks after `start` that did not fail: a use whose id is in `self.failed`, or whose result, paired by
        tool_use_id, is an error, is left out. A use with no id or no result stays."""
        results = self._results()
        return (use for r in self.records[start:] if r.get("type") == "assistant"
                for use in _transcript.tool_uses(r)
                if use.get("id") not in self.failed
                and (results.get(use.get("id")) or {}).get("is_error") is not True)
```
- lint/_transcript.py, markers 110-129: keep ours 111-114 (`results_by_id`), two blank lines, then theirs 116-128 (`failed_tool_use_ids`).
- hooks/test_feedback_inbox.py hunk 1, markers 1955-1972: ours 1956-1961, then the line `                       "fb-0958-21", REPO_SLUG)` and two blank lines, then theirs 1963-1971. Shared tail line 1973 then closes the second case.
- hooks/test_feedback_inbox.py hunk 2, markers 4246-4250: ours 4247, then theirs 4249.
- Proof: `python3 hooks/test_feedback_inbox.py` gave "PASS: all 193 cases green".
