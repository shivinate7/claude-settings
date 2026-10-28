# c149-orchestrator-no-box

- c149: PR #665 (session-board refuses the box while work runs) is merged; this lane builds on it, in the same check.
- c149: built at fcbafb4 (builder opus): the box is refused once the session made a successful start_session or create_session call; the count survives a reload. Red 3/138 on old code, then green; local gates pass. Review round 1 (opus) running. Draft PR not yet open.
