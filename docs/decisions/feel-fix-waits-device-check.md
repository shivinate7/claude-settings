# A feel-fix closes only after a device trial

## The ruling

A feel-fix is a change to how a screen feels: its motion, touch, timing or scroll. CI cannot judge a
feel. So a landed feel-fix does not close on CI alone.

Two terms:

- A device trial is one run of a feel-fix on a simulator or a device. Its record holds how it ran and
  when.
- A try-it item is a waiting-page item of kind `task` (skill `waiting-page`) that asks the owner to try a
  feel on a device.

The order is:

1. CI passes.
2. The step or debt stays open.
3. A device trial is recorded on it.
4. Triage opens a try-it item on the waiting page.

A try-it item's `ref` is the step id, or the debt's slug, so no step or debt gets two. Its `Why yours:` line
names the device trial and says a feel on a real device is the owner's to judge.

- A step is a feel-fix when its `feel` field is set. `false` and `null` mean not a feel-fix. Any other
  value means a feel-fix, so a misread value keeps the step open.
- A step's `deviceCheck` field is `{"how": "simulator" | "device", "at": "<ISO time with zone>"}`. It is
  valid only when `how` is one of the two and `at` parses as an ISO time with a zone. Anything else counts
  as no device trial. Triage writes both fields on the record branch.
- A debt is a feel-fix when one of its lines starts `**Feel.**`. A line counts when it starts with the
  marker at column one, or after an optional leading `- `.
- A device-trial line starts `**Device check.**` (the marker keeps its name), then `simulator` or `device`,
  then an ISO time with a zone. Any other form is not valid. A session adds it after the fix has landed.
- The debt check fails a PR that deletes a feel debt, renames it out of the debt folder, or edits out its
  `**Feel.**` line. It fails unless origin/main's text holds a valid device-trial line. Its fix PR keeps the
  file.

Upkeep list (`skills/roadmap/build.py`):

- Row `landed, waiting for a device trial`: each landed step that is a feel-fix with no valid device trial.
  Entry `<id> (<marks>)`, where `<marks>` is the step's pull request (`#N`), or its commit's short hash when
  no pull request is known, joined with `, `. When `deviceCheck` is present but not valid, the entry reads
  `<id> (<marks>; device trial unreadable)`.
- Row `landed, waiting for triage to close` drops those steps. A feel-fix step with a valid device trial
  reads `<id> (<marks>; open a try-it item)`.
- Row `doing` or `active` with no live lane: a landed feel-fix with no valid device trial is not listed. It
  never reads "set to done".
- The new row sits just before `landed, waiting for triage to close`. It adds no status.

Debt check (`lint/check_record_slugs.py`):

- It fails with `check_record_slugs: FAIL: feel-fix debt deleted with no device check: <path>`.
- It reads deletions and renames in the diff it already runs. That diff call switches to `--name-status`,
  so one git process reads added, changed, deleted and renamed files.
- If a `git show` fails, it prints `check_record_slugs: UNKNOWN, ...`. The exit code follows the check
  today: red in CI, 0 elsewhere.
- Files given on the command line skip git and skip this check.

Known limits:

- The upkeep list and the debt check read the lines. They do not know whether a device trial was real. A
  line with a false trial passes.
- Triage can set a feel step to done with no device trial. The step then leaves every upkeep row. Note
  `feel-step-set-done-untried` (in `docs/debts/notes.md`) names this gap.

Incident:

- 2026-11-01 17:44 CST, relayed by the owner from a session in its home repo: a fix for how a screen feels
  closed on CI alone. Its record still said it waited on the owner to try it.

Built against that incident. Landed 2026-11-01.

Scope: the debt lint runs in each repo whose CI runs `lint/check_record_slugs.py`. The step row runs
wherever the roadmap builder runs.

Cost:

- Step fields: no new git process, file, timer or log. The fields ride in the step JSON that the builder
  already loads.
- Debt check: no new diff process, because the diff call it already makes switches to `--name-status`. The
  lint reads the origin/main text of each deleted, renamed or edited debt file: one `git show` each, usually
  zero. It reads the HEAD text only when main's text has `**Feel.**` and no valid device-trial line. The
  debt folder's `README.md` and `notes.md` are not debts, so the lint does not read them. It writes no file.

Kind: process
Home: skills/roadmap/build.py
