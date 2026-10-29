# opus-grant-on-step (lane session_013NEJL3EgprbQ7B9yQu3Ms7)

Draft PR #805, branch opus-grant-on-step, head 5332c5db. Review passed in round 2 (round 1 found that a lifted Opus spawn skipped the load brake; fixed). All done-when gates pass on head.
To use it: the coordinator writes `"lane": "session_<id>"` on the step at lane start. Triage writes `"grants": [{"words", "at", "role", "by": "triage"}]`. The lane fetches `+refs/heads/roadmap:refs/remotes/origin/roadmap` before its first Opus spawn.
Open notes (owner's call, not blocking): the field name `lane` holds a session id, while the glossary names a lane by its branch slug; `laneSession` would match better. Debt notes: step-grant-revoke-stale, step-grant-one-bad-entry.
