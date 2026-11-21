---
id: pending
slug: guard-cases-from-base
---

# A pull request may not loosen a guard case without a trailer, and the check matches name first, then content

## The ruling

Incident to stop: a change that loosens a guard could loosen the case that pins it in the same pull request. Both edits then agree, the suite is green, and nothing names the loosening. Harm: a refusal that Claude relied on stops working with no one told.

`lint/check_guard_cases_from_base.py --base REF` lists the cases of the merge base of REF and HEAD, and the cases of HEAD, both with this checkout's runner (`GUARD_LIST` in `hooks/test_guard.py`, rows from `lint/_guard_case_list.py`). It reads RED for a case whose verdict drops (allow, ask, deny in rising order), or whose payload is gone from the head while the base case was a deny or an ask. A commit of REF..HEAD with the exact trailer `Guard-case-loosened: <name>` turns a RED into WAIVED. A list that cannot be read is UNKNOWN, and exits 1 (`ci-unknown-is-red`).

Compare order, and why:

- **Name first.** A base case takes the head case of its own name when both hold the same payload (the key without its verdict suffix). Many cases share one payload, for example the PPID-1 kill cases, so a match by payload alone pairs a flipped case with any peer that kept its verdict, and reads the flip as a rename. Name first reads the flip as a flip. It also reads two cases that swap verdicts (A deny to allow, B allow to deny) as the loosening and the tightening they are, never as two renames.
- **Then content.** A base case still open takes a head case still open with its payload: a rename. It takes the one of its own verdict first, else the lowest verdict, so a shared payload reads as loosely as it can.
- **One answer each.** A head case answers one base case at most. A removed case then finds no peer left to hide behind and reads RED.
- **Nothing left.** A base case with no head case reads RED when it was a deny or an ask (removed, or its payload changed), else REPORT.

A name alone is no match, since a case may be renamed. A payload alone is no match, since payloads are shared.

Limits: both lists use the head's runner, so only a base section file that loads there is read. A reason that changes is out of scope. Cases that only the log checks run are not listed.

Tests: `lint/test_check_guard_cases_from_base.py`, the flip, removed and rename groups.

Kind: process
Home: lint/check_guard_cases_from_base.py
