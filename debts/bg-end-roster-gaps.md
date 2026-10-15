# Background end-note rule misses servers outside its roster

- **What.** The roster is a closed list. Watch flags other than `--watch` and `tsc -w` are not read: `jest --watchAll`, `mocha -w` and `vitest -w` pass. Servers outside the roster pass: `ng serve`, `nx serve`, `manage.py runserver`, `gunicorn` and `docker compose up`. So does any interpreter run on a file. `bundle exec`, `setsid`, `Invoke-Expression`, `iex` and `Start-Job` are not read, and neither are runner flags with an unlisted value. A server detached inside a foreground call (`nohup x &`) has no `run_in_background`, so this rule skips it. The detached-launch rule refuses that shape.
- **Where.** `watch_flag`, `server_program` and `_tokens_hit` in `hooks/guard_stream.py`.
- **Decision.** `background-needs-end-note` (a background server needs an `until:` note).
- **Retire.** Read watch flags per tool, add the common servers, and read `bundle exec`, `setsid` and the PowerShell job forms. Tests for `ng serve`, `jest --watchAll` and `bundle exec rails s` are refused with no note.
