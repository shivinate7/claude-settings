# A mockup that a waiting item or a roadmap step names lives in the design folder

## The ruling

Git is each artifact's home (owner ruling fb-1458-1, 2026-11-02 14:58 CST, option A). A mockup that a waiting item or a roadmap step names is a file in the repo's design folder: layout kind `design`, `docs/design/` by default. Git carries that file to every computer and account.

- Refused: a path outside the design folder, a link, or no path. A machine folder is outside it.
- Guard rule `mockup-home` (`hooks/guard.py`, `mockup_home_hit`). An `ArtifactData` set or update of a waiting item that carries `designs` is denied when a design has no `file`, or a `file` outside the design folder. The judge is `lint/layout.py` `mockup_home_problem`, through `hooks/question_form.py` `design_file_problems`. It judges path shape only. It reads no mockup file and asks no origin. A closed item, or a write with no `designs`, is not judged.
- Roadmap build (`skills/roadmap/build.py`, `mockup_misses`). A step's note, why or ask that cites a mockup id (`item<N>-<letter>`, such as `item48-a`, as a whole token) needs an entry in the step's `mockups` field, `{"<id>": "<path>"}`. The build prints `mockup with no file: <step id> <mockup id>` for each miss, then exits 1. An entry is a miss when it has no file, its path is outside the design folder or a link, or origin does not hold the file.
- Origin check (`mockup_on_origin`). Origin is the remote-tracking ref of the default branch and of the record branch, as a fetch leaves them. The checkout's own files do not count. Unknown, never a miss, when origin cannot be shown: no default-branch ref, a shallow checkout, a failed git read, or an unreadable layout. The build prints `mockup file unread: <step id> <mockup id> (<why>)` and exits 0.
- Incident class: named incident (rule `building-guard-needs-incident`). The mockups for this repo's waiting items 48 and 49 lived only in `~/Library/Application Support/Claude-Work/side-session-notes/<session id>/`. The owner switched Claude accounts on the same Mac, and they were lost. The roadmap steps named them by id (`item48-a`) with no path. Landed 2026-11-02.
- Scope: a file in a machine folder survives only on that computer. Git reaches every computer. The session notes folder may hold a copy, never the only one.
- Cost:
  - Guard: pure Python on an item write that carries `designs`. Reads the layout and extras files of the checkout. No process, no file written, no log line except one `noted` line when the layout cannot be read.
  - Build: up to five short git reads per cited entry. No file, no log.
  - Every other call: nothing.
- Known limit: the guard judges shape, not existence. A design-folder path to a file never written passes at write. The build reads it as a miss once origin lacks the file.
- Known limit: the build reads steps of every status. A done step that cites an id with no `mockups` entry keeps the build red until its entry is added.

Kind: process
Home: rule:questions-go-to-owner
