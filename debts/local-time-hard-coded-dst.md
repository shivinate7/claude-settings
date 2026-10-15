# The local time hook hard-codes the US DST rule

- **What.** The rule is the US rule in force since 2007, and it is coded in `hooks/local_time.py`. If the US changes its DST dates, the hook needs an edit there. The zoneinfo upgrade, with this rule as the fallback, is not built.
- **Where.** `hooks/local_time.py`.
- **Decision.** `local-time-central` (sessions speak times in US Central).
- **Retire.** The hook reads zoneinfo when present and keeps this rule as the fallback. The checks in `hooks/test_local_time.py` stay green.
