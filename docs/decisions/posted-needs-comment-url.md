# A reply line that claims a posted comment cites the comment URL

## The ruling

The posted-comment check, in the Stop hook `lint/report_guard.py` (rule `posted-needs-comment-url`), refuses a reply when one of its lines claims a posted PR comment or review record. The line must cite the comment URL. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite with no refusal before it stays quiet. The rewrite follows the ruling in decision `answered-needs-source` (answered-source check).

**What it reads.** Each line of the last reply, outside fences and inline code spans, that names a PR and holds a claim. A PR ref is a `#<n>`, a github.com URL or the word PR. A claim is a posting verb with a noun in the same clause. The verbs are posted, left, filed and commented. The nouns are review record, review and comment. "commented" needs no noun. "left" needs the noun after it. A word joined to another by a hyphen (`posted-needs-comment-url`) is not the word. A clause breaks at `. ; ! ?`, a comma or a dash, and not at a colon.

**What counts as a source.** One comment-anchored GitHub URL on the same line: a link with `/pull/<n>` or `/issues/<n>`, then `#issuecomment-<digits>`, `#discussion_r<digits>` or `#pullrequestreview-<digits>`. A source inside an inline code span counts. A bare PR link, a `#<n>`, a commit hash, a repo path and a time are no source. When the line also holds a `#<n>` outside its URLs, one of them must equal a cited URL's number. A line with no `#<n>` passes on the URL alone.

**What is exempt.** A line that ends in `?` asks and claims nothing. Fences opened by ``` or by ~~~ are skipped. A claim verb is exempt in these cases:
- A negator or modal sits in the auxiliary chain directly before it, up to 3 words. The negators and modals are not, n't, never, yet, cannot, will, would, shall, should, must, can, could, may, might and to. The other chain words are be, been, being, have, has, had, is, are, was, were, get and gets. The chain needs at least one negator or modal.
- A subordinator (after, when, whenever, until, once, before, if, unless) comes directly before it.
- A subordinator comes earlier in the clause and the verb is passive, with an auxiliary right before it.
- "no" or "nothing" comes right before the noun phrase ("No review record was posted"), or a want-verb does (needs, wants, awaits, waits for).
- "left" has "unchanged", "as is" or "alone" after it in the clause.

**Lane choices, process-only (lane ruling 15:31 CST, session_013NEJL45afxTyvacTQtAEwZ).**
- Verb set: posted, left, filed, commented.
- Noun set: review record, review, comment. A bare "record" is not a noun, so "posted the step record" is no claim.
- A claim needs a PR ref on the line.
- A negator or modal exempts only inside the auxiliary chain directly before the verb. A negator earlier in the clause exempts nothing, so "After CI passed I posted the review record on #1500" refuses.
- A subordinator exempts only a verb it directly precedes, or a passive verb.
- The `#<n>` compare is lenient: one match between the line's `#<n>` refs and the cited URL numbers passes. The line refuses only when none matches.
- A URL is cut out of the line before clauses are read, so its dots break nothing.
- The noun read crosses a colon, so a label before a colon ("Review record: posted to PR #1500") is the noun.

Risk kind: likely risk. The incident: lane notes-fix-page's reply at 14:54 CST said it "posted the round-1 review record on PR #1500". The comment went up at 15:01 CST.

Harm: a runner trusts a review record that does not exist yet.

Cost: a regex over the reply. No file, no process, no GitHub read. `PostedNeedsCommentUrlTests` in `lint/test_report_guard.py` proves it.

Known limits:
- The URL is not resolved against GitHub. The guard makes no GitHub reads, and a resolve would be a new process start. A well-formed URL for a comment that does not exist passes.
- A line that ends in `?` is skipped, as in the answered check, so "Posted the review on #1500?" claims nothing.
- The verbs submitted, published and added are not read.
- A rewrite after a posted-only refusal is not checked again, mirroring the answered check.
- "commented" on a line with no comment (a code comment, "the reviewer commented that") is read as a claim when the line names a PR.
- Code reads tokens, not what they cite.

Kind: process
Home: lint/report_guard.py
