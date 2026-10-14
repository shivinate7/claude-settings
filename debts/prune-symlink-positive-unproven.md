# The symlink-capable branch of the prune cases is unproven

- **What.** No Windows machine here can grant `SeCreateSymbolicLinkPrivilege` to this account. The probe and the early-return guard are proven only on the negative branch, where the privilege is absent. The positive branch needs a runner with the privilege.
- **Where.** The symlink probe in `hooks/test_install_src.sh`, and the prune1, prune3 and prune5 cases.
- **Decision.** `prune-cases-skip-without-symlink-privilege` (prune cases skip when this account cannot make a real symlink).
- **Retire.** A reviewer with Developer Mode, or a Linux or macOS runner, runs the positive branch, and prune1, prune3 and prune5 pass there.
