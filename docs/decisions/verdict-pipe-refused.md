# The guard refuses a pipe out of verdict

## The ruling

The `verdict-pipe` rule in `hooks/guard.py` refuses a shell command (Bash or PowerShell) that pipes the output of `verdict` into another command, such as `verdict <cmd> | tail`. It reads each segment whose command word is `verdict`, by any path.

- Refused: `verdict <cmd> | <any command>`, with or without `2>&1`, after `cd x &&`, or after an env prefix.
- Passes: `verdict <cmd>` alone, `verdict <cmd> && <next>`, `verdict <cmd> || <next>`, a redirect to a file, and a `|` inside a quoted argument.
- The remedy: run `verdict <cmd>` with nothing after it. Its output is already short: one verdict line, then at most 30 lines.

Coordinator ruling, 2026-11-08 03:44 CST: a separate verdict-pipe-exit rule is dropped. It would have refused `verdict <check> | <filter> && ...` only when pipefail is off. This rule already refuses every `verdict` pipe, so it covers that job.

## The mistake and the harm

On 2026-11-07 13:51 CST, a lane session ran `verdict <cmd> | tail` and read exit 0 as a pass. A pipe returns the exit of its last command, here `tail`, so a red run reads green. And `verdict` prints its `FAIL ... rc=` line first, so `tail` can cut the one line that says red. On 2026-10-17, an orchestrator's `| tail` on a background merge read as a false exit 3 (debt `verdict-pipe-drops-line`, a pipe after verdict hides its verdict line; this record retires it).

Harm: a red check reads as green, and a broken change merges.

Why deny and not ask: a pipe after `verdict` adds nothing, because `verdict` already prints a short verdict. So no normal work needs the form.

The retired debt asked for the verdict line printed last and a guard that asks. The deny meets the same outcome by a stronger path. No pipe can follow `verdict`, so no filter can mask its exit or cut its line. The line order then no longer matters.

Kind: process
Home: hooks/guard.py
Check: hooks/test_guard.py
