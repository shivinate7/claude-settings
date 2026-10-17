# STE001 stops counting a citation's generated gloss

## The ruling

`lint/ste_lint.py`'s `STE001` counts words per sentence. A caller such as q_max cites a decision as
`D-nnn, title`, never a bare id, and a tool writes that gloss from the target entry's own title. The
author types one token, so `STE001` must not count the inserted words.

- `ste_lint.py` has `build_gloss_pattern(decisions_dir)`. It reads each entry's front matter, `id:` and
  `title:`, directly, with the standard library only. It pairs each id with the exact title of the entry
  that id names, so `D-042, some other text` never collapses.
- A reversed entry's gloss carries a suffix, `(reversed by D-nnn, title)`. The tool reads that the same
  way, from a `reverses: D-nnn` marker line in another entry's own prose.
- The pattern is matched against the raw sentence, before any other masking runs. It then folds into
  `Masker`'s existing token step, the one that turns a code span or a link into one word for the count. A
  title that itself holds inline code still collapses whole.
- The feature stays off unless a decisions folder exists at a configured path. The flag is
  `--decisions-dir`. Its default is `docs/decisions`, the path `decision-refs.mjs` uses. The path resolves
  from the linter's own working directory. A repository with no such folder sees no change.
- `actions/ste-lint/action.yml` has a matching `decisions-dir` input, same default. It passes the value
  straight through to the script.
- A generated gloss must not choose the mode of a section. A heading picks its section's mode, procedural
  or descriptive, by scanning its raw text for a trigger word such as `run` or `test`
  (`PROCEDURAL_HEADINGS`). `_degloss_for_mode` folds a collapsed citation span into one space wherever a
  heading's mode gets decided. It is a no-op when no decisions folder is set (`_GLOSS_PATTERN` stays
  `None`). STE001 holds one budget of 30 words in both modes (`plain-prose-lint`). The mode decides only
  whether STE015 (condition order, a warning) runs.
- The list-item path needs no fix. Its first-word scan reads only the letters from the text's first
  character, so an id such as `D-448` stops that scan at its hyphen and never reaches the gloss.

Reason: q_max's `harness/decision-refs.mjs` (`glossSpanPattern`) solved the same defect for its own
checker, where inserted titles pushed hundreds of sentences over the limit that no person had typed.

Kind: process
Home: lint/ste_lint.py
