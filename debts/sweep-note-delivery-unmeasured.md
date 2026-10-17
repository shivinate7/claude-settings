# The sweep note may reach the user only

- **What.** When a turn has advisory findings and no errors, `md_sweep` prints a `systemMessage` and nothing else. Unmeasured: whether the model sees a Stop hook `systemMessage`. If only the user sees it, the writer never gets the nudge.
- **Where.** The notes-only branch of `main()` in `lint/md_sweep.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** A live Stop run shows whether the model sees the note. The result is recorded here. If the model does not see it, the path changes or the decision records the accepted loss.
