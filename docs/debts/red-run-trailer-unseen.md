# The Red-run trailer rule shows only at red CI

**What.** Only after CI goes red, a solo session or a builder that changes a test path learns of the Red-run trailer. The check's remedy does not say how to add a trailer to a commit already pushed.

**Where.** Root `CLAUDE.md` and `agents/builder.md` do not name the trailer. `agents/test-author.md` (lines 18-19) names it, and so does `GLOSSARY.md`. The check is `lint/check_red_run.py`: its remedy is at lines 128-129. CI runs it in `.github/workflows/checks.yml` lines 294-299, on pull requests only.

**Decision.** `red-run-trailer-on-test-commits`, the decision that requires a `Red-run:` trailer on each commit that adds test lines.

**Retire.** Two steps:

- Reword the remedy at `lint/check_red_run.py` lines 128-129. It names how to add a trailer to a pushed commit: reword that commit, then push with `--force-with-lease`. When a test in `lint/test_check_red_run.py` pins that text, this step is closed.
- Add one line to root `CLAUDE.md` under `roles-each-layer-proves-once` (each layer proves a change once) that names the trailer. The owner's grant is needed before this line is added.
