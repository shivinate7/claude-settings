# The SendMessage prompt hook may never fire

- **What.** Nobody has checked that the SendMessage prompt hook fires at all. It may be close to a no-op.
- **Where.** The `SendMessage` matcher in `settings.json`. The hook judges `parallelism-no-mid-task-talk`.
- **Decision.** `haiku-prompt-hooks` (the trial of the blocking prompt hooks, which names this hook).
- **Retire.** A logged SendMessage call shows that the hook ran and gave a verdict. Record the result in `haiku-prompt-hooks`, then delete this file.
