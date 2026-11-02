# A mockup a waiting item or a roadmap step names lives in a mockup home

## The ruling

A mockup that a waiting item or a roadmap step names is a file in one of two homes. A path anywhere else is refused at write, or red in the roadmap build. The mockup then survives an account switch (decision `questions-go-to-owner`, skill `waiting-page`, "Add a design"; skill `roadmap`).

- The machine home: `~/Developer/<repo name>-imports/<item folder>/<file>`. It is a folder of the owner's own computer, outside every Claude app folder. The repo name is the name part of the origin's `owner/name`.
- The design home: the repo's design folder (layout kind `design`, `docs/design/` by default), inside the checkout. A file there is in git, so it also reaches another computer.
- `lint/layout.py` is the one home of both paths (rule `building-allow-list-is-the-constant`): `mockup_homes(root, home=None)` gives the two folders, `mockup_home_problem(root, file, home=None)` gives None or a sentence. The guard and the build import them and keep no copy.
- Guard rule `mockup-home` (`hooks/guard.py`, `mockup_home_hit`; the judge is `question_form.design_file_problems`, beside `design_writes`). An `ArtifactData` set or update of a waiting item that carries `designs` is denied when a design has no `file`, or a `file` that `mockup_home_problem` refuses. It judges path shape only, against this machine's home. It reads no file and runs before `page-item-design`, so a refused path never starts node. The reason names the two homes and the `file` field, and never the refused path. A closed item and a write with no `designs` are not judged.
- Roadmap build (`skills/roadmap/build.py`, `mockup_misses`). A step's note, why or ask that cites `item<N>-<letter>` as a whole token needs an entry in its `mockups` field, `{"<id>": "<path>"}`. The build prints `mockup with no file: <step id> <mockup id>` for each miss, writes the page, and exits 1.
  - A miss: no entry, a path outside both homes (a link too), or a design-home file that is not in the checkout. A machine-home file that is not there is a miss when this machine's `<repo name>-imports` folder is.
  - Unknown, never a miss (ruling, lane `mockup-homes`, 2026-11-02 12:06 CST): a machine-home path of another computer (for example a Windows owner's `C:\Users\x\Developer\<repo name>-imports\item48\a.html` read by a Linux cloud build), or this machine's home when its `<repo name>-imports` folder does not exist. The build prints `mockup file unread: <step id> <mockup id> (<why>)` and exits 0.
  - The waiting-page guard keeps judging against this machine's home. It has no unknown: a file that is not in a home on this machine is refused.
- Incident class: named incident (rule `building-guard-needs-incident`), Nov 2 2026.
  - The mockups for the home repo's waiting items 48 and 49 lived only in `~/Library/Application Support/Claude-Work/side-session-notes/<session id>/`. They were lost when the owner switched Claude accounts on the same Mac. The roadmap steps named them by id (`item48-a`) with no path.
  - Landed 2026-11-02.
- Scope: one computer, a switch of Claude accounts. On another computer only the repo and GitHub survive, so a mockup that must be kept belongs in the design home. `side-session-notes` may hold a copy, never the only one.
- Cost:
  - Guard: pure Python on an item write that carries `designs`: one read of the origin line in the git config file, one read of HOME. No new process, no file written, no log line beyond the one `noted` line when the layout cannot be read.
  - Build: one stat per cited mockup id, after the page is written. No process, no file, no log.
  - Every other call: nothing.
- Known limit: the guard judges shape, not existence. A path in a home to a file that was never written passes at write, and the build reads it red only on the machine that holds the home.
- Known limit: the machine home's folder name is the origin's repo name, lowercased. A repo with capitals in its name reads unknown on a case-sensitive disk.
- Known limit: the build reads steps of every status. A done step that cites an id with no `mockups` entry keeps the build red until its entry is added.

Kind: process
Home: rule:questions-go-to-owner
