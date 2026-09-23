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

This change ran `STE001` over q_max's tracked `*.md` files on `main`, before and after.
Before, it reported 715 errors. After, with `docs/decisions` present, it reported 254.
Of the 715, checking every over-long sentence's own text found exactly one that even
names a decision id. That one names a range, `D-332 to D-334`, not a gloss, so it is
left alone, correctly. The rest of the drop is citation gloss, collapsed.

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

## A second path: the section's own word budget

The word count was not the only place a generated gloss could change a verdict. A
heading picks its section's word budget, procedural (20 words) or descriptive (25).
It picks that by scanning the heading's raw text for a trigger word, such as `run`
or `test`, in `PROCEDURAL_HEADINGS`. That scan ran before the collapse above.

q_max's real `D-448` is titled "The operator tiers run themselves". A heading citing
it as `(D-448, The operator tiers run themselves)` carries `run`. The whole section
under that heading then measured at 20 words, not 25. Nobody who wrote the heading
chose that word. Reproduced with one fixed 23-word body, under three otherwise
identical headings: no citation gives no error. A citation whose gloss carries `run`
gives one. A citation whose gloss carries no trigger word gives none.

The fix reads `_degloss_for_mode`. It folds a collapsed citation span into one space,
wherever a heading's mode gets decided. It changes nothing when no decisions folder
is set. `_GLOSS_PATTERN` stays `None` then, so the function is a no-op there.

The list-item path was checked too. Its own first-word scan reads only the letters
starting at the text's first character, through `re.match(r"([A-Za-z]+)", body)`. An
id such as `D-448` stops that scan one letter in, at its own hyphen. It never reaches
the gloss. That path needed no fix. A test proves it, sized so a wrong classification
would have failed the test.

## What this closes

The 715-to-270 count this decision first reported did not match the 644-to-180 the
request expected. Both gaps are now explained, not merely defended.

First, that estimate came from a different branch, one that already carried about
174 earlier sentence splits. A different total was expected on that account alone.

Second, on `main` itself, a finding-by-finding diff against an independent count of
254 found this decision's own result a strict superset. Sixteen sentences carried
the difference, every one under a heading whose gloss held a trigger word. That is
exactly the defect fixed above. `main`'s own count is now 254, the independent count,
exactly.
