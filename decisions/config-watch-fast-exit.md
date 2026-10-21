# The config watch exits fast when no watched file changed

## The ruling

Owner, 2026-10-20. `hooks/config_watch.py` hashes the two watched settings files on every call. It does this before it imports the guard. It imports the guard only when a hash changed.

Why: the cost is the import, not the hash. There is no mtime or size stamp. A same-size edit with a reset mtime must not slip past the model-cap watch (`predicate-is-the-act`, the watch reads file content, never a proxy for it).

- **Check now.** A missing or corrupt record means check now. A recorded lift past its deadline means check now, because a deadline passes with no write of its own (`opus-grant-expires`, an Opus grant expires within 24 hours). Any exception in the fast check falls through to the full check.
- **One shared module.** `hooks/shared_names.py` holds `PROJECT_FROZEN_FILES` and `config_dir`. It uses the standard library only, so the fast exit can read it before the guard loads. There is no second copy. It lands in the guard set (`guard.d/<id>/`) with the guard files. Lane `local-time-light-import` adds `MACHINE_TAGS` there later.
- **First sight.** On first sight of a file, a cap at Sonnet stays silent. A `_FORCE` flag set to `0`, `1`, `true` or `false` beside a Sonnet cap also stays silent, because it only pins Sonnet (owner ruling 2026-10-20). Any other reading, such as a model key above Sonnet or a `_FORCE` key that names a model, is reported as unknown.

## Note, not a debt

A JSON-escaped cap key outside `env` skips its expiry check in the fast check. Only an attacker writes that form (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker).

Kind: process
Home: hooks/config_watch.py
