# The stable workflow's if gate has no test

**What.** The job `if:` in `stable.yml` is the only term set that keeps a pull request run from moving stable. It checks the conclusion, the event (`push`), the branch (`main`) and the repository. No test reads it. `checks.yml` runs only `actions/stable-mover/test_action.sh`, which tests `run.sh`. So a change that drops a term goes unseen.

**Where.** `.github/workflows/stable.yml`, the `move` job's `if:` (lines 26-30).

**Decision.** `none`.

**Retire.** A test parses the workflow and asserts all four terms of the job's `if:`. Check: `lint/test_stable_workflow.py`, where its mutant that drops `event == 'push'` must make the test fail. The lint folder has no YAML library (`lint/workflow_steps.py` is stdlib only), so the test reads the `if:` by line.
