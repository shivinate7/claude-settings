# Plan: the one-home check

This plan turns the one-home rule (`building-one-home-per-capability`, the rule that a shared
thing has one home and is cited everywhere) into a check. It covers three gaps: copies inside
this repo, reworded rule text, and child repos that carry their own nuance.

The work ships as one lane, branch `one-home-check`. This file is deleted when that lane merges.
Before then, the rules are the working text here.

## Problem

### The incident

- The STE output rule (`output-write-in-ste`) was reworded in commit 9d577ab4 (the plain-prose
  lint commit, 2026-10-17). The removed sentence reads, in full:

```
**Output.** Write in Simplified Technical English by default, to me and between agents,
unless told otherwise.<!-- rule:output-write-in-ste -->
```

- The old sentence has 15 words. In the old file it wrapped across two lines.
- On origin/main 5a5f081e, eight files in `agents/` still hold the old phrase, as a 5-word
  fragment. The brief said nine. A search finds eight. `agents/design-reviewer.md` does not
  hold it.
- A ninth file holds it: the debt line `ste-into-agent-briefs` in `docs/debts/notes.md`. That
  line quotes the copies. It cites decision `plain-prose-lint`.
- So the copies were a recorded deferral. The debt waits for an owner grant or for 30 days
  after the plain-prose lint merged.
- Draft PR #1105, which fixed the copies, is not read here. Its state is unknown.

### The rule

`building-one-home-per-capability` says a capability has one home. Other files call it. They
never copy it. The rule has no check. Its row in `lint/rule_mechanisms.json` (the mechanism
table) says `unmechanized`. The row names a narrow guard, the item-field guard in decision
`item-field-rendered`. That guard covers one case only.

### What exists today

- `lint/find_copies.py` (the copy finder) compares a child repo with the parent. It has no
  in-repo mode. It matches whole files (byte-equal) and near-equal files, by whole lines of 8 or
  more characters. A copy wrapped at other line breaks shares few whole lines, so its score
  falls. It knows no rule ids.
- `lint/test_retired_names.py` (the retired-names test) fails when a hand-listed old name
  appears as a whole word. It sees only names someone listed. It exempts `GLOSSARY.md` and
  `docs/records.md`.
- `lint/stale_cites.py` (the stale-cites check) reads a base...head range. It fails a line that
  names a removed path (STALE001) or a removed def (STALE002). A removed sentence names neither,
  so the check misses rewording. A shallow base is unknown, not a finding. Each tracked `.md` is
  read once, only when a name was removed.
- `lint/rule_audit.py` (the rule audit) reads the rule files in `RULE_FILES`. That list holds
  `CLAUDE.md` and `output-styles/shiv-stylisms.md`. The audit checks each mechanism row for shape.
  It does not compare text.

### What each one misses

- The 8-word floor (a sentence must hold 8 words before it counts) misses the incident. The
  copies are 5 words. Measured: the 8 agent files hold a 5-word run of the old sentence, and no
  8-word run.
- A re-flowed copy defeats the copy finder's line match. The old sentence itself wrapped across
  a line break.
- The retired-names test misses any phrase nobody listed.
- The stale-cites check misses any rewording that removes no path and no def.

## Design

Each part names its home. Nothing copies a list. Each part reads one place.

### Shared step: read the rule sentences

- Home: `lint/rule_audit.py`. It gets one function that returns each rule id with its sentences.
  The copy finder and the reword check both import it (`building-one-home-per-capability`).
- Sources: the files in `RULE_FILES`. That list is read, never copied
  (`building-allow-list-is-the-constant`, the allow-list rule). Measured: 97 distinct rule ids
  in `CLAUDE.md`, and 22 lines in `output-styles/shiv-stylisms.md` carry a rule anchor.
- A rule span runs from the previous rule anchor, or from the paragraph start, up to this anchor.
  A bold lead-in such as `**Output.**` is dropped. A span splits into sentences at `.`, `!` or
  `?` followed by a space.
- An anchor inside a fenced block or an inline code span is quoted text. It is not a source
  (`building-scanner-respects-strings`, the scanner rule: a scanner respects strings and
  comments).
- Normalizing: drop HTML comments, code marks, emphasis marks, quote marks, list marks and
  heading marks. Keep link text. Lowercase. Keep letters and digits as words. Line breaks become
  spaces.

### a) One home: copies inside this repo

- Entry: `python3 lint/find_copies.py --in-repo`. This is a new mode. The cross-repo modes stay.
- A copy is a run of 8 or more words from a rule sentence, found whole in another tracked
  `*.md` file after normalizing. A sentence under 8 words is never a copy. Short terms and stock
  phrases ("Start with the point.") therefore pass.
- A copy is exempt when the rule id sits in the same paragraph, the same table row, the same
  fenced block or the same blockquote. The id may appear as text or as a rule anchor. A quote
  that carries its anchor is not a copy.
