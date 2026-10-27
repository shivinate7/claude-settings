# Brief: c125, a lane runs every gates lint step before it joins a batch

Repo: shivinate7/claude-settings, from main d4e1b86. One lane: builder (sonnet), then reviewer (sonnet).

## Task
Three batches went red on Oct 27 from lint steps the lanes never ran (`check_comment_narration`, `test_check_glossary`, `check_record_slugs`). `bin/ci-job` already runs every step of a workflow job (one home; extend it, do not write `bin/gates-local`).
- Add a mode to `bin/ci-job` that runs only the gates job's fast lint and check steps: every `python3 lint/...`, `python3 actions/...` and `bin/ste-changed` step, not the full hook suites or mutation tests. Pick the set from the step commands, not a hand list (building-allow-list-is-the-constant).
- The lane brief template (where briefs are written: skill project-ops templates and any brief template in the repo) names that command as the lane's batch-join check.
- The rule lanes-run-no-full-ci-job stays: this mode is lint only. Update its record in place if its wording now conflicts.

## Rulings
- roles-each-layer-proves-once: full suites and mutation tests stay CI's.
- building-one-home-per-capability: extend ci-job.

## Failure classes
- A lint step added to gates.yml later that the mode misses (the test must build the set from gates.yml).
- The mode running a full suite by accident (a step whose command matches the pattern but runs `hooks/test_guard.py`).

## Check that proves it done
New cases in ci-job's test file, red on main d4e1b86, green on the branch: the mode lists exactly the lint steps of today's gates.yml, and a fake workflow with a new lint step is picked up. Run the new mode on the branch itself and give its verdict. Also lint/rule_audit.py, lint/hook_catalog.py --check, bin/ste-changed origin/main.

## Report
At most 15 lines: PR, head, the mode's name, the step count it runs and its wall time, red run, green run, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.
