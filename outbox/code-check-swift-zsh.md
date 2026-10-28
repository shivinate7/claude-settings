# code-check-swift-zsh

Status: green and reviewed. Draft PR #769 (code-check Swift and zsh rows) is at head 75059947.
- Swift row and zsh row: every layer skips, with a reason. .entitlements is in not_code. zsh never reaches ShellCheck.
- Test red on main (4 "no row" problems), green on the branch. Gates PASS. Silent-undo PASS.
- Review: 1 round (reviewer opus), APPROVE. Builder opus.
- Notes that do not block: .zshrc-style dotfiles and extensionless swift scripts still fail with "no row".
