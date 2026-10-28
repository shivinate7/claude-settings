# o2-layout-waiting-page

Status: ready. Draft PR #742 (o2, rolled-out mark is its own extras key). Head eee3bc7f, a merge of main 4e913588.

- Home probe, before (main 4e913588) and after (eee3bc7f), against home main 69949d76: identical. `layout.py path` resolves decisions, debts, plans, specs and design to docs/*, and records to records. Compliance groups give the same output and exit codes. Layout reads "out - 4 finding(s)" on both sides: home has no .claude/rules, docs/decisions, docs/specs or docs/records.md (home's leftovers, c169). #742 adds no home finding.
- Gates: `ci-job gates --lint`, test_layout plus test_compliance_probes, and silent-undo --strict all pass.
- Review: round 1 (Opus) APPROVE, with no semantic break from main's 17 files. The callers of rolled_out() and has_extras() are unchanged.
- Note, not a debt: test_compliance_probes has no case for an extras file without the mark (it should read "not rolled out", exit 0). skills/roadmap/test_build.py covers the read side.
- Models: builder (merge, solo) Opus; reviewer Opus.