- Excluded files: the generated `docs/records.md` and `GLOSSARY.md`. Both names come from one
  constant. `lint/test_retired_names.py` already holds the same two names. The builder imports
  the constant. It does not copy it.
- Output: one line per copy, `path:line: COPY001 <rule id> copied`. COPY001 is the code for a
  copy. The last line reads `copies: PASS` or `copies: FAIL`.
- Exit codes match the copy finder's contract: 0 no copies, 1 copies, 2 a read that could not
  run.
- Known gap: a copy of 7 words or fewer passes. This keeps stock phrases quiet. It is a note,
  not a debt, until a real incident (`roles-findings-are-debts-or-notes`, the debt or note rule).

### b) Reword check: removed rule text

- Home: `lint/stale_cites.py`, as a new code STALE003 (the reword code). The stale-cites check
  already reads a range. It handles a shallow base. It reads each tracked `.md` only when a name
  was removed. A second range reader in the copy finder would be a second home.
- Trigger: a rule sentence present at base and absent or changed at head.
- Floor: the removed sentence uses a 5-word floor, not 8. Measured on origin/main 5a5f081e: the
  5-word run of the old sentence appears in 9 tracked files. Those are the 8 agent files and the
  debt line. At 8 words the count is zero.
- Scan: the whole tree at head, not the diff. There are 381 tracked `.md` files on origin/main.
  The check lists each file that holds a 5-word run of the removed sentence. It names the rule
  id that changed.
- The check fails until each listed file is fixed, or the file names the rule id nearby (the
  same exemption as part a).
- After the fix, the old phrase joins the list `RETIRED` in `lint/test_retired_names.py`. The
  retired-names test then fails if the phrase returns. Input Needed, question 1 decides this.
- False-alarm rate for other removed sentences: unmeasured. The builder measures it on the first
  run of the fixture set.

### c) Child repos

- A child repo reads the parent's rule ids from the parent's `RULE_FILES`. It never reads a
  copied list.
- Entry: `python3 lint/find_copies.py --in-repo --parent <claude-settings checkout>`, run in the
  child's CI. The child's CI checks out claude-settings at a pinned sha. This follows the pin
  rule (`action-pins-follow-sessions`). Input Needed, question 3 confirms it.
- A child exception is one line in the child's own file:

  `<!-- override: <rule-id> reason: <text> -->`

  The prose term is "child exception". The word `override` is the brief's syntax. `GLOSSARY.md`
  uses `override` for the owner's prompt (decision `owner-override`). Input Needed, question 2
  decides the word.
- The check fails when:
  1. the reason is empty, or holds fewer words than `REASON_MIN_WORDS` in `lint/rule_audit.py`.
     That constant is imported, not copied;
  2. the rule id is not a rule id in the parent. The rule is gone from the parent;
  3. the exception covers no copy in its own file. It is unused. ESLint's
     `reportUnusedDisableDirectives` makes the same call for disable comments (Sources).
- Scope: an exception covers copies of its own rule id, in its own file only.
- Import only: a child file whose only content is an `@`-import line, such as
  `@~/claude-settings-main/CLAUDE.md`, holds no rule sentence. It is never flagged.
- Nuance: a child that rewords a rule sentence is not a verbatim copy. This check does not see
  it. The child exception is how the child declares the nuance. Paraphrase detection is out of
  scope. It is a note.

### d) Mechanism row

Change the row `building-one-home-per-capability` in `lint/rule_mechanisms.json`:

- `kind`: `check`
- `ref`: `lint/find_copies.py`
- `test`: one test in `lint/test_find_copies.py`, named by the builder. It must resolve by AST,
  as the rule audit requires.

The row holds one kind, so the reason text leaves the row. The unmechanized half stays as one
note line in `docs/debts/notes.md`. That half is "two differently named functions do one job".
It also keeps the item-field guard mention.

### Cost

The checks run in CI, once per push and once per pull request. They never run as a hook or on
a timer.

- `find_copies.py --in-repo`: one python start, one `git ls-files`, one read of each tracked
  `.md` file (381 on origin/main), no writes, no process left running.
- STALE003: runs only when a rule sentence changed in the range. It adds one `git cat-file
  --batch` read of each tracked `.md` file. The existing stale-cites starts still apply.
- The cost tests count the process starts, the reads and the writes. They follow the pattern of
  `CostTests` in `lint/test_stale_cites.py`. A test proves each count
  (`outcomes-mechanize-rules`, the cost rule).

## Tests (red first)

The test-author writes these cases before the builder changes any code. Each case is recorded
red on the current code (`outcomes-tests-are-statements`, the failing-test rule). The check is
trusted only after it goes red on the defect it guards (`verification-trust-guard-after-red`).

1. Incident, red then green. The fixture holds the eight agent lines and the debt line, as they
   are on origin/main 5a5f081e. A rule change moves the old sentence to the current one. The
   reword check lists all nine files. It goes green when each is fixed.
2. Copy, red. A current rule sentence of 8 or more words is copied into an `agents/` file, with
   no rule id nearby. The copy finder reports COPY001.
