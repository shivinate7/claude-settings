# Some git fetch network texts revert the claim

- **What.** The `git fetch` pattern misses some network texts. Each one reverts the claim: HTTP/2 INTERNAL_ERROR, Empty reply from server, GnuTLS recv error, Failed sending data to the peer, and ssh kex_exchange_identification.
- **Where.** The `git fetch` pattern in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does when a network error stops a call).
- **Retire.** Each listed text stops the run without a revert, and a case per text pins it.
