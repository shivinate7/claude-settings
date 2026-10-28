# A shared machine names one owning repo

## The ruling

Owner, 2026-10-27 13:22 CDT (cmsg_01DoF7thf3iq2Srr1UsfXgh2FS8R88VGL2A75ER5mnDyai), roadmap step c140: the
HA Green box (4 GB) is loaded by home, degen, home-app and mailaudit. It crashed 3 times in 8 days. No
repo owned its load budget, and fixes deadlocked across repos.

- Each user repo owns its own deploy and restart scripts.
- The owning repo owns only the shared health check (preflight) and the hold record.
- A change to the preflight or the holds goes to the owner as a hand-off, never an override.
- Every user repo's session runs the preflight before a deploy, a restart or a bulk import, and reads
  the holds.
- A repo declares each shared machine in `.claude/layout-extras.json` under `shared-resources`:
  `{"name", "owner", "preflight", "holds"}`. `name` is unique in the file. `owner` is
  `<gh-owner>/<repo>`, with no `.git`. `preflight` and `holds` are paths inside the owner repo, with no
  whitespace around them. The owner repo must hold its preflight file.
- `python3 lint/layout.py shared-resources <root>` prints the declaration. `lint/layout.py` is the only
  reader. `lint/check_shared_resources.py` goes red on a bad declaration.
- Rolling this out to other repos is a later step (roadmap step c141).

Why: with no owner, each repo fixed its own side, and a fix in one repo needed a change in another.
One owner per machine ends the deadlock. A hand-off keeps the owner's guard whole.

Risk kind: incident, per `building-guard-needs-incident`: the 3 crashes in 8 days above, landed 2026-10-28.

Cost: CI only: two CI steps, about 23 Python starts per run (one per test case, one for the suite, one for the check), no file written.

Protected by `lint/test_check_shared_resources.py`.

Kind: process
Home: lint/layout.py
Home: lint/check_shared_resources.py
Home: skills/project-ops/SKILL.md
