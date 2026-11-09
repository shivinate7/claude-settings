# Merge notes: lane notes-fix-large-1, main 624dcc188 into chain A and the frozen stack

Written by lane notes-fix-large-1 (session_013NEJL4DPEKRiC91yHkQV7m), 2026-11-09 15:41 CST, U1 ruled 15:44 CST. Notes, not a record: triage's branch cleanup deletes this branch once the merges land.

## Rules for the resolver
- One test-author owns each whole merge, product files included (ruling mixed-merge-resolver, owner item 420 a). Your hooks must be current: `grep -c merge_route_paths ~/.claude/hooks/guard.py` reads non-zero.
- Ordinary `git merge`. No rebase, no force push, no amend. Bottom first. Only #1486 merges origin/main. Each level above merges the NEW head of the level below.
- Main's behaviour stands. The branch's own changes stand. Union lists without duplicates. Each claim appears once.
- After each merge: `python3 bin/verdict python3 lint/check_silent_undo.py --upstream <parent> --head HEAD --strict`, and the guard family tests. A Drops-lines trailer shares the last trailer paragraph with Co-Authored-By.
- If batch 70 moved main past 624dcc188, merge the new main at #1486. Then re-read each hunk: these notes name the parent each was read against.
- Stop and report on any hunk these notes do not cover. U1 below is ruled.

## Stacks, bottom first
- Chain A: #1486 notes-fed-test-write (base main) → #2211 builder-find-cp-tests → #2305 builder-find-cap-pins-v2 → #2331 cp-written-limits → #2373 made-folder-glob → #2384 fold-root-unc → #2432 fed-cp-gaps → #2448 fed-cp-limits.
- Frozen stack, on #1486: #1613 fed-write-followups → #2022 fed-write-r3 → #2133 frozen-output-flags → #2288 frozen-reader-limits → #2338 frozen-cd-limits → #2402 trailing-amp-cd → #2418 frozen-cd-gaps → #2437 case-arm-gaps.
- Warning: the frozen stack does not chain by ancestry. 3f1df4d18 (#1486) is not an ancestor of f9fb50537 (#1613), and f9fb50537 is not an ancestor of eb848f298 (#2022). So #1613's merge of #1486's new head also brings #1486's own branch changes. Its hunks may differ from the frozen notes below, which were read against origin/main.

## Chain A (read against the simulated merge of the level below; exact)
Old heads: #1486 3f1df4d18, #2211 1bf3b7a6c, #2305 2522c9cb3, #2331 0ac7aad2b, #2373 be8a18f23, #2384 067e24954, #2432 4f10abbcf, #2448 ddcb754d1.

- #1486 vs origin/main 624dcc188 (merge base 8bc28980b). Three hunks:
  - docs/decisions/builders-cannot-edit-tests.md:66: both sides rewrote the "Reads" bullet (ours: read_fed feeds; main: script files run by name). Replace the whole marker block with the single bullet "Literal A" below. All 29 sentences of both sides appear once.
  - hooks/guard.py:2257-2274: replace the marker block with "Literal B" below (docstring and return of builder_shell_test_hit; one POWERSHELL_CALL line).
  - hooks/test_guard.py:17991-18015: keep both. Ours (20 SHELL_TEST_ALLOWS read_fed cases) first, then theirs (the mutate_x comment and entry). Drop the three marker lines.
- #2211, #2305, #2331, #2373, #2384: no conflict against #1486's resolved head and the level below. Commit the merge as is.
- #2432 docs/decisions/builders-cannot-edit-tests.md:66-77: ours rewrote the Reads bullet ("It adds refusals ... and lifts these reads") and adds seven bullets. Theirs is #1486's Literal A. Replace the marker block with "Literal C" below (8 lines). The lines after the block stay.
- #2448: no conflict.
- Check: after all eight, hooks/guard.py and hooks/test_guard.py parse, with no conflict markers under docs/ or hooks/.

## Frozen stack (read against origin/main; approximate above #1486)
Old heads: #1613 f9fb50537, #2022 eb848f298, #2133 e94a2c537, #2288 fdae8032b, #2338 33e77ec07, #2402 4660dbec2, #2418 6b4385a8a, #2437 b7d549d3e. Line numbers are marker lines in `git merge-tree --write-tree <head> origin/main`.

### Hidden defects that merge with no marker (fix in #1613's merge)
- H1: hooks/guard_frozen.py would define `_cp_start` twice. Main's `def _cp_start(raw) -> int` returns -1. The branch's `def _cp_start(raw, keywords=False)` returns None, and the later def wins. Delete the branch's def, with its trailing blank line. Call sites: see #1613's 594 and 668.
- H2: main renamed test helper `hm_deny` to `hm_refuse`, with the same body. Delete the branch's `def hm_deny` and rename every `hm_deny(` call to `hm_refuse(`.
- Leave main's own duplicate test_guard.py names (`listing`, `_load_git_reads`, `counted`, `main`).

### U1, unresolved: the copy-destination rule (every level from #1613)
- Where: guard_frozen.py at #1613:647, #2022:746, #2133:762, #2288:823, #2338:800, #2402:800, #2418:800, #2437:809. Test blocks: #1613:18108, #2022:18232, #2133:18411, #2288:18603, #2338:18810, #2402:18934, #2418:19068, #2437:19178.
- Main (e9c6e9629, "Keep a live substitution, a repo head and a frozen copy destination judged"): refuses a copy whose destination holds `$`, a backtick, `*`, `?`, `[`, `{`, `<` or `>`, unless the destination is a lone quoted variable such as `"$f"`.
- Branch: a test copied to a fixed prefix outside the test roots is a read (`_fixed_prefix_outside`). Main's condition makes that unreachable.
- Branch cases that go red under main's rule: `for f in tests/*.py; do cp "$f" /tmp/backup/$f; done` and `for f in tests/*.py; do cp $f /tmp/bak_$(basename $f); done`.
- Ruled (coordinator 15:44 CST 2026-11-09, rule building-port-keeps-behaviour): main's refusal at e9c6e9629 stands. At each level, keep theirs (main's condition), and drop the branch's `_fixed_prefix_outside` branch and its def if nothing else calls it. Re-point the two branch cases above from allow to deny, red then green, in your own worktree. Do not stop here.

