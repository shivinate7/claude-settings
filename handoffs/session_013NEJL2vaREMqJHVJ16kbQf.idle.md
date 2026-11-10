# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2vaREMqJHVJ16kbQf

## Reply at 2026-11-10T17:27:38Z UTC

IDLE (B)
Goal: build page item 358 a+b (owner 2026-11-07 14:41 CST): notes carry `Seen: YYYY-MM-DD xN`, x2 makes a debt, a note unseen 30 days expires via the janitor sweep; one debt-fix lane per batch; pace number five (debts opened/closed). Step notes-sightings-expiry (triage commit b1dc12123).
State: PR #1619, branch notes-sightings-expiry, head 721ccc144, draft, nothing unpushed. Lane lint PASS on 721ccc144. Review round 1 FAIL (9) and round 2 FAIL (2), all fixed or filed; fix check green. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za).
Depends on PR #1516 (notes-name-their-fix): #1619 carries its commits as of 0bfff0521. If #1516 moved past that, re-merge it into notes-sightings-expiry first (conflicts last time: header Cost lines in lint/check_record_slugs.py, cap dates in lint/test_check_record_slugs.py ~727, docs/debts/README.md). Then re-run `merge --lane-lint 1619`.
Left: the merge only. Deferred gap: note same-slug-add-reads-as-edit, Fix: step:notes-same-slug-edit (that step owns it).
Files: docs/decisions/notes-sightings-expiry.md (spec), lint/check_record_slugs.py, janitor/sweep.py (--expire-notes), janitor/mutate_sweep.py, their tests, CLAUDE.md (two rules), skills/ci-hygiene/SKILL.md step 8, docs/debts/README.md, docs/debts/notes.md.
Branch notes-sightings-expiry-build is a mirror of the lane branch; it can be deleted after merge.

