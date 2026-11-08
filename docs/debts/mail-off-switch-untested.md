# The mailbox off switch has no test

- **What.** No case runs the mailbox with `MAILBOX_REPO` unset. A mutant that drops the early return in `turn_start_lines` passes all 30 cases, and it would then print `mail unknown` on every prompt in every session. Build step 2 (Mac and Windows auth) edits this function.
- **Where.** `hooks/mail.py` `turn_start_lines`; `bin/mail` `main`; `hooks/test_mail.py`.
- **Decision.** session-messages (messages to and from sessions).
- **Retire.** One case in `hooks/test_mail.py` with `MAILBOX_REPO` unset asserts `[]` from `turn_start_lines` and exit 2 from `bin/mail read`.
