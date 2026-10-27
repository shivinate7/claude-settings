# A recursive delete after a cd names an absolute path

## The ruling

Rule `rm-after-cd` in `hooks/guard.py` refuses a recursive `rm` (`-r`, `-R`, `--recursive`) with a relative target, when a `cd` joined by `;`, `&&` or a newline came before it in the same command. The shape: `cd "$S"; rm -rf dl/*`.

1. Claude Code's own critical-path prompt cannot follow the cd, so it asks the owner. A failed cd also runs the rm in the working folder.
2. The refusal prints the target under the cd folder: `rm -rf "$S"/dl/*`. A literal absolute cd folder is joined as it is. Any other cd word prints `"$DIR"`, which the session sets to the full path.
3. An absolute target, a `"$VAR"/…` target, an `rm` with no recursive flag, and a recursive `rm` with no cd before it pass. A `cd X || rm …` is no landed cd and passes.
4. The check reads segments and tokens through `split_segments` and `segment_tokens`, so a quote or a comment holds no rm. Subshells, brace groups and `set -e;` are walked. An `sh -c` body is not (`guard-guards-mistakes-only`).
5. `hooks/rm_prompt_answer.py` is unchanged. It answers only the `${NAME:?}` form, so the printed form still reaches Claude Code's own rules. Whether a permission allow rule can quiet that prompt for a session's scratchpad is unmeasured and needs a local session.

Risk kind: likely risk. A scratch cleanup of the shape `cd $S; rm -rf dl/*` was written in normal work. Seen 2026-10-27, on the owner's screen.

Kind: process
Home: rule:shared-trees-delete-names-absolute-path
