// The watchdog for test_stamp.mjs. The suite is synchronous, so a timer inside it never fires while a
// command hangs. Run normally, the suite re-runs itself as a child with piped stdio, so no process
// under it holds the runner's output pipe, and the timer lives here, in the parent. On expiry the
// watchdog names the running test, kills the process tree, prints what ran and exits 1. After the
// child closes, normally or not, it finds each process the suite started that still runs, kills it,
// names it and exits 1. STAMP_SUITE_CAP_S sets the cap, inside the CI step's own.
//
// Budget, against the CI step's 300 s cap (timeout-minutes 5 in checks.yml). The suite's cap is
// DEFAULT_CAP_S = 180 s. A hard stop fires HARD_STOP_AFTER_CAP_S = 30 s after that. A synchronous
// call cannot be interrupted, so the hard stop waits for the longest blocking stretch that began
// before it: 35 s (Windows tree-walk fallback: taskkill 10 + walk 15 + taskkill 10; POSIX: one ps at
// 5 s for the process group, then up to four ps scans at 5 s each). The hard stop's own kills take at
// most 10 s (Windows taskkill; POSIX two ps scans), and its output drain 2 s. Worst case:
// 180 + 30 + 35 + 10 + 2 = 257 s, which leaves 43 s of margin. A normal run on the Windows job path
// ends far inside it: close, a 3 s grace, then one 20 s bounded request to the helper.
//
// What the suite leaves running. The watchdog finds each process the suite started that still runs,
// by a mark that survives a detach or a dead parent, never by image name or parent pid:
//  - Linux: STAMP_SUITE_RUN=<id> in the child's env. A process inherits it from its parent, and
//    /proc/<pid>/environ reads it back. macOS: the same mark, read with ps -E.
//  - Windows has no readable environ, so the child runs in an unnamed Job Object with
//    KILL_ON_JOB_CLOSE. A job holds every descendant, however detached, and nothing can break away
//    from it. Only a handle can list or end an unnamed job, and a handle lives as long as its process,
//    so one PowerShell helper holds the job for the suite's life and lists and kills its members on
//    request. If the watchdog is killed, the helper's pipe closes, the helper ends, and the job closes
//    with every member in it. The child waits on a go-file until the helper has put it in the job, so
//    on CI no test runs outside it: a run that cannot get a job fails by name. Off CI the child is
//    released anyway, and leftovers are found by a walk of the process tree, with a printed note.
//    A child whose go-file never appears fails by name (see waitForGo).
// An unreadable sweep is unknown, never "nothing found": on CI it exits 1 too.
// Cost: one extra PowerShell process on Windows, for the suite's own run only.

import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const CHILD = "STAMP_SUITE_CHILD";
export const HANG = "STAMP_SUITE_HANG_FIXTURE"; // a pid file: the child runs only the hang fixture
export const START = "STAMP-START "; // the child prints it before each test, so the parent can name a hung one
const RUN = "STAMP_SUITE_RUN";
const GO = "STAMP_SUITE_GO"; // Windows: the child starts its tests when this file exists
const NO_JOB = "STAMP_SUITE_NO_JOB"; // "1": Windows: the watchdog makes no job object, as if it could not
const GO_WAIT_MS = "STAMP_SUITE_GO_WAIT_MS"; // ms the child waits for the go file before it fails; default 40000
const GO_FAIL = "STAMP_SUITE_GO_FAIL"; // "1": Windows: the go-file write fails, as if the disk refused it
// A seam for the wiring test, not a feature. A clean fixture leaves nothing, so no real run reaches
// the "pid still alive after the kill" or "sweep could not read" results. "alive" or "unknown" makes
// the sweep report that result on top of what it really found, and the real leftoverExit wiring then
// decides the exit. It injects the result only: it kills and lists nothing differently.
const SWEEP_FAULT = "STAMP_SUITE_SWEEP_FAULT";
export const DEFAULT_CAP_S = 180; // the slowest normal run took 102 s (run 42456407663); the slowest of 28 earlier runs, 90 s
export const HARD_STOP_AFTER_CAP_S = 30; // see the budget above
const LEFTOVER_GRACE_MS = 3000; // a process may still be exiting when the suite closes
// The go file is written at most ASSIGN_WAIT_MS after the child spawns. The child's go wait (the
// GO_WAIT_MS default in waitForGo) must stay above it: a longer assign would fail a healthy off-CI run.
const ASSIGN_WAIT_MS = 25_000;
const SWEEP_WAIT_MS = 20_000;

