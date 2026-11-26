# A repo states each tool's version once; its CI and its machines match it

## The ruling

Owner, 2026-11-25, typed in the consultant's chat unless said:

- 09:54 CST: "pins 3.15 and also it's a updating/moving pin right? and it'll be dynamic for the repos?"
- 10:02 CST, typed in the role session's chat and relayed: "send this to the consultant which just did pinnings for python it's stupid that we failed somewhere else on this when the broader concept it did could have been applied everywhere"
- 10:07 CST: "and ideally, the conceptual just holds if i add new/more tools and/or other repos tag along"
- 10:19 CST: "i didnt say that at all? i said this concept of pins aligning between whats tested and whats worked on needs to be done for all repos, not that all repos need python 3.15 pinned forcefully... and remember i'm just trying to voice the conceptual here"
- 10:19 CST, on installing the pinned git on his Mac with Homebrew and upgrading Git for Windows: "this"
- 10:47 CST, on where the check runs; the reason the plan ran: "i wonder how the check would run on cloud vs windows local vs mac local shd it be upon merge or some sorta start session thing or readying a pr? send an opus agent on this i actually dont know how to pick on this"
- 10:53 CST, on "may the tool-pins decision take over debt `gh-version-unpinned`": option a, "approved". Option a's text, the consultant's wording and not the owner's: "the tool-pins decision takes over the debt. Gain: one home, one check. Lose: the debt's older plan is dropped."
- 11:05 CST, on "when a runner image moves a tool past its pin": option a, his word: "approved". The current ruling, with the 15:33 CST words below applied: CI's own tools are judged on the daily run, red on a mismatch, with a line naming the tool, the pin and the version found; a PR's run is red only when that PR moves a pin or the checker; a lane's local lint on a machine whose tools miss the pins reads unknown, so it is no proof and the merge waits for the PR's own CI run; session start and the ready mark run the check, and the merge adds nothing. First approved with session start, the ready mark and the merge adding nothing. Stated cost, accepted at 11:05 CST and still true: after an image move main reads red until a one-line pin PR lands, and merges wait for full PR CI meanwhile. A lagging Mac is refused at ready. A lagging cloud session warns and goes on, so its lanes merge on CI only.
- 15:33 CST, feedback item fb-1533-2, Nov 25: "there's something that checks that things are in alignment before like say a pr is marked ready"

## Lane picks, not rulings

The lane that built the check chose these. The owner has not ruled on them.

- A cloud session warns and goes on at the ready run. Session start does not run in a cloud session.
- A pin file that cannot be parsed or read refuses at the ready run. Session start prints an `unknown` line for it.
- The winget ids in the Windows `# fix:` lines, `Python.Python.3.15` and `Git.Git`, are unverified. No winget runs on the Mac.
- A tool newer than its pin is no failure. Session start and the ready run let it pass.

## What it means

- Each repo states each tool's version once, in its root `.tool-versions`.
- `lint/check_tool_pins.py` compares the tools on the machine it runs on with that repo's own file.
- A new tool is one line. A tool with odd output takes its pin, plus a `# read:` line and a `# match:` line when it needs them. Example, swift: `swift 6.4` and `# match: swift = Apple Swift version (\d+(?:\.\d+)*)`. Its default read, `swift --version`, needs no line.
- Values belong to each repo. No shared values. No repo compares its pins with another repo.
- The concept applies to every repo. It does not force 3.15 on any repo.

## The mistake and its harm

Reported, not read from a CI log or a run:

- CI's git is 2.56.1. The owner's Mac ran Apple's git 2.54.
- Pull request 3883, the lease tool, went red only in CI. Git 2.56 writes a remote-tracking ref on a push by URL; git 2.54 does not. No local run could show it.

## What is built

- File format, `.tool-versions`:
  - One `<tool> <version>` per line. `lint/check_tool_pins.py` `parse` refuses any other line. A file with no pin, an empty file included, is refused and exits 1.
  - A comment sits on its own line. The file's header says actions/setup-python reads the python line with a strict pattern. Not checked here.
  - `# read: <tool> = <command>` gives a tool its own version command. The default is `<tool> --version`. `lint/check_tool_pins.py` `run_version_command` runs it with no shell (the Windows path is unrun). A tool may have several `# read:` lines: they are tried in order, and the first that runs and prints a version wins.
  - `# match: <tool> = <regex>` names the version. The regex has one group, and the group is the version. The directive words `read` and `match` are case-insensitive.
  - `# fix: <tool> <macos|windows|linux> = <command>` gives the command that brings the tool up to its pin on one platform. The owner runs it. A second fix line for the same tool and platform is refused, and so is one for a tool with no pin.
  - A UTF-8 BOM is ignored.
