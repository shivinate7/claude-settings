# A repo matches a shared format; the shared tool never grows a second form

## The ruling

Owner, 2026-10-27 12:51 CDT, topic t18 (one home, then variants): when a repo differs from a shared format, the repo changes to match it. The shared tool never grows a second accepted form to fit one repo.

- An option that widens what a shared tool accepts is a second accepted form, an allow-list entry or a per-repo exception. It carries "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo" and is never the recommended option. Rule `style-question-form` holds the text.
- On the waiting page (skill `waiting-page`), such an option carries `widens: true`. Its card shows the label.
- Guard rule `uniform-pick` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set or update to `items` whose `recommended` (old name `pick`) names an option with `widens: true`. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`), and only an item of kind `decision` or with no kind.
  - It is built against a named incident, below. It landed 2026-10-28.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: an update that sets `recommended` without `options` cannot see the stored options and passes. The writer carries `options` again on such an update.
  - Known limit: the guard reads the `widens` mark, not the option's text. An unmarked widening option passes this rule. The call judge is the backstop.
- Call judge (`hooks/call_judge.py`, a model, rule `question-judge`): on an `ArtifactData` set or update of a waiting-page item that carries `options`, the one model prompt adds `WIDENING_RULE`. The model is told to refuse an option that widens a shared tool and lacks the mark, and to name the option key in its reason. The mark is `WIDENS_KEY` in `hooks/question_form.py`, set to the JSON boolean `true`. Code does not check that the key is named. Like every call-judge verdict, it fails open on a model error or timeout. Owner ruling, 2026-11-03 22:28 CST. It adds text to the model call the judge already makes, so it adds no model call or process. What the change does to what the shared tool accepts decides it, never how many repos it names. The prompt says a change that makes the shared tool accept what it refused before widens it. A change that adds a second accepted form, a shared allow-list entry or a per-repo exception widens the tool, whatever it says about repos, one for every repo included. The prompts say "exception" bare; it names a per-repo exception. A change that makes one same rule apply to every repo and adds none of the three is not widening. That carve-out needs a change that keeps what the tool accepts the same or narrows it. A change that only tightens the tool is not widening. A change that tightens, or applies to every repo, and also adds one of the three still widens. Each sentence that names the three names all three.
- Reply judge (`hooks/reply_judge.py`, a model, never blocks): it flags a widening option only when the reply recommends it or offers it without the label. It never flags a labelled widening option that is not the recommended one. It runs on the Stops it already judges, so it adds no model call. Its prompt holds the same sentences, with flag in place of block.
  - Known limit (both judges): that a model reads the widening sentences as written is unmeasured. A widening form hidden in an option worded "for every repo" can still pass.
- A shared check that today lets one repo's variant through is a debt to remove (debt `layout-legacy-repos`).

Incident:

- 2026-10-27 12:51 CDT: a waiting-page item recommended loosening a shared tool so it would accept banchi's record titles.
- 2026-11-01 11:43 CST: the card text quoted a bare topic id (rule `speak-cite-id-plus-gloss`). The card now says the ruling in plain words.
- Before 2026-11-14 15:12 CST: the judge model called two options widening that keep what the shared tool accepts the same or narrow it. Page item 729 a put the tree-equal push skip in the shared CI form, so every repo gets it. Page item 835 a let a PR whose tree is byte-identical cite a reviewed record, read by tree sha. Both verdicts were judged false alarms. No owner ruling is cited for that reading; the work went ahead on the coordinator's go-ahead (coordinator, 2026-11-14 15:12 CST). The same-or-narrow condition on the every-repo carve-out comes from these sightings.

Kind: process
Home: rule:style-question-form
