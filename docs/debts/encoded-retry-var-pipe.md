# A decoded variable piped to a shell passes after a refusal

**What.** A decode goes into a variable, and the variable is piped to a shell: `s=$(base64 -d f); echo "$s" | sh`, `printf %s "$s" | bash`, or `| source /dev/stdin`. The same decode also runs in a container or remote shell: `docker exec c sh -c "$(base64 -d f)"` and `ssh host "$(…)"`. After a refusal, the guard reads none of these. It is a plausible retry shape: decode into a variable, then pipe it to a shell.

**Where.** `hooks/guard_encoded.py`, `encoded_form_hit` (L278-285).

**Decision.** `encoded-retry-after-refusal`, a refused command is not sent again in an encoded form. The decision's Not read list names this form.

**Retire.** Closed when a red case with a fresh refusal row in `hooks/test_guard.py` refuses `s=$(base64 -d f); echo "$s" | sh` and `printf %s "$s" | bash`, and its no-refusal twin passes.

## Ruling

None yet.
