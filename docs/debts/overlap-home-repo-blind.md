# A session on the lanes' home repo is never checked

- **What.** Rule `lane-start-overlap` filters out the session's home repo, so a session whose home repo is the lanes' repo is never checked. Example: a q_max-home session with q_max-only lanes. This is the incident's own repo shape for such a session.
- **Decision.** `session-tiers` (the session shapes; the lane-start-overlap bullet).
- **Retire.** A start on the home repo beside an open lane on that repo is asked. A case in family `lane-one-topic` checks it.
