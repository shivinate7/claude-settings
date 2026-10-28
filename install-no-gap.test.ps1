# Test: a re-run of install.ps1 leaves no gap in the landed copies.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-no-gap.test.ps1
#
# The defect: with no symlink rights, install.ps1 deletes each landed copy and then copies it
# again. Between the two steps the file is absent. The gate hooks fail closed on a missing
# script, so every session is refused for as long as the gap lasts.
#
# The main case runs install.ps1 once, then re-runs it 20 times against a scratch clone and a
# scratch CLAUDE_CONFIG_DIR, with copy mode forced. Each re-run changes both hook files to the other
# of two large versions. A reader loop, in this process, opens and reads guard.py and guard_core.py
# in a tight loop for the whole series. It fails on a missing shipped name, an unreadable file, or a
# read that is not one whole version. A read pair whose INSTALL_ID values differ is a mixed-id
# window, which the guard waits through: each must clear within 5 s, and none may be open at the
# end. No case counts watcher events: a rename over a name emits a Deleted event, so a count of
# them fails a correct atomic replace. The fixture skill has nested dirs, and a nested file the
# source drops must be pruned.
#
# Three more cases, each in its own scratch tree. symrun and linkfail need symlink rights. On a
# runner without them they print SKIP with the reason and do not count; with CI set, a SKIP of
# either is a FAIL, since a CI runner has the rights:
#   symrun    a real file from an earlier copy, then a run where links can be made: the same reader
#             loop sees no fault and sees the mixed-id window between the two swaps, and
#             hooks\guard.py is a link at the end.
#   linkfail  dest is a symlink to elsewhere and the copy fails: a file must still exist at dest.
#   lock1     first local run, skill locked: a .bak or no copy marker after run 1, and no person
#             file lost after run 2. Needs no symlink rights; copy mode is forced.
#
# One more, read1: the text a run printed reads back while another handle still holds the file open
# for write, and a missing file still throws.
#
# One more, hooks-whole, at the end of the file: no live hook file is rewritten in place. A rewrite
# in place keeps a file's identity, so each changed hook file must get a new one, through install.ps1
# run 2 and through the post-merge hook it writes. The hook route needs git and a Git Bash sh, and
# FAILs without them.
#
# Seams. install.ps1 must honour each one:
#   CLAUDE_CONFIG_DIR              target dir.
#   CLAUDE_SETTINGS_USER_ENV_KEY   throwaway registry key for the PATH write.
#   CLAUDE_SETTINGS_FORCE_COPY=1   every symlink attempt throws (New-Link), so copy mode runs on any machine.
#
# The main case also fails when copy mode was not forced: a shipped name is a symlink after run 1.
# Without that check, a run on a machine with symlink rights would pass and prove nothing.
#
# Windows only. Elsewhere it prints SKIP and exits 0. Exits 1 on any FAIL.
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { Write-Host 'SKIP: install no-gap (Windows only)'; exit 0 }

$Repo   = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Repo 'testing\SharedRead.ps1')   # Read-Shared: a child's output reads back while a handle holds it
$Failed = 0
function Check([string]$name, [bool]$ok) {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: $name"; $script:Failed++ }
}

# Reads each hook file in a tight loop on its own thread. Every read is opened with read, write and
# delete sharing, so the installer's writes and renames are never refused by the reader. A pass
# reads each path in order, checks each Present path exists, then compares the two stamps. The pass
# that begins after Stop runs too, so the state the installs left is always seen.
#
# A stamp is the INSTALL_ID line at the top of a hook file: a commented placeholder reads as
# "(placeholder)", an uncommented line as its quoted id, and no line as "(none)". A read is whole
# when its text, without that line, equals one version's text without its line. Faults, by kind:
#   missing <name>        the file, or a path listed in Present, is not there.
#   unreadable <name>     the open or read failed: a sharing violation, or access denied on a file
#                         that is being deleted. Any other throw is counted here too, with its type,
#                         so the reader thread never dies and ends the test process silently.
#   short read <name>     the read is not one whole version.
# Mixed-id windows, on the pair of hook files: a window opens at the first pass where both reads
# are whole and their stamps differ, and closes at the first pass where they match. Its length is
# the time between those two passes. A window is not a fault. A window that is longer than the
# guard's wait, or still open when the re-runs end, is.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

public class HookReader
{
    public string[] Paths = new string[0];
    public string[] Versions1 = new string[0];
    public string[] Versions2 = new string[0];
    public string[] Present = new string[0];
    private string[] body1 = new string[0];
    private string[] body2 = new string[0];
    private readonly ConcurrentDictionary<string, long> faults = new ConcurrentDictionary<string, long>();
    private static readonly Regex QuotedRe = new Regex("INSTALL_ID = \"([^\"]*)\"");
    private long passes;
    private volatile bool stop;
    private Thread worker;
    private int windows;
    private double maxWindow;
    private volatile bool windowOpen;
    private long windowStart;

    public long Passes { get { return Interlocked.Read(ref passes); } }
    public int Windows { get { return windows; } }
    public double MaxWindowSeconds { get { return maxWindow; } }
    public bool WindowOpen { get { return windowOpen; } }

    public void Start()
    {
        body1 = new string[Versions1.Length];
        body2 = new string[Versions2.Length];
        for (int i = 0; i < Versions1.Length; i++) body1[i] = StripStamp(Versions1[i]);
        for (int i = 0; i < Versions2.Length; i++) body2[i] = StripStamp(Versions2[i]);
        worker = new Thread(Loop);
        worker.IsBackground = true;
        worker.Start();
    }

    public void Stop()
    {
        stop = true;
        if (worker != null) { worker.Join(); worker = null; }
    }

    public long Count(string prefix)
    {
        long total = 0;
        foreach (var kv in faults) if (kv.Key.StartsWith(prefix, StringComparison.Ordinal)) total += kv.Value;
        return total;
    }

    public long Total()
    {
        long total = 0;
        foreach (var kv in faults) total += kv.Value;
        return total;
    }

    public string[] Report()
    {
        var lines = new System.Collections.Generic.List<string>();
        foreach (var kv in faults) lines.Add(kv.Key + " x" + kv.Value);
        return lines.ToArray();
    }

    private void Fault(string kind)
    {
        faults.AddOrUpdate(kind, 1L, (k, v) => v + 1);
    }

    private static string ReadAll(string path)
    {
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (MemoryStream ms = new MemoryStream())
        {
            fs.CopyTo(ms);
            return Encoding.UTF8.GetString(ms.ToArray());
        }
    }

    private static bool HasStampLine(string text)
    {
        return text.StartsWith("# INSTALL_ID", StringComparison.Ordinal) || text.StartsWith("INSTALL_ID", StringComparison.Ordinal);
    }

    private static string StripStamp(string text)
    {
        if (!HasStampLine(text)) return text;
        int nl = text.IndexOf('\n');
        return nl < 0 ? "" : text.Substring(nl + 1);
    }

