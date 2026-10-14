# Ruling-kind lint fails open on --dir=

- **What.** `lint/check_ruling_kind.py` reads `--dir=x`, or any other unknown option, as a file name. It then skips git and checks nothing, and exits 0.
- **Where.** `lint/check_ruling_kind.py`, the argument loop near line 181.
- **Decision.** `rulings-declare-kind` (rulings declare a Kind; each repo sets its folder).
- **Retire.** Read `--dir=VALUE` as `--dir VALUE` and refuse any leftover option, as `lint/check_record_slugs.py` does. A test with `--dir=nope` exits non-zero.
