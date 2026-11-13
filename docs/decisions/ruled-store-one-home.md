# An owner ruling not yet on main lives in one store, read by one module

## The ruling

The owner's rulings that main has not taken in sit in one store: `roadmap/rulings/<slug>.json` on `origin/roadmap`, one file per ruling. An entry holds `id`, `at`, `ruling`, `source`, `status`, `supersedes` or `supersedes_none`, and optionally `quote` (the owner's words), `step` (the roadmap step that lands the ruling) and `lands_in`. `lint/ruled_store.py` is the only reader. The session-start hook (`hooks/session_start.sh`) prints the open entries once. The question judge's past-ruling search (`past_rulings` in `hooks/question_form.py`) lists first, as `ruled:<id>`, the open entries that share a word with the question. It lists the most shared words first, the newest first among equal counts, and at most eight. An entry closes when its `status` is `closed`, or when the text in its `lands_in` is found on `origin/main` at the path it names. Triage writes the entries. The restart plan cites an entry by id and does not copy the ruling.

The switch `ENTRIES_LIFT_GUARDS` in `lint/ruled_store.py` is True, by owner ruling R59 (the entry `roadmap/rulings/r59.json` on branch `roadmap`; owner, 15:05 CST Nov 12, item 646: "ruling governs the guard right away"; home decision `owner-override`). An open entry whose `supersedes` names a guard rule governs that rule, unless `check_entry` flags the entry. The rule id is the first token of the ref, in kebab-case. `ruling_for_guard` returns the newest such entry. `guard_ruling_line` words the line a guard prints when it lets the ruled act through. No guard calls the lookup yet. A follow-up step wires it into the shared guard core. Set False, the lookup returns nothing and an entry is text only.

An open entry whose `step` is done is a stale entry. With a `steps` list, it is stale when every listed step is done. `ruled_store.py check` flags it, so an entry left open after main took it in does not govern for long. It also flags two open entries that supersede one ref of one kind, a store file that is not valid JSON, and a guard-rule ref with no rule id. Nothing runs `check` yet. Triage runs it at each roadmap build, and a follow-up step wires it.

An entry whose `supersedes_none` starts with "unread" is unchecked: triage has not read what it supersedes. The past-ruling search marks it "(unchecked, not law)". It never governs a guard, even when it lists a guard ref. Neither does an entry whose `status` is not `open`.

Protected by `lint/test_ruled_store.py` (the reader, the close rule, the switch, the guard lookup and its line, the session lines, two git starts for one read), `hooks/test_session_start.py` (the hook prints the block, and prints nothing when no entry is open) and `hooks/test_question_form.py` (the entry is the first candidate, a closed one is none, an unrelated one is left out, no more than eight are listed, an absent store is only an unknown source). `python3 lint/ruled_store.py check REPO` exits 1 on an entry that lacks `id`, `at`, `ruling` or `source`. It also exits 1 on an `at` with no zone, a `status` outside `open` and `closed`, or an entry with neither `supersedes` nor `supersedes_none`. It also exits 1 on the flags above. `lint/test_ruled_store.py` runs each.

Cost: the hook starts one python and up to three read-only git processes per session start. It has no file or timer of its own. A stale `origin/roadmap` (last fetch older than 60 seconds) adds one `git fetch` of at most 2 seconds through `lint/roadmap_ref.py` (pinned by `lint/test_roadmap_ref.py`). When it fails, the session block's header ends "read as of HH:MM TZ", or "read as of an unknown time" when no fetch time is known (a timed-out fetch with no roadmap fetch on record). It ends "read as of unknown: <why>" when the freshness check itself cannot run.

Freshness (step roadmap-ref-fresh-before-verdict): fresh means FETCH_HEAD holds a roadmap fetch line within 60 seconds. A fetch of main alone does not count. The past-ruling check of `hooks/sendmessage_state.py` fetches a stale ref through the same helper. So do the Opus step grant of `hooks/override.py` and the step notes of `hooks/question_form.py`. Each says "read as of" on stderr or in the guard log when it cannot.

This record is dated by one fact: the store lives on `origin/roadmap`. If the entries move to main, rewrite the record.

Kind: build
Plan: docs/decisions/ruled-store-one-home.md#the-ruling (all)
Home: lint/ruled_store.py
