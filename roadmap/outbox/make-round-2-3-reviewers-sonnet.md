# Make round 2 and 3 reviewers run Sonnet (c142, a reviewer at round 2 or 3 runs Sonnet)

Done Oct 28: green and reviewed. Head 3f2ca35 on c142-reviewer-sonnet, draft PR #730, from main e0f9e2d.
Re-added after triage f79a299 filed the earlier note while the lane still ran.

Pick: (a), the guard. (b), a Sonnet pin in agents/reviewer.md, breaks the table row "reviewer | haiku"
in decision agent-model-cap (the model-per-role table), a ruling only shiv changes.
Stale premise in the brief: the Agent and Task path already denied a `Round 2 of 3` reviewer with no
sonnet model on main 6a3e842 (rule roles-third-try-steps-up). The real gap was a Workflow agent() call
(notes line step-up-plugin-types). This lane closes it.

- Build (builder opus): 72bfb8b, Workflow step-up, 6 cases red on main. Try 2 de8741f reads template
  static text with ${} blanked and decodes JS escapes; 3 more red-then-green cases.
- Review: round 1 opus PASS, round 2 sonnet PASS. Its one minor bypass is notes line
  step-up-workflow-hex-escape (3f2ca35).
- Gates via bin/verdict: rule9, mask-script, model-cap families, ste-changed, hook_catalog, rule_audit PASS.
  Full test_guard.py: 1 of 4055 wrong, "load-brake: probe control: a child process the probe starts is
  counted", red on main too (environment). check_silent_undo unknown (shallow clone); CI runs it.
