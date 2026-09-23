# STE001 stops counting a citation's generated gloss

`lint/ste_lint.py`'s `STE001` counts words per sentence. A caller such as q_max cites a
decision as `D-nnn, title`, never a bare id. A tool writes that gloss from the target
entry's own title. The author types one token. The tool inserts several more words.
`STE001` counted every inserted word as if a person had typed it.

## What was measured

q_max's `harness/decision-refs.mjs` already solved this for its own checker. Its
`glossSpanPattern` function collapses a citation and its gloss into one span. It matches
the span against the real title of the id it names, read from `docs/decisions/`. Its own
comment records the same defect in that checker's own history. A gloss run once took its
sentence-length count from 0 to 165 over-long sentences. Every one was pushed over by an
inserted title. None was touched by a person.

This change ran `STE001` over q_max's tracked `*.md` files, before and after. Before, it
reported 715 errors. After, with `docs/decisions` present, it reported 270. Of the 715,
checking every over-long sentence's own text found exactly one that even names a decision
id. That one names a range, `D-332 to D-334`, not a gloss, so it is left alone, correctly.
The rest of the drop is citation gloss, collapsed.

Those two counts sit below the 644 and 180 the request that started this work expected.
Excluding the vendored `.claude/skills/**` tree, wording this repository does not own,
drops the "before" count further, to 550. That undershoots the expectation the other way.
The likely cause is a different exact file set, or a different linter commit, at
measurement time. It is not a defect in the collapse. The per-sentence check above shows
the collapse removes almost every citation-caused case it exists to fix.

## What this decision does

`ste_lint.py` gains `build_gloss_pattern(decisions_dir)`. It reads each entry's front
matter, `id:` and `title:`, directly. It needs no dependency outside the standard
library. It pairs each id with the exact title of the entry that id names. That is the
same narrowness `glossSpanPattern` uses. `D-042, some other text` never collapses.

A reversed entry's gloss carries a suffix, `(reversed by D-nnn, title)`. The tool reads
that the same way, from a `reverses: D-nnn` marker line in another entry's own prose.

The pattern is matched against the raw sentence, before any other masking runs. It then
folds into `Masker`'s existing token step, the one that already turns a code span or a
link into one word for the count. A title that itself holds inline code still collapses
whole.

The feature stays off unless a decisions folder exists at a configured path. The flag is
`--decisions-dir`. Its default is `docs/decisions`, the same path `decision-refs.mjs`
uses. The path resolves from the linter's own working directory, a repository's root in
every caller today. A repository with no such folder sees no change. One test proves
that: it diffs the linter's own output with the pattern on and with it off, over the same
input. The whole existing `lint/test_gates.py` suite also stays green, 121 tests, unchanged.

`actions/ste-lint/action.yml` carries a matching `decisions-dir` input, same default. It
passes the value straight through to the script. No existing caller changes its own
inputs. No existing caller's behavior changes.

## What remains open

The counts above do not match the numbers the request that started this decision
expected. The collapse itself checks out: one non-gloss id mention sits among 715
over-long sentences, and that one is correctly left alone. The gap in the raw totals
stays unexplained. It is worth a second look if it matters to a future reader.
