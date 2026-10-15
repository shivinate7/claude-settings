# A refusal ending in `: HTTP 5xx (url)` reads as a network error

- **What.** `NET_ERROR` matches `: HTTP 5xx (url)` at a line end. A refusal whose text ends that way, such as a PR title, reads as a network error. The merge retries, then stops with a NetStop, and does not revert. The same holds for a line `: HTTP 403: API rate limit ... (url)` in a PR title or check text, which also waits 60 s a retry.
- **Where.** `NET_ERROR` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (a network error retries, a proven refusal reverts).
- **Retire.** Find a mark that splits gh's wrapped HTTPError line from refusal text, and pin a refusal that ends `: HTTP 502 (url)` as not a network error.
