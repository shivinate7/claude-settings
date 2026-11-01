# A waiting page behind main is not published

## The ruling

Every republish of a waiting page is main's `skills/waiting-page/page.html` with the live `designData` and roadmap blocks kept, never the live page's own code (decision `questions-go-to-owner`, skill `waiting-page`, "Keep the page on main's code"). A session that publishes from an older file puts old page code on the page the owner reads. The guard now refuses that publish, and a stamp lets the next session start say when the page is behind.

- Guard rule `page-stale` (`hooks/guard.py`, `page_stale_hit`) judges an `Artifact` call that publishes this repo's waiting page.
  - It judges only a call with no `action` or `action` publish, no `asset: true`, a `file_path`, and a `url` equal to `layout.waiting_page` of the cwd's repo (`question_form.waiting_page_root`). Any other call, a read, a list, an asset upload or a publish of another page, leaves before it loads `stale_pages`.
  - It loads `stale_pages.py` from `skills/waiting-page/` beside the hooks folder, else from the config folder. It gets main's `page.html` with `find_template(None)` and compares with `matches`, the one home of "current". The designData body, the roadmap block and the title text are ignored, so a page that `stale_pages.py --write` built passes.
  - Behind: it denies. The reason says to read the live page, run `stale_pages.py --page <saved live page> --write <out>`, and publish `<out>`. It names no forbidden target.
  - Unknown (main unreadable, the file unreadable or empty, `stale_pages.py` missing): it allows and logs one `noted` line under `page-stale`. The rule fails open.
  - Current: it allows and writes the stamp, `<git common dir>/waiting-page-built`, holding the full 40-hex blob sha of main's `page.html`. The sha comes from `stale_pages.read_origin_main`, which already parses it: the one home of "main's page version". No constant and no copy of the template exists.
- `hooks/session_start.sh` runs `stale_pages.py --session-line <toplevel>` in a repo whose extras file names a waiting page. It prints one line naming the page as behind when the stamp differs from main's blob sha. No stamp, or an unreadable main, prints nothing.
- Kind: likely risk (rule `building-guard-needs-incident`). Claude is likely to republish a page from a stale saved copy in normal work, and the page's data and Status tab were lost that way before. Landed 2026-11-01.
- Cost:
  - `guard.py` already starts on each call of its matcher. The matcher now also names `Artifact`, so it starts once per `Artifact` call. A read or a list exits before the heavy imports.
  - Per waiting-page publish: one python import of `stale_pages`, one read-only git process (no fetch, no network), one file read, one stamp file write.
  - Session start: one python start and one git process, only in a repo with a waiting page. Any other repo pays one grep.
  - No timer, no new long-lived process, no new log beyond the one `noted` line on unknown.
- Known limit: a first publish with no `url` passes.
- Known limit: an `ArtifactData` write is not gated here. It writes items, not page code.
- Known limit: a fresh cloud container has no stamp, so its session start prints no line.
- Known limit: the stamp records the last allowed publish from this clone, not the live page. A publish from another machine, or by hand, moves the page without moving the stamp.

Kind: process
Home: rule:questions-go-to-owner
