# Starts the outside advisor: its own config folder (no claude-settings rules), sharing only the
# list of running sessions with ~\.claude so working sessions and the advisor can message each other.
$cfg = "$HOME\.claude-advisor"
$link = "$cfg\sessions"
New-Item -ItemType Directory -Force -Path $cfg | Out-Null
$item = Get-Item $link -ErrorAction SilentlyContinue
if (-not $item -or $item.LinkType -ne 'Junction') {
    if ($item) { Remove-Item $link -Recurse -Force }
    New-Item -ItemType Junction -Path $link -Target "$HOME\.claude\sessions" | Out-Null
}
$env:CLAUDE_CONFIG_DIR = $cfg
Set-Location C:\advisor
claude --dangerously-skip-permissions
