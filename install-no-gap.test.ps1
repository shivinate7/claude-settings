# Test: a re-run of install.ps1 leaves no gap in the landed copies.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-no-gap.test.ps1
#
# The defect: with no symlink rights, install.ps1 deletes each landed copy and then copies it
# again. Between the two steps the file is absent. The gate hooks fail closed on a missing
# script, so every session is refused for as long as the gap lasts (incident 2026-10-13).
#
# The test runs install.ps1 twice against a scratch clone and a scratch CLAUDE_CONFIG_DIR, with
# copy mode forced. A FileSystemWatcher on the scratch CLAUDE dir records Deleted and Renamed
# events during run 2. It fails if any name the clone ships is deleted or renamed away. A name
# the clone no longer ships may be removed.
#
# Seams. install.ps1 must honour each one:
#   CLAUDE_CONFIG_DIR              target dir. Exists.
#   CLAUDE_SETTINGS_USER_ENV_KEY   throwaway registry key for the PATH write. Exists.
#   CLAUDE_SETTINGS_FORCE_COPY=1   every symlink attempt throws, so copy mode runs on any machine.
#                                  Not in install.ps1 yet. The builder adds it before each
#                                  New-Item -ItemType SymbolicLink (per file, skills, settings.json).
#
# The test also fails when copy mode was not forced: a shipped name is a symlink after run 1.
# Without that check, a run on a machine with symlink rights would pass and prove nothing.
#
# Windows only. Elsewhere it prints SKIP and exits 0. Exits 1 on any FAIL.
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { Write-Host 'SKIP: install no-gap (Windows only)'; exit 0 }

$Repo   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Failed = 0
function Check([string]$name, [bool]$ok) {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: $name"; $script:Failed++ }
}

# Records Deleted and Renamed events on one directory tree. Relative names only.
# A canary is a file the test creates and deletes; Arm sets its name, WaitCanary waits for it.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Threading;

public class NoGapRecorder : IDisposable
{
    private readonly string root;
    private readonly FileSystemWatcher watcher;
    private readonly object armLock = new object();
    private readonly ManualResetEvent canarySeen = new ManualResetEvent(false);
    private string canary = "";
    public readonly ConcurrentQueue<string> Gone = new ConcurrentQueue<string>();
    public readonly ConcurrentQueue<string> Errors = new ConcurrentQueue<string>();

    public NoGapRecorder(string dir)
    {
        root = dir.TrimEnd('\\');
        watcher = new FileSystemWatcher(dir);
        watcher.IncludeSubdirectories = true;
        watcher.InternalBufferSize = 65536;
        watcher.NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName;
        watcher.Deleted += OnDeleted;
        watcher.Renamed += OnRenamed;
        watcher.Error += OnError;
        watcher.EnableRaisingEvents = true;
    }

    private string Rel(string full)
    {
        if (full.Length > root.Length + 1
            && full.StartsWith(root, StringComparison.OrdinalIgnoreCase)
            && full[root.Length] == '\\')
            return full.Substring(root.Length + 1);
        return "OUTSIDE:" + full;
    }

    public void Arm(string name)
    {
        lock (armLock) { canary = name; canarySeen.Reset(); }
    }

    public bool WaitCanary(int ms)
    {
        return canarySeen.WaitOne(ms);
    }

    private void Seen(string rel)
    {
        lock (armLock)
        {
            if (string.Equals(rel, canary, StringComparison.OrdinalIgnoreCase)) canarySeen.Set();
        }
    }

    private void OnDeleted(object sender, FileSystemEventArgs e)
    {
        string rel = Rel(e.FullPath);
        Gone.Enqueue("D|" + rel);
        Seen(rel);
    }

    private void OnRenamed(object sender, RenamedEventArgs e)
    {
        Gone.Enqueue("R|" + Rel(e.OldFullPath) + "|" + Rel(e.FullPath));
    }

    private void OnError(object sender, ErrorEventArgs e)
    {
        Errors.Enqueue(e.GetException().Message);
    }

    public void Dispose()
    {
        watcher.EnableRaisingEvents = false;
        watcher.Dispose();
    }
}
'@

$Tmp    = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-nogap-' + [guid]::NewGuid().ToString('N'))
$Clone  = Join-Path $Tmp 'clone'
$Cfg    = Join-Path $Tmp 'claude'
$EnvSub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
$Utf8   = New-Object Text.UTF8Encoding($false)
$Rec    = $null

function Write-Fixture([string]$rel, [string]$text) {
    $p = Join-Path $Clone $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $p) | Out-Null
    [IO.File]::WriteAllText($p, $text, $Utf8)
}

# Runs the clone's install.ps1 in a child shell. Returns its exit code.
function Invoke-Install([string]$LogName) {
    $log     = Join-Path $Tmp $LogName
    $argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Clone 'install.ps1') + '"'
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $argLine -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $log -RedirectStandardError ($log + '.err')
    return $p.ExitCode
}

