# The mirror refresh warns of local commits only when main holds one

## The ruling

Question: when does the mirror refresh warn "local commits on main"?

- It warns only when main holds a commit the fetched ref lacks. Only then does it keep the clone.
- It tests that with `merge-base --is-ancestor`, against a fetch that keeps history from a day before main's tip (`--shallow-since`). It runs this only when main differs from the recorded sha.
- An undecided result from that check, any exit other than 0 or 1, warns unknown and keeps the clone.
- A failed fetch while main differs from the recorded sha also warns unknown and keeps the clone.

## Harm stopped

A stale recorded sha made the refresh warn and keep the mirror behind, though main held nothing the ref lacked. The record goes stale when its write fails after main moved.

## Cost

- At most two extra local git reads, `git log -1` and `git merge-base`. Both run only when main differs from the recorded sha.
- The fetch count stays at one.
- No file written. No timer. The reads run inside the install step already running.
- Tests `caseM11` to `caseM13` pin the verdicts. No test pins the read count.

Kind: process
Home: install.sh
