# Merge notes: PR #2209 merge of febeda66f

Merge of PR #2121 (source, head `febeda66f`) into PR #2209 (target, branch `owed-record-chained-push`, tip `97f9a7f96` before the merge). Stopped: the `test-author-scope` guard refused the test-author's Edit to `hooks/guard.py`. Roadmap step 931 (`merge-route-author-paths`) fixes that refusal.

Source: the in-progress merge worktree `agent-a205f96164cd2c50e`. Line numbers below are that worktree's.

## hooks/guard.py conflict hunks

Hunk 1, imports. The marker lines (465, 467, 469) are dropped. Both sides are kept:

Ours (#2209, 97f9a7f96): guard.py line 466.

```python
            conflict_markers_hit, head_moved_before, gh_call_of, git_call_of, merge_call_of, merge_check, merge_check_reason, record_writer_hit, records_page_hit, role_proof_hit,
```

Theirs (#2121, febeda66f): guard.py line 468.

```python
            HOOK_BYPASS_REASON, conflict_markers_hit, hook_bypass_hit, _push_calls, gh_call_of, git_call_of, merge_call_of, merge_check, merge_check_reason, record_writer_hit, records_page_hit, role_proof_hit,
```

Hunk 2, push loop. The marker lines (4336, 4342, 4346) are dropped. Both sides are kept:

Ours (#2209, 97f9a7f96): guard.py lines 4337-4341.

```python
    push_segments = split_segments(stripped)
    for seg_number, segment in enumerate(push_segments):
        for subcommand, args in git_calls(push_text(segment)):
            where, overrides = push_target(segment, stripped, cwd) if subcommand == "push" else ("", {})
            verdict = push_verdict(args, where, overrides) if subcommand == "push" else ""
```

Theirs (#2121, febeda66f): guard.py lines 4343-4345.

```python
    for segment in (part for text in texts for part in split_segments(text)):
        for args, where, overrides in _push_calls(segment, stripped, cwd):
            verdict = push_verdict(args, where, overrides)
```

## Planned guard.py resolution

Imports: take the union of both lists. That is 13 names:

```
HOOK_BYPASS_REASON, conflict_markers_hit, hook_bypass_hit, _push_calls, gh_call_of, git_call_of, head_moved_before, merge_call_of, merge_check, merge_check_reason, record_writer_hit, records_page_hit, role_proof_hit,
```

`head_moved_before` comes from HEAD. `HOOK_BYPASS_REASON`, `hook_bypass_hit` and `_push_calls` come from the other side. The rest are on both.

Push loop: replace the whole hunk. Build `steps` from `texts` (the stripped command, then its substitution commands). Split each text into segments, and pair each segment with the segments before it in the same text. Then loop over `steps` with main's `_push_calls` loop:

```python
    steps = [(segments[:i], segment)
             for text in texts
             for segments in [split_segments(text)]
             for i, segment in enumerate(segments)]
    for before, segment in steps:
        for args, where, overrides in _push_calls(segment, stripped, cwd):
            verdict = push_verdict(args, where, overrides)
```

For the stripped text, `before` is the same list HEAD built as `push_segments[:seg_number]`.

The shared body from line 4347 stays as it is. Lines 4347-4368 read no `subcommand`, `push_text` or `push_target`.

Line 4355 is shared and sits outside the hunk. It changes one argument: `head_moved_before(push_segments[:seg_number])` becomes `head_moved_before(before)`:

```python
owed = owed_record_hit(args, where, overrides, cwd, head_moved_before(before))
```

## hooks/mutate_guard.py resolution

No conflict markers are left in this file. Lines 415-470 of the resolved file, verbatim. The block starts and ends mid-entry on purpose:

```python
     'if False:', "guard", 'C12 an entry for branch A at H'),
    ("push-owes-review-record: a branch that no longer descends from the head still counts as holding it",
     'if tip != sha:',
     'if False:', "guard", 'C13 an entry at H, then the remote branch rewritten off H'),
    ("push-owes-review-record: the default-branch skip is dropped, so a head main holds still owes a record",
     'if base and base.startswith("origin/"):',
     'if False:', "guard", 'G1 the reviewer stopped at a head on main'),
    ("push-owes-review-record: the newest entry per branch is not picked, so every unrecorded entry governs",
     '                if newest is None or written > newest:\n                    newest, heads = written, [sha]\n'
     '                elif written == newest:\n                    heads.append(sha)\n                break',
     '                heads.append(sha)\n                break', "guard", 'G2 an entry at H0 never got a record'),
    ("push-owes-review-record: the moved flag is ignored, so a chained push reads its source as HEAD",
     '(None if moved else _plain_source(',
     '(_plain_source(', "guard", 'H1 a commit then a push in one command'),
    ("push-owes-review-record: reset is dropped from the head-moving verbs",
     '("commit", "revert", "reset") + _CONFLICT_VERBS',
     '("commit", "revert") + _CONFLICT_VERBS', "guard", 'J3r reset --soft to a commit past H'),
    ("push-needs-review-record: a verdict on the Done label line is not read",
     '                if loose and marker:\n                    return loose.group(), "round" if marker.group(1) else "fix", int(marker.group(1)) if marker.group(1) else None',
     '                if loose and marker:\n                    return None', "guard",
     'a reviewer FAIL round 1 on the Done label line, no record, then the push'),
    ("push-needs-review-record: a held report is never counted",
     '    return counted',
     '    return []', "guard",
     'a FAIL naming diff base A then head B'),
    ("push-needs-review-record: a commit on main counts for a held report",
     '    if on_main is not False:',
     '    if False:', "guard",
     'a FAIL naming only diff base A'),
    ("push-needs-review-record: a report no PR counts is dropped, not kept for the next PR",
     'early = [report for report in early if report[:-1] not in counted]   # held for a later PR',
     'early = []', "guard",
     'a FAIL naming head B, then a PR for another branch'),
    ("push-needs-review-record: the Done label round marker ignores case",
     '", re.I)\n_LABEL_WORD',
     '")\n_LABEL_WORD', "guard",
     'a Done label line reading Round 1 with a capital R'),
    ("push-needs-review-record: the Done label verdict is the first all-caps word",
     ' if word.group() in verdicts',
     '', "guard",
     'a Done label line whose first all-capitals word is HEAD'),
    ("force-push: quoted text is read as a push",
     'return PUSH_QUOTED.sub(" ", segment)', 'return segment', "guard",
     'false alarm: --force quoted in a commit message'),
    ("force-push: a deny names the wrong reason",
     'refuse(tool, verdict, "force-push", PUSH_REASON, "git push " + " ".join(args))',
     'refuse(tool, verdict, "force-push", PUSH_ASK_REASON, "git push " + " ".join(args))',
     "guard", 'the long force flag'),
    # push-main and push-stray-branch (owner rulings 207 a and 206 a).
    ("push-main: a colon-less main is not a destination",
     '            elif source.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK:\n                # A local origin makes main() empty; the other refspecs are still read for agent and stray.\n                if main():\n                    return "main"',
     '            elif False:\n                if main():\n                    return "main"', "guard", 'a push of main from a feature branch asks'),
    ("push-main: a refspec target of main is not a destination",
     '                if target.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK and main():\n                    return "main"',
     '                if False:\n                    return "main"', "guard", 'HEAD:main from a feature branch asks'),
    ("push-main: a main refspec ends the read on a local origin",
```

All 8 mutants kept, anchors unchanged. That is the merge brief's claim. It was not re-counted when this file was written.

The `ask-step-hidden` mutant anchors on the `_push_calls` line. Keep that line's 8-space indent and the name `segment`. In origin/main's copy of the file, the anchor is at lines 2214-2216.

## Note

A push inside `bash -c` or `eval` gets `moved=False`. Both sides of the merge have this gap. The planned resolution does not close it.
