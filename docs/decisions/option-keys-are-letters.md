# A waiting-page option's key is the letter the page shows

## The ruling

The waiting page shows an option by its position, as a letter: the first option is A, the second B (`skills/waiting-page/page.html`, symbol `letterOf`). The key of each option is that letter in lowercase. A session keys its options `a`, `b`, `c` in the order the page shows them, and names an option in item text by its letter, never by another key.

- Guard rule `option-letter-keys` (`hooks/question_form.py`, function `option_letter_hit`) refuses an `ArtifactData` set or update to `items`, of `kind: decision` or with no `kind`, when `options` has an option that:
  - has no string `key`;
  - repeats another option's key;
  - has the key `none` (the page's `NONE`, which it reads as "none of these"); or
  - has a key that is not the lowercase letter of its position; or
  - has a label that opens with a letter tag for a letter other than its key. A tag is one of "B:", "B.", "B)", "B -" (hyphen, en dash or em dash), "(B)", "[B]", "Option B:", "Option B -" or the whole label "Option B", in any case. Only a tag that names another letter refuses: "A:" on key a passes, and "A:" on key b is refused. A label that opens with a word, such as "A rail", "I would", "Another" or "B2B", has no tag and passes. A label carries no letter of its own: the page key is the only letter.
  - It judges a design's label (`designs[].label`) the same way, against the design's keys. It reads them as the page's `optionDesigns` does (`skills/waiting-page/page.html`):
    - A design's own `option`, a non-empty string, wins. It is the design's only key, even when another option's `design` is its slug.
    - That key is judged even when no option in the write has it. So an `option` that names a missing key still refuses a tag for another letter.
    - An update that carries `designs` and no `options` judges each design that has its own `option`.
    - A design with no `option`, or `option: ""`, belongs to each option whose `design` is its slug. With no such option, it is not judged.
    - Any other `option`, such as a number, gives no key, and the design is not judged.
  - It also refuses an item whose text (title, context, why, an option's text or a step) names an option by a letter-and-digit key, such as "option e2". The words that start the match are option, pick and key, in any case. A colon, a bracket, a quote or markdown emphasis may stand between the word and the key, as in "Option: e2", "Option [e2]" and "Pick **e2**". The key also matches in any case, since the page shows its letter in capitals, so "Option E2" is refused. "Option A", "pick b" and "option 2" pass, and so do the decision id "D12" and the topic id "t18", each in that case only.
  - It judges a `str_replace` on the text it adds (`new_str`), in any field, by this text rule only. The stored item is unseen, so a `str_replace` that adds a key-named option is refused even on a task, a note or a closed item.
  - It reads each write in a batch and data read from `file_path`. It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It passes a set or update of a task, a note or a closed item. It passes an update that carries no `options`, no matching text and no design label tagged against the design's own `option`. It passes a call to another artifact.
  - It reads last, after the form rules (`question-form`, `owner-judge`). Each older rule keeps naming its own refusals.
  - The reason says: key the options a, b, c in the order shown, each once, never none, and name an option by its letter. A label carries no letter of its own. It names no target.
  - It is built against a named incident, below. The rule landed 2026-10-30. The label and design-label clause landed 2026-11-01.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: the guard copies the page's letters in `_letter_of` and `OPTION_NONE_KEY`. A test reads the page's `letterOf` and `NONE` lines and fails when they are not `String.fromCharCode(65 + i % 26)` and `"none"`. It compares the page to those two forms, not to the guard's copy.
  - Known limit: more than 26 options always refuse, because the page repeats letters after Z and the key then repeats.
  - Known limit: an option named in text by a word, such as "the lint option", or by a key the page never shows that is not letter-and-digit, passes.
  - Known limit: an id or cell with a key's shape, such as the step id "c188", "key d4" or "Pick A1", is refused after option, pick or key.
  - Known limit: a label with markup before its tag, such as "**B:** strip", passes. A label with a tag that matches its key, such as "B) strip" on key b, passes.
  - Known limit: a tag with no space after its mark passes: "B.strip", "B)strip", "B-strip", "B–strip" and "B—strip". Only the colon needs no space.
  - Known limit: "Option B strip", with no mark after the letter, passes. Only the whole label "Option B" is a tag without a mark.
  - Known limit: only "Option" is a prefix. "Variant B:", "Choice B:" and "Plan B:" pass.
  - Known limit: a roman numeral reads as a tag, so "I. Intro" or "V. Vendor" under another key is refused.
  - Known limit: an update that carries `options` but no `kind` is judged as a decision, so a task update that carries options is refused only if its keys are wrong. The writer carries `kind: task` again on such an update.

Incident:

- 2026-11-01 16:12 CST: a waiting item keyed its options a to d but labelled them "B: a bottom strip", "D: drag sideways", "A: a rail" and "C: a grab line". The page showed two letter sets, so an answer "a" was ambiguous.
- 2026-10-30 15:09 CDT, waiting item 77: an option keyed `e2` sat in the first position, so the page showed it as A. The owner's answer "A" was read as the option keyed `a`, which sat second.
- 2026-10-28 12:47 CDT, waiting item 44: an option keyed `none` hid the page's own "none of these" answer.

Kind: process
Home: rule:questions-go-to-owner
