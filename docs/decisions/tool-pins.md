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
- 11:05 CST, on "when a runner image moves a tool past its pin": option a, his word: "approved". Option a's text, the consultant's wording and not his: "CI's own tools are judged on the daily run, red on a mismatch, with a line naming the tool, the pin and the version found; a PR's run is red only when that PR moves a pin or the checker; a lane's local lint on a machine whose tools miss the pins reads unknown, so it is no proof and the merge waits for the PR's own CI run; session start, the ready mark and the merge add nothing." Stated cost, accepted (the consultant's wording): "after an image move main reads red until a one-line pin PR lands, and merges wait for full PR CI meanwhile; while a Mac or a cloud session lags, its lanes merge on CI only."

## What it means

The consultant reads the ruling this way; the owner's words are quoted above.

- Each repo states each tool's version once, in its root `.tool-versions`.
- `lint/check_tool_pins.py` compares the tools on the machine it runs on with that repo's own file.
- A new tool is one line. A tool with odd output takes up to three: the pin, a `# read:` line, and a `# match:` line. Example, swift: `swift 6.4` and `# match: swift = Apple Swift version (\d+(?:\.\d+)*)`. Its default read, `swift --version`, needs no line.
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
  - `# read: <tool> = <command>` gives a tool its own version command. The default is `<tool> --version`. `lint/check_tool_pins.py` `run_version_command` runs it with no shell (the Windows path is unrun).
  - `# match: <tool> = <regex>` names the version. The regex has one group, and the group is the version. The directive words `read` and `match` are case-insensitive.
  - A UTF-8 BOM is ignored.
- Version: the first dotted number in the output, or a bare number when none is dotted. A number inside a path token is never the version.
- Precision: `lint/check_tool_pins.py` `matches` accepts a pin at the precision it states. `3.15` accepts 3.15.2. `3` accepts 3.2.1. `2.56` accepts 2.56.1. `2.105` rejects 2.10.5. A pre-release (3.15.0rc1) matches only a pin that states it.
- `--local` prints a mismatch as a note and exits 3 (`LOCAL_MISMATCH` in `lint/check_tool_pins.py`). A tool that is not found, whose command fails, or that prints no version reads `unknown` and exits 1, also with `--local`. `unknown` wins over a mismatch.
- Cost: one version command per pin, per run, pinned by `test_one_process_per_pin_and_no_network` in `lint/test_check_tool_pins.py`. The case proves the process count, not the network. No file written. Runs only when invoked.

## State

- This repo pins python 3.15 and git 2.56 in `.tool-versions`.
- The 40 literal `python-version: "3.15"` lines still stand: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. Pull request 3876 moved them.
- Built: the checker, its fixture suite (57 cases, run by a CI step), the `tool_pins` scope flag (`.github/scripts/ci-scope.sh`), and a `.tool-versions` row in the code-check standard (not code).
- Run points, per the 11:05 CST ruling above: the `Tool pins (this runner)` step runs in `checks`, `checks-macos` and `checks-windows` (`.github/workflows/checks.yml`). It runs on a daily run, a dispatch, and a pull request that moves `.tool-versions` or the checker. On a pull request, the macOS and Windows steps also need their own scope flag. A lane's `--lint` run reads a mismatch as `unknown`, so the merge waits for the pull request's own CI run (`bin/ci-job` `read_tool_pins`).
- Not built:
  - Other repos take the check through the lint action they already call.
  - Read (plan and refuter, Nov 25): a red daily run blames no PR and does not stop `stable` (`actions/ci-alarm/clear_rule.py` `blames`; `.github/workflows/stable.yml`).
  - Who moves a pin when a runner image moves a tool: the owner's open question QAG.
- Machines: the Mac has Homebrew git 2.56.1 since 10:21 CST, 2026-11-25. The Windows upgrade is the owner's act.
- Debt `gh-version-unpinned` stays open until one `gh` line lands in `.tool-versions`. The pin value needs a read of CI's gh first.

## Related

- Decision `ci-pins-newest-interpreter` (CI pins the newest Python that passes its checks).
- Decision `action-pins-follow-sessions` (a CI action pin follows the session's tools when they differ).
- Debt `gh-version-unpinned` (nothing pins or checks the gh version). This decision takes it over.

Kind: process
Home: .tool-versions