### Q2, check while resolving
Removing the `keywords` flag drops the `$(` skip that the branch's LOOP_KEYWORDS (guard_core.py) gives fed commands. Main's resolve_command skip set lacks it. Run the frozen family tests after #1613. A red fed `cp` case starting with `$(` is a stop-and-report.

### Per level
- #1613 (tree dce66441d):
  - record :66: if #1486 took Literal A, re-read this hunk against #1486's new head. Otherwise, in the order 67, 73, 68, 69, 70, the branch's Cost line 71 reads "no process, no file written, no timer". After "(debt note `fed-loop-word-cost`).", add: "A builder's shell call that runs python or node by a file name reads that file once, at most 256 KB; a python file over that size is parsed at most `_PY_PREFIX_TRIES` times." Drop 74-76 (duplicates).
  - guard.py:2257: Literal B.
  - guard_frozen.py:12: the import union, "Import 21" below.
  - guard_frozen.py:594: keep theirs (`start = _cp_start(raw)` / `if start < 0:`). Apply H1. Remove the `keywords` parameter from `_copy_reads`. Its caller (merged ~1360) becomes `_copy_reads(raw, predicate, cwd, prefix=command_position)`.
  - guard_frozen.py:647: U1.
  - guard_frozen.py:668: same as 594, for `_cp_link_source`. Its caller (~1357) drops `bool(fed)`. Keep `return ""`.
  - guard_frozen.py:1402: "Sed 8" below.
  - guard_frozen.py:1440: ours (sed-script helpers `_BRACE_LIMIT` .. `_sed_script_words`), two blank lines, then theirs (`_PS_LAUNCHER`, `_powershell_scripts_of`).
  - test_guard.py:18108: ours (53 allow cases), then theirs (2 lines). Re-point the two U1 cases to deny.
