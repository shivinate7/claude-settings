# A repo should match a shared format, rather than the shared tool grow a second form

## The ruling

Owner, 2026-10-27 12:51 CDT, topic t18 (one home, then variants): when a repo differs from a shared format, the repo changes to match it. The shared tool never grows a second accepted form to fit one repo. (The owner's words that day; the 2026-11-06 entry below sets the strength.)

Owner, 2026-11-06 12:41 CST, item 278: the ruling reads as a guideline, not a fixed rule. A mark on an option goes by scope.

Scope: widening is when the shared tool changes to fit one repo. It accepts a second form, an allow-list entry or an exception for that repo's sake. A change made the same way for every repo, for every repo's sake, is not widening. Loosening a shared tool to accept one repo's titles (the 2026-10-27 case below) is widening.

- An option that widens, by that scope, carries "Goes against your ruling: a repo should change to fit the shared tool, rather than the tool change to fit a repo" and is not the recommended option. Rule `style-question-form` holds the text.
- On the waiting page (skill `waiting-page`), such an option carries `widens: true`. Its card shows the label.
- Guard rule `uniform-pick` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set or update to `items` whose `recommended` (old name `pick`) names an option with `widens: true`. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`), and only an item of kind `decision` or with no kind.
  - It is built against a named incident, below. It landed 2026-10-28.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: an update that sets `recommended` without `options` cannot see the stored options and passes. The writer carries `options` again on such an update.
  - Known limit: the guard reads the `widens` mark, not the option's text. An unmarked widening option passes this rule. The call judge is the backstop.
- Call judge (`hooks/call_judge.py`, a model, rule `question-judge`): on an `ArtifactData` set or update of a waiting-page item that carries `options`, the one model prompt adds `WIDENING_RULE`. The model is told to refuse an option that widens a shared tool and lacks the mark, and to name the option key in its reason. The mark is `WIDENS_KEY` in `hooks/question_form.py`, set to the JSON boolean `true`. Code does not check that the key is named. Like every call-judge verdict, it fails open on a model error or timeout. Owner ruling, 2026-11-03 22:28 CST. It adds text to the model call the judge already makes, so it adds no model call or process.
- Reply judge (`hooks/reply_judge.py`, a model, never blocks): it flags a reply whose recommended option widens a shared tool, and a widening option offered without the label. It runs on the Stops it already judges, so it adds no model call.
- A shared check that today lets one repo's variant through is a debt to remove (debt `layout-legacy-repos`).

Incident:

- 2026-10-27 12:51 CDT: a waiting-page item recommended loosening a shared tool so it would accept banchi's record titles.
- 2026-11-01 11:43 CST: the card text quoted a bare topic id (rule `speak-cite-id-plus-gloss`). The card now says the ruling in plain words.
- 2026-11-06 12:41 CST: a false alarm. Auto-mode allow lines that apply the same way to every repo were marked as widening. The owner ruled the ruling reads as a guideline and the mark goes by scope (item 278). The mark's words, both judge prompts and the card changed.

Kind: process
Home: rule:style-question-form
