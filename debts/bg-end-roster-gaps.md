# Background end-note rule misses servers outside its roster

- **What.** The roster is a closed list. Other watch flags, other servers, interpreters run on a file, and some wrappers pass with no note.
- **Where.** `watch_flag`, `server_program` and `_tokens_hit` in `hooks/guard_stream.py`.
- **Decision.** `background-needs-end-note` (a background server needs an `until:` note).
- **Retire.** Read watch flags per tool, add the common servers, and read `bundle exec`, `setsid` and the PowerShell job forms. Tests for `ng serve`, `jest --watchAll` and `bundle exec rails s` are refused with no note.