- #2022 (tree 07eac8d8a):
  - record :66: #1613's rule, with #2022's text for the two branch bullets.
  - guard.py:2257, guard_frozen :12, :693, :767: as in #1613. :746 is U1.
  - guard_frozen :1515: #1613's "Sed 8", then append "Output 4" below after the sed loop.
  - guard_frozen :1557: ours block (`_command_reads`, `_split_background`, `_output_targets`), then theirs (PS block).
  - test_guard :18232: as in #1613's 18108.
- #2133 (tree 9e9bac527):
  - Same as #2022: record :66, guard.py :2257, guard_frozen :12, :709 (=594), :783 (=668). :762 is U1. test_guard :18411 is U1.
  - guard_frozen :1476: "Typed 2" below.
  - guard_frozen :1525, in this order:
    - a. theirs' two comment lines and `word = _typed(word.rstrip(")`") or word, word)`;
    - b. ours' `glued = index and word.startswith("&") and raw[index - 1].endswith(">")` / `if glued:` / comment / `word = word[1:]`;
    - c. theirs' `pieces = _words_of(word) if _has_quote(word) else [word]`;
    - d. theirs' two comment lines and `pieces = [_typed(piece.rstrip("`") or piece, piece) for piece in pieces]`;
    - e. ours' `words.extend(pieces)`, `shown.extend(pieces)`, `kept = scripts[number][index]`, `if glued:` / `kept = kept[1:]`;
    - f. theirs' `script.extend(_words_of(kept) if _has_quote(kept) else [kept])`;
    - g. ours' sed loop and `_output_targets` loop, unchanged.
  - guard_frozen :1590: ours (`_commands_run`, `_reads_only`, `_READERS`), then theirs (PS block).
- #2288 (tree b936a6ea1):
  - Same as #2133: record, guard.py, :12, :770 (=594), :844 (=668), :1537 (= Typed 2). :823 is U1.
  - guard_frozen :1587: #2133's 1525 order, with step e's `words.extend(pieces)` replaced by "Escapes 3" below.
  - guard_frozen :1655: ours (`_outside_single_quotes`, `_reads_only` change), then theirs (PS block).
  - test_guard :18603 is U1.
  - test_guard :30452: ours (`session_home_background_cd_case` and its cases), then theirs (`sh_lost_lane` and its cases).