- Version: the first dotted number in the output, or a bare number when none is dotted. A number inside a path token is never the version.
- Precision: `lint/check_tool_pins.py` `matches` accepts a pin at the precision it states. `3.15` accepts 3.15.2. `3` accepts 3.2.1. `2.56` accepts 2.56.1. `2.105` rejects 2.10.5. A pre-release (3.15.0rc1) matches only a pin that states it.
- `--local` prints a mismatch as a note and exits 3. Lane lint reads 0 as a match and 3 as a mismatch. A tool that is not found, whose command fails, or that prints no version reads `unknown` and exits 1, also with `--local`.
- `--behind ROOT`: session start and the ready run read ROOT's `.tool-versions`. A tool older than its pin prints a `BEHIND` line with the version found, the path it ran from and this platform's fix, and the exit is 3. A tool newer than its pin is no failure. An unreadable tool prints `unknown` and exits 1; unknown wins over behind. The reads of one run share one time budget. At session start it is the smaller of `CS_TOOL_PINS_BUDGET` (default 5) and 10 - 2 - elapsed seconds, elapsed being the seconds since the hook began; under 1 s the read is skipped and a line says so. The ready run passes its own 20 seconds.
- Session start: `hooks/session_start.sh` calls `--behind` on a startup in a checkout with a root `.tool-versions`. It never runs in a cloud session. It prints only the lines that are not `ok` lines, so a tool at or ahead of its pin prints nothing. A refused pin file prints one `tool-pins: unknown:` line. A tool whose read fails or runs out of time prints its own `tool-pins: <tool> unknown` line.
- Ready run: `merge/merge.py` `ready_tool_pins` is the first call in `draft_step`, before any fetch of the base, worktree, check or push. It reads the head's `.tool-versions`; a head with none runs nothing. A head this checkout lacks is fetched once, by its branch, as a ref update only. A tool behind its pin, a tool that cannot be read, or a pin file that cannot be read stops the run with the fix lines. The pull request stays a draft and nothing is pushed. A cloud session prints the same lines as a warning and goes on.
- Lane lint: `bin/ci-job` runs the checker once with `--local` on `--lint`, in a checkout with a root `.tool-versions` and `lint/check_tool_pins.py`. A tool that misses its pin, or cannot be read, prints one `unknown` line and exits 2, so the merge waits for the pull request's own CI run. A match prints nothing. A checkout with exactly one of the two files prints one `unknown` line that names the missing one.
- CI: the `Tool pins (this runner)` step runs `lint/check_tool_pins.py` in the `checks`, `checks-macos` and `checks-windows` jobs of `.github/workflows/checks.yml`. `.github/scripts/ci-scope.sh` sets its `tool_pins` flag: on for a schedule, a dispatch, a pull request or push whose diff moves `.tool-versions` or the checker, and a run with no readable diff. The suite, `lint/test_check_tool_pins.py`, runs as its own CI step.
- Cost, checker: one version command per pin, per run, pinned by `test_one_process_per_pin_and_no_network` in `lint/test_check_tool_pins.py`. The case proves the process count, not the network. A second `# read:` line runs only when the first prints no version. No file written.
- Cost, session start: in a repo with a pin file, one checker start and one version command per pin, pinned by `test_a_repo_with_a_pin_file_starts_one_checker_and_one_version_command_per_pin` in `hooks/test_session_start.py`. A repo with no pin file starts no checker, pinned by `test_a_repo_with_no_pin_file_starts_no_checker_process`. No network, no file written, no timer, no process kept.
- Cost, ready run: one `git cat-file -e` of the head, one fetch when the head is not local, one `git ls-tree` of the head's pin file, one `git show` of that file when the head lists it, then one version command per pin; unmeasured, as no test counts these git calls.
- Cost, lane lint: one checker run per `--lint` run in a checkout with a pin file or a checker; unmeasured, as no test names this read.
- Cost, CI: the checker runs once in each of the three jobs the scope flag turns on; unmeasured, as no test counts these runs.

## State

- This repo pins python 3.15 and git 2.56 in `.tool-versions`.
- The 40 literal `python-version: "3.15"` lines still stand: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. Pull request 3876 moved them.
- Built: the checker; its fixture suite (76 test methods in `lint/test_check_tool_pins.py`) and the CI step that runs it; the four call sites under What is built (session start, ready run, lane lint, CI); and a `.tool-versions` row in the code-check standard (not code).
- Not built:
  - Other repos take the check through the lint action they already call.
  - Who moves a pin when a runner image moves a tool: the owner's open question QAG.
  - Read (plan and refuter, Nov 25): a red daily run blames no PR and does not stop stable (`actions/ci-alarm/clear_rule.py` `blames`; `.github/workflows/stable.yml`).
- Machines: the Mac has Homebrew git 2.56.1 since 10:21 CST, 2026-11-25. The Windows upgrade is the owner's act.
- Debt `gh-version-unpinned` stays open until one `gh` line lands in `.tool-versions`. The pin value needs a read of CI's gh first.

## Related

- Decision `ci-pins-newest-interpreter` (CI pins the newest Python that passes its checks).
- Decision `action-pins-follow-sessions` (a CI action pin follows the session's tools when they differ).
- Debt `gh-version-unpinned` (nothing pins or checks the gh version). This decision takes it over.

Kind: process
Home: .tool-versions
