# A repo states each tool's version once; its CI and its machines match it

## The ruling

Owner, 2026-11-25, typed in the consultant's chat unless said:

- 09:54 CST: "pins 3.15 and also it's a updating/moving pin right? and it'll be dynamic for the repos?"
- 10:02 CST, typed in the role session's chat and relayed: "send this to the consultant which just did pinnings for python it's stupid that we failed somewhere else on this when the broader concept it did could have been applied everywhere"
- 10:07 CST: "and ideally, the conceptual just holds if i add new/more tools and/or other repos tag along"
- 10:19 CST: "i didnt say that at all? i said this concept of pins aligning between whats tested and whats worked on needs to be done for all repos, not that all repos need python 3.15 pinned forcefully... and remember i'm just trying to voice the conceptual here"
- 10:19 CST, on installing the pinned git on his Mac with Homebrew and upgrading Git for Windows: "this"

## What it means

The consultant reads the ruling this way; the owner's words are quoted above.

- Each repo states each tool's version once, in its root `.tool-versions`.
- `lint/check_tool_pins.py` compares the tools on the machine it runs on with that repo's own file.
- A new tool is one line in the file.
- Values belong to each repo. No shared values. No repo compares its pins with another repo.
- The concept applies to every repo. It does not force 3.15 on any repo.

## The mistake and its harm

- CI's git is 2.56.1 (reported; not read from a CI log). The owner's Mac ran Apple's git 2.54.
- Pull request 3883, the lease tool, went red only in CI. Git 2.56 writes a remote-tracking ref on a push by URL. Git 2.54 does not. No local run could show it.

## What is built

At head `1ad9bbe43c`:

- File format, `.tool-versions`:
  - One `<tool> <version>` per line. `lint/check_tool_pins.py parse` refuses any other line.
  - A comment sits on its own line. The file's header says actions/setup-python reads the python line with a strict pattern. Not checked here.
  - `# read: <tool> = <command>` gives a tool its own version command. The default is `<tool> --version`.
- Precision: `lint/check_tool_pins.py matches` matches a pin at the precision it states. `3.15` accepts 3.15.2. `2.56` accepts 2.56.1. `2.105` rejects 2.10.5. Departs from "one stated version" (the consultant's pick).
- `--local`: `lint/check_tool_pins.py main` prints a mismatch as a note and exits 0. An unknown tool still exits 1.
- Unknown: a tool that is not found, or whose command fails, prints `unknown` and exits 1.
- Cost: one version command per pin, per run. No network. No file written. Runs only when invoked.

## State

- This repo pins python 3.15 and git 2.56 in `.tool-versions`.
- The 40 literal `python-version: "3.15"` lines still stand: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. Pull request 3876 moved them.
- Built: the checker, its fixture suite (20 cases), the CI step that runs the suite, and a `.tool-versions` row in the code-check standard (not code).
- Not built:
  - No CI job runs the check. Only its fixture suite runs.
  - The check must also run in one Windows job and one macOS job.
  - Other repos take the check through the lint action they already call.
  - Who moves a pin when a runner image moves a tool: the owner's open question QAG.
- Machines: the Mac has Homebrew git 2.56.1 since 10:21 CST, 2026-11-25. The Windows upgrade is the owner's act.

## Related

- Decision `ci-pins-newest-interpreter` (CI pins the newest Python that passes its checks).
- Decision `action-pins-follow-sessions` (a CI action pin follows the session's tools when they differ).
- Debt `gh-version-unpinned` (nothing pins or checks the gh version). Not changed here.

Kind: process
Home: .tool-versions
