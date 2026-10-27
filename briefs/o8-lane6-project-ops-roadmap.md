# Brief: o8 lane 6, project-ops points at skills/roadmap

Repo: shivinate7/claude-settings, from main 43d9af20 (batch #698). One lane: builder (sonnet), then reviewer (sonnet). Plan: plans/o8-living-roadmap-plan.md on the roadmap branch.

## Task
skills/project-ops/SKILL.md, section "The roadmap page", still says the page builder's one home is `roadmap/build.py` on the claude-settings roadmap branch and that a repo's own record "has no page". Since batch #637, skills/roadmap builds the page for any checkout, and since #652 the publisher passes live work with --live.
1. Point project-ops at skills/roadmap as the one home for building and publishing the page; remove the stale claims. Keep the step file shape text only if skills/roadmap does not already state it; otherwise point at it.
2. scaffold.py and templates/: anything that names roadmap/build.py as the builder for a new repo points at skills/roadmap instead. The roadmap/README.md the scaffold writes says how to build the page with skills/roadmap, including --live.
3. If the triage role template (templates/operating-model.md or roster.md) says who publishes the page, it says triage passes --live at each publish.

## Rulings
- building-one-home-per-capability; speak-rewrite-superseded-in-place.

## Failure classes
- A scaffolded repo whose README names a builder that does not exist in that repo.

## Check that proves it done
A test in skills/project-ops/tests: red on main (the scaffolded roadmap/README.md names roadmap/build.py, or does not name skills/roadmap), green on the branch. Existing project-ops and roadmap tests pass. `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass.

## Report
At most 12 lines: PR (draft), head, red run, green run, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
