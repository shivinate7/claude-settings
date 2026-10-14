# An STE-lint exclude star can skip files in deeper folders

- **What.** After the git glob exclude, `run.sh` matches each file again with a bash pattern. There `*` crosses `/`, so `skills/*.md` also skips `skills/x/y.md`. Main does the same.
- **Where.** The `[[ "$f" == $pattern ]]` match in `actions/ste-lint/run.sh`.
- **Decision.** `opt-in-ci-templates-composite` (repos adopt the CI templates, such as ste-lint, by pin).
- **Retire.** The bash match is dropped, or uses a pattern where `*` stops at `/`. A case shows `skills/*.md` keeps `skills/x/y.md` in scope.
