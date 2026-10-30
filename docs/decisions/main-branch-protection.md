# main branch protection

## The ruling

`main` of shivinate7/claude-settings requires the checks that its branch protection lists. The list lives in
the protection and nowhere else: `.github/stamp.json` `merge.requiredChecks` is `"protection"`, so the `merge` tool reads
the names from the protection. GitHub's branch protection setting is the owner's to change.

- A merge needs a pull request and no approval.
- `strict` is false: GitHub merges a PR that lacks main's newest commit. The `merge` tool refuses it (`merge-needs-current-base`, a merge needs a green run on the current base).
- Admins are included (`enforce_admins`), so the rule binds the owner.
- Force pushes and branch deletion are blocked. The repo has no rulesets.
- The protection holds the one list of contexts. Change it when a job is renamed or added. A repo that pins a list in
  `stamp.json` instead has `merge` refuse the run when the pinned list and a non-empty protection disagree, and name both
  sets (c189).
- The PUT is `gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input <json>`.
  A PUT replaces the whole rule, so the input carries every field. It needs the owner's login:
  `ssemwal-cdc` has push, not admin.
- Before every merge, read the checks yourself and refuse on red. The `merge` tool reads its checks
  from the branch protection.
- Owner ruling, 2026-10-28 (waiting-page item 33 a): a rename of required checks switches branch
  protection in the merge act. The owner switches it, then the batch merges at once.

Reason: agent rules alone did not stop red merges.

Temporary grant (owner, 2026-10-30 15:37 CDT): "changing a repo's protection is generally mine to do, but i can and am granting you protection changes as a temporary grant (i will say when it's withdrawn untilthen you can treat it on)". The ruling above is the default, and it holds without the grant. While the grant holds, the coordinator, and the batch runner it names, may make a branch-protection write in any of the owner's repos at merge time. The write must match the gold form: one required check, `all-jobs-passed`; `strict` false; `enforce_admins` true. The grant holds until the owner withdraws it in chat. Then delete this paragraph.

Kind: process
Home: .github/stamp.json
