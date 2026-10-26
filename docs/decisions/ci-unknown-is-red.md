# In CI, an unknown read is red

## The ruling

A lint that cannot read its input prints UNKNOWN. Locally it exits 0. When env `CI` is set it exits non-zero, because the CI exit code is the verdict (`verification-report-unknown-reads`, report a read that could not run as unknown). Only `lint/check_record_slugs.py` and `lint/check_silent_undo.py` have this shape. `ci-scope.sh` fails safe by running the harness. The other lints exit 1 on a failed read.

Why: a green exit on an unread input hides a defect.

Where CI runs a suite is in `test-strategy-reset` (tests prove outcomes, run where their subject lives).

Kind: process
Home: lint/check_record_slugs.py
Home: lint/check_silent_undo.py
