# Hooks share the transcript reader

## The ruling

The Stop hooks read the transcript through one module, `lint/_transcript.py`. It holds `read_transcript`, `is_last_human`, `tool_uses`, `records_after_last_human` and `last_reply`. `lint/report_guard.py` imports it. So does the config report section of `hooks/decision_watch.py`.

- The cheap Stop reads live there too. `last_human_epoch` and `read_turn` read only the tail of the transcript since the last human message. `hooks/decision_watch.py` (with its config report section) and `hooks/ruling_home.py` call the tail readers.
- `hooks/config_watch.py` calls neither, because its expiry rule fires with no file change, so no such exit is safe there.
- `building-allow-list-is-the-constant` does not govern it: a transcript helper is not a permit list.

Why: four hooks carried copies of the same readers, and the statement that each Stop hook stays in one file with no import between hooks was already false.

Protection of the old outcome (one bad edit must mute one reporter, never all four):

- `lint/test_report_guard.py` runs each guard as a subprocess, so an import error in `lint/_transcript.py` fails the guard suite in CI.
- A break in the shared module is loud. The import sits at the top of each hook file, above `main`, so the fail-open `try` and `except` in `main` never sees it. The hook exits 1 and prints a traceback.
- The fail-open path still catches a bad transcript, a missing file or a parse error inside a running hook. Such a hook exits 0 and prints nothing.

Accepted risk (owner): one bad edit to `lint/_transcript.py` that passes CI can break all four reporters at once. How often a bad edit passes CI is unmeasured.
Kind: process
Home: lint/_transcript.py
