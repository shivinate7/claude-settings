# A mockup that a waiting item or a roadmap step names lives in the design folder

## The ruling

Git is each artifact's home (owner ruling fb-1458-1, 2026-11-02 14:58 CST, option A). A mockup that a waiting item or a roadmap step names is a file in the repo's design folder: layout kind `design`, `docs/design/` by default. Git carries that file to every computer and account.

- Refused: a path outside the design folder, a link, a folder path (text that ends in `/` or `\`), or no path. A machine folder is outside it.
- Guard rule `mockup-home` (`hooks/guard.py`, `mockup_home_hit`). An `ArtifactData` set or update of a waiting item that carries `designs` is denied when a design has no `file`, or a `file` that is refused (see Refused above). The judge is `lint/layout.py` `mockup_home_problem`, through `hooks/question_form.py` `design_file_problems`. It judges path shape only. It reads no mockup file and asks no origin. A closed item, or a write with no `designs`, is not judged.
- Roadmap build (`skills/roadmap/build.py`, `mockup_misses`). A step's note, why or ask that cites a mockup id (`item<N>-<letter>`, such as `item48-a`, as a whole token) needs an entry in the step's `mockups` field, `{"<id>": "<path>"}`. The build prints `mockup with no file: <step id> <mockup id> (commit the file under the design folder and push it; if it is pushed, run git fetch)` for each miss, then exits 1. An entry is a miss when it has no file, or its path is outside the design folder, a link or a folder. An entry is also a miss when origin does not hold the file as a file: a folder, link or submodule at the path on origin is no file. A `mockups` field that is not an object counts as no entries.
- Only open steps (status not done) are judged. A done step is skipped, so no check reads its mockup.
- Origin check (`mockup_on_origin`). Origin is every ref under `refs/remotes/origin/`, as a fetch leaves them. The file need not be on the default or record branch: any origin ref that holds it as a file counts, an open PR's branch too. The checkout's own files do not count. Unknown, never a miss or a pass, when origin cannot be shown. That covers no origin ref, a shallow checkout, a failed git read, a path outside the checkout, and a layout that cannot be read. The build prints `mockup file unread: <step id> <mockup id> (<why>)` and exits 0.
- Malformed extras: a malformed extras file reads each entry that names a file as unknown, never a raise. A layout that fails to import reads every cited id as unknown. Neither stops the build.
- Lane rulings (process-only): any origin ref counts, and only open steps are judged.
- Incident class: named incident (rule `building-guard-needs-incident`). The mockups for this repo's waiting items 48 and 49 lived only in `~/Library/Application Support/Claude-Work/side-session-notes/<session id>/`. The owner switched Claude accounts on the same Mac, and they were lost. The roadmap steps named them by id (`item48-a`) with no path.
- Scope: a file in a machine folder survives only on that computer. Git reaches every computer. The session notes folder may hold a copy, never the only one.
- Cost:
  - Guard: pure Python on an item write that carries `designs`. Reads the layout and extras files of the checkout. No process, no file written, no log line except one `noted` line when the layout cannot be read.
  - Build: at most four git processes per build, however many entries and origin refs (the ref listing, the shallow check, one batched type read, and one batched link read when a ref holds a blob at an entry's path). Check: `test_five_entries_over_fifty_origin_refs_start_at_most_four_git_processes` in `skills/roadmap/test_build.py`. No file, no log.
  - Every other call: nothing.
- Known limit: the guard judges shape, not existence. A design-folder path to a file never written passes at write. The build reads it as a miss once origin lacks the file. A link whose target file holds the link's own target-path text reads as ok.

Kind: process
Home: rule:questions-go-to-owner
