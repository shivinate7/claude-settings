# Test: the bin files install.ps1 lands are the pin's own, and no shell script has a CR in it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-bin-eol.test.ps1
#
# The incident: ~/.claude/bin/rm was a CRLF byte copy (3,012 bytes, 79 CR) of an LF file. sh cannot
# run a script whose lines end in CR. A Windows checkout with core.autocrlf=true writes CRLF into
# every tracked text file that no .gitattributes line pins to LF.
#
# Check 1, bin-faithful: install.ps1 runs against a scratch clone on main (so it makes the pin,
# <clone>-live) and a scratch CLAUDE_CONFIG_DIR, once with copy mode forced and once with links
# allowed. Each entry it lands in <config>\bin is a link to the pin's bin file, or byte-equal to it.
# A control then rewrites one landed copy with CRLF and must see it fail.
#
# Check 2, lf-scripts: no tracked shell script holds a CR byte in its working copy. A tracked file is
# a shell script when its name ends .sh, or its #! line names sh, bash or zsh, directly or through
# env. The #! line is read after its CR is stripped, so a CRLF script is still found. Each fixture
# below must be classified right first: the scanner reads line 1 only, so a comment opener, a quote
# or a template literal in a later line must not make it see a #! line.
#
# Seam. REPO_UNDER_TEST is the repo root both checks read, for a red or green run against another
# checkout. It defaults to the folder of this file.
#   CLAUDE_CONFIG_DIR, CLAUDE_SETTINGS_USER_ENV_KEY, CLAUDE_SETTINGS_FORCE_COPY=1: as in
#   install-no-gap.test.ps1.
#
# Windows only. Elsewhere it prints SKIP and exits 0. Exits 1 on any FAIL.
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { Write-Host 'SKIP: install bin eol (Windows only)'; exit 0 }

$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo   = if ($env:REPO_UNDER_TEST) { $env:REPO_UNDER_TEST } else { $Here }
$GitExe = (Get-Command git -ErrorAction Stop).Source
$Utf8   = New-Object Text.UTF8Encoding($false)
. (Join-Path $Here 'testing\SharedRead.ps1')   # Read-Shared: a child's output reads back while a handle holds it
$Failed = 0
function Check([string]$name, [bool]$ok, [string]$why = '') {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: ${name}: $why"; $script:Failed++ }
}

$Tmp    = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-bineol-' + [guid]::NewGuid().ToString('N'))
$EnvSub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