const POSIX = process.platform !== "win32";
const clip = (s) => (s.length > 300 ? s.slice(0, 300) + "..." : s);
const sleepMs = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

// One bounded command. A timeout or a spawn failure throws, so each caller names it.
function bounded(cmd, args, timeoutMs, opts = {}) {
  const r = spawnSync(cmd, args, { encoding: "utf8", timeout: timeoutMs, killSignal: "SIGKILL", windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"], ...opts });
  if (r.error) throw r.error;
  return r;
}

// The Windows orphan sweep by tree walk runs only in CI or when asked. It reads a process by name and
// path, so on a dev machine another session's process could match. With a job, or on POSIX with the
// env mark, a leftover is provably this run's and is always swept.
export const sweepAllowed = (ci, env) => ci || env.STAMP_SUITE_SWEEP === "1";

// The exit code, once the sweep has run. A leftover the sweep found fails the run whatever the
// suite's own code was, and whether or not a line named it. lines: one per leftover found. alive:
// pids still running after the kill. unknown: reads that could not run; the caller passes it on CI
// only, where a sweep that could not read must not pass. With none of them, the suite's own code.
export function leftoverExit(code, { lines = [], alive = [], unknown = [] } = {}) {
  if (lines.length || alive.length || unknown.length) return 1;
  return code ?? 1;
}

// The child calls it before its first test. Windows: it waits for the go file, which the watchdog
// writes once this process is in its job, or, off CI with no job, once it has chosen the fallback.
// A go file that never appears means the watchdog is dead or stuck, so no job, cap or sweep covers
// this process. It waits GO_WAIT_MS (default 40 s), then exits 1 before any test rather than run
// tests nothing watches.
export function waitForGo(env = process.env) {
  if (!env[GO]) return;
  const waitMs = Number(env[GO_WAIT_MS]) || 40_000;
  for (const t0 = Date.now(); !existsSync(env[GO]);) {
    if (Date.now() - t0 >= waitMs) {
      console.error(`FAIL - no go file at ${env[GO]} after ${waitMs} ms, so the watchdog is dead or stuck and no test ran`);
      process.exit(1);
    }
    sleepMs(50);
  }
}

// Linux and macOS: each live process of the run but this one, as { found: [{ pid, cmd }], unreadable }.
// unreadable is a reason, or null: a sweep that could not list processes found nothing out.
function markedProcesses(runId) {
  const mark = `${RUN}=${runId}`;
  const found = [];
  if (process.platform === "linux") {
    let names;
    try {
      names = readdirSync("/proc");
      readFileSync(`/proc/${process.pid}/environ`); // an environ the watchdog cannot read for itself reads for no one
    } catch (e) { return { found, unreadable: `/proc: ${e.message}` }; }
    for (const name of names) {
      if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
      try {
        if (!readFileSync(`/proc/${name}/environ`, "latin1").split("\0").includes(mark)) continue;
        found.push({ pid: Number(name), cmd: clip(readFileSync(`/proc/${name}/cmdline`, "latin1").replace(/\0/g, " ").trim()) });
      } catch {} // gone, or another user's, so not the suite's
    }
    return { found, unreadable: null };
  }
  const re = new RegExp(`(^|\\s)${mark}(\\s|$)`);
  try {
    const ps = bounded("ps", ["-axEww", "-o", "pid=,command="], 5_000, { maxBuffer: 1 << 26 });
    if (ps.status !== 0) return { found, unreadable: `ps exited ${ps.status}: ${clip(ps.stderr.trim())}` };
    for (const line of ps.stdout.split("\n")) {
      const m = /^\s*(\d+)\s+(.*)$/.exec(line);
      if (m && Number(m[1]) !== process.pid && re.test(m[2])) found.push({ pid: Number(m[1]), cmd: clip(m[2].replace(re, " ").trim()) });
    }
  } catch (e) { return { found, unreadable: `ps: ${e.message}` }; }
  return { found, unreadable: null };
}

// Waits up to graceMs for them to exit on their own, then kills each, in at most `rounds` passes, and
// returns what it saw: { lines, alive, unreadable }.
function sweepMarked(runId, graceMs, rounds = 3) {
  const seen = new Map();
  let unreadable = null;
  const scan = () => {
    const r = markedProcesses(runId);
    unreadable ??= r.unreadable;
    return r.found;
  };
  let now = scan();
  for (const t0 = Date.now(); now.length && Date.now() - t0 < graceMs;) { sleepMs(100); now = scan(); }
  for (let round = 0; round < rounds && now.length; round++) {
    for (const p of now) { seen.set(p.pid, p.cmd); try { process.kill(p.pid, "SIGKILL"); } catch {} }
    sleepMs(100);
    now = scan();
  }
  return { lines: [...seen].map(([pid, cmd]) => `${pid} ${cmd}`), alive: now.map((p) => p.pid), unreadable };
}

// The Windows job helper's script. One request per line on stdin, a reply ended by an END line.
//   assign <pid>   puts that process in the job; replies OK
//   sweep <ms>     waits up to ms for the members to end, lists the rest as LEFT <pid> <command line>, kills them
const JOB_PS = String.raw`$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class StampJob {
  [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateJobObject(IntPtr attrs, string name);
  [DllImport("kernel32.dll", SetLastError = true)] static extern bool SetInformationJobObject(IntPtr job, int cls, IntPtr info, int len);
  [DllImport("kernel32.dll", SetLastError = true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr proc);
  [DllImport("kernel32.dll", SetLastError = true)] static extern bool QueryInformationJobObject(IntPtr job, int cls, IntPtr info, int len, IntPtr ret);
  [DllImport("kernel32.dll", SetLastError = true)] static extern bool TerminateJobObject(IntPtr job, uint code);
  static IntPtr job;
  static void Fail(string what) { throw new Exception(what + " failed, error " + Marshal.GetLastWin32Error()); }
  public static void Create() {
    job = CreateJobObject(IntPtr.Zero, null);
    if (job == IntPtr.Zero) Fail("CreateJobObject");
    int len = IntPtr.Size == 8 ? 144 : 112;
    IntPtr p = Marshal.AllocHGlobal(len);
    for (int i = 0; i < len; i++) Marshal.WriteByte(p, i, 0);
    Marshal.WriteInt32(p, 16, 0x2000);
    bool ok = SetInformationJobObject(job, 9, p, len);
    Marshal.FreeHGlobal(p);
    if (!ok) Fail("SetInformationJobObject");
  }
  public static void Assign(IntPtr proc) { if (!AssignProcessToJobObject(job, proc)) Fail("AssignProcessToJobObject"); }
  public static void Terminate() { if (!TerminateJobObject(job, 1)) Fail("TerminateJobObject"); }
  public static int[] Members() {
    int n = 4096, len = 8 + IntPtr.Size * n;
    IntPtr p = Marshal.AllocHGlobal(len);
    try {
      for (int i = 0; i < len; i++) Marshal.WriteByte(p, i, 0);
      if (!QueryInformationJobObject(job, 3, p, len, IntPtr.Zero) && Marshal.GetLastWin32Error() != 234) Fail("QueryInformationJobObject");
      int c = Math.Min(Marshal.ReadInt32(p, 4), n);
      int[] ids = new int[c];
      for (int i = 0; i < c; i++) ids[i] = (int)Marshal.ReadIntPtr(p, 8 + i * IntPtr.Size);
      return ids;
    } finally { Marshal.FreeHGlobal(p); }
  }
}
'@
function Emit([string]$s) { [Console]::Out.WriteLine($s); [Console]::Out.Flush() }
$createError = $null
try { [StampJob]::Create() } catch { $createError = $_.Exception.Message }
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line -or $line -eq 'quit') { break }
  $parts = $line.Split(' ')
  try {
    if ($createError) { throw $createError }
    if ($parts[0] -eq 'assign') {
      $proc = [System.Diagnostics.Process]::GetProcessById([int]$parts[1])
      [StampJob]::Assign($proc.Handle)
      Emit 'OK'
    } elseif ($parts[0] -eq 'sweep') {
      $grace = [int]$parts[1]
      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      $ids = @([StampJob]::Members())
      while ($ids.Count -gt 0 -and $sw.ElapsedMilliseconds -lt $grace) { Start-Sleep -Milliseconds 100; $ids = @([StampJob]::Members()) }
      if ($ids.Count -gt 0) {
        $cmd = @{}
        try { foreach ($w in Get-CimInstance Win32_Process) { if ($ids -contains [int]$w.ProcessId) { $cmd[[int]$w.ProcessId] = ($w.CommandLine -replace '\s+', ' ') } } } catch {}
        foreach ($id in $ids) { $c = $cmd[[int]$id]; if (-not $c) { $c = '(command line unreadable)' }; Emit ('LEFT ' + $id + ' ' + $c) }
        [StampJob]::Terminate()
        $sw.Restart()
        $ids = @([StampJob]::Members())
        while ($ids.Count -gt 0 -and $sw.ElapsedMilliseconds -lt 5000) { Start-Sleep -Milliseconds 100; $ids = @([StampJob]::Members()) }
        if ($ids.Count -gt 0) { Emit ('ALIVE ' + ($ids -join ' ')) }
      }
    }
  } catch { Emit ('ERR ' + $_.Exception.Message) }
  Emit 'END'
}
`;

// Starts the helper. ask(cmd, ms) resolves to the reply's lines, or null when it gave none in ms.
function jobHelper() {
  const ps = spawn("powershell", ["-NoProfile", "-NonInteractive", "-EncodedCommand", Buffer.from(JOB_PS, "utf16le").toString("base64")],
    { stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
  const lines = [];
  let buf = "", errText = "", waiter = null, dead = false;
  ps.stdout.setEncoding("utf8");
  ps.stderr.setEncoding("utf8");
  ps.stdout.on("data", (d) => {
    const parts = (buf + d).split(/\r?\n/);
    buf = parts.pop();
    lines.push(...parts);
    waiter?.();
  });
  ps.stderr.on("data", (d) => { errText += d; });
  ps.stdin.on("error", () => {});
  ps.on("close", () => { dead = true; waiter?.(); });
  // No powershell on the path, or it cannot start: an event, not a crash, and no reply ever comes.
  ps.on("error", (e) => { errText += ` ${e.message}`; dead = true; waiter?.(); });
  const ask = (cmd, ms) => new Promise((resolve) => {
    if (dead) return resolve(null);
    lines.length = 0;
    const timer = setTimeout(() => { waiter = null; resolve(null); }, ms);
    waiter = () => {
      const end = lines.indexOf("END");
      if (end < 0 && !dead) return;
      clearTimeout(timer);
      waiter = null;
      resolve(end < 0 ? null : lines.splice(0, end + 1).slice(0, -1));
    };
    try { ps.stdin.write(cmd + "\n"); } catch { waiter(); }
  });
  // Ending the helper closes the job, and KILL_ON_JOB_CLOSE ends every member still in it.
  const stop = () => {
    try { ps.stdin.end(); } catch {}
    try { ps.kill(); } catch {}
    ps.stdout.destroy();
    ps.stderr.destroy();
    ps.unref();
  };
  return { ask, stop, isDead: () => dead, why: () => clip(errText.trim().replace(/\s+/g, " ")) };
}

// POSIX: each live process in the child's group, with its command line. The child leads its own
// group, so the group holds even an orphan. ps is fast, so it lists before the kill.
function posixTree(root) {
  try {
    const ps = bounded("ps", ["-eo", "pid=,ppid=,pgid=,args="], 5_000);
    return ps.stdout.split("\n").filter((l) => l.trim().split(/\s+/)[2] === String(root));
  } catch (e) {
    return [`(process tree unreadable: ${e.message})`];
  }
}

// Windows, with no job: processes the tree kill missed. An orphan's parent pid names a dead
// process, and a dead parent's own parent is unreadable, so "ours" is read from what is left: a
// process the suite's programs run, started after the suite, whose parent is dead, and whose command
// line names a fixture dir. Plus their trees. Only the root's tree when sweepAllowed says no.
function windowsLeftovers(root, startedAt, sweep, tempPrefix) {
  const prefix = tempPrefix.replace(/'/g, "''");
  const walk = `$start = [datetime]::Parse('${new Date(startedAt).toISOString()}');
$all = @(Get-CimInstance Win32_Process); $live = @{}; foreach ($p in $all) { $live[[int]$p.ProcessId] = 1 }
$ids = @(${root});
if ($${sweep ? "true" : "false"}) { foreach ($p in $all) { if ($p.CreationDate -gt $start -and -not $live.ContainsKey([int]$p.ParentProcessId) -and $p.Name -match '^(node|git|git-[\\w-]+|bash|sh)\\.exe$' -and $p.CommandLine -and $p.CommandLine.Contains('${prefix}')) { $ids += [int]$p.ProcessId } } }
for ($i = 0; $i -lt $ids.Count; $i++) { foreach ($p in $all) { if ($p.ParentProcessId -eq $ids[$i] -and $ids -notcontains $p.ProcessId) { $ids += [int]$p.ProcessId } } }
foreach ($p in $all) { if ($ids -contains $p.ProcessId) { '{0} {1} {2}' -f $p.ProcessId, $p.ParentProcessId, ($p.CommandLine -replace '\\s+', ' ') } }`;
  try {
    const ps = bounded("powershell", ["-NoProfile", "-NonInteractive", "-Command", walk], 15_000);
    return ps.stdout.split(/\r?\n/).filter((l) => l.trim());
  } catch (e) {
    return [`(leftover processes unreadable: ${e.message})`];
  }
}

const taskkill = (pids) => {
  try {
    return bounded("taskkill", ["/T", "/F", ...pids.flatMap((p) => ["/PID", String(p)])], 10_000).stdout;
  } catch (e) {
    return `(taskkill failed: ${e.message})`;
  }
};

// Runs the suite file `self` as a child under the watchdog and sets process.exitCode.
//   ci          true when the runner is CI (the caller reads GITHUB_ACTIONS before it clears it)
//   tempPrefix  the start of every fixture dir name, for the Windows tree-walk fallback
export async function watchdog({ self, ci, tempPrefix }) {
  const capS = Number(process.env.STAMP_SUITE_CAP_S) || DEFAULT_CAP_S;
  const runId = randomUUID();
  const startedAt = Date.now() - 1000;
  const goFile = POSIX ? null : join(tmpdir(), `stamp-suite-go-${runId}`);
  const env = { ...process.env, [CHILD]: "1", [RUN]: runId };
  if (goFile) env[GO] = goFile; else delete env[GO];
  const child = spawn(process.execPath, [self], { env, stdio: ["ignore", "pipe", "pipe"], detached: POSIX, windowsHide: true });
  let current = null, pending = "", over = false, closed = false, stopping = false, timer;
  const forward = (line) => {
    const bare = line.replace(/\r$/, "");
    if (bare.startsWith(START)) current = bare.slice(START.length);
    else process.stdout.write(line + "\n");
  };
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (d) => {
    const lines = (pending + d).split("\n");
    pending = lines.pop();
    lines.forEach(forward);
  });
  child.stderr.on("data", (d) => process.stderr.write(d));
  const flush = () => { if (pending) { forward(pending); pending = ""; } };

  // Windows: put the child in the job before it runs a test (startJob, below). On CI a run with no
  // job fails by name. Off CI the child still starts, and leftovers are found by walking the tree.
  const forceNoJob = !POSIX && process.env[NO_JOB] === "1";
  const job = POSIX || forceNoJob ? null : jobHelper();
  let jobOk = false, noJob = null, jobReady = Promise.resolve();

  // Lists and kills what the suite left running: { lines, alive, unknown, notes }. unknown holds the
  // reads that could not run: they are named, and never read as "nothing left".
  const sweep = async (graceMs) => {
    const r = await sweepFound(graceMs);
    const fault = process.env[SWEEP_FAULT];
    if (fault === "alive") return { ...r, alive: [...r.alive, String(child.pid)] };
    if (fault === "unknown") return { ...r, unknown: [...r.unknown, `${SWEEP_FAULT}=unknown`] };
    return r;
  };
  const sweepFound = async (graceMs) => {
    await jobReady;
    if (POSIX) {
      const r = sweepMarked(runId, graceMs);
      return { lines: r.lines, alive: r.alive, unknown: r.unreadable ? [r.unreadable] : [], notes: [] };
    }
    if (jobOk) {
      const r = await job.ask(`sweep ${graceMs}`, SWEEP_WAIT_MS);
      if (!r) {
        job.stop(); // closing the job ends every process in it
        return { lines: [], alive: [], notes: [],
          unknown: [`the job sweep gave no answer in ${SWEEP_WAIT_MS / 1000} s; the job was closed, which ends every process in it`] };
      }
      return {
        lines: r.filter((l) => l.startsWith("LEFT ")).map((l) => l.slice(5)),
        alive: r.filter((l) => l.startsWith("ALIVE ")).flatMap((l) => l.slice(6).split(" ")),
        unknown: r.filter((l) => l.startsWith("ERR ")).map((l) => l.slice(4)),
        notes: [],
      };
    }
    taskkill([child.pid]);
    const left = windowsLeftovers(child.pid, startedAt, sweepAllowed(ci, process.env), tempPrefix);
    const pids = left.map((l) => l.split(" ")[0]).filter((p) => /^\d+$/.test(p));
    if (pids.length) taskkill(pids);
    return {
      lines: left.filter((l) => !l.startsWith("(")), alive: [],
      unknown: left.filter((l) => l.startsWith("(")).map((l) => l.slice(1, -1)),
      notes: noJob ? [`(no job object: ${noJob}; leftovers are found by walking the process tree)`] : [],
    };
  };

  // Ends without process.exit, so the output still queued on a Windows pipe drains first.
  const finish = (code) => {
    if (over) return;
    over = true;
    clearTimeout(timer);
    clearTimeout(hard);
    flush();
    child.stdout.destroy();
    child.stderr.destroy();
    child.unref();
    job?.stop();
    if (goFile) { try { rmSync(goFile, { force: true }); } catch {} }
    process.exitCode = code;
  };
  const report = (r) => {
    for (const n of r.notes) console.error(n);
    for (const u of r.unknown) console.error(`unknown - leftover sweep could not read: ${u}`);
    if (r.alive.length) console.error(`Still running after the kill: ${r.alive.join(" ")}`);
  };
  const stopTree = async (why) => {
    if (over || stopping) return;
    stopping = true;
    flush();
    console.error(why);
    if (POSIX) {
      const lines = posixTree(child.pid);
      console.error(lines.length ? lines.join("\n") : "(none)");
      try { process.kill(-child.pid, "SIGKILL"); } catch {}
      sleepMs(200); // the group's own processes finish dying, so they do not read as outside it
    }
    const r = await sweep(0);
    if (r.lines.length) console.error((POSIX ? "Outside its process group, killed now:\n" : "") + r.lines.join("\n"));
    else if (!POSIX) console.error("(none)");
    report(r);
    finish(1);
  };
  // On CI the suite needs its job: without one it cannot find what it leaves running. The child has
  // not been released, so it has run no test. Its tree is killed and the run fails by name.
  const failBeforeTests = (message) => {
    if (over || stopping) return;
    stopping = true;
    flush();
    console.error(message);
    const killed = taskkill([child.pid]).trim();
    if (killed) console.error(killed);
    finish(1);
  };
  const failNoJob = () => failBeforeTests(
    `FAIL - no job object: ${noJob}. On CI the suite must put its tests in one, to find and kill what they leave running.`);
  // Ends the process once what is queued on stdout and stderr is written, or after 2 s. A pipe on
  // Windows may write asynchronously, and process.exit would cut the queue.
  const exitAfterDrain = (code) => {
    let left = 2;
    const done = () => { if (--left === 0) process.exit(code); };
    process.stdout.write("", done);
    process.stderr.write("", done);
    setTimeout(() => process.exit(code), 2000);
  };
  // The last bound: stop everything and exit, whatever a call above is still waiting on.
  const hard = setTimeout(() => {
    if (over) return;
    over = true;
    flush();
    console.error(`FAIL - ${current ?? "(before the first test)"}\nThe watchdog passed its own bound (${capS} s cap + ${HARD_STOP_AFTER_CAP_S} s) and stopped the suite.`);
    if (POSIX) { try { process.kill(-child.pid, "SIGKILL"); } catch {} sweepMarked(runId, 0, 1); }
    else { job?.stop(); taskkill([child.pid]); }
    exitAfterDrain(1);
  }, (capS + HARD_STOP_AFTER_CAP_S + (process.env[HANG] ? 30 : 0)) * 1000);
  hard.unref();

  const arm = () => {
    timer = setTimeout(() => stopTree(
      `FAIL - ${current ?? "(before the first test)"}\nThe suite ran past its ${capS} s cap (STAMP_SUITE_CAP_S). Processes under it:`,
    ), capS * 1000);
  };
  // The proof's cap counts from the fixture's pid file, so a slow start cannot read red early.
  if (process.env[HANG]) {
    const t0 = Date.now();
    const wait = setInterval(() => {
      if (existsSync(process.env[HANG]) || Date.now() - t0 > 30_000) { clearInterval(wait); if (!over) arm(); }
    }, 50);
    wait.unref();
  } else arm();

  // A close is the normal end, and still a failure when a process the suite started runs on.
  child.on("close", async (code) => {
    if (over || stopping) return;
    closed = true;
    clearTimeout(timer);
    const r = await sweep(LEFTOVER_GRACE_MS);
    flush();
    if (r.lines.length || r.alive.length) console.error(`FAIL - the suite left processes running:${r.lines.length ? "\n" + r.lines.join("\n") : ""}`);
    report(r);
    finish(leftoverExit(code, { lines: r.lines, alive: r.alive, unknown: ci ? r.unknown : [] }));
  });
  // An exit with no close means a process the suite started still holds its output.
  child.on("exit", (code) => {
    clearTimeout(timer);
    setTimeout(() => { if (!closed) stopTree(`FAIL - the suite exited ${code}, but a process it started still holds its output:`); }, 5000).unref();
  });
  for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => stopTree(`Stopped by ${sig}. Processes under the suite:`));

  // Windows: the child waits on the go-file, so this ends before any test runs. On CI no job means
  // no release: the run fails, and the child is killed where it waits.
  if (!POSIX) {
    jobReady = (async () => {
      if (forceNoJob) noJob = `${NO_JOB}=1 asked for no job object`;
      else {
        const r = await job.ask(`assign ${child.pid}`, ASSIGN_WAIT_MS);
        jobOk = r?.[0] === "OK";
        if (!jobOk) {
          const why = job.why();
          noJob = r ? `the job helper said: ${r.join(" ")}`
            : job.isDead() ? `the PowerShell helper did not run${why ? `: ${why}` : ""}`
            : `the job helper gave no answer in ${ASSIGN_WAIT_MS / 1000} s`;
        }
      }
      if (!jobOk && ci) { failNoJob(); return; }
      // On CI the child never runs a test outside the job: with no job the run has failed above. Off CI
      // with no job, the documented fallback releases the child anyway, with a printed note. Either way
      // a go file that cannot be written is a failure, since the child would wait for it unreleased.
      try {
        if (process.env[GO_FAIL] === "1") throw new Error(`${GO_FAIL}=1 asked for a failed write`);
        writeFileSync(goFile, "go");
      } catch (e) {
        failBeforeTests(`FAIL - go file: ${e.message}. The suite's tests start only once it is written, so none ran.`);
      }
    })();
  }
}
