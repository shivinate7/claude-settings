# Owner messages sent mid-turn are untested in the inbox hook

- **What.** UserPromptSubmit fired for owner messages sent mid-turn in the audit session of 2026-10-13, and the time line showed on each. No test pins this.
- **Where.** The UserPromptSubmit capture path of the inbox hook.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to an inbox before the turn ends).
- **Retire.** A test sends a mid-turn message through the hook and pins the capture.
