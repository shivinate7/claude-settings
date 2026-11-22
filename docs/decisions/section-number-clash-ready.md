# A clash of guard section numbers is red before the merge

## The ruling

Question: how does a branch learn that another branch took the same guard test section number? Ruling: the step `Record slug length` joins `merge.readyChecks` in `.github/stamp.json`, and the fault names every file on the number and the next free one. The step already refuses two section files on one `# section <n>` number over the whole tree (`lint/check_record_slugs.py` `section_faults`, header read by `lint/_guard_sections.py`). It ran in the CI run only, so a draft that went ready on a tree older than main met no clash.

- The ready run takes the tree the draft step would push, after it has merged main. A branch whose sibling landed first is red there, and the second branch renumbers before it is marked ready.
- The fault reads `section number N is on 2 section files (a.py, b.py); the next free number is M`. M is one above the highest header in the folder, so on the merged tree it is free.
- `hooks/test_guard.py` `load_sections` reads the same fault text, so a run of the guard suite names the same pair.

## Incident, risk and cost

Incident: 2026-11-20 23:15 CST, PRs 3755 and 3756 each took section 43723 as the next free number on main. Again 2026-11-22: open PRs 3781 and 3784 each took 43725. Each branch counted from its own checkout, and nothing read the other. Risk kind: named incident. Harm: a red run after the first lands, and a renumber by hand on the second.

Sections could take the number from the merge tool, which claims record numbers at merge (`.github/stamp.json`, decision `one-shared-record-stamp`). That is not built here: a section file's number is inside the file and its name, and the claim commit rewrites cites in `*.md` only.

Cost: one more step in the ready run, a read of the section folder and a `git ls-files` listing of the tree, with no process left running and no file written. Not pinned beyond `lint/test_check_record_slugs.py`.

Reader: the draft step's `fail Record slug length` line, and the CI step of the same name.

Kind: build
Home: lint/_guard_sections.py
