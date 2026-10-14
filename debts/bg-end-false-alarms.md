# Background end-note rule refuses some commands that end

- **What.** The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. It also reads flask and jupyter option values and sub-verbs as server verbs.
- **Where.** `server_script` and the `SERVER_VERBS` check in `hooks/guard_stream.py`.
- **Decision.** `background-needs-end-note` (a background server needs an `until:` note).
- **Retire.** Count a script part only when it is the last part, and skip option values before the verb. Tests for `npm run build:dev` and `flask --app run db upgrade` pass with no note.
