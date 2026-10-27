# o4 scorecard-file lane

- o4 (rework compliance-check), finding: `lint/layout.json` has no kind for `docs/health`, where the new scorecard file goes. In a rolled-out repo the layout probe will report `docs/health/` as neither a kind nor an extra, so Layout scores out because of the scorecard itself. Filed as debt `health-folder-not-in-layout` in PR #709. Needs a placement before r1 (run compliance-check on each child repo): add a health kind to the layout (one-layout-every-repo), then point `scorecard` at it.
- o4, finding: skill-order input with a lower-case group name puts an item under the next group. Filed as debt `scorecard-item-wrong-group` in PR #709. Fix it in the next compliance-check lane.