- #2338 (tree 4f6d8137b):
  - record and guard.py as above. guard_frozen :12: "Import 24" below.
  - guard_frozen :747 (=594), :821 (=668), :1514 (= Typed 2), :1566 (= #2288's 1587). :800 is U1.
  - guard_frozen :1607: ours (per-folder loop for a cd that may not run, sed `e` per folder), then theirs (PS block).
  - guard_stream.py:435: theirs' docstring (it holds ours'), theirs' `sleeps, loop, watcher, run_watch, followed = [], False, "", "", False` and `token_rows = []`. Then ours' two comment lines and generator header `for segment in (part for whole in segments for part in ([whole] if is_powershell(whole) else split_background(whole))):` in place of `for segment in segments:`.
  - test_guard :18810 is U1.
  - test_guard :19582: ours (FROZEN_COST_LABEL, its LOG_CHECKS_EXTRA append and LOG_FAMILY), then theirs (UNREAD labels, AGENT_NOTED loop).
  - test_guard :30675: ours, then theirs (as #2288's 30452).
- #2402 (tree be4fe553a): no new hunks. All 13 match #2338 by text. test_guard :18934 (U1), :19706, :30799.
- #2418 (tree 8402cd658):
  - New hunk, guard_frozen :1608: ours (the `sh -c` / `bash -c` body walk: `tokens = bodies[number] if follow_cd else None`, `body = guard_core.inline_script(tokens) if tokens else ""`, the `_shell_write_scan` block returning `_from_cwd(hit, at, cwd)`), then theirs (PS block).
  - All other hunks as in #2338, at #2418's lines.
- #2437 (tree c5d2581d4):
  - New hunk, test_guard :4499. The two drive-path lines once, as `hm_refuse`. Then ours' two comment lines and its three case/control cases, renamed to `hm_refuse`. Then theirs' for-loop case.
  - guard_frozen :1617 is as in #2418's 1608. All other hunks as in #2338, at #2437's lines.

## Literals
### Import 21 (guard_frozen.py:12, #1613 to #2288)
```
from guard_core import (
    LOOP_KEYWORDS, PS_DOUBLE_QUOTES, PS_SINGLE_QUOTES, PS_STRAIGHT_QUOTES, REDIRECT, PowerShellScript,
    _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally, _walk_wrappers, basename,
    checkout_root_by_stat, dir_before_segment, is_powershell, nested_script, norm, path_is_inside,
    resolve_command, segment_tokens, split_segments,
)
```
### Import 24 (guard_frozen.py:12, #2338 and up)
```
from guard_core import (
    LOOP_KEYWORDS, PRINTERS, PS_DOUBLE_QUOTES, PS_SINGLE_QUOTES, PS_STRAIGHT_QUOTES, QUIET_COMMANDS, REDIRECT,
    PowerShellScript, _expanded, _resolved, _split_heredocs, _strip_heredoc_bodies_unconditionally,
    _walk_wrappers, basename, checkout_root_by_stat, dir_before_segment, is_powershell, nested_script, norm,
    path_is_inside, resolve_command, segment_tokens, split_background, split_segments,
)
```
### Sed 8 (guard_frozen.py, #1613's 1402)
```
                script.extend(_words_of(kept) if _has_quote(kept) else [kept])
            files, commands = sed_targets.get(index, ((), ()))
            # a sed script's w or W names a file, and its e runs a command: the words that command writes
            for target in [*files, *(word for command in commands for word in _sed_command_words(command))]:
                # `>` marks the target as written, as a redirect would: a sed with no -i has no other write mark.
                words.extend((">", target))
                shown.extend((">", target))
                script.extend((">", target))
```
### Output 4 (#2022 and up, after the sed loop)
```
        for target in _output_targets([_unquoted(word) for word in raw]):   # the file an output flag names is written
            words.extend((">", target))
            shown.extend((">", target))
            script.extend((">", target))
```
### Typed 2 (#2133 and up)
```
    parsed = [[_typed(word, segment) for word in _quoted_words(segment)] for segment in segments]
    own = [_reads_only(raw) for raw in parsed]
```
### Escapes 3 (#2288 and up, step e)
```
                # printf and echo -e read `\n` as a line break, so a path ends there: its parts are candidates too
                cut = [part for piece in pieces for part in re.split(r"\\[nrt]", piece) if part] if prints_escapes else []
                words.extend(pieces + [part for part in cut if part not in pieces])
```
### Literal B (hooks/guard.py, builder_shell_test_hit docstring and return)
```
    """The test path a builder's shell command writes, else ''. Two readings: the plain forms (a
    redirect, `tee`, `sed -i`, `cp`, a heredoc header) on the heredoc-stripped command, with the paths
    that `find`, `xargs`, a `for` list and a substitution feed to a writer read too (`read_fed`), and
    the python or node script a heredoc body, `-c` / `-e` or a script file run by name holds, on the raw
    command (this is the one caller that reads script files). `tool` is the
    call's tool: it sets which shell's rules read the text."""
    POWERSHELL_CALL[0] = tool == "PowerShell"
    return (_shell_write_hit(stripped, cwd, builder_test_path, follow_cd=True, command_position=True,
                             read_fed=True)
            or interpreter_write_hit(raw, cwd, builder_test_path, script_files=True))
```

The docstring's opening line ("The test path a builder's shell command writes ...") appears once. If it sits above the marker block, keep it there and drop it from this literal.

### Literal A (#1486 record, the one Reads bullet)
```
- Reads: a redirect, `tee`, `sed -i` or `cp` onto a test path (`_shell_write_hit` in `hooks/guard_frozen.py`, with `command_position`). It also reads a python or node heredoc body, or a `-c` or `-e` script, that opens a test path for write (`interpreter_write_hit`, same module). Only this check also reads a script file that a python or node command runs by name (`interpreter_write_hit` with `script_files=True`). The other-checkout rule does not, and it spawns no more than before. The file is read from disk (first 256 KB). A python file longer than that is judged by the longest run of whole lines from its start that parses. The scan tries at most `_PY_PREFIX_TRIES` parses. When none parses, it is no hit. The string-literal fallback for an unparsable body is never used on a cut file. Each heredoc of the same command that writes it before the run is read too, an append (`>>`, `tee -a`) or a second body included: each body is judged as a heredoc body is. `__file__` (python) and `__dirname` / `__filename` (node) are the script's own path and folder, so `dirname(__file__)/../tests/x` is a test path. A temp folder is no repo path: python's `mkdtemp` and the like, and node's `os.tmpdir()`, or `fs.mkdtempSync` given a prefix under it, held in a name or as the first piece of `path.join`. Nothing under it is judged. A node `path.join` whose first piece the scan cannot tell is not judged; `process.cwd()` is the cwd, so a join from it is. A folder, a missing or an unreadable file is no hit. Both use the Edit path's predicate (`builder_test_path`, in `hooks/guard.py`). The shell reading also follows a path that a command feeds to a writer (`read_fed`, `_fed_command`). It reads these feeds: the roots of `find` piped to `xargs` (appended, or replacing the `-I` string). It reads `{}` in `find -exec` and `-execdir`. It reads the list of a `for` loop in place of `$v`, `"$v"` and `${v}` in its body. It reads a `$( )` or backtick substitution as the roots of its inner command. A root is a `find` word before its first `-`, `(` or `!`, a grep or rg word after the pattern, or a non-flag word of any other command. A `-name` or `-path` value is never a root. A `while read` loop and `find -delete` are not read. Only `builder_shell_test_hit` asks for `read_fed`; rule 7c (`builder-test-edit`) and the never-lifted check (`never_lifted`) both call it. A pipe at a line's end feeds the next line. A pipeline that ends in a count (`wc`, or `grep -c` with no root of its own) feeds no roots. It only adds refusals to main's reading, except that a `cp` source that is a whole substitution (`$( )` or backticks, quoted or not) is a read. A substitution anywhere else in a `cp` keeps main's reading: in the destination, after or glued to `-t` or `--target-directory`, or glued to other text, as in `tests/$(...)` or `/tmp/$(basename tests/a.py)`.
```

### Literal C (#2432 record, lines 66-73)
```
- Reads: a redirect, `tee`, `sed -i` or `cp` onto a test path (`_shell_write_hit` in `hooks/guard_frozen.py`, with `command_position`). It also reads a python or node heredoc body, or a `-c` or `-e` script, that opens a test path for write (`interpreter_write_hit`, same module). Only this check also reads a script file that a python or node command runs by name (`interpreter_write_hit` with `script_files=True`). The other-checkout rule does not, and it spawns no more than before. The file is read from disk (first 256 KB). A python file longer than that is judged by the longest run of whole lines from its start that parses. The scan tries at most `_PY_PREFIX_TRIES` parses. When none parses, it is no hit. The string-literal fallback for an unparsable body is never used on a cut file. Each heredoc of the same command that writes it before the run is read too, an append (`>>`, `tee -a`) or a second body included: each body is judged as a heredoc body is. `__file__` (python) and `__dirname` / `__filename` (node) are the script's own path and folder, so `dirname(__file__)/../tests/x` is a test path. A temp folder is no repo path: python's `mkdtemp` and the like, and node's `os.tmpdir()`, or `fs.mkdtempSync` given a prefix under it, held in a name or as the first piece of `path.join`. Nothing under it is judged. A node `path.join` whose first piece the scan cannot tell is not judged; `process.cwd()` is the cwd, so a join from it is. A folder, a missing or an unreadable file is no hit. Both use the Edit path's predicate (`builder_test_path`, in `hooks/guard.py`). The shell reading also follows a path that a command feeds to a writer (`read_fed`, `_fed_command`). It reads these feeds: the roots of `find` piped to `xargs` (appended, or replacing the `-I` string). It reads `{}` in `find -exec` and `-execdir`. It reads the list of a `for` loop in place of `$v`, `"$v"` and `${v}` in its body. It reads a `$( )` or backtick substitution as the roots of its inner command. A root is a `find` word before its first `-`, `(` or `!`, a grep or rg word after the pattern, or a non-flag word of any other command. A `-name` or `-path` value is never a root. A `while read` loop and `find -delete` are not read. Only `builder_shell_test_hit` asks for `read_fed`; rule 7c (`builder-test-edit`) and the never-lifted check (`never_lifted`) both call it. A pipe at a line's end feeds the next line. A pipeline that ends in a count (`wc`, or `grep -c` with no root of its own) feeds no roots. It adds refusals to main's reading, and lifts these reads: a `cp` source that is a whole substitution, `$( )` or backticks, quoted or not (`cp $(ls src/test_a.py) backup`); the sources of a `cp` whose DEST has a quote mark and a live glob, when no match is a test (`_dest_values`, below); a fed `cp` whose sources are all files that exist, which writes DEST itself (`for f in src/test_a.py; do cp "$f" out; done`); a loop that runs once per word, which writes each word's own DEST (`for f in tests/*.py; do cp "$f" "/tmp/$f"; done`); a sibling backup (`cp "$f" "$f.bak"`, below); and a value inside a `sed` script (below). A substitution anywhere else in a `cp` keeps main's reading: in the destination, after or glued to `-t` or `--target-directory`, or glued to other text, as in `tests/$(...)` or `/tmp/$(basename tests/a.py)`.
- A `cp` is also refused by the path it writes (`_copy_written_hit`), also when DEST is no test path: each source is expanded (braces, globs) and judged as `DEST/<its name>`, or `DEST/<source as named>` with `--parents`. DEST is a folder when it ends in a slash, exists, is made earlier in the command, follows `-t`, is fed, or when there are two or more sources. A source folder is walked.
- A walk that passes its cap is refused, not allowed: past 5000 entries judged or folders entered (`_WALK_LIMIT`), or 50000 entries listed (`_LIST_LIMIT`), or a source glob that expands past 5000 names. The refusal says the folder is too large to check for a test and asks for a narrower path. When a `find` name filter already narrowed the walk, it says so, and its remedy names no `-name` filter.
- `-tDIR` and `--target-directory=DIR`, glued, are read as the spaced `-t DIR` on `cp`, `mv` and `install` (`_glued_cp_target`).
- A `for` list of two or more words, or a list with a glob, put in the DEST of a `cp`, `mv` or `install`, or in the target of a redirect (`> "$f"`), is one run per word (`_run_loop_names`, `_fill_loop_variables`). Each word is a DEST or a target, and none is read as a source or as a second target. A glob in any `for` list is put as its matches in the folder the loop starts in (`_listed_loop`): the folder a `cd` before it moved to, else the working folder. So `for f in src/*.py; do cp "$f" "$f.bak"; done` writes each `.bak` name and no folder, and `cd src && for f in test_a*; do rm "$f"; done` deletes `src/test_a.py`.
- A DEST word with a quote mark and a live glob is judged as its matches on disk (`_dest_values`). A loop leaves that form for a glob item, as in `""/tmp/run*""`. A copy of a test out to a folder outside the repo is then allowed. The check of the path a `cp` writes (`_copy_written_hit`) reads a glob DEST with no quote mark the same way (`cp x test_*` writes each match), and a fed copy writes DEST itself when DEST is a file that exists, or when every source is a file that exists. Any other fed copy writes `DEST/<source name>`.
- A `$( )` that is a `grep -c` of one file feeds no roots: it prints a count, never a path (`_prints_a_file_count`). A lone `cat` feeds its file name, which stands in for the words in the file, since the check does not read the file. So a list kept in a test folder is refused where its value is a writer's word (`n=$(cat tests/list.txt); rm $n`), and a list kept elsewhere is not read. A value is judged by where it is used: in a `sed` script, which is text, it is no path (`sed -i "s/N/$n/" src/a.py`), whatever command made it (`_put_values`, `_sed_script_words`). With `-e`, `-f` or `--file`, spaced or glued, no operand is the script, so `sed -i -f fix.sed $f` edits the file `$f` holds.
- A fed `cp` of one source, with no `-t`, `--parents` or recursive flag, whose DEST is the source and a suffix with no slash (`cp "$f" "$f.bak"` in a loop over `$(git ls-files src)`), writes a sibling of each file the source names (`_copy_written_hit`). A source folder is walked for its files. Such a DEST is never a folder.
```
