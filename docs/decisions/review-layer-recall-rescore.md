# The review-layer recall rescores once per main push

## The ruling

Owner, 2026-11-18 11:04 CST (waiting-page item reviewer-eval-cases, pick a): count true reviewer misses only, rescore once per batch on main's tip, baseline spend granted, cost measured on the first run.

- The scorer is `lint/review_layer_recall.py`.
- The `checks` job runs the step `Review-layer recall line (main push)` on a push to main only. It prints one line of per-layer recall.
- The step gates nothing. `continue-on-error` keeps a failed read from turning main red.
- The scorer reads the committed fixture `tests/review_layer_recall/fixture.json` only. It uses no network.
- The step passes no verdicts file (the `--findings` flag). With none, the line prints `unknown` for every layer. It stays `unknown` until the step reads a verdicts file from a baseline run.
- The baseline run is the next step: a paid reviewer run on the fixture, granted in the same pick.

Cost, as designed: one Python process per main push, inside a job that already runs. It writes no file and no log. Its reader is the person who opens the run page. Unmeasured.

Why: a score nobody reads on demand costs more than it tells (rule `outcomes-mechanize-rules`).

Kind: process
Home: .github/workflows/checks.yml
