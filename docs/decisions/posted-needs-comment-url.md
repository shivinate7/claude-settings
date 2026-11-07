# A reply line that claims a posted comment cites the comment URL

## The ruling

The posted-comment check, in the Stop hook `lint/report_guard.py` (rule `posted-needs-comment-url`), refuses a reply when one of its lines claims a posted PR comment or review record. The line must cite the comment URL. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite after a posted-only refusal stays quiet, as with the answered-source refusal (`stop_hook_active`). A rewrite with no refusal before it stays quiet too. The rewrite follows the ruling in decision `answered-needs-source` (answered-source check).

**What it reads.** Each line of the last reply, outside fences and inline code spans, that holds a claim. A claim is a posting verb with a noun in the same clause. The verbs are posted, left, filed and commented. The nouns are comment, review and record, in the singular or plural. "commented" needs no noun. "left" needs the noun after it. A word joined to another by a hyphen (`posted-needs-comment-url`) is not the word.

**What counts as a source.** One comment-anchored GitHub URL on the same line: a link with `/pull/<n>` or `/issues/<n>`, then `#issuecomment-<digits>`, `#discussion_r<digits>` or `#pullrequestreview-<digits>`. A source inside an inline code span counts. A bare PR link, a `#<n>`, a PR ref, a commit hash, a repo path and a time are no source. When the line also holds a `#<n>` outside its URLs, one of them must equal a cited URL's number. A line with no `#<n>` passes on the URL alone.

**What is exempt.** A line where a negator sits in the same clause before the verb. The negators are not, n't, no, none, nothing, nobody, never, cannot and yet to. The modals and conditionals count too: will, would, should, shall, must, can, could, may, might, need, needs, once, until, when, whenever, after, before, if, unless and "to be". A line that ends in `?` asks and claims nothing. Fences opened by ``` or by ~~~ are skipped.

**Lane choices, process-only.**
- Verb set: posted, left, filed, commented. Noun set: comment, review, record.
- "left" needs the noun after it, so "two records left to move" is no claim.
- The `#<n>` compare is lenient: one match between the line's `#<n>` refs and the cited URL numbers passes, so "blocked by #1499" beside a URL for #1500 passes.
- A URL is cut out of the line before clauses are read, so its dots break no clause.
- The negator list is the answered-source list plus modals. It is a second regex built from the same base, not a copy; the answered check keeps its own list.

Risk kind: likely risk. The incident: lane notes-fix-page's reply at 14:54 CST said it "posted the round-1 review record on PR #1500". The comment went up at 15:01 CST.

Harm: a runner trusts a review record that does not exist yet.

Cost: a regex over the reply. No file, no process, no GitHub read. `PostedNeedsCommentUrlTests` in `lint/test_report_guard.py` proves it.

Known limits: the URL is not resolved against GitHub. The guard makes no GitHub reads, and a resolve would be a new process start. A well-formed URL for a comment that does not exist passes. A negator anywhere earlier in the clause exempts the verb. "commented" on a line with no comment (a code comment, "the reviewer commented that") is read as a claim and needs the URL, or other words. Code reads tokens, not what they cite.

Kind: process
Home: lint/report_guard.py
