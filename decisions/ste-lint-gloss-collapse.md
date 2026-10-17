# STE001 stops counting a citation's generated gloss

## The ruling

`STE001` must not count the gloss that a tool writes after a decision id. A caller such as q_max cites
`D-nnn, title`, never a bare id, and the tool writes the title from the target entry. The author types one
token.

- `build_gloss_pattern(decisions_dir)` in `lint/ste_lint.py` reads each entry's front matter `id:` and
  `title:`, standard library only. It pairs each id with the exact title of the entry that id names, so
  `D-042, some other text` never collapses.
- A reversed entry's gloss carries a suffix, `(reversed by D-nnn, title)`. The tool reads it from a
  `reverses: D-nnn` marker line in another entry's prose.
- The pattern is matched against the raw sentence, before other masking, and folds into `Masker`'s token
  step. A title that holds inline code still collapses whole.
- The feature is off unless a decisions folder exists at the configured path. Flag `--decisions-dir`,
  default `docs/decisions`, resolved from the linter's working directory. `actions/ste-lint/action.yml` has
  a matching `decisions-dir` input with the same default. A repository with no such folder sees no change.
- A generated gloss must not choose the mode of a section. `_degloss_for_mode` folds a collapsed citation
  span into one space wherever a heading's mode is decided. STE001 holds one budget of 30 words in both
  modes (`plain-prose-lint`).

Reason: inserted titles pushed hundreds of q_max sentences over the limit that no person had typed.
q_max's `harness/decision-refs.mjs` solved the same defect for its own checker.

Kind: process
Home: lint/ste_lint.py
