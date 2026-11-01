# A feel-fix closes only after a simulator or device check

## The ruling

A feel-fix is a change to how a screen feels: its motion, touch, timing or scroll. CI cannot judge a
feel. So a landed feel-fix does not close on CI alone.

A device check is one run on a simulator or a real device. Its record holds how it ran and when. The
order is:

1. CI passes.
2. The step or debt stays open.
3. A device check is recorded on it.
4. Triage opens a try-it task on the waiting page.

A try-it task is a waiting-page task (skill `waiting-page`). Its `ref` is the step id, so no step gets
two. Its `Why yours:` line names the device check and says a feel on a real device is the owner's to
judge.

- A step is a feel-fix when its `feel` field is set. `false` and `null` mean not a feel-fix. Any other
  value means a feel-fix, so a misread value keeps the step open.
- A step's `deviceCheck` field is `{"how": "simulator" | "device", "at": "<ISO time with zone>"}`. It is
  valid only when `how` is one of the two and `at` parses as an ISO time with a zone. Anything else counts
  as no check. Triage writes both fields on the record branch.
- A debt is a feel-fix when one of its lines starts `**Feel.**`. Its device check is a line that starts
  `**Device check.**`, then `simulator` or `device`, then the ISO time with a zone. A session adds it after
  the fix has landed.
- A feel-fix debt file is deleted only when origin/main holds its device check line. Its fix PR keeps the
  file.

Upkeep list (`skills/roadmap/build.py`):

- Row `landed, waiting for a simulator or device check`: each landed step that is a feel-fix with no valid
  check. Entry `<id> (<marks>)`, where `<marks>` joins the step's marks with `, `. When `deviceCheck` is
  present but not valid, the entry reads `<id> (<marks>; device check unreadable)`.
- Row `landed, waiting for triage to close` drops those steps. A feel-fix step with a valid check reads
  `<id> (<marks>; open a try-it task)`.
- Row `doing` or `active` with no live lane: a landed feel-fix with no valid check is not listed. It never
  reads "set to done".
- The new row sits just before `landed, waiting for triage to close`. It adds no status.

Debt check (`lint/check_record_slugs.py`):

- It fails a deletion of a feel-fix debt file whose origin/main text has no device check line:
  `check_record_slugs: FAIL: feel-fix debt deleted with no device check: <path>`.
- It reads deletions in the diff it already runs. That diff call switches to `--name-status`, so one git
  process reads both added and deleted files.
- It runs one `git show` per deleted debt file. Usually there are none.
- If a `git show` fails, it prints `check_record_slugs: UNKNOWN, ...`. The exit code follows the check
  today: red in CI, 0 elsewhere.
- Files given on the command line skip git and skip this check.

Known limits:

- The upkeep list and the debt check read the lines. They do not know whether a device check was real.
  A line with a false check passes.

Incident:

- 2026-11-01 17:44 CST, relayed by the owner from a session in its home repo: a fix for how a screen feels
  closed on CI alone. Its record still said it waited on the owner to try it.

Built against that incident. The rule applies to every repo. Landed 2026-11-01.

Cost:

- Step fields: no new git process, file, timer or log. The fields ride in the step JSON that the builder
  already loads.
- Debt check: no new process. It runs inside the diff call that the check already makes. It writes no file.

Kind: process
Home: skills/roadmap/build.py