    private static string StampOf(string text)
    {
        if (text.StartsWith("# INSTALL_ID", StringComparison.Ordinal)) return "(placeholder)";
        if (text.StartsWith("INSTALL_ID", StringComparison.Ordinal))
        {
            Match m = QuotedRe.Match(text);
            return m.Success ? m.Groups[1].Value : "(malformed)";
        }
        return "(none)";
    }

    private void CloseWindow(long now)
    {
        double seconds = (double)(now - windowStart) / Stopwatch.Frequency;
        windows++;
        if (seconds > maxWindow) maxWindow = seconds;
        windowOpen = false;
    }

    private void Loop()
    {
        string[] got = new string[Paths.Length];
        bool[] whole = new bool[Paths.Length];
        string[] stamp = new string[Paths.Length];
        while (true)
        {
            bool last = stop;
            for (int i = 0; i < Paths.Length; i++)
            {
                string name = Path.GetFileName(Paths[i]);
                got[i] = null;
                whole[i] = false;
                try { got[i] = ReadAll(Paths[i]); }
                catch (FileNotFoundException) { Fault("missing " + name); continue; }
                catch (DirectoryNotFoundException) { Fault("missing " + name); continue; }
                catch (IOException) { Fault("unreadable " + name); continue; }
                catch (Exception e) { Fault("unreadable " + name + " " + e.GetType().Name); continue; }
                string body = StripStamp(got[i]);
                whole[i] = body == body1[i] || body == body2[i];
                if (whole[i]) stamp[i] = StampOf(got[i]);
                else Fault("short read " + name);
            }
            for (int j = 0; j < Present.Length; j++)
            {
                if (!File.Exists(Present[j]) && !Directory.Exists(Present[j]))
                    Fault("missing " + Path.GetFileName(Present[j]));
            }
            if (whole[0] && whole[1])
            {
                long now = Stopwatch.GetTimestamp();
                bool mixed = stamp[0] != stamp[1];
                if (mixed && !windowOpen) { windowOpen = true; windowStart = now; }
                else if (!mixed && windowOpen) CloseWindow(now);
            }
            Interlocked.Increment(ref passes);
            if (last) break;
        }
    }
}
'@

$Tmp    = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-nogap-' + [guid]::NewGuid().ToString('N'))
$Clone  = Join-Path $Tmp 'clone'
$Cfg    = Join-Path $Tmp 'claude'
$EnvSub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
$Utf8   = New-Object Text.UTF8Encoding($false)
$Landed = @('agents', 'lint', 'hooks', 'skills')

# Writes one fixture file. $path is absolute.
function Write-FixtureFile([string]$path, [string]$text) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [IO.File]::WriteAllText($path, $text, $Utf8)
}

# Writes one fixture file under the main clone.
function Write-Fixture([string]$rel, [string]$text) {
    Write-FixtureFile (Join-Path $Clone $rel) $text
}

# The text a child run printed to a redirected file. A missing or unreadable file throws.
function Get-RunText([string]$Path) {
    return Read-Shared $Path
}

# Runs install.ps1 from the clone $CloneDir in a child shell. Returns its exit code.
function Invoke-Install([string]$CloneDir, [string]$LogName) {
    $log     = Join-Path $Tmp $LogName
    $argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $CloneDir 'install.ps1') + '"'
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $argLine -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $log -RedirectStandardError ($log + '.err')
    return $p.ExitCode
}

# Names the clone ships, relative to the CLAUDE dir: CLAUDE.md, settings.json, and every entry
# under each landed dir, nested ones too.
function Get-ShippedNames([string]$CloneDir, [string[]]$Dirs) {
    $names = @('CLAUDE.md', 'settings.json')
    foreach ($sub in $Dirs) {
        $base = Join-Path $CloneDir $sub
        $names += $sub
        foreach ($item in @(Get-ChildItem -LiteralPath $base -Recurse -Force)) {
            $names += $sub + $item.FullName.Substring($base.Length)
        }
    }
    return $names
}

# True when $Path is a symlink or junction. A missing path is not a link.
function Test-ReparsePoint([string]$Path) {
    $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $i) { return $false }
    return (([int]$i.Attributes) -band [int][IO.FileAttributes]::ReparsePoint) -ne 0
}

# Empty when this runner can make symlinks, else the reason it cannot.
function Get-SymlinkBlocker {
    $probe = Join-Path ([IO.Path]::GetTempPath()) ('nogap-symprobe-' + [guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType SymbolicLink -Path $probe -Target (Join-Path $Repo 'install.ps1') -ErrorAction Stop | Out-Null
        Remove-Item -LiteralPath $probe -Force
        return ''
    } catch {
        return $_.Exception.Message
    }
}

# A scratch clone and CLAUDE dir for one extra case, under $Tmp. It ships CLAUDE.md, settings.json
# and the given landed dirs. The caller adds the rest with Write-FixtureFile.
function New-Scratch([string]$Name, [string[]]$Dirs) {
    $root = Join-Path $Tmp $Name
    $s = @{ Root = $root; Clone = (Join-Path $root 'clone'); Cfg = (Join-Path $root 'claude') }
    New-Item -ItemType Directory -Force -Path $s.Clone, $s.Cfg | Out-Null
    Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $s.Clone 'install.ps1')
    Write-FixtureFile (Join-Path $s.Clone 'CLAUDE.md') '# scratch fixture'
    Write-FixtureFile (Join-Path $s.Clone 'settings.json') '{}'
    Write-FixtureFile (Join-Path $s.Clone 'landed-dirs.txt') (($Dirs -join "`n") + "`n")
    return $s
}

# ---- fixture: a small clone with the landed dirs that matter, plus the real install.ps1 --------
New-Item -ItemType Directory -Force -Path $Clone, $Cfg | Out-Null
Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $Clone 'install.ps1')
Write-Fixture 'CLAUDE.md' '# nogap fixture'
Write-Fixture 'settings.json' '{}'
Write-Fixture 'landed-dirs.txt' (($Landed -join "`n") + "`n")
Write-Fixture 'agents\builder.md' '# builder'
Write-Fixture 'lint\ste_lint.py' '# lint'
# The hook files in two versions, A and B. Each file is the repo's commented INSTALL_ID placeholder,
# a label line, then padding, so a version is large: a copy of it takes long enough for the reader
# to land inside it. The installer swaps the placeholder for its run id at copy time, as it does for
# the repo's own hook files. The reader compares a read without that line. $Pad is the number of
# padding lines; a case that needs no long copy passes a small one.
$HookPadLines = 40000
$HookPlaceholder = '# INSTALL_ID = "uninstalled"'
function New-HookText([string]$File, [string]$Label, [int]$Pad = $HookPadLines) {
    $head = $HookPlaceholder + "`n" + '# ' + $File + ' ' + $Label + "`n"
    return $head + (('# padding, so a copy of this file takes a while to write' + "`n") * $Pad)
}
# The text without its INSTALL_ID line, placeholder or stamped: what a landed copy must match.
function Remove-StampLine([string]$Text) { return ($Text -replace '^(# )?INSTALL_ID = [^\r\n]*\r?\n', '') }
$HookA = @((New-HookText 'guard.py' 'version A'), (New-HookText 'guard_core.py' 'version A'))
$HookB = @((New-HookText 'guard.py' 'version B'), (New-HookText 'guard_core.py' 'version B'))
Write-Fixture 'hooks\guard.py' $HookA[0]
Write-Fixture 'hooks\guard_core.py' $HookA[1]
Write-Fixture 'skills\sample\SKILL.md' '# sample'
Write-Fixture 'skills\sample\notes.md' '# notes'
# Nested dirs, as real skills have (skills/impeccable/reference/, scripts/data/). The source drops
# scripts\data\old.json between run 1 and run 2, so run 2 must prune it from the landed copy.
Write-Fixture 'skills\sample\reference\guide.md' '# guide'
Write-Fixture 'skills\sample\scripts\data\table.json' '{"rows":1}'
Write-Fixture 'skills\sample\scripts\data\old.json' '{"dropped":true}'
$DroppedRel = 'skills\sample\scripts\data\old.json'

