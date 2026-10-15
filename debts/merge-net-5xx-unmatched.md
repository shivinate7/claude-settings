# REST 5xx and 429 texts are not network errors

- **What.** REST 5xx texts from `gh api` do not match `NET_ERROR`: `gh: Server Error (HTTP 502)`, `gh: HTTP 503`, and `HTTP 502 (url)`. HTTP 500, the GraphQL "Something went wrong" text and 429 do not match either. In `required_names()`, during the wait, a server error reverts the claim.
- **Where.** `NET_ERROR` and `required_names()` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does when a network error stops a call).
- **Retire.** Each listed text matches `NET_ERROR`, and a case per text retries instead of reverting.
