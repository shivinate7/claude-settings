# The plain-diff secret name list misses some file names

- **What.** Some secret file names are not caught by name. `terraform.tfstate`, `.kube/config`, `wp-config.php` and `AuthKey_*.p8` are examples. The `.p8` file is caught only when the diff shows its BEGIN line. The name list holds the names known so far.
- **Where.** The path deny-list in `mods/plain-diff/hooks/lib.mjs` (`isSecretPath`).
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** The four example names are caught by name, and a case per name passes in `mods/plain-diff/plain-diff.test.mjs`.