$Shipped = @(Get-ShippedNames $Clone $Landed)
Write-Host "info: $($Shipped.Count) shipped names in the fixture"

$env:CLAUDE_CONFIG_DIR = $Cfg
[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($EnvSub).Close()
$env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$EnvSub"

try {
    # ---- run 1: land the copies (copy mode forced) ---------------------------------------------
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    $rc1 = Invoke-Install $Clone 'run1.log'
    Check "setup: run 1 exits 0 (exit $rc1)" ($rc1 -eq 0)

    $Missing1 = @($Shipped | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Cfg $_)) })
    Check "setup: run 1 lands every shipped name" ($Missing1.Count -eq 0)
    foreach ($m in $Missing1) { Write-Host "  missing after run 1: $m" }
    Check "setup: run 1 lands the nested file the source drops later" (Test-Path -LiteralPath (Join-Path $Cfg $DroppedRel))

    # Copy mode must be real. A symlink here means the seam is not honoured by install.ps1.
    $Linked = @()
    foreach ($item in $Shipped) {
        $p = Join-Path $Cfg $item
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $attr = [int](Get-Item -LiteralPath $p -Force).Attributes
        if (($attr -band [int][IO.FileAttributes]::ReparsePoint) -ne 0) { $Linked += $item }
    }
    Check "copy mode forced: no shipped name is a symlink after run 1" ($Linked.Count -eq 0)
    foreach ($l in $Linked) { Write-Host "  symlink, seam not honoured: $l" }

    # The source drops one nested file between the runs. Its name leaves the shipped set, so its
    # removal is not a gap. Run 2 must still prune it from the landed copy.
    Remove-Item -LiteralPath (Join-Path $Clone $DroppedRel) -Force
    $Shipped     = @(Get-ShippedNames $Clone $Landed)
    $NestedNames = @($Shipped | Where-Object { ($_ -split '\\').Count -ge 4 })
    Check "fixture: nested names are in the shipped set ($($NestedNames.Count))" ($NestedNames.Count -ge 3)

    # ---- run 2 to run 21: the re-runs under the reader -----------------------------------------
    # Each round writes the other version into the clone, then re-runs install.ps1. The reader runs
    # from before the first round to after the last. Its passes are counted per round, so a round
    # the reader did not run in shows up.
    $InstallRounds = 20
    $Reader = New-Object -TypeName HookReader
    $Reader.Paths = [string[]]@((Join-Path $Cfg 'hooks\guard.py'), (Join-Path $Cfg 'hooks\guard_core.py'))
    $Reader.Versions1 = [string[]]$HookA
    $Reader.Versions2 = [string[]]$HookB
    # Shipped names checked for existence on every pass.
    $Reader.Present = [string[]]@((Join-Path $Cfg 'CLAUDE.md'), (Join-Path $Cfg 'settings.json'), (Join-Path $Cfg 'agents'), (Join-Path $Cfg 'lint'), (Join-Path $Cfg 'skills'))
    $RoundPasses = @()
    $RoundFaults = @()
    $RoundsExit0 = 0
    $RoundsLanded = 0
    $Reader.Start()
    try {
        for ($round = 1; $round -le $InstallRounds; $round++) {
            $Want = if ($round % 2 -eq 1) { $HookB } else { $HookA }
            Write-Fixture 'hooks\guard.py' $Want[0]
            Write-Fixture 'hooks\guard_core.py' $Want[1]
            $passesBefore = $Reader.Passes
            $faultsBefore = $Reader.Total()
            $rcR = Invoke-Install $Clone ("run2-round$round.log")
            $RoundPasses += ($Reader.Passes - $passesBefore)
            $RoundFaults += ($Reader.Total() - $faultsBefore)
            if ($rcR -eq 0) { $RoundsExit0++ }
            $landed = ((Remove-StampLine ([IO.File]::ReadAllText((Join-Path $Cfg 'hooks\guard.py')))) -eq (Remove-StampLine $Want[0])) -and ((Remove-StampLine ([IO.File]::ReadAllText((Join-Path $Cfg 'hooks\guard_core.py')))) -eq (Remove-StampLine $Want[1]))
            if ($landed) { $RoundsLanded++ }
        }
    } finally {
        $Reader.Stop()
    }
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue

    $RedRounds = @($RoundFaults | Where-Object { $_ -gt 0 }).Count
    Write-Host "info: $RedRounds of $InstallRounds re-runs had a reader fault; $($Reader.Passes) reader passes in all"
    foreach ($line in $Reader.Report()) { Write-Host "  reader fault: $line" }
    $NoPass = @($RoundPasses | Where-Object { $_ -lt 1 }).Count
    Check "reader ran during every re-run ($NoPass of $InstallRounds re-runs had no reader pass, want 0)" ($NoPass -eq 0)
    Check "all $InstallRounds re-runs exit 0 ($RoundsExit0 of $InstallRounds)" ($RoundsExit0 -eq $InstallRounds)
    Check "every re-run lands its new text in both hook files ($RoundsLanded of $InstallRounds, non-vacuous)" ($RoundsLanded -eq $InstallRounds)
    Check "no shipped name is missing during the re-runs: the hook files, CLAUDE.md, settings.json, agents, lint, skills ($($Reader.Count('missing ')) faults)" ($Reader.Count('missing ') -eq 0)
    Check "no hook file is unreadable during the re-runs ($($Reader.Count('unreadable ')) faults)" ($Reader.Count('unreadable ') -eq 0)
    Check "no hook read is short: each read is one whole version ($($Reader.Count('short read ')) faults)" ($Reader.Count('short read ') -eq 0)
    # A pair of reads whose INSTALL_IDs differ is a window the guard waits through. It must clear
    # within the guard's wait, measured from the first mixed read to the first matching read.
    $MixedMaxSeconds = 5
    $LongestWindow = [math]::Round($Reader.MaxWindowSeconds, 3)
    Write-Host "info: $($Reader.Windows) mixed-id windows; longest $LongestWindow s"
    Check "every mixed-id window clears within $MixedMaxSeconds s ($($Reader.Windows) windows, longest $LongestWindow s)" ($Reader.MaxWindowSeconds -le $MixedMaxSeconds)
    Check "no mixed-id window is still open when the re-runs end" (-not $Reader.WindowOpen)
    Check "run 2 prunes the nested file the source dropped" (-not (Test-Path -LiteralPath (Join-Path $Cfg $DroppedRel)))

    $Missing2 = @($Shipped | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Cfg $_)) })
    Check "all shipped names present after run 2" ($Missing2.Count -eq 0)
    foreach ($m in $Missing2) { Write-Host "  missing after run 2: $m" }

    # ---- symrun: a real file from an earlier copy, then a run where links can be made ----------
    # Run 1 forces copy mode, so both hook files are real stamped files. Run 2 can make links, so
    # each is swapped for a link to the repo file, which holds the placeholder. The same reader loop
    # runs through run 2. The guard_core.py and guard.py reads differ in id (a copy has its stamp, a
    # link the placeholder) from the first swap to the second: a window, which must clear.
    $Blocker = Get-SymlinkBlocker
    if ($Blocker) {
        # A CI runner has symlink rights. A skip there would hide the link route, so it fails.
        if ($env:CI) { Check "symrun: runs on CI, where links can be made (no symlink rights: $Blocker)" $false }
        else { Write-Host "SKIP: symrun (no symlink rights: $Blocker)" }
    } else {
        $Sym      = New-Scratch 'symrun' @('hooks')
        # Small files: a link needs no long copy, and a fast reader pass lands inside a short gap.
        $SymText  = @((New-HookText 'guard.py' 'symrun' 100), (New-HookText 'guard_core.py' 'symrun' 100))
        Write-FixtureFile (Join-Path $Sym.Clone 'hooks\guard.py') $SymText[0]
        Write-FixtureFile (Join-Path $Sym.Clone 'hooks\guard_core.py') $SymText[1]
        $SymGuard = Join-Path $Sym.Cfg 'hooks\guard.py'

        $env:CLAUDE_CONFIG_DIR = $Sym.Cfg
        $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        $rcS1 = Invoke-Install $Sym.Clone 'symrun-run1.log'
        Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
        Check "symrun: run 1 (forced copy) exits 0 (exit $rcS1)" ($rcS1 -eq 0)
        Check "symrun: run 1 leaves a real file at hooks\guard.py, the earlier copy" ((Test-Path -LiteralPath $SymGuard) -and (-not (Test-ReparsePoint $SymGuard)))

        $SymReader = New-Object -TypeName HookReader
        $SymReader.Paths = [string[]]@($SymGuard, (Join-Path $Sym.Cfg 'hooks\guard_core.py'))
        $SymReader.Versions1 = [string[]]$SymText
        $SymReader.Versions2 = [string[]]$SymText
        $SymReader.Present = [string[]]@((Join-Path $Sym.Cfg 'CLAUDE.md'), (Join-Path $Sym.Cfg 'settings.json'), (Join-Path $Sym.Cfg 'hooks'))
        $SymReader.Start()
        try {
            $passesBefore = $SymReader.Passes
            $rcS2 = Invoke-Install $Sym.Clone 'symrun-run2.log'
            $SymPasses = $SymReader.Passes - $passesBefore
        } finally {
            $SymReader.Stop()
            Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        }
        foreach ($line in $SymReader.Report()) { Write-Host "  reader fault: $line" }
        $SymLongest = [math]::Round($SymReader.MaxWindowSeconds, 3)
        Write-Host "info: symrun: $($SymReader.Windows) mixed-id windows; longest $SymLongest s"
        Check "symrun: run 2 exits 0 (exit $rcS2)" ($rcS2 -eq 0)
        Check "symrun: reader ran during run 2 ($SymPasses passes, want 1 or more)" ($SymPasses -ge 1)
        Check "symrun: no shipped name is missing during run 2 ($($SymReader.Count('missing ')) faults)" ($SymReader.Count('missing ') -eq 0)
        Check "symrun: no hook file is unreadable during run 2 ($($SymReader.Count('unreadable ')) faults)" ($SymReader.Count('unreadable ') -eq 0)
        Check "symrun: no hook read is short during run 2 ($($SymReader.Count('short read ')) faults)" ($SymReader.Count('short read ') -eq 0)
        Check "symrun: every mixed-id window clears within $MixedMaxSeconds s ($($SymReader.Windows) windows, longest $SymLongest s)" ($SymReader.MaxWindowSeconds -le $MixedMaxSeconds)
        Check "symrun: no mixed-id window is still open when run 2 ends" (-not $SymReader.WindowOpen)
        # Between the two swaps guard.py and guard_core.py differ in id, so the reader must have seen
        # a window. With none, the checks above passed on no evidence.
        Check "symrun: the reader saw the mixed-id window between the two swaps ($($SymReader.Windows) windows, want 1 or more)" ($SymReader.Windows -ge 1)
        Check "symrun: run 2 leaves hooks\guard.py a link (non-vacuous: the link route ran)" (Test-ReparsePoint $SymGuard)
    }

    # ---- linkfail: dest is a symlink to elsewhere and the copy fails: a file must remain -------
    if ($Blocker) {
        if ($env:CI) { Check "linkfail: runs on CI, where links can be made (no symlink rights: $Blocker)" $false }
        else { Write-Host "SKIP: linkfail (no symlink rights: $Blocker)" }
    } else {
        $Lf     = New-Scratch 'linkfail' @('hooks')
        $LfSrc  = Join-Path $Lf.Clone 'hooks\guard.py'
        Write-FixtureFile $LfSrc '# guard'
        $LfElse = Join-Path $Lf.Root 'elsewhere\guard.py'
        Write-FixtureFile $LfElse '# elsewhere'
        $LfDest = Join-Path $Lf.Cfg 'hooks\guard.py'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LfDest) | Out-Null
        New-Item -ItemType SymbolicLink -Path $LfDest -Target $LfElse -ErrorAction Stop | Out-Null

        $Lock = [IO.File]::Open($LfSrc, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
        try {
            $DestItem = Get-Item -LiteralPath $LfDest -Force
            Check "linkfail: dest is a symlink to elsewhere before the run" (($DestItem.LinkType -eq 'SymbolicLink') -and (@($DestItem.Target)[0] -eq $LfElse))

            $LockHeld = $false
            try { Copy-Item -LiteralPath $LfSrc -Destination (Join-Path $Lf.Root 'probe.py') -ErrorAction Stop }
            catch { $LockHeld = $true }
            Check "linkfail: the source is locked, so a read through Copy-Item fails" $LockHeld

            $env:CLAUDE_CONFIG_DIR = $Lf.Cfg
            $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
            $rcL = Invoke-Install $Lf.Clone 'linkfail-run.log'
            Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
            $After = Get-Item -LiteralPath $LfDest -Force -ErrorAction SilentlyContinue
            Check "linkfail: a file still exists at dest after the failed copy (exit $rcL)" ($null -ne $After)
        } finally {
            $Lock.Dispose()
            Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        }
    }

    # ---- lock1: first local run, the person's skill is locked, so its backup rename fails ----------
    # Review finding 1. No copy marker yet, so the person's own skill dir is a first-run backup
    # candidate. A handle held open on one of its files, with FileShare.Read (no Delete), makes the
    # rename of the directory fail. Run 1 must leave a .bak of that skill, or no copy marker, so
    # run 2 is still a first run. After the lock is released, run 2 must keep the person's files at
    # the skill dir or in a .bak, and prune none of them. Copy mode is forced: no symlink needed.
    $L1      = New-Scratch 'lock1' @('skills')
    Write-FixtureFile (Join-Path $L1.Clone 'skills\lockskill\SKILL.md') '# shipped lockskill'
    $L1Skill  = Join-Path $L1.Cfg 'skills\lockskill'
    $L1Notes  = Join-Path $L1Skill 'my-notes.md'
    $L1Marker = Join-Path $L1.Cfg '.claude-settings-installed'
    Write-FixtureFile (Join-Path $L1Skill 'SKILL.md') "person's own skill"
    Write-FixtureFile $L1Notes "person's own notes"

    $L1Lock = [IO.File]::Open($L1Notes, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $env:CLAUDE_CONFIG_DIR = $L1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        # Fixture: the open handle must block a rename of the skill dir, or run 1 proves nothing.
        $Blocked = $false
        try { [IO.Directory]::Move($L1Skill, "$L1Skill.probe") } catch { $Blocked = $true }
        if (-not $Blocked) { [IO.Directory]::Move("$L1Skill.probe", $L1Skill) }
        Check "lock1 fixture: a rename of the locked skill dir is refused while the handle is open" $Blocked

        $rcL1 = Invoke-Install $L1.Clone 'lock1-run1.log'
        Write-Host "info: lock1 run 1 exit $rcL1"
        $BakL1    = @(Get-ChildItem -LiteralPath (Join-Path $L1.Cfg 'backups\skills') -Directory -Filter 'lockskill.*' -ErrorAction SilentlyContinue)
        $MarkerL1 = Test-Path -LiteralPath $L1Marker
        Check "lock1: run 1 leaves a .bak of the skill, or no copy marker ($($BakL1.Count) bak, marker $MarkerL1)" (($BakL1.Count -gt 0) -or (-not $MarkerL1))
    } finally {
        $L1Lock.Dispose()
    }

    # The lock is released. Run 2 must keep the person's files and prune none of them.
    try {
        $rcL2 = Invoke-Install $L1.Clone 'lock1-run2.log'
        Write-Host "info: lock1 run 2 exit $rcL2"
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }
    $L1Roots   = @($L1Skill) + @(Get-ChildItem -LiteralPath (Join-Path $L1.Cfg 'backups\skills') -Directory -Filter 'lockskill.*' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $NotesKept = @($L1Roots | Where-Object { (Test-Path -LiteralPath (Join-Path $_ 'my-notes.md')) -and ((Get-Content -Raw -LiteralPath (Join-Path $_ 'my-notes.md')).Trim() -eq "person's own notes") }).Count -gt 0
    $SkillKept = @($L1Roots | Where-Object { (Test-Path -LiteralPath (Join-Path $_ 'SKILL.md')) -and ((Get-Content -Raw -LiteralPath (Join-Path $_ 'SKILL.md')).Trim() -eq "person's own skill") }).Count -gt 0
    Check "lock1: run 2 keeps the person's my-notes.md at the skill dir or in a .bak, never pruned" $NotesKept
    Check "lock1: run 2 keeps the person's SKILL.md content at the skill dir or in a .bak" $SkillKept

    # ---- hooks-whole: no live hook file is ever seen truncated (temp, then rename) --------------
    # The installer writes each file to a temp name and renames it into place, so a reader sees
    # the old file or the new one, never a half-written one. An in-place rewrite keeps the file's identity. A rename into place gives it a
    # new identity. So in a re-run that changes a hook file's text, each hook file that changes must
    # get a new identity, and the new text must land (non-vacuous). Two routes: install.ps1 run 2 in
    # copy mode, and the post-merge hook install.ps1 writes into .git\hooks, run by git's sh.
    if (-not ('FileIdentity' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class FileIdentity
{
    [StructLayout(LayoutKind.Sequential)]
    public struct FileInfoById
    {
        public uint Attributes;
        public uint CreatedLo, CreatedHi, AccessedLo, AccessedHi, WrittenLo, WrittenHi;
        public uint Volume;
        public uint SizeHi, SizeLo;
        public uint Links;
        public uint IndexHi, IndexLo;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInfoById info);

    // Identity of the object at path, following links. A rewrite in place keeps it; a rename gives a new one.
    // Access 0 (query only), share read|write|delete, OPEN_EXISTING, BACKUP_SEMANTICS.
    public static string Of(string path)
    {
        using (SafeFileHandle h = CreateFileW(path, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero))
        {
            if (h.IsInvalid) throw new IOException("cannot open " + path + ", Win32 error " + Marshal.GetLastWin32Error());
            FileInfoById info;
            if (!GetFileInformationByHandle(h, out info)) throw new IOException("no file information for " + path);
            return info.Volume.ToString("x") + ":" + info.IndexHi.ToString("x") + ":" + info.IndexLo.ToString("x");
        }
    }
}
'@
    }

    $HookFiles = @('guard.py', 'guard_core.py')
    $HookV1 = @('# guard v1', '# guard core v1')
    $HookV2 = @('# guard v2, new text of another length', '# guard core v2, new text of another length')

    # Writes the two hook files the case watches, in the clone.
    function Use-HookSource([string]$Dir, [string[]]$Texts) {
        Write-FixtureFile (Join-Path $Dir 'hooks\guard.py') $Texts[0]
        Write-FixtureFile (Join-Path $Dir 'hooks\guard_core.py') $Texts[1]
    }

    # True when both hook files in $Hooks hold exactly $Texts. A missing file reads as empty.
    function Test-HookLanded([string]$Hooks, [string[]]$Texts) {
        $g = ''; $c = ''
        if (Test-Path -LiteralPath (Join-Path $Hooks 'guard.py')) { $g = [IO.File]::ReadAllText((Join-Path $Hooks 'guard.py')) }
        if (Test-Path -LiteralPath (Join-Path $Hooks 'guard_core.py')) { $c = [IO.File]::ReadAllText((Join-Path $Hooks 'guard_core.py')) }
        return ($g -eq $Texts[0]) -and ($c -eq $Texts[1])
    }

    # The identity of each hook file in $Hooks, by name.
    function Get-HookIds([string]$Hooks) {
        $ids = @{}
        foreach ($n in $HookFiles) { $ids[$n] = [FileIdentity]::Of((Join-Path $Hooks $n)) }
        return $ids
    }

    # The hook files whose identity did not change: each one was rewritten in place.
    function Get-InPlaceHookFiles($Before, $After) {
        return @($HookFiles | Where-Object { $Before[$_] -eq $After[$_] })
    }

    # The git Bash sh: from PATH, else beside the git on PATH (Git\cmd\git.exe -> Git\bin\sh.exe).
    function Get-GitSh {
        $c = Get-Command sh -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
        $g = Get-Command git -ErrorAction SilentlyContinue
        if ($g) {
            $p = Join-Path (Split-Path (Split-Path $g.Source -Parent) -Parent) 'bin\sh.exe'
            if (Test-Path -LiteralPath $p) { return $p }
        }
        return $null
    }

    # Route 1: install.ps1 run 2 in copy mode.
    $H1 = New-Scratch 'hooks-whole-install' @('hooks')
    $H1Hooks = Join-Path $H1.Cfg 'hooks'
    Use-HookSource $H1.Clone $HookV1
    $env:CLAUDE_CONFIG_DIR = $H1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rcH1 = Invoke-Install $H1.Clone 'hooks-whole-install-run1.log'
        Check "hooks-whole: install run 1 (forced copy) exits 0 (exit $rcH1)" ($rcH1 -eq 0)
        Check "hooks-whole: install run 1 lands both hook files as copies, not links" ((Test-HookLanded $H1Hooks $HookV1) -and (-not (Test-ReparsePoint (Join-Path $H1Hooks 'guard.py'))))
        Use-HookSource $H1.Clone $HookV2
        $idsH1 = Get-HookIds $H1Hooks
        $rcH2 = Invoke-Install $H1.Clone 'hooks-whole-install-run2.log'
        Check "hooks-whole: install run 2 exits 0 (exit $rcH2)" ($rcH2 -eq 0)
        Check "hooks-whole: install run 2 lands the new text in both hook files (non-vacuous)" (Test-HookLanded $H1Hooks $HookV2)
        $inPlaceH1 = @(Get-InPlaceHookFiles $idsH1 (Get-HookIds $H1Hooks))
        foreach ($f in $inPlaceH1) { Write-Host "  rewritten in place by install run 2: $f" }
        Check "hooks-whole: install run 2 rewrites no hook file in place ($($inPlaceH1.Count) in place)" ($inPlaceH1.Count -eq 0)
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }

    # Route 2: the post-merge hook that install.ps1 writes into .git\hooks, run by git's sh.
    $H2 = New-Scratch 'hooks-whole-hook' @('hooks')
    $H2Hooks = Join-Path $H2.Cfg 'hooks'
    Use-HookSource $H2.Clone $HookV1
    $GitCmd = Get-Command git -ErrorAction SilentlyContinue
    $Sh = Get-GitSh
    if (-not $GitCmd -or -not $Sh) {
        Check "hooks-whole: git and a Git Bash sh are both found, so the post-merge hook can run" $false
    } else {
        $env:CLAUDE_CONFIG_DIR = $H2.Cfg
        $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        try {
            # A real repo on main, with one commit, so the hook's branch check passes.
            & git -C $H2.Clone init -q
            & git -C $H2.Clone symbolic-ref HEAD refs/heads/main
            & git -C $H2.Clone -c core.autocrlf=false add -A
            & git -C $H2.Clone -c core.autocrlf=false -c user.name=hooks-whole-test -c user.email=hooks-whole-test@example.invalid commit -q -m fixture
            Check "hooks-whole: the scratch clone is a git repo on main with one commit (exit $LASTEXITCODE)" ($LASTEXITCODE -eq 0)

            $rcH2a = Invoke-Install $H2.Clone 'hooks-whole-hook-run1.log'
            Check "hooks-whole: hook route: install run 1 (forced copy) exits 0 (exit $rcH2a)" ($rcH2a -eq 0)
            Check "hooks-whole: hook route: install run 1 writes the post-merge hook into .git\hooks" (Test-Path -LiteralPath (Join-Path $H2.Clone '.git\hooks\post-merge'))
            Use-HookSource $H2.Clone $HookV2
            $idsH2 = Get-HookIds $H2Hooks
            # The hook reads CLAUDE_CONFIG_DIR inside sh, so it gets forward slashes.
            $env:CLAUDE_CONFIG_DIR = $H2.Cfg.Replace('\', '/')
            $hookLog = Join-Path $Tmp 'hooks-whole-hook-run2.log'
            $pH = Start-Process -FilePath $Sh -ArgumentList '.git/hooks/post-merge' -WorkingDirectory $H2.Clone -Wait -PassThru -NoNewWindow -RedirectStandardOutput $hookLog -RedirectStandardError ($hookLog + '.err')
            Check "hooks-whole: hook route: the post-merge hook exits 0 (exit $($pH.ExitCode))" ($pH.ExitCode -eq 0)
            Check "hooks-whole: hook route: the hook lands the new text in both hook files (non-vacuous)" (Test-HookLanded $H2Hooks $HookV2)
            $inPlaceH2 = @(Get-InPlaceHookFiles $idsH2 (Get-HookIds $H2Hooks))
            foreach ($f in $inPlaceH2) { Write-Host "  rewritten in place by the hook: $f" }
            Check "hooks-whole: hook route: the hook rewrites no hook file in place ($($inPlaceH2.Count) in place)" ($inPlaceH2.Count -eq 0)
        } finally {
            Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
        }
    }
    # ---- stamp1: after an install, every installed guard*.py carries one real INSTALL_ID -----------
    # The repo's hook files carry a commented placeholder. An install must replace it, in every
    # guard*.py, with one uncommented id for the whole run. A placeholder left behind, a missing line,
    # or two different ids fails.
    $S1 = New-Scratch 'stamp-install' @('hooks')
    $S1Hooks = Join-Path $S1.Cfg 'hooks'
    $S1Names = @('guard.py', 'guard_core.py', 'guard_pointer.py')
    foreach ($n in $S1Names) {
        Write-FixtureFile (Join-Path $S1.Clone ('hooks\' + $n)) ($HookPlaceholder + "`n# " + $n + " body`n")
    }
    $env:CLAUDE_CONFIG_DIR = $S1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rcS1 = Invoke-Install $S1.Clone 'stamp1-run1.log'
        Check "stamp1: install exits 0 (exit $rcS1)" ($rcS1 -eq 0)
        $StampIds = @()
        foreach ($n in $S1Names) {
            $text = [IO.File]::ReadAllText((Join-Path $S1Hooks $n))
            $m = [regex]::Match($text, '(?m)^INSTALL_ID = "([^"]*)"')
            if ($m.Success) { $StampIds += $m.Groups[1].Value } else { $StampIds += '(none)' }
        }
        $Distinct = @($StampIds | Select-Object -Unique)
        Write-Host "info: INSTALL_ID after install: $($StampIds -join ', ')"
        Check "stamp1: every installed guard*.py carries an uncommented INSTALL_ID line" (-not ($StampIds -contains '(none)'))
        Check "stamp1: one and the same INSTALL_ID in every guard*.py ($($Distinct.Count) distinct)" ($Distinct.Count -eq 1)
        Check "stamp1: that INSTALL_ID is a real id, not the placeholder" (($Distinct.Count -eq 1) -and ($Distinct[0] -notin @('uninstalled', '(none)', '')))
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }

    # ---- replace1: a replace that fails for good makes install.ps1 exit non-zero and name the file --
    # A reader holds guard_pointer.py open with no delete sharing, so the rename over it is refused on
    # every retry. The install must print the file it could not replace, leave that file as it was,
    # and exit non-zero.
    $R1 = New-Scratch 'replace-fail' @('hooks')
    $R1Hooks = Join-Path $R1.Cfg 'hooks'
    Write-FixtureFile (Join-Path $R1.Clone 'hooks\guard.py') '# guard v1'
    Write-FixtureFile (Join-Path $R1.Clone 'hooks\guard_pointer.py') '# pointer v1'
    $env:CLAUDE_CONFIG_DIR = $R1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rcR1 = Invoke-Install $R1.Clone 'replace1-run1.log'
        Check "replace1: run 1 (forced copy) exits 0 (exit $rcR1)" ($rcR1 -eq 0)
        Write-FixtureFile (Join-Path $R1.Clone 'hooks\guard.py') '# guard v2'
        Write-FixtureFile (Join-Path $R1.Clone 'hooks\guard_pointer.py') '# pointer v2'
        $Held = [IO.FileStream]::new((Join-Path $R1Hooks 'guard_pointer.py'), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        try {
            $rcR2 = Invoke-Install $R1.Clone 'replace1-run2.log'
        } finally {
            $Held.Dispose()
        }
        $R1Log = Get-RunText (Join-Path $Tmp 'replace1-run2.log')
        Check "replace1: run 2 exits non-zero when one replace fails for good (exit $rcR2)" ($rcR2 -ne 0)
        Check "replace1: run 2 prints the file it could not replace" ($R1Log -match 'could not (replace|refresh) .*guard_pointer\.py')
        Check "replace1: the file it could not replace is unchanged (still pointer v1)" ([IO.File]::ReadAllText((Join-Path $R1Hooks 'guard_pointer.py')) -eq '# pointer v1')
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }
    # ---- prose1: only the exact placeholder line is stamped; a prose comment is copied unchanged -----
    # A comment that starts INSTALL_ID = " but says something else is not the placeholder. Each stamper
    # (install.ps1's copy path, the post-merge hook) must leave it as it is, so the
    # installed copy is the source. The installed copy must also still parse as Python. Only the exact
    # line # INSTALL_ID = "uninstalled" is stamped.
    $ProseLine = '# INSTALL_ID = "<id>", and the cases put that line at the top of every copy, as an install does.'
    $ProseText = $ProseLine + "`n" + 'X = 1' + "`n"
    $PlaceText = $HookPlaceholder + "`n" + 'Y = 2' + "`n"
    function Test-AstParse([string]$Path) {
        $py = $null
        foreach ($c in @('python', 'python3', 'py')) { if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break } }
        if (-not $py) { return $null }
        & $py -c "import ast, sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" "$Path"
        return ($LASTEXITCODE -eq 0)
    }
    function Test-ProseFolder([string]$Label, [string]$Hooks) {
        # Names differ from $ProseText by more than case: PowerShell variables are case-insensitive.
        $proseFile = Join-Path $Hooks 'guard_prose.py'
        $stampFile = Join-Path $Hooks 'guard_stamp.py'
        $gotProse = ''; $gotStamp = ''
        if (Test-Path -LiteralPath $proseFile) { $gotProse = [IO.File]::ReadAllText($proseFile) }
        if (Test-Path -LiteralPath $stampFile) { $gotStamp = [IO.File]::ReadAllText($stampFile) }
        Check ($Label + ': the prose comment is copied unchanged') ($gotProse -ceq $ProseText)
        Check ($Label + ': the prose file still parses as Python') ((Test-Path -LiteralPath $proseFile) -and ((Test-AstParse $proseFile) -eq $true))
        Check ($Label + ': the exact placeholder line is stamped with a real id') ([regex]::IsMatch($gotStamp, '(?m)^INSTALL_ID = "[^"]+"') -and -not $gotStamp.Contains('uninstalled'))
        Check ($Label + ': the stamped placeholder file still parses as Python') ((Test-Path -LiteralPath $stampFile) -and ((Test-AstParse $stampFile) -eq $true))
    }

    # Route 1: install.ps1, copy mode (Set-InstallId).
    $P1 = New-Scratch 'prose-install' @('hooks')
    Write-FixtureFile (Join-Path $P1.Clone 'hooks\guard_prose.py') $ProseText
    Write-FixtureFile (Join-Path $P1.Clone 'hooks\guard_stamp.py') $PlaceText
    $env:CLAUDE_CONFIG_DIR = $P1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rcP1 = Invoke-Install $P1.Clone 'prose1-install.log'
        Check "prose1: install route: install.ps1 exits 0 (exit $rcP1)" ($rcP1 -eq 0)
        Test-ProseFolder 'prose1: install route' (Join-Path $P1.Cfg 'hooks')
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }

    # Route 2: the post-merge hook install.ps1 writes into .git\hooks (put), run by git's sh.
    $P2 = New-Scratch 'prose-hook' @('hooks')
    Write-FixtureFile (Join-Path $P2.Clone 'hooks\guard_prose.py') $ProseText
    Write-FixtureFile (Join-Path $P2.Clone 'hooks\guard_stamp.py') $PlaceText
    $Sh2 = Get-GitSh
    if (-not (Get-Command git -ErrorAction SilentlyContinue) -or -not $Sh2) {
        Check "prose1: hook route: git and a Git Bash sh are both found, so the post-merge hook can run" $false
    } else {
        $env:CLAUDE_CONFIG_DIR = $P2.Cfg
        $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        try {
            & git -C $P2.Clone init -q
            & git -C $P2.Clone symbolic-ref HEAD refs/heads/main
            & git -C $P2.Clone -c core.autocrlf=false add -A
            & git -C $P2.Clone -c core.autocrlf=false -c user.name=prose-test -c user.email=prose-test@example.invalid commit -q -m fixture
            $rcP2a = Invoke-Install $P2.Clone 'prose1-hook-run1.log'
            Check "prose1: hook route: install run 1 exits 0 (exit $rcP2a)" ($rcP2a -eq 0)
            Check "prose1: hook route: install run 1 writes the post-merge hook" (Test-Path -LiteralPath (Join-Path $P2.Clone '.git\hooks\post-merge'))
            $env:CLAUDE_CONFIG_DIR = $P2.Cfg.Replace('\', '/')
            $hookLog2 = Join-Path $Tmp 'prose1-hook-run2.log'
            $pP2 = Start-Process -FilePath $Sh2 -ArgumentList '.git/hooks/post-merge' -WorkingDirectory $P2.Clone -Wait -PassThru -NoNewWindow -RedirectStandardOutput $hookLog2 -RedirectStandardError ($hookLog2 + '.err')
            Check "prose1: hook route: the post-merge hook exits 0 (exit $($pP2.ExitCode))" ($pP2.ExitCode -eq 0)
            Test-ProseFolder 'prose1: hook route' (Join-Path $P2.Cfg 'hooks')
        } finally {
            Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
        }
    }

    # ---- first1: a first install over an unstamped set (the repo's placeholder set) ----------------
    # No install marker, and the installed copy is the placeholder set from main: the first run. After it,
    # every guard*.py carries one real id. A reader loop runs through the install. Each mixed-id window
    # must clear within the guard's wait (5 s), and none may be open when the install ends.
    $F1 = New-Scratch 'first-install' @('hooks')
    $F1Hooks = Join-Path $F1.Cfg 'hooks'
    $F1Names = @('guard.py', 'guard_core.py', 'guard_pointer.py')
    $F1Old = @{}; $F1New = @{}
    foreach ($n in $F1Names) {
        # The installed copy is unstamped, as main's copies are: no INSTALL_ID line at all.
        $F1Old[$n] = Remove-StampLine (New-HookText $n 'first install, unstamped installed copy')
        $F1New[$n] = New-HookText $n 'first install, source with the placeholder'
        Write-FixtureFile (Join-Path $F1Hooks $n) $F1Old[$n]
        Write-FixtureFile (Join-Path $F1.Clone ('hooks\' + $n)) $F1New[$n]
    }
    $Reader1 = New-Object -TypeName HookReader
    $Reader1.Paths = [string[]]@((Join-Path $F1Hooks 'guard.py'), (Join-Path $F1Hooks 'guard_core.py'))
    $Reader1.Versions1 = [string[]]@($F1Old['guard.py'], $F1Old['guard_core.py'])
    $Reader1.Versions2 = [string[]]@($F1New['guard.py'], $F1New['guard_core.py'])
    $env:CLAUDE_CONFIG_DIR = $F1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    $Reader1.Start()
    try {
        $rcF1 = Invoke-Install $F1.Clone 'first1-install.log'
    } finally {
        $Reader1.Stop()
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }
    Check "first1: the first install exits 0 (exit $rcF1)" ($rcF1 -eq 0)
    $F1Ids = @()
    foreach ($n in $F1Names) {
        $mm = [regex]::Match([IO.File]::ReadAllText((Join-Path $F1Hooks $n)), '(?m)^INSTALL_ID = "([^"]*)"')
        if ($mm.Success) { $F1Ids += $mm.Groups[1].Value } else { $F1Ids += '(none)' }
    }
    $F1Distinct = @($F1Ids | Select-Object -Unique)
    Check "first1: every guard*.py carries one and the same uncommented real INSTALL_ID ($($F1Ids -join ', '))" (($F1Distinct.Count -eq 1) -and ($F1Distinct[0] -notin @('(none)', 'uninstalled', '')))
    Check "first1: the reader ran through the install ($($Reader1.Passes) passes, want at least 10)" ($Reader1.Passes -ge 10)
    $F1Gone = $Reader1.Count('missing ') + $Reader1.Count('unreadable ')
    Check "first1: no hook file is missing or unreadable during the install ($F1Gone faults)" ($F1Gone -eq 0)
    Check "first1: no hook read is short ($($Reader1.Count('short read ')) faults)" ($Reader1.Count('short read ') -eq 0)
    $LongestF1 = [math]::Round($Reader1.MaxWindowSeconds, 3)
    Check "first1: every mixed-id window clears within 5 s ($($Reader1.Windows) windows, longest $LongestF1 s)" ($Reader1.MaxWindowSeconds -le 5)
    Check "first1: no mixed-id window is still open when the install ends" (-not $Reader1.WindowOpen)

    # ---- read1: a run's printed text is read while another handle still holds the file open for write ---
    # A child the run left behind can hold its redirected output open for write. The read must still
    # return the text. A missing file must still throw, so a case never takes absent text for empty text.
    $R1Dir = Join-Path $Tmp 'read1'
    New-Item -ItemType Directory -Force -Path $R1Dir | Out-Null
    $R1File = Join-Path $R1Dir 'run.log'
    [IO.File]::WriteAllText($R1File, "one printed line`n", $Utf8)
    $R1Hold = [IO.File]::Open($R1File, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
    try { $R1Text = Get-RunText $R1File; $R1Err = '' } catch { $R1Text = ''; $R1Err = $_.Exception.Message } finally { $R1Hold.Close() }
    Check "read1: a run's printed text held open for write by another handle reads back whole" ($R1Text.Trim() -eq 'one printed line')
    if ($R1Err) { Write-Host "  read1 error: $R1Err" }
    $R1Missing = try { $null = Get-RunText (Join-Path $R1Dir 'absent.log'); 'no error' } catch { 'threw' }
    Check "read1: a read of a missing file still throws" ($R1Missing -eq 'threw')

    # ---- retry1: a file that Resolve-Failures recovers on retry leaves no failure behind -----------
    # A first install: no install marker, and person files already sit at two names. A reader holds
    # guard_pointer.py open with no delete sharing for 5 s. Move-OverFile gives up after about 2.5 s, and
    # Resolve-Failures retries after 2 s, when the lock is gone. Such a run must exit 0, print the retry,
    # write no 'failed' to the install log, and write the install marker.
    $T1 = New-Scratch 'retry-install' @('hooks')
    $T1Hooks = Join-Path $T1.Cfg 'hooks'
    Write-FixtureFile (Join-Path $T1.Clone 'hooks\guard.py') '# guard v1'
    Write-FixtureFile (Join-Path $T1.Clone 'hooks\guard_pointer.py') '# pointer v2'
    Write-FixtureFile (Join-Path $T1Hooks 'guard.py') "# person's guard"
    Write-FixtureFile (Join-Path $T1Hooks 'guard_pointer.py') "# person's pointer"
    $T1Marker = Join-Path $T1.Cfg '.claude-settings-installed'
    $T1InstallLog = Join-Path $T1.Cfg 'claude-settings-install.log'
    $T1Out = Join-Path $Tmp 'retry1-install.log'
    $T1Held = [IO.FileStream]::new((Join-Path $T1Hooks 'guard_pointer.py'), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $env:CLAUDE_CONFIG_DIR = $T1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $pT1 = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $T1.Clone 'install.ps1') + '"') -PassThru -NoNewWindow -RedirectStandardOutput $T1Out -RedirectStandardError ($T1Out + '.err')
        # Reading Handle now keeps the exit code reachable after the process ends.
        $null = $pT1.Handle
        Start-Sleep -Milliseconds 5000
        $T1Held.Dispose()
        $pT1.WaitForExit()
        $pT1.Refresh()
        $rcT1 = $pT1.ExitCode
    } finally {
        $T1Held.Dispose()
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }
    $T1Printed = if (Test-Path -LiteralPath $T1Out) { Get-RunText $T1Out } else { '' }
    $T1Text = if (Test-Path -LiteralPath $T1InstallLog) { Get-RunText $T1InstallLog } else { '' }
    Check "retry1: the first install exits 0 (exit $rcT1)" ($rcT1 -eq 0)
    Check "retry1: the run printed a retry (non-vacuous: the failed replace happened)" ($T1Printed -match 'retrying in')
    Check "retry1: guard_pointer.py holds the new text after the retry" ([IO.File]::ReadAllText((Join-Path $T1Hooks 'guard_pointer.py')) -eq '# pointer v2')
    Check "retry1: the install log was written" (Test-Path -LiteralPath $T1InstallLog)
    Write-Host "  install log (retry1): $($T1Text.Trim())"
    Check "retry1: the install log has no 'failed' for a file the retry recovered" ($T1Text -notmatch '(?i)failed')
    Check "retry1: the install marker is written on the first install" (Test-Path -LiteralPath $T1Marker)
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
    try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