3. Quote in a fenced block, green. The same sentence sits in a fence that carries the rule
   anchor. No COPY001.
4. Quote in a blockquote, green. The same as case 3, in a blockquote.
5. Stock phrase, green. "Start with the point. No preamble." and other phrases under 8 words.
6. Glossary row, green. A glossary-style table row with a term. No COPY001.
7. `@`-import, green. A child file holding only an `@`-import line. No flag.
8. Re-flow, red. The old sentence, wrapped at a different point from the pre-9d577ab4 wrap, is
   copied. COPY001 fires. The line-based copy finder misses this case.
9. Scanner, correct result. An anchor in an inline code span is text, not a source. A lone
   apostrophe in ordinary text does not change the word run. A `//` or `/*` inside a rule sentence does
   not hide a copy.
10. Child exception. (i) A reason and a copy in the same file: green. (ii) An empty reason: red.
    (iii) A rule id that the parent lacks: red. (iv) No copy in the file: red.
11. Cost. One python start, one `git ls-files`, one read per file, zero writes.
12. Mechanism row. The rule audit passes on the new row. The check resolves, and the test resolves
    by AST.

## Deviations from the brief

- The brief said nine agent files. The measured count is eight. The ninth hit is the debt line in
  `docs/debts/notes.md`.
- The 8-word floor misses the incident copies. The reword check uses a 5-word floor for removed
  text. Measured: nine files at 5 words, none at 8.
- The reword check lives in `lint/stale_cites.py`, not `lint/find_copies.py`. Range reads have one
  home.
- The rule sources are the two files in `RULE_FILES`, not `CLAUDE.md` alone.
- The brief's syntax keeps the word `override`. The prose term is "child exception". Input
  Needed, question 2 decides the word.
- The brief said to fix or add each copy. The plan reads that as: fix each copy, then ban the old
  phrase so it cannot return. Input Needed, question 1 confirms the reading.
- `lint/rule_mechanisms.json`, `lint/find_copies.py`, `lint/stale_cites.py`,
  `lint/test_retired_names.py` and the test files are not Markdown. This lane does not edit them.
  The builder lane does.

## Input Needed

1. The retired-names list. Ban the old phrase after the fixes, or exempt it? Adding the phrase
   to `lint/test_retired_names.py` makes that test fail on any file that still holds it. It
   cannot pass a file that holds the phrase. Recommendation: ban, after the fixes.
2. The child exception word. `override` is the brief's word, but `GLOSSARY.md` uses it for the
   owner's prompt. Recommendation: `exempt`, as in `<!-- exempt: <rule-id> reason: <text> -->`.
3. How a child reaches the parent in CI. Recommendation: a checkout of claude-settings at a pinned
   sha, as the ste-lint pin works. The alternative copies the rule ids. That breaks
   `building-allow-list-is-the-constant`.
4. The floor for removed text. Recommendation: 5 words. Measured: nine files at 5 words, none at
   8. A rule sentence removed later may give other counts. Unmeasured.
5. Debt `ste-into-agent-briefs`. Its copies are fixed by PR #1105, which is not read here. Should
   the debt close now? Or stay open for the move of the STE standard into agent briefs? Owner's
   word.
6. Paraphrase copies, where a child rewords a rule. Not caught. Recommendation: a note now. It
   becomes a debt only after a real incident.

## Sources

Checked on 2026-11-02 with WebFetch. The web search was thin. Items marked unverified come from
background knowledge.

- Vale substitution check, https://docs.vale.sh/checks/substitution. Verified: a `swap` map pairs
  an observed term with its expected form. A space in a key also matches a line break.
- ESLint `reportUnusedDisableDirectives`, the `linterOptions` setting, at
  https://eslint.org/docs/latest/use/configure/rules. Verified: it reports disable comments that
  disable rules that would not have reported. Default is `warn`. The CLI flag
  `--report-unused-disable-directives`: unverified.
- eslint-plugin-eslint-comments, https://github.com/eslint-community/eslint-plugin-eslint-comments.
  Verified: the README exists. The rule names `require-description` and `no-unused-disable` are
  not on the README, which points to a docs site. Those two names: unverified.
- openfasttrace, https://github.com/itsallcode/openfasttrace. Verified: it traces the work that
  implements each requirement, by item id. It does not check text coverage. It is a contrast
  case: id tracing, not text matching.
- adr-tools, https://github.com/npryce/adr-tools. Verified: `adr new -s <n>` marks record n as
  superseded and updates its status. The exact link format: unverified.
- gds-vale-styles, `types-of-rules.md`, https://github.com/alphagov/gds-vale-styles. The page
  returned 404. Unverified.
- jscpd, https://www.npmjs.com/package/jscpd. The page returned 403. Unverified: background
  knowledge says it is a copy-paste detector with a minimum token count.
- Renovate presets, tsconfig `extends`, Kustomize overlays and OPA bundles. Unverified. Not
  fetched.
