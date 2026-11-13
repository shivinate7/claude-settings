# A brief with no readable Topic gets the wrong steer

- **What.** Rule `lane-one-topic` (refuses a lane brief for another topic) refuses a marker brief whose `Topic:` it cannot read, such as a missing `Topic:`, a topic in backticks, or no dot after it. The steer says "start a new lane", but the brief is on topic. A coordinator that slips on the format is sent to start a lane it does not need.
- **Where.** `hooks/guard_merge.py` `brief_hit`, reason `BRIEF_TOPIC_REASON`.
- **Decision.** `session-tiers` (session roles; the lane-one-topic bullet).
- **Retire.** A brief with no parsed topic is refused with "put `Topic: <slug>.` on the first line". A case in family `lane-one-topic` checks the reason.
