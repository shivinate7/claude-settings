# Slug lints skip absolute and .MD names

- **What.** `lint/check_record_slugs.py` and `lint/check_ruling_kind.py` do not judge an absolute file argument or a name ending in `.MD`. Both exit 0. CI cannot reach either, because it reads names from `git diff`.
- **Where.** The file-argument paths of both lints.
- **Decision.** `rulings-declare-kind` (rulings declare a Kind; each repo sets its folder).
- **Retire.** Make the file argument relative to the repo root and fold the extension case. A test with each form exits non-zero for a bad slug.
