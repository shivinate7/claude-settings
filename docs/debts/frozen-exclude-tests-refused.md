# Search exclusions that skip tests are not read, so a safe search is refused

**What.** `grep -rl old . --exclude-dir=tests`, `find . -path ./tests -prune -o ...`, `rg -g '!tests/**'` and `git grep ... ':!tests'` are not read as skipping the tests folder. So a search whose only matches lie under the excluded folder is refused, though main allows it. A reviewer probe on `./tests/test_a.py` was refused. This is a false alarm: the builder retries with explicit folders. Found in PR #2774, head d08e55b9a8d599665111ee33841ec61323506895; open on PR #2774 until merge.

**Where.** `hooks/guard_frozen.py`, `_name_filters` (~1423-1480 on the PR #2774 head; not on main).

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests. It is the rule the read enforces. No decision names this false alarm.

**Retire.** A red case per form above, with the only matching test under the excluded folder, expects the read allowed, as main allows it. Test file: `hooks/test_guard.py`.