# Creates and deletes one canary file, then waits (bounded) for its Deleted event. Returns $true
# when the watcher delivered it. Events queued before it are then delivered too.
function Flush-Canary($Recorder, [string]$Name) {
    $Recorder.Arm($Name)
    $p = Join-Path $Cfg $Name
    [IO.File]::WriteAllText($p, '', $Utf8)
    Remove-Item -LiteralPath $p -Force
    return $Recorder.WaitCanary(15000)
}

# ---- fixture: a small clone with the landed dirs that matter, plus the real install.ps1 --------
$Landed = @('agents', 'lint', 'hooks', 'skills')
New-Item -ItemType Directory -Force -Path $Clone, $Cfg | Out-Null
Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $Clone 'install.ps1')
Write-Fixture 'CLAUDE.md' '# nogap fixture'
Write-Fixture 'settings.json' '{}'
Write-Fixture 'landed-dirs.txt' (($Landed -join "`n") + "`n")
Write-Fixture 'agents\builder.md' '# builder'
Write-Fixture 'lint\ste_gate.py' '# gate'
Write-Fixture 'lint\ste_lint.py' '# lint'
Write-Fixture 'hooks\guard.py' '# guard'
Write-Fixture 'hooks\guard_core.py' '# guard core'
Write-Fixture 'skills\sample\SKILL.md' '# sample'
Write-Fixture 'skills\sample\notes.md' '# notes'

# Shipped names, relative to the CLAUDE dir, listed from the fixture. Hashtable keys ignore case.
$Shipped = New-Object System.Collections.Generic.List[string]
$Shipped.Add('CLAUDE.md')
$Shipped.Add('settings.json')
foreach ($sub in $Landed) {
    $base = Join-Path $Clone $sub
    $Shipped.Add($sub)
    foreach ($item in @(Get-ChildItem -LiteralPath $base -Recurse -Force)) {
        $Shipped.Add($sub + $item.FullName.Substring($base.Length))
    }
}
$ShippedSet = @{}
foreach ($s in $Shipped) { $ShippedSet[$s] = $true }
Write-Host "info: $($Shipped.Count) shipped names in the fixture"

$env:CLAUDE_CONFIG_DIR          = $Cfg
$env:CLAUDE_SETTINGS_FORCE_COPY = '1'
[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($EnvSub).Close()
$env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$EnvSub"

try {
    # ---- run 1: land the copies -------------------------------------------------------------
    $rc1 = Invoke-Install 'run1.log'
    Check "setup: run 1 exits 0 (exit $rc1)" ($rc1 -eq 0)

    $Missing1 = @($Shipped | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Cfg $_)) })
    Check "setup: run 1 lands every shipped name" ($Missing1.Count -eq 0)
    foreach ($m in $Missing1) { Write-Host "  missing after run 1: $m" }

    # Copy mode must be real. A symlink here means the seam is not honoured by install.ps1.
    $Linked = @()
    foreach ($s in $Shipped) {
        $p = Join-Path $Cfg $s
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $attr = [int](Get-Item -LiteralPath $p -Force).Attributes
        if (($attr -band [int][IO.FileAttributes]::ReparsePoint) -ne 0) { $Linked += $s }
    }
    Check "copy mode forced: no shipped name is a symlink after run 1" ($Linked.Count -eq 0)
    foreach ($l in $Linked) { Write-Host "  symlink, seam not honoured: $l" }

    # ---- run 2: the re-run under watch -------------------------------------------------------
    $Rec = New-Object -TypeName NoGapRecorder -ArgumentList $Cfg
    $pre = Flush-Canary $Rec '__nogap_canary_pre.tmp'
    Check "watcher live before run 2 (canary delivered)" $pre

    $rc2 = Invoke-Install 'run2.log'
    Check "setup: run 2 exits 0 (exit $rc2)" ($rc2 -eq 0)

    $post = Flush-Canary $Rec '__nogap_canary_post.tmp'
    Check "watcher delivered run 2 events (post canary)" $post
    $Errs = @($Rec.Errors.ToArray())
    Check "watcher raised no error (an overflow would make the result unknown)" ($Errs.Count -eq 0)
    foreach ($e in $Errs) { Write-Host "  watcher error: $e" }

    $Gone = @($Rec.Gone.ToArray())
    $Hits = @()
    foreach ($ev in $Gone) {
        $f = $ev.Split('|')
        $name = $f[1]
        $kind = if ($f[0] -eq 'D') { 'deleted' } else { 'renamed away' }
        if ($ShippedSet.ContainsKey($name)) { $Hits += "$kind $name" }
    }
    foreach ($h in $Hits) { Write-Host "  gap: $h during run 2" }
    Write-Host "info: $($Gone.Count) Deleted or Renamed events during run 2"
    Check "run 2 deletes or renames no shipped name ($($Hits.Count) gap events)" ($Hits.Count -eq 0)

    $Missing2 = @($Shipped | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Cfg $_)) })
    Check "all shipped names present after run 2" ($Missing2.Count -eq 0)
    foreach ($m in $Missing2) { Write-Host "  missing after run 2: $m" }
} finally {
    if ($Rec) { $Rec.Dispose() }
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
    try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
