# A quoted fence line closes the fence early

- **What.** A quoted fence line `>code`, with no space after `>`, closes the fence early. That line can give a false alarm.
- **Where.** The fence scan in `actions/stamp/stamp.mjs`.
- **Decision.** `stamp-cite-near-miss` (the stamp cite near-miss check).
- **Retire.** Read `>code` as quoted text inside a quoted fence. A test with that line gives no false alarm.
