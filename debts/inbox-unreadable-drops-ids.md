# An unreadable inbox drops open ids from the compaction note

- **What.** An unreadable inbox drops the open ids from the post-compaction note. The Stop gate still names the file.
- **Where.** The post-compaction note in the compact hook.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to an inbox before the turn ends).
- **Retire.** The note names the inbox file and says the ids could not be read. A test pins the note.