# The number of CR bytes in a file.
function Get-CrCount([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $n = 0; $i = -1
    while (($i = [Array]::IndexOf($bytes, [byte]13, $i + 1)) -ge 0) { $n++ }
    return $n
}

# The first line of a file, up to 512 bytes, without its CR or LF.
function Get-FirstLine([string]$Path) {
    $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try { $buf = New-Object byte[] 512; $got = $fs.Read($buf, 0, 512) } finally { $fs.Close() }
    $end = [Array]::IndexOf($buf, [byte]10, 0, $got)
    if ($end -lt 0) { $end = $got }
    return ([Text.Encoding]::ASCII.GetString($buf, 0, $end)).TrimEnd("`r")
}

# The interpreter a #! line names, by file name: '/bin/sh' reads as sh, and '/usr/bin/env -S bash -e'
# as bash. '' when the line is no #! line.
function Get-Interpreter([string]$Line) {
    $l = $Line.TrimEnd("`r")
    if (-not $l.StartsWith('#!')) { return '' }
    $tok = @($l.Substring(2).Trim() -split '\s+' | Where-Object { $_ -ne '' })
    if ($tok.Count -eq 0) { return '' }
    $name = [IO.Path]::GetFileName($tok[0])
    if ($name -ceq 'env') {
        $rest = @($tok | Select-Object -Skip 1 | Where-Object { -not $_.StartsWith('-') -and $_ -notmatch '=' })
        $name = if ($rest.Count -gt 0) { [IO.Path]::GetFileName($rest[0]) } else { '' }
    }
    return $name
}

# The paths in $Rel (relative to $Root) that are shell scripts. A path the working copy lacks, such as
# a file deleted and not yet committed, has nothing to read and is skipped.
function Get-ShellScripts([string]$Root, [string[]]$Rel) {
    foreach ($r in $Rel) {
        $p = Join-Path $Root $r
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { continue }
        if ($r.EndsWith('.sh', [StringComparison]::Ordinal) -or (@('sh', 'bash', 'zsh') -ccontains (Get-Interpreter (Get-FirstLine $p)))) { $r }
    }
}

# Every tracked path of the repo at $Root, from git ls-files -z. A git failure throws: an unread list
# is never a clean one.
function Get-TrackedFiles([string]$Root) {
    $o = Join-Path $Tmp ('ls-' + [guid]::NewGuid().ToString('N'))
    $p = Start-Process -FilePath $GitExe -ArgumentList ('-C "' + $Root + '" ls-files -z') -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $o -RedirectStandardError "$o.err"
    if ($p.ExitCode -ne 0) { throw "git ls-files failed in ${Root}: $(Read-Shared "$o.err")" }
    return @($Utf8.GetString([IO.File]::ReadAllBytes($o)) -split "`0" | Where-Object { $_ -ne '' })
}

# One line per landed bin entry that is neither a link to the pin's file nor byte-equal to it.
function Get-BinProblems([string]$Cfg, [string]$Pin) {
    foreach ($e in @(Get-ChildItem -LiteralPath (Join-Path $Cfg 'bin') -Force)) {
        $pinFile = Join-Path $Pin ('bin\' + $e.Name)
        if (-not (Test-Path -LiteralPath $pinFile -PathType Leaf)) { "$($e.Name): the pin has no such bin file"; continue }
        if ($e.LinkType -eq 'SymbolicLink') {
            $t = @($e.Target)[0]
            if ($t -and ([IO.Path]::GetFullPath($t) -ieq [IO.Path]::GetFullPath($pinFile))) { continue }
        }
        if ($e.PSIsContainer) { "$($e.Name): a folder, not the pin's file"; continue }
        if ((Get-FileHash -LiteralPath $e.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $pinFile -Algorithm SHA256).Hash) {
            "$($e.Name): not a link to the pin's file and not byte-equal to it: it is $((Get-Item -LiteralPath $e.FullName).Length) bytes with $(Get-CrCount $e.FullName) CR, the pin's is $((Get-Item -LiteralPath $pinFile).Length) bytes with $(Get-CrCount $pinFile) CR"
        }
    }
}

# git in a scratch clone, quiet. git warns on stderr about CRLF, which must not throw.
function Invoke-Git([string]$Dir, [string[]]$GitArgs) {
    $ErrorActionPreference = 'Continue'
    & $GitExe -C $Dir -c user.name=test -c user.email=test@example.invalid -c commit.gpgsign=false @GitArgs 2>&1 | Out-Null
    return $LASTEXITCODE
}

# Runs install.ps1 from the clone in a child shell, then returns its exit code. A failed run prints its log.
function Invoke-Install([string]$Cfg, [bool]$ForceCopy, [string]$LogName) {
    $log = Join-Path $Tmp $LogName
    $env:CLAUDE_CONFIG_DIR = $Cfg
    if ($ForceCopy) { $env:CLAUDE_SETTINGS_FORCE_COPY = '1' } else { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    $p = Start-Process -FilePath 'powershell.exe' -Wait -PassThru -NoNewWindow `
        -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Clone 'install.ps1') + '"') `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"
    if ($p.ExitCode -ne 0) { Get-Content -LiteralPath $log, "$log.err" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  install log: $_" } }
    return $p.ExitCode
}

# ---- check 2 scanner fixtures: each must be classified right before the real scan counts -------
function Join-Lines([string[]]$Lines, [string]$Eol) { return (($Lines -join $Eol) + $Eol) }
$LF = "`n"; $CRLF = "`r`n"; $Tick = [string][char]96
$Fixtures = @(
    @{ Name = 'plain.sh';        Text = (Join-Lines @('echo hi') $LF);                                         Shell = $true;  Cr = $false },
    @{ Name = 'crlf.sh';         Text = (Join-Lines @('echo hi') $CRLF);                                       Shell = $true;  Cr = $true },
    @{ Name = 'shebang-lf';      Text = (Join-Lines @('#!/bin/sh', 'echo "don''t"') $LF);                     Shell = $true;  Cr = $false },
    @{ Name = 'shebang-crlf';    Text = (Join-Lines @('#!/bin/sh', 'echo hi') $CRLF);                          Shell = $true;  Cr = $true },
    @{ Name = 'env-bash';        Text = (Join-Lines @('#!/usr/bin/env bash', 'echo hi') $CRLF);                Shell = $true;  Cr = $true },
    @{ Name = 'env-S-zsh';       Text = (Join-Lines @('#!/usr/bin/env -S zsh -f', 'echo hi') $LF);             Shell = $true;  Cr = $false },
    @{ Name = 'spaced-bash';     Text = (Join-Lines @('#! /bin/bash -e', 'echo hi') $LF);                      Shell = $true;  Cr = $false },
    @{ Name = 'quotes-in-sh.sh'; Text = (Join-Lines @('# "/*" // ''', 'printf ''a\r\n''') $LF);                Shell = $true;  Cr = $false },
    @{ Name = 'py';              Text = (Join-Lines @('#!/usr/bin/env python3', 'print(1)') $CRLF);           Shell = $false; Cr = $true },
    @{ Name = 'node';            Text = (Join-Lines @('#!/usr/bin/env node') $CRLF);                           Shell = $false; Cr = $true },
    @{ Name = 'bashful';         Text = (Join-Lines @('#!/usr/bin/bashful') $CRLF);                            Shell = $false; Cr = $true },
    @{ Name = 'notes.sh.md';     Text = (Join-Lines @('echo hi') $CRLF);                                       Shell = $false; Cr = $true },
    @{ Name = 'opener.js';       Text = (Join-Lines @('const a = "#!/bin/sh"; // /* don''t', 'x') $CRLF);      Shell = $false; Cr = $true },
    @{ Name = 'template.mjs';    Text = (Join-Lines @(('const t = ' + $Tick), '#!/bin/sh', ($Tick + ';')) $CRLF); Shell = $false; Cr = $true },
    @{ Name = 'jsx.jsx';         Text = (Join-Lines @('<p>Don''t</p>') $CRLF);                                  Shell = $false; Cr = $true }
)
$Fx = Join-Path $Tmp 'fixtures'
New-Item -ItemType Directory -Force -Path $Fx | Out-Null
foreach ($f in $Fixtures) { [IO.File]::WriteAllBytes((Join-Path $Fx $f.Name), [Text.Encoding]::ASCII.GetBytes($f.Text)) }
$FxShell = @(Get-ShellScripts $Fx @($Fixtures | ForEach-Object { $_.Name }))
foreach ($f in $Fixtures) {
    $isShell = $FxShell -contains $f.Name
    $hasCr   = (Get-CrCount (Join-Path $Fx $f.Name)) -gt 0
    Check "scanner fixture $($f.Name): shell=$($f.Shell), CR=$($f.Cr)" ($isShell -eq $f.Shell -and $hasCr -eq $f.Cr) "read as shell=$isShell, CR=$hasCr"
}

# ---- check 2: the repo under test ---------------------------------------------------------------
$Tracked = @(Get-TrackedFiles $Repo)
$Shells  = @(Get-ShellScripts $Repo $Tracked)
Write-Host "info: $($Tracked.Count) tracked files, $($Shells.Count) shell scripts, in $Repo"
Check 'lf-scripts: the scan reads tracked files and finds shell scripts' ($Tracked.Count -gt 0 -and $Shells.Count -gt 0) 'it found none, so no CR check is made'
$CrScripts = @($Shells | ForEach-Object { $n = Get-CrCount (Join-Path $Repo $_); if ($n -gt 0) { "$_ ($n CR)" } })
foreach ($c in $CrScripts) { Write-Host "  CR in shell script: $c" }
Check "lf-scripts: no shell script has a CR ($($Shells.Count) scanned)" ($CrScripts.Count -eq 0) "$($CrScripts.Count) file(s): $($CrScripts -join ', ')"

# ---- check 1: install.ps1 lands the pin's bin files ---------------------------------------------
$Clone   = Join-Path $Tmp 'clone'
$Pin     = $Clone + '-live'
$CfgCopy = Join-Path $Tmp 'claude-copy'
$CfgLink = Join-Path $Tmp 'claude-link'
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $Clone 'bin'), $CfgCopy, $CfgLink | Out-Null
    Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $Clone 'install.ps1')
    [IO.File]::WriteAllText((Join-Path $Clone 'CLAUDE.md'), "# bin eol fixture`n", $Utf8)
    [IO.File]::WriteAllText((Join-Path $Clone 'settings.json'), "{}`n", $Utf8)
    [IO.File]::WriteAllText((Join-Path $Clone 'landed-dirs.txt'), "bin`n", $Utf8)
    foreach ($b in @(Get-ChildItem -LiteralPath (Join-Path $Repo 'bin') -File)) { Copy-Item -LiteralPath $b.FullName -Destination (Join-Path $Clone ('bin\' + $b.Name)) }
    # The repo's own attributes, so the pin's checkout converts line ends as the real pin's does.
    if (Test-Path -LiteralPath (Join-Path $Repo '.gitattributes')) { Copy-Item -LiteralPath (Join-Path $Repo '.gitattributes') -Destination (Join-Path $Clone '.gitattributes') }
    $gitOk = (Invoke-Git $Clone @('init', '-q', '-b', 'main')) -eq 0 -and (Invoke-Git $Clone @('add', '-A')) -eq 0 -and (Invoke-Git $Clone @('commit', '-q', '-m', 'fixture')) -eq 0
    Check 'bin-faithful: setup: the scratch clone is a git repo on main' $gitOk 'git init, add or commit failed'

    [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($EnvSub).Close()
    $env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$EnvSub"

    $rcCopy = Invoke-Install $CfgCopy $true 'run-copy.log'
    Check "bin-faithful: setup: the copy-mode run exits 0 (exit $rcCopy)" ($rcCopy -eq 0)
    $rcLink = Invoke-Install $CfgLink $false 'run-link.log'
    Check "bin-faithful: setup: the default run exits 0 (exit $rcLink)" ($rcLink -eq 0)
    Check 'bin-faithful: setup: the run made the pin' (Test-Path -LiteralPath (Join-Path $Pin 'bin') -PathType Container) "no $Pin\bin"

    $copied = @(Get-ChildItem -LiteralPath (Join-Path $CfgCopy 'bin') -Force -ErrorAction SilentlyContinue)
    $linked = @(Get-ChildItem -LiteralPath (Join-Path $CfgLink 'bin') -Force -ErrorAction SilentlyContinue)
    Write-Host "info: landed $($copied.Count) bin entries in copy mode, $($linked.Count) in the default mode ($(@($linked | Where-Object { $_.LinkType }).Count) of them links)"
    Check 'bin-faithful: setup: copy mode lands bin entries, and none is a link' ($copied.Count -gt 0 -and @($copied | Where-Object { $_.LinkType }).Count -eq 0) 'no entry landed, or a link was made with copy mode forced'
    Check 'bin-faithful: setup: the default mode lands bin entries' ($linked.Count -gt 0) 'no entry landed'

    $pCopy = @(Get-BinProblems $CfgCopy $Pin)
    Check 'bin-faithful: each bin copy is byte-equal to the pin file' ($pCopy.Count -eq 0) ($pCopy -join '; ')
    $pLink = @(Get-BinProblems $CfgLink $Pin)
    Check 'bin-faithful: each bin entry from the default run is a link to the pin file or byte-equal to it' ($pLink.Count -eq 0) ($pLink -join '; ')

    # Control: a landed copy with its line ends flipped (CR added, or removed where the pin's file has them)
    # must be seen. Without it a loop that reads nothing would pass.
    $victim = @($copied | Where-Object { -not $_.LinkType -and -not $_.PSIsContainer } | Select-Object -First 1)
    if ($victim.Count -eq 1) {
        $latin1 = [Text.Encoding]::GetEncoding(28591)
        $text = [IO.File]::ReadAllText($victim[0].FullName, $latin1)
        $flipped = if ($text.Contains("`r")) { $text -replace "`r", '' } else { $text -replace "`n", "`r`n" }
        [IO.File]::WriteAllText($victim[0].FullName, $flipped, $latin1)
        Check "bin-faithful: control: a copy of $($victim[0].Name) with its line ends flipped is seen" ($flipped -cne $text -and @(Get-BinProblems $CfgCopy $Pin).Count -ge 1) 'the loop passed a changed copy'
    } else {
        Check 'bin-faithful: control: a copy exists to change' $false 'copy mode landed no plain file'
    }
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
    try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host 'all cases passed'
exit 0
