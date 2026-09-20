# A check that cries wolf

A check that fails for a reason nobody must act on is worse than no check. It
trains the reader past the alarm. The next failure, the real one, reads as more
noise. CLAUDE.md already says "Never merge failing CI". A check that is always
red makes that rule unenforceable.

## The evidence

`~/Developer/mailaudit` commits its built page, and a check asks whether that page
is still the code in the repo. The first version compared the two pages whole. The
page carries the code and a snapshot of data that legitimately moves between
builds. Its own CLAUDE.md records the result:

```text
Diffing whole pages therefore fails one of
two ways, and CI managed the first - **always**, because `actions/checkout` is
single-branch, so the runner has no `origin/data`, builds seedless, and every
comparison differs (main was red for four runs on exactly this, while
`npm test` itself passed); or **at random**, if you fetch the branch and race
the phone. A check that cries wolf is worse than no check, because it trains
you past the alarm.
```

The fix was not a louder alarm or a retry. The fix was to narrow the claim. The
check now compares the code and ignores the data. The narrowing lives beside the
template that writes the data, so the two cannot drift apart.

## The test to apply

Before a check lands, name the act it must catch. Then name every reason it can
go red without that act. When the second list is not empty, the check is not
ready.
Narrow it, or move it to where the noise does not exist.

A check that is red for a known reason is already failed. Do not annotate it. Do
not let the team learn to skip it. Fix the claim or delete the check.

## The other direction

A check can also be quiet for the wrong reason. A guard that never runs opens no
issue. That looks exactly like a guard that ran and found nothing wrong. The
same repo hosts its backup alarm in a private repo for that reason. GitHub
stops a scheduled workflow in a public repo after 60 days of quiet. Both
failures are the same failure. The signal stopped meaning what the reader thinks
it means.
