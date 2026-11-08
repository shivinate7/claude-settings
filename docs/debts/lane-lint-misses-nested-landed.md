# Lane lint misses a nested file in a landed folder

**What.** A lane added a test fixture in a subfolder of a landed folder. `install.sh` `land_dir` lands only top-level files, so the case `mirror_landed_tree1` of `hooks/test_install_src.sh` went red in batch CI and the batch was dropped. `merge --lane-lint` had passed, because it does not run the install suite. The harm was one dropped batch and a restack of five PRs. Claude is likely to repeat it, since a `testdata/` subfolder is a common habit.

**Where.** `lint/check_landed_dirs.py` (the landed-folder check), `landed-dirs.txt` (the landed folders), `install.sh` `land_dir`, and `merge --lane-lint`.

**Decision.** `none`. The rule that makes this a debt is `building-guard-needs-incident` (a guard is built after a mistake Claude is likely to repeat).

**Retire.** Make `lint/check_landed_dirs.py` refuse a tracked file in a subfolder of a landed folder, except under `actions/code-check/tools/`, which `mirror_landed_tree1` exempts by name. This is the cheaper of two fixes. The other runs `mirror_landed_tree1` in lane lint when a diff adds a file under a landed folder. Check: a fixture test with a tracked file in a subfolder of a landed folder. The check refuses it. Red on the current code, green after the fix.
