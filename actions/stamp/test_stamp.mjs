#!/usr/bin/env node
// Runnable self-test for stamp.mjs. `node actions/stamp/test_stamp.mjs`. No framework: each
// test is a function that throws via `node:assert` on failure. Every test builds its own
// throwaway directory under the OS temp dir and removes it when done, so tests never touch this
// repository's own tree and never share state with each other.

import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, readdirSync, statSync } from "node:fs";
import { execFileSync, spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { stamp, claim, check, loadConfig, currentBranch, onDefaultBranch } from "./stamp.mjs";

// Each fixture builds its own git repo. A CI run's GITHUB_REF and GITHUB_BASE_REF name the
// runner's branch, not the fixture's. GITHUB_ACTIONS picks a hard refusal or an UNKNOWN line
// for an unreadable base, so each test that reads one sets it itself.
delete process.env.GITHUB_REF;
delete process.env.GITHUB_BASE_REF;
delete process.env.GITHUB_ACTIONS;

// A fixture repo has no remote. The off-branch question reads the local default branch instead.
const LOCAL = { base: "main" };

const HERE = dirname(fileURLToPath(import.meta.url));

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

function withTempDir(fn) {
  const dir = mkdtempSync(join(tmpdir(), "stamp-test-"));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function write(root, rel, content) {
  const abs = join(root, rel);
  mkdirSync(join(abs, ".."), { recursive: true });
  writeFileSync(abs, content);
}

function read(root, rel) {
  return readFileSync(join(root, rel), "utf8");
}

function git(root, ...args) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8" });
}

function initRepo(root) {
  git(root, "init", "-q", "-b", "main");
  git(root, "config", "user.email", "test@example.com");
  git(root, "config", "user.name", "test");
  git(root, "config", "core.autocrlf", "false"); // quiet; this suite writes LF and reads it back
}

function commit(root, message) {
  git(root, "add", "-A");
  git(root, "commit", "-q", "-m", message);
}

// The CLI's --check, with GITHUB_ACTIONS set to `actions` ("true") or left out (undefined).
function runCheck(root, configPath, actions, extra = []) {
  const env = { ...process.env };
  delete env.GITHUB_ACTIONS;
  if (actions !== undefined) env.GITHUB_ACTIONS = actions;
  return spawnSync("node", [join(HERE, "stamp.mjs"), "--check", ...extra, "--config", configPath], { cwd: root, encoding: "utf8", env });
}

function withEnv(name, value, fn) {
  const old = process.env[name];
  process.env[name] = value;
  try {
    return fn();
  } finally {
    if (old === undefined) delete process.env[name];
    else process.env[name] = old;
  }
}

// ---------------------------------------------------------------- format 1: frontmatter only,
// max_plus_one, merge order, allowRanges
const frontmatterConfig = () => loadConfig(join(HERE, "examples/frontmatter.stamp.json"));

test("frontmatter-only: pending records get distinct, sequential numbers in merge order", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/first.md", "---\nid: D-001\nslug: first\ntitle: First\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "add first");
    write(root, "docs/decisions/second.md", "---\nid: pending\nslug: second\ntitle: Second\ndate: 2026-01-02\n---\n\nCites [[third]].\n");
    write(root, "docs/decisions/third.md", "---\nid: pending\nslug: third\ntitle: Third\ndate: 2026-01-03\n---\n\nBody.\n");
    commit(root, "two branches merge in one run: second, then third");

    const config = frontmatterConfig();
    const result = stamp(root, config);
    assert.equal(result.problems.length, 0);
    assert.equal(result.assigned.length, 2);
    // Merge order is read from git, oldest add first: second's file was added before third's, in
    // the same commit, and the two-branches case this test names is exactly "more than one
    // pending record land before the stamp runs" — they must not collide.
    const bySlug = new Map(result.assigned.map((a) => [a.slug, a.id]));
    assert.equal(bySlug.get("second"), "D-002");
    assert.equal(bySlug.get("third"), "D-003");
    assert.equal(read(root, "docs/decisions/second.md").includes("id: D-002"), true);
    // The cite rewrite ran: [[third]] became "D-003, Third".
    assert.equal(read(root, "docs/decisions/second.md").includes("Cites D-003, Third."), true);
  }));

test("frontmatter-only: an existing range is parsed for the max, never produced", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/ranged.md", "---\nid: D-044 to D-046\nslug: ranged\ntitle: Ranged\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "docs/decisions/next.md", "---\nid: pending\nslug: next\ntitle: Next\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "add ranged and next");

    const result = stamp(root, frontmatterConfig());
    assert.equal(result.problems.length, 0);
    assert.equal(result.assigned[0].id, "D-047");
  }));

// ---------------------------------------------------------------- format 1: lowest_free, date
// order, a cite that names its own prefix
const prefixedCiteConfig = () => loadConfig(join(HERE, "examples/frontmatter-prefixed-cite.stamp.json"));

test("frontmatter-only, lowest_free: a gap in the taken numbers is filled before the max", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "decisions/one.md", "---\nid: D1\nslug: one\nkind: decision\nstatus: open\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "decisions/three.md", "---\nid: D3\nslug: three\nkind: decision\nstatus: open\ndate: 2026-01-02\n---\n\nBody.\n");
    write(root, "decisions/pending-one.md", "---\nid: pending\nslug: gap-fill\nkind: decision\nstatus: open\ndate: 2026-01-03\n---\n\nCited as D‹gap-fill›.\n");
    commit(root, "one, three, and a pending record");

    const result = stamp(root, prefixedCiteConfig());
    assert.equal(result.problems.length, 0);
    assert.equal(result.assigned[0].id, "D2");
    // A "{id}" template writes the bare id, no gloss.
    assert.equal(read(root, "decisions/pending-one.md").includes("Cited as D2."), true);
  }));

test("frontmatter-only cite: a citation naming the wrong kind's letter is left unresolved", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "decisions/one.md", "---\nid: D1\nslug: shared-slug\nkind: decision\nstatus: open\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "findings/two.md", "---\nid: pending\nslug: other-slug\nkind: finding\nstatus: observed\ndate: 2026-01-02\n---\n\nCited wrongly as F‹shared-slug›.\n");
    commit(root, "mismatched prefix");

    stamp(root, prefixedCiteConfig());
    // "shared-slug" is a D record. "F<shared-slug>" names the wrong letter, so it is left as
    // text rather than resolved to the D record's id.
    assert.equal(read(root, "findings/two.md").includes("Cited wrongly as F‹shared-slug›."), true);
  }));

// ---------------------------------------------------------------- format 2: frontmatter AND
// filename, lowest_free, date order, a required gloss
const filenameConfig = () => loadConfig(join(HERE, "examples/frontmatter-filename.stamp.json"));

test("frontmatter+filename: a pending record is renamed and its cite gains its gloss", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/_2026-01-05-widgets.md",
      '---\nid:\nslug: widgets\ngloss: "widgets ship in v2"\ndate: 2026-01-05\n---\n\nBody.\n');
    write(root, "README.md", "See [[widgets]] for the plan.\n");
    commit(root, "add a pending record with an underscore filename");

    const result = stamp(root, filenameConfig());
    assert.equal(result.problems.length, 0);
    assert.equal(result.assigned[0].id, "D1");
    assert.equal(existsSync(join(root, "docs/decisions/D1_2026-01-05-widgets.md")), true);
    assert.equal(existsSync(join(root, "docs/decisions/_2026-01-05-widgets.md")), false);
    assert.equal(read(root, "docs/decisions/D1_2026-01-05-widgets.md").includes("id: D1"), true);
    assert.equal(read(root, "README.md").includes("See D1, widgets ship in v2 for the plan."), true);
  }));

test("frontmatter+filename: a pending record missing a required field refuses --stamp and writes nothing", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/_no-date.md", '---\nid:\nslug: no-date\ngloss: "no date here"\n---\n\nBody.\n');
    commit(root, "add a malformed pending record");

    const before = read(root, "docs/decisions/_no-date.md");
    const result = stamp(root, filenameConfig());
    assert.equal(result.problems.length > 0, true);
    assert.equal(result.assigned.length, 0);
    assert.equal(read(root, "docs/decisions/_no-date.md"), before);
    assert.equal(existsSync(join(root, "docs/decisions/D1_no-date.md")), false);
  }));

// ---------------------------------------------------------------- --check, structural
test("--check refuses a duplicate id", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "docs/decisions/b.md", "---\nid: D-001\nslug: b\ntitle: B\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "two records, one id");

    const problems = check(root, frontmatterConfig());
    assert.equal(problems.some((p) => p.includes("duplicate id D-001")), true);
  }));

test("--check refuses a cite that points at no record", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "README.md", "See [[does-not-exist]].\n");
    commit(root, "a dangling cite");

    const problems = check(root, frontmatterConfig());
    assert.equal(problems.some((p) => p.includes("does-not-exist")), true);
  }));

test("--check refuses a malformed record (neither pending nor numbered)", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: not-a-number\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a malformed record");

    const problems = check(root, frontmatterConfig());
    assert.equal(problems.some((p) => p.includes("malformed record")), true);
  }));

test("--check is silent on a well-formed tree", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "README.md", "See D-001, A.\n");
    commit(root, "a clean tree");

    assert.deepEqual(check(root, frontmatterConfig()), []);
  }));

// ---------------------------------------------------------------- --check, the default-branch
// question. The claim runs before the merge, so a pending record on the default branch is
// refused, whichever commit added it.
test("--check on the default branch refuses a pending record older than HEAD", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/old.md", "---\nid: pending\nslug: old\ntitle: Old\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "add old, still pending");
    write(root, "docs/decisions/unrelated.md", "---\nid: D-001\nslug: unrelated\ntitle: Unrelated\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "an unrelated later commit");

    assert.equal(currentBranch(root), "main");
    const config = frontmatterConfig(); // defaultBranch: "main"
    const problems = check(root, config);
    assert.equal(problems.some((p) => p.includes("docs/decisions/old.md") && p.includes("pending")), true);
  }));

test("--check on the default branch refuses a pending record HEAD itself just added", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/settled.md", "---\nid: D-001\nslug: settled\ntitle: Settled\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a settled record");
    write(root, "docs/decisions/fresh.md", "---\nid: pending\nslug: fresh\ntitle: Fresh\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "fresh, never claimed");

    const problems = check(root, frontmatterConfig());
    assert.equal(problems.length, 1);
    assert.match(problems[0], /docs\/decisions\/fresh\.md is still pending on main/);
  }));

test("frontmatter --check passes a pending record on a feature branch, and never asks the default-branch question there", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/settled.md", "---\nid: D-001\nslug: settled\ntitle: Settled\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "docs/decisions/old.md", "---\nid: pending\nslug: old\ntitle: Old\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a settled record, and one still pending");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/newer.md", "---\nid: pending\nslug: newer\ntitle: Newer\ndate: 2026-01-02\n---\n\nBody.\n");
    write(root, "docs/decisions/settled.md", "---\nid: D-001\nslug: settled\ntitle: Settled, retitled\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "another pending record on a branch, and an edit to a numbered one");

    assert.equal(currentBranch(root), "wt/lane");
    assert.deepEqual(check(root, frontmatterConfig(), LOCAL), []);
  }));

// ---------------------------------------------------------------- --check, the off-branch
// question: a record numbered on a branch is refused, for every shape, against the base tree.
test("frontmatter --check refuses a new record numbered on a feature branch", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/b.md", "---\nid: D-002\nslug: b\ntitle: B\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "a branch numbers its own record");

    const problems = check(root, frontmatterConfig(), LOCAL);
    assert.equal(problems.length, 1);
    assert.equal(problems[0].includes("docs/decisions/b.md") && problems[0].includes("D-002") && problems[0].includes("on a branch"), true);
  }));

test("frontmatter --check refuses a record pending on the base and numbered on the branch", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: pending\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "main, with a pending record");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a branch claims the pending record by hand");

    const problems = check(root, frontmatterConfig(), LOCAL);
    assert.equal(problems.some((p) => p.includes("docs/decisions/a.md") && p.includes("D-001") && p.includes("on a branch")), true);
  }));

test("frontmatter --check refuses a numbered record moved to a new number on a branch", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/a.md", "---\nid: D-007\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a branch renumbers a record");

    assert.equal(check(root, frontmatterConfig(), LOCAL).some((p) => p.includes("D-007")), true);
  }));

test("frontmatter+filename --check refuses a record numbered on a feature branch", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "one"\ndate: 2026-01-01\n---\n\nBody.\n');
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D2_two.md", '---\nid: D2\nslug: two\ngloss: "two"\ndate: 2026-01-02\n---\n\nBody.\n');
    commit(root, "a branch numbers its own record");

    const problems = check(root, filenameConfig(), LOCAL);
    assert.equal(problems.length, 1);
    assert.equal(problems[0].includes("docs/decisions/D2_two.md") && problems[0].includes("on a branch"), true);
  }));

test("frontmatter+filename --check passes a pending record on a feature branch", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "one"\ndate: 2026-01-01\n---\n\nBody.\n');
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/_two.md", '---\nid:\nslug: two\ngloss: "two"\ndate: 2026-01-02\n---\n\nBody.\n');
    commit(root, "a branch writes a slug");

    assert.deepEqual(check(root, filenameConfig(), LOCAL), []);
  }));

test("--check in GitHub Actions refuses to pass when the base ref cannot be read, and the CLI exits non-zero", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");

    // No remote, so the default base, origin/main, does not exist.
    const problems = withEnv("GITHUB_ACTIONS", "true", () => check(root, frontmatterConfig()));
    assert.equal(problems.length, 1);
    assert.equal(problems[0].includes("could not run") && problems[0].includes("origin/main") && problems[0].includes("fetch-depth: 0"), true);

    const cfg = join(HERE, "examples/frontmatter.stamp.json");
    const run = runCheck(root, cfg, "true");
    assert.equal(run.status, 1);
    assert.equal(run.stderr.includes("could not run"), true);
    // --base names a ref git can read, and the same tree passes.
    assert.equal(runCheck(root, cfg, "true", ["--base", "main"]).status, 0);
  }));

// Every way the base can be unreadable: a ref git cannot read, no defaultBranch and no --base,
// and a tree with no git. In GitHub Actions each fails. Elsewhere each prints UNKNOWN and exits 0,
// and never claims the tree is in order.
test("--check with an unreadable base fails in GitHub Actions, and prints UNKNOWN and exits 0 elsewhere", () =>
  withTempDir((root) => {
    const record = "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n";
    const noDefault = JSON.parse(read(HERE, "examples/frontmatter.stamp.json"));
    delete noDefault.defaultBranch;
    const cases = {
      "unreadable ref": { repo: true, config: JSON.parse(read(HERE, "examples/frontmatter.stamp.json")), remedy: "fetch-depth: 0" },
      "no defaultBranch, no --base": { repo: true, config: noDefault, remedy: "pass --base <ref>" },
      "no git": { repo: false, config: JSON.parse(read(HERE, "examples/frontmatter.stamp.json")), remedy: "fetch-depth: 0" },
    };
    for (const [name, c] of Object.entries(cases)) {
      const dir = join(root, name.replace(/[^a-z]+/g, "-"));
      mkdirSync(dir);
      write(dir, "docs/decisions/a.md", record);
      if (c.repo) {
        initRepo(dir);
        commit(dir, "main");
        git(dir, "checkout", "-q", "-b", "wt/lane");
      }
      const cfg = join(root, `${name.replace(/[^a-z]+/g, "-")}.json`);
      writeFileSync(cfg, JSON.stringify(c.config));

      const ci = runCheck(dir, cfg, "true");
      assert.equal(ci.status, 1, `${name}: CI exit`);
      assert.equal(ci.stderr.includes("could not run") && ci.stderr.includes(c.remedy), true, `${name}: CI names the remedy`);
      assert.equal(ci.stderr.includes("UNKNOWN"), false, `${name}: CI prints no UNKNOWN`);

      const local = runCheck(dir, cfg, undefined);
      assert.equal(local.status, 0, `${name}: local exit`);
      const lines = local.stderr.split("\n").filter(Boolean);
      assert.equal(lines.length, 1, `${name}: one line`);
      assert.equal(lines[0].startsWith("UNKNOWN:") && lines[0].includes(c.remedy), true, `${name}: the UNKNOWN line names the remedy`);
      assert.equal(local.stdout.includes("in order"), false, `${name}: no in-order line`);
    }
  }));

test("--check reads GITHUB_BASE_REF for the base, and a pull_request checkout is off the default branch", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "base");
    git(root, "branch", "base-branch");
    write(root, "docs/decisions/b.md", "---\nid: D-002\nslug: b\ntitle: B\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "numbered here, on a branch named main locally");
    // A fixture remote named origin, so origin/base-branch resolves the way a CI fetch makes it.
    git(root, "remote", "add", "origin", root);
    git(root, "fetch", "-q", "origin", "base-branch:refs/remotes/origin/base-branch");

    const config = frontmatterConfig();
    assert.equal(onDefaultBranch(root, config), true);
    try {
      process.env.GITHUB_BASE_REF = "base-branch";
      assert.equal(onDefaultBranch(root, config), false);
      const problems = check(root, config);
      assert.equal(problems.some((p) => p.includes("D-002") && p.includes("origin/base-branch")), true);
      delete process.env.GITHUB_BASE_REF;
      process.env.GITHUB_REF = "refs/pull/7/merge";
      assert.equal(onDefaultBranch(root, config), false);
    } finally {
      delete process.env.GITHUB_BASE_REF;
      delete process.env.GITHUB_REF;
    }
  }));

// ---------------------------------------------------------------- format 3: the number in a
// heading, and for a split corpus in the filename too.
const headingConfig = () => loadConfig(join(HERE, "examples/heading.stamp.json"));

// Python's json.dumps(indent=2), the byte shape the manifest holds.
const manifestText = (order) => JSON.stringify({ order }, null, 2) + "\n";

function headingTree(root, { order = ["_preamble.md", "D001-one.md", "D003-three.md"] } = {}) {
  write(root, "docs/decisions/ORDER.json", manifestText(order));
  write(root, "docs/decisions/_preamble.md", "# Settled decisions\n");
  write(root, "docs/decisions/D001-one.md", "## D1 — One\n\nBody.\n");
  // D2 is a hole, on purpose: max_plus_one never reuses one.
  write(root, "docs/decisions/D003-three.md", "## D3 — Three\n\nBody.\n");
  write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\nBody.\n");
}

// Every file under root, as text, for a "nothing was written" assertion.
function snapshot(root) {
  const out = {};
  (function go(dir, rel) {
    for (const name of readdirSync(dir)) {
      if (name === ".git") continue;
      const abs = join(dir, name);
      const r = rel ? `${rel}/${name}` : name;
      if (statSync(abs).isDirectory()) go(abs, r);
      else out[r] = readFileSync(abs, "utf8");
    }
  })(root, "");
  return out;
}

test("heading: the filename pads to 3 digits and the heading does not", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");
    write(root, "README.md", "See D-two-thing.\n");

    const result = stamp(root, headingConfig());
    assert.deepEqual(result.problems, []);
    assert.equal(result.assigned[0].id, "D4");
    assert.equal(existsSync(join(root, "docs/decisions/D-two-thing.md")), false);
    assert.equal(read(root, "docs/decisions/D004-two-thing.md").split("\n")[0], "## D4 — Two thing");
    assert.equal(read(root, "README.md"), "See D4.\n");
  }));

test("heading: ORDER.json gets the new name in the old name's own place", () =>
  withTempDir((root) => {
    headingTree(root, { order: ["_preamble.md", "D001-one.md", "D-two-thing.md", "D003-three.md"] });
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");

    stamp(root, headingConfig());
    assert.equal(read(root, "docs/decisions/ORDER.json"),
      manifestText(["_preamble.md", "D001-one.md", "D004-two-thing.md", "D003-three.md"]));
  }));

test("heading: an unlisted entry leaves ORDER.json alone, for regenerate to append", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");
    const before = read(root, "docs/decisions/ORDER.json");

    stamp(root, headingConfig());
    assert.equal(read(root, "docs/decisions/ORDER.json"), before);
  }));

test("heading: a gap in the sequence is never reused", () =>
  withTempDir((root) => {
    headingTree(root); // D1 and D3, no D2
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");
    write(root, "docs/decisions/D-zed-thing.md", "## D-zed-thing — Zed thing\n\nBody.\n");

    const result = stamp(root, headingConfig());
    assert.deepEqual(result.assigned.map((a) => a.id), ["D4", "D5"]);
    assert.equal(existsSync(join(root, "docs/decisions/D002-two-thing.md")), false);
  }));

test("heading: a pending heading in the flat corpus is numbered in place, and cites follow", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C-new-code — New code\n\nBody.\n");
    write(root, "docs/specs/a.md",
      "C-new-code, C-new-code-longer, and `docs/decisions/D-two-thing.md` by path. D-two-thing too.\n");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "node_modules/x.md", "C-new-code\n");
    write(root, ".github/x.md", "C-new-code\n");
    write(root, "docs/x.csv", "C-new-code\n");

    const result = stamp(root, headingConfig());
    assert.deepEqual(result.problems, []);
    assert.equal(read(root, "docs/codes.md"), "# Codes\n\n## C1 — First\n\n## C2 — New code\n\nBody.\n");
    assert.equal(read(root, "docs/specs/a.md"), "C2, C-new-code-longer, and D4 by path. D4 too.\n");
    // Not walked, by the config's own walk: a skipDirs dir, a dot dir, a suffix outside its set.
    assert.equal(read(root, "node_modules/x.md"), "C-new-code\n");
    assert.equal(read(root, ".github/x.md"), "C-new-code\n");
    assert.equal(read(root, "docs/x.csv"), "C-new-code\n");
  }));

test("heading: a malformed pending heading is refused and nothing is written", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "docs/decisions/D-Bad_Slug.md", "## D-Bad_Slug — Mixed case and an underscore\n");
    write(root, "README.md", "See D-two-thing and D-Bad_Slug.\n");
    const before = snapshot(root);

    const result = stamp(root, headingConfig());
    assert.equal(result.problems.some((p) => p.includes("malformed pending heading") && p.includes("D-Bad_Slug")), true);
    assert.equal(result.assigned.length, 0);
    assert.deepEqual(snapshot(root), before);
  }));

test("heading --check refuses a record numbered on a branch", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D004-four.md", "## D4 — Four, numbered on the branch\n");
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C2 — Numbered here too\n");
    commit(root, "a branch that numbered its own records");

    const problems = check(root, headingConfig(), LOCAL);
    assert.equal(problems.some((p) => p.includes("docs/decisions/D004-four.md") && p.includes("on a branch")), true);
    assert.equal(problems.some((p) => p.includes("C2") && p.includes("on a branch")), true);
  }));

test("heading --check refuses a pending heading numbered on a branch, in both corpus shapes", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    write(root, "docs/decisions/D-four-thing.md", "## D-four-thing — Four\n");
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C-two-code — Two\n");
    commit(root, "main, with two pending records");
    git(root, "checkout", "-q", "-b", "wt/lane");
    git(root, "mv", "docs/decisions/D-four-thing.md", "docs/decisions/D004-four-thing.md");
    write(root, "docs/decisions/D004-four-thing.md", "## D4 — Four\n");
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C2 — Two\n");
    commit(root, "a branch claims both by hand");

    const problems = check(root, headingConfig(), LOCAL);
    assert.equal(problems.some((p) => p.includes("docs/decisions/D004-four-thing.md") && p.includes("D4")), true);
    assert.equal(problems.some((p) => p.includes("docs/codes.md") && p.includes("C2")), true);
  }));

test("heading --check is silent on a branch that only adds pending records", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D-four-thing.md", "## D-four-thing — Four\n");
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C-two-code — Two\n");
    commit(root, "a branch that writes slugs");

    assert.deepEqual(check(root, headingConfig(), LOCAL), []);
  }));

test("heading --check on the default branch refuses a pending heading older than HEAD", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C-old-code — Old\n");
    commit(root, "a pending code entry the stamp never claimed");
    write(root, "docs/decisions/D-fresh-thing.md", "## D-fresh-thing — Fresh\n");
    commit(root, "a pending decision, waiting its turn");

    const problems = check(root, headingConfig());
    assert.equal(problems.some((p) => p.includes("C-old-code") && p.includes("still pending")), true);
    assert.equal(problems.some((p) => p.includes("D-fresh-thing") && p.includes("still pending")), true);
  }));

test("heading: a pending slug main already claimed under a number is refused", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/D004-two-thing.md", "## D4 — Two thing\n");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");

    const result = stamp(root, headingConfig());
    assert.equal(result.problems.some((p) => p.includes("already claimed as D4")), true);
  }));

test("heading --check refuses a branch number that main took after the cut", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    commit(root, "main, at the cut");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D004-four.md", "## D4 — Four, numbered on the branch\n");
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C2 — Numbered on the branch\n");
    commit(root, "the branch numbers D4 and C2");
    // main moves: it takes D4 (same filename) and C2 for other records after the cut. Measured
    // against main's TIP, both numbers read as "already there" and the defect hides.
    git(root, "checkout", "-q", "main");
    write(root, "docs/decisions/D004-four.md", "## D4 — Four, claimed on main\n");
    write(root, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C2 — Claimed on main\n");
    commit(root, "main takes D4 and C2");
    git(root, "checkout", "-q", "wt/lane");

    const problems = check(root, headingConfig(), LOCAL);
    assert.equal(problems.some((p) => p.includes("docs/decisions/D004-four.md") && p.includes("on a branch")), true);
    assert.equal(problems.some((p) => p.includes("C2") && p.includes("on a branch")), true);
  }));

test("--check passes a branch when main numbered a record after the cut", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/D001-one.md", "---\nid: D-001\nslug: one\ntitle: One\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "main, at the cut");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/pending.md", "---\nid: pending\nslug: pending\ntitle: Pending\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "the branch adds a pending record");
    // main moves: it takes D-005 after the cut. Measured against main's TIP, D-005 would read
    // as "already there" and hide the defect that the branch read the tip instead of the merge base.
    git(root, "checkout", "-q", "main");
    write(root, "docs/decisions/D005-five.md", "---\nid: D-005\nslug: five\ntitle: Five\ndate: 2026-01-05\n---\n\nBody.\n");
    commit(root, "main takes D-005");
    git(root, "checkout", "-q", "wt/lane");

    const problems = check(root, frontmatterConfig(), LOCAL);
    assert.deepEqual(problems, []);
  }));

test("heading: a rename onto a file that already exists is refused and nothing is written", () =>
  withTempDir((root) => {
    write(root, "docs/decisions/ORDER.json", manifestText(["_preamble.md", "D001-one.md"]));
    write(root, "docs/decisions/_preamble.md", "# Settled decisions\n");
    write(root, "docs/decisions/D001-one.md", "## D1 — One\n");
    // No numbered heading, so it does not raise the ceiling, but it holds the name D2 would take.
    write(root, "docs/decisions/D002-extra.md", "Stray notes. No heading.\n");
    write(root, "docs/decisions/D-foo-bar-extra.md", "## D-foo-bar — Foo bar\n");
    const before = snapshot(root);

    const result = stamp(root, headingConfig());
    assert.equal(result.problems.some((p) => p.includes("docs/decisions/D002-extra.md") && p.includes("already exists")), true);
    assert.equal(result.assigned.length, 0);
    assert.deepEqual(snapshot(root), before);
  }));

test("heading: ORDER.json is written with Python json.dumps's escapes, U+007F included", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/ORDER.json",
      '{\n  "order": [\n    "_preamble.md",\n    "ghost\\u007f \\u00e9\\ud83d\\ude00.md",\n    "D-two-thing.md"\n  ]\n}\n');
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");

    stamp(root, headingConfig());
    // The bytes Python 3 prints for json.dumps({"order": [...]}, indent=2) on the same data.
    assert.equal(read(root, "docs/decisions/ORDER.json"),
      '{\n  "order": [\n    "_preamble.md",\n    "ghost\\u007f \\u00e9\\ud83d\\ude00.md",\n    "D004-two-thing.md"\n  ]\n}\n');
  }));

test("heading: a duplicate pending slug is refused with the one true message", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "docs/decisions/D-two-thing-copy.md", "## D-two-thing — Two thing, again\n");
    const before = snapshot(root);

    const result = stamp(root, headingConfig());
    assert.deepEqual(result.problems.filter((p) => !p.startsWith("duplicate pending slug D-two-thing")), []);
    assert.equal(result.problems.length, 1);
    assert.deepEqual(snapshot(root), before);
  }));

test("heading --check reads a non-ASCII filename git added, on and off the default branch", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    commit(root, "main");
    write(root, "docs/decisions/D-two-thing-café.md", "## D-two-thing — Two thing\n");
    commit(root, "HEAD adds a pending record with a non-ASCII filename");
    // On main: any pending record is refused, a non-ASCII filename included.
    assert.equal(check(root, headingConfig()).some((p) => p.includes("D-two-thing-café.md") && p.includes("still pending")), true);

    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D004-café.md", "## D4 — Numbered on the branch\n");
    commit(root, "a branch numbers a record with a non-ASCII filename");
    const problems = check(root, headingConfig(), LOCAL);
    assert.equal(problems.some((p) => p.includes("D004-café.md") && p.includes("on a branch")), true);
  }));

// ---------------------------------------------------------------- unclaimed: a marker the repo
// has no claim rule for yet (here a pending step, `0. \`step <slug>\`` under docs/steps/). This
// engine never numbers one. It only refuses, in both modes, naming the file, the slug, and the
// config's own message.
const pendingStep = "# Steps\n\n0. `step add-widget`\n";

test("unclaimed: --check refuses a pending step, naming the file, its slug and the config's message", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    write(root, "docs/steps/some-file.md", pendingStep);
    commit(root, "a pending step on the default branch");

    const config = headingConfig();
    const problems = check(root, config);
    assert.equal(problems.some((p) =>
      p.includes("docs/steps/some-file.md") &&
      p.includes("step add-widget") &&
      p.includes(config.unclaimed[0].message)), true);
  }));

test("unclaimed: --stamp refuses a pending step, and writes nothing", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/steps/some-file.md", pendingStep);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n"); // would stamp, if not refused first
    const before = snapshot(root);

    const result = stamp(root, headingConfig());
    assert.equal(result.problems.some((p) => p.includes("docs/steps/some-file.md") && p.includes("add-widget")), true);
    assert.equal(result.assigned.length, 0);
    assert.deepEqual(snapshot(root), before);
  }));

test("unclaimed: a numbered line, a number ending in 0, an indented marker, and prose, all stay silent", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/steps/numbered.md", "# Steps\n\n2. `step add-widget`\n");
    // The anchor is "^0\.", not "0\.": a number that merely ENDS in 0 must not match either.
    write(root, "docs/steps/numbered-ten.md", "# Steps\n\n10. `step add-widget`\n");
    // The anchor is line START, not "somewhere on the line after leading space".
    write(root, "docs/steps/indented.md", "# Steps\n\n   0. `step add-gadget`\n");
    write(root, "docs/steps/prose.md", "# Steps\n\nSee step add-widget for details.\n");
    initRepo(root);
    commit(root, "the default branch");

    assert.deepEqual(check(root, headingConfig()), []);
    assert.deepEqual(stamp(root, headingConfig()).problems, []);
  }));

test("unclaimed: a config without the key stays silent on the same tree", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/steps/some-file.md", pendingStep);
    initRepo(root);
    commit(root, "the default branch");
    const config = headingConfig();
    delete config.unclaimed;

    assert.deepEqual(check(root, config), []);
    assert.deepEqual(stamp(root, config).problems, []);
  }));

test("unclaimed: a config entry whose pattern has no \"slug\" group is a config error, before any tree read", () =>
  withTempDir((root) => {
    write(root, "actions/stamp/examples/bad.stamp.json", JSON.stringify({
      ...JSON.parse(readFileSync(join(HERE, "examples/heading.stamp.json"), "utf8")),
      unclaimed: [{ folder: "docs/steps", pattern: "^0\\.(\\s+`step ([a-z-]+)`)", message: "x" }],
    }));
    assert.throws(() => loadConfig(join(root, "actions/stamp/examples/bad.stamp.json")), /named group.*slug/);
  }));

test("unclaimed: a config entry with an invalid regex pattern is a config error", () =>
  withTempDir((root) => {
    write(root, "actions/stamp/examples/bad.stamp.json", JSON.stringify({
      ...JSON.parse(readFileSync(join(HERE, "examples/heading.stamp.json"), "utf8")),
      unclaimed: [{ folder: "docs/steps", pattern: "(unterminated", message: "x" }],
    }));
    assert.throws(() => loadConfig(join(root, "actions/stamp/examples/bad.stamp.json")), /not a valid regex/);
  }));

test("unclaimed: a config entry missing a required field is a config error", () =>
  withTempDir((root) => {
    write(root, "actions/stamp/examples/bad.stamp.json", JSON.stringify({
      ...JSON.parse(readFileSync(join(HERE, "examples/heading.stamp.json"), "utf8")),
      unclaimed: [{ folder: "docs/steps", pattern: "^0\\.(?<slug>x)" }], // no "message"
    }));
    assert.throws(() => loadConfig(join(root, "actions/stamp/examples/bad.stamp.json")), /missing "message"/);
  }));

// ---------------------------------------------------------------- config fields the tests above
// do not reach on their own
test("cite.scanGlobs and cite.excludeGlobs: a scanned suffix is rewritten, an excluded file is not", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/_widgets.md", '---\nid:\nslug: widgets\ngloss: "widgets ship"\ndate: 2026-01-05\n---\n\nBody.\n');
    write(root, "data/links.csv", "ref\n[[widgets]]\n");
    write(root, "data/links.txt", "[[widgets]]\n");
    write(root, "test/fixtures/sample.md", "[[widgets]]\n");
    write(root, "docs/citation-syntax.md", "Write [[slug]] to cite a record.\n");
    commit(root, "a pending record, cites in three places, and a syntax example");

    // the syntax example is excluded. Only the pending record itself is refused, on main.
    assert.deepEqual(check(root, filenameConfig()).filter((p) => !p.includes("still pending")), []);
    stamp(root, filenameConfig());
    assert.equal(read(root, "data/links.csv"), "ref\nD1, widgets ship\n");
    assert.equal(read(root, "data/links.txt"), "[[widgets]]\n"); // .txt is not in scanGlobs
    assert.equal(read(root, "test/fixtures/sample.md"), "[[widgets]]\n"); // excluded
  }));

test("excludeFiles: a listed file in a record folder is not read as a record", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "decisions/_index.md", "# Index\n\nNo frontmatter here.\n");
    write(root, "decisions/one.md", "---\nid: D1\nslug: one\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a record and an index");

    assert.deepEqual(check(root, prefixedCiteConfig()), []);
    const config = prefixedCiteConfig();
    config.kinds[0].excludeFiles = [];
    assert.equal(check(root, config).some((p) => p.includes("decisions/_index.md") && p.includes("malformed")), true);
  }));

test("order \"filename\": pending records are numbered in filename order", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "questions/b.md", "---\nid: pending\nslug: bee\n---\n\nBody.\n");
    write(root, "questions/a.md", "---\nid: pending\nslug: ay\n---\n\nBody.\n");
    commit(root, "two pending questions");

    const result = stamp(root, prefixedCiteConfig());
    assert.deepEqual(result.assigned.map((a) => [a.slug, a.id]), [["ay", "Q1"], ["bee", "Q2"]]);
  }));

test("heading walk.extensionlessDirs: an extensionless file in a named dir is rewritten", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "scripts/githooks/pre-commit", "# see D-two-thing\n");
    write(root, "scripts/other/pre-commit", "# see D-two-thing\n");

    stamp(root, headingConfig());
    assert.equal(read(root, "scripts/githooks/pre-commit"), "# see D4\n");
    assert.equal(read(root, "scripts/other/pre-commit"), "# see D-two-thing\n");
  }));

test("heading manifestKey and manifestAscii: another key is renamed, and false writes plain UTF-8 JSON", () =>
  withTempDir((root) => {
    headingTree(root);
    write(root, "docs/decisions/ORDER.json", JSON.stringify({ files: ["_preamble.md", "caf\u00e9.md", "D-two-thing.md"] }, null, 2) + "\n");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    const config = headingConfig();
    config.kinds[0].manifestKey = "files";
    config.kinds[0].manifestAscii = false;

    stamp(root, config);
    assert.equal(read(root, "docs/decisions/ORDER.json"),
      JSON.stringify({ files: ["_preamble.md", "caf\u00e9.md", "D004-two-thing.md"] }, null, 2) + "\n");
  }));

// ---------------------------------------------------------------- --check off the default
// branch: a renamed numbered record, a removed number, and a title edit, in every shape.
const renamed = (p) => p.includes("was renamed") && !p.includes("numbered D") && !p.includes("pending marker");

test("--check refuses a renamed numbered record, and names the old key and the new key, in every shape", () =>
  withTempDir((root) => {
    const shapes = [
      {
        name: "frontmatter", config: frontmatterConfig,
        base: (d) => write(d, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n"),
        branch: (d) => write(d, "docs/decisions/a.md", "---\nid: D-001\nslug: a-new\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n"),
        oldKey: '"a"', newKey: '"a-new"',
      },
      {
        name: "frontmatter+filename", config: filenameConfig,
        base: (d) => write(d, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "one"\ndate: 2026-01-01\n---\n\nBody.\n'),
        branch: (d) => { git(d, "mv", "docs/decisions/D1_one.md", "docs/decisions/D1_uno.md"); write(d, "docs/decisions/D1_uno.md", '---\nid: D1\nslug: uno\ngloss: "one"\ndate: 2026-01-01\n---\n\nBody.\n'); },
        oldKey: '"one"', newKey: '"uno"',
      },
      {
        name: "heading", config: headingConfig,
        base: (d) => headingTree(d),
        branch: (d) => git(d, "mv", "docs/decisions/D001-one.md", "docs/decisions/D001-uno.md"),
        oldKey: '"docs/decisions/D001-one.md"', newKey: '"docs/decisions/D001-uno.md"',
      },
    ];
    for (const sh of shapes) {
      const dir = join(root, sh.name.replace(/[^a-z]+/g, "-"));
      mkdirSync(dir);
      initRepo(dir);
      sh.base(dir);
      commit(dir, "main");
      git(dir, "checkout", "-q", "-b", "wt/lane");
      sh.branch(dir);
      commit(dir, "a branch renames a numbered record");

      const problems = check(dir, sh.config(), LOCAL);
      assert.equal(problems.length, 1, `${sh.name}: ${problems.join(" | ")}`);
      assert.equal(renamed(problems[0]) && problems[0].includes(sh.oldKey) && problems[0].includes(sh.newKey), true, `${sh.name}: ${problems[0]}`);
    }
  }));

test("--check refuses a branch that removes a numbered record, in every shape", () =>
  withTempDir((root) => {
    const shapes = [
      {
        name: "frontmatter", config: frontmatterConfig, ids: ["D-002"], remedy: "list its number",
        base: (d) => {
          write(d, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
          write(d, "docs/decisions/b.md", "---\nid: D-002\nslug: b\ntitle: B\ndate: 2026-01-02\n---\n\nBody.\n");
        },
        branch: (d) => git(d, "rm", "-q", "docs/decisions/b.md"),
      },
      {
        name: "frontmatter+filename", config: filenameConfig, ids: ["D2"], remedy: "list its number",
        base: (d) => {
          write(d, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "one"\ndate: 2026-01-01\n---\n\nBody.\n');
          write(d, "docs/decisions/D2_two.md", '---\nid: D2\nslug: two\ngloss: "two"\ndate: 2026-01-02\n---\n\nBody.\n');
        },
        branch: (d) => git(d, "rm", "-q", "docs/decisions/D2_two.md"),
      },
      {
        // Both corpus shapes: a folder record, and a heading in the flat file, keyed by its number.
        name: "heading", config: headingConfig, ids: ["D3", "C2"], remedy: "no retired list",
        base: (d) => { headingTree(d); write(d, "docs/codes.md", "# Codes\n\n## C1 — First\n\n## C2 — Second\n"); },
        branch: (d) => { git(d, "rm", "-q", "docs/decisions/D003-three.md"); write(d, "docs/codes.md", "# Codes\n\n## C1 — First\n"); },
      },
    ];
    for (const sh of shapes) {
      const dir = join(root, sh.name.replace(/[^a-z]+/g, "-"));
      mkdirSync(dir);
      initRepo(dir);
      sh.base(dir);
      commit(dir, "main");
      git(dir, "checkout", "-q", "-b", "wt/lane");
      sh.branch(dir);
      commit(dir, "a branch deletes a numbered record");

      const problems = check(dir, sh.config(), LOCAL);
      assert.equal(problems.length, sh.ids.length, `${sh.name}: ${problems.join(" | ")}`);
      for (const id of sh.ids) {
        assert.equal(problems.some((p) => p.startsWith(`${id} `) && p.includes("Numbers are permanent") && p.includes(sh.remedy)), true, `${sh.name}: ${id}`);
      }
    }
  }));

test("--check passes a branch that fixes a typo in a numbered record's title, in every shape", () =>
  withTempDir((root) => {
    const shapes = [
      {
        name: "frontmatter", config: frontmatterConfig,
        base: (d) => write(d, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: Teh title\ndate: 2026-01-01\n---\n\nBody.\n"),
        branch: (d) => write(d, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: The title\ndate: 2026-01-01\n---\n\nBody.\n"),
      },
      {
        name: "frontmatter+filename", config: filenameConfig,
        base: (d) => write(d, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "teh one"\ndate: 2026-01-01\n---\n\nBody.\n'),
        branch: (d) => write(d, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "the one"\ndate: 2026-01-01\n---\n\nBody.\n'),
      },
      {
        name: "heading", config: headingConfig,
        base: (d) => headingTree(d),
        branch: (d) => {
          write(d, "docs/decisions/D001-one.md", "## D1 — One, fixed\n\nBody.\n");
          write(d, "docs/codes.md", "# Codes\n\n## C1 — First, fixed\n\nBody.\n");
        },
      },
    ];
    for (const sh of shapes) {
      const dir = join(root, sh.name.replace(/[^a-z]+/g, "-"));
      mkdirSync(dir);
      initRepo(dir);
      sh.base(dir);
      commit(dir, "main");
      git(dir, "checkout", "-q", "-b", "wt/lane");
      sh.branch(dir);
      commit(dir, "a branch fixes a title");

      assert.deepEqual(check(dir, sh.config(), LOCAL), [], sh.name);
    }
  }));

// ---------------------------------------------------------------- the retired-numbers list
const rec = (n, slug) => `---\nid: D-${String(n).padStart(3, "0")}\nslug: ${slug}\ntitle: ${slug}\ndate: 2026-01-0${n}\n---\n\nBody.\n`;

// Base: D-001 and D-002 (D-002 is the top number). The branch runs `branch`, then commits.
function retiredBranch(root, base, branch) {
  initRepo(root);
  write(root, "docs/decisions/a.md", rec(1, "a"));
  write(root, "docs/decisions/b.md", rec(2, "b"));
  base?.(root);
  commit(root, "main");
  git(root, "checkout", "-q", "-b", "wt/lane");
  branch(root);
  commit(root, "branch");
  return check(root, frontmatterConfig(), LOCAL);
}

test("retired list: an unlisted removal fails", () =>
  withTempDir((root) => {
    const problems = retiredBranch(root, null, (d) => git(d, "rm", "-q", "docs/decisions/b.md"));
    assert.equal(problems.length, 1, problems.join(" | "));
    assert.match(problems[0], /D-002 .*removed on a branch/);
  }));

test("retired list: a removal named in RETIRED passes", () =>
  withTempDir((root) => {
    const problems = retiredBranch(root, null, (d) => {
      git(d, "rm", "-q", "docs/decisions/b.md");
      write(d, "docs/decisions/RETIRED", "D-002 b\n");
    });
    assert.deepEqual(problems, []);
  }));

test("retired list: a number removed from RETIRED fails, and a number added stays quiet", () =>
  withTempDir((root) => {
    const problems = retiredBranch(root,
      (d) => write(d, "docs/decisions/RETIRED", "D-002 b\n"),
      (d) => { git(d, "rm", "-q", "docs/decisions/b.md"); write(d, "docs/decisions/RETIRED", "D-003 later\n"); });
    assert.equal(problems.length, 2, problems.join(" | "));
    assert.equal(problems.some((p) => /D-002 is removed from .*RETIRED.*append-only/.test(p)), true, problems.join(" | "));
    assert.equal(problems.some((p) => /D-002 .*removed on a branch/.test(p)), true, problems.join(" | "));
  }));

test("retired list: a listed top number is never allocated again, in both numbering modes", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", rec(1, "a"));
    write(root, "docs/decisions/RETIRED", "D-002 gone\nD-003\n");
    write(root, "docs/decisions/p.md", "---\nid: pending\nslug: p\ntitle: P\ndate: 2026-02-01\n---\n\nBody.\n");
    commit(root, "main");
    const result = stamp(root, frontmatterConfig());
    assert.deepEqual(result.assigned.map((a) => a.id), ["D-004"]);

    const dir = join(root, "lowest");
    mkdirSync(dir);
    initRepo(dir);
    write(dir, "docs/decisions/D1_one.md", '---\nid: D1\nslug: one\ngloss: "one"\ndate: 2026-01-01\n---\n\nBody.\n');
    write(dir, "docs/decisions/RETIRED", "D2 gone\n");
    write(dir, "docs/decisions/_new.md", '---\nid:\nslug: new\ngloss: "new"\ndate: 2026-02-01\n---\n\nBody.\n');
    commit(dir, "main");
    assert.deepEqual(stamp(dir, filenameConfig()).assigned.map((a) => a.id), ["D3"]);
  }));

test("retired list: a listed number that a record still holds, and a malformed line, both fail", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", rec(1, "a"));
    write(root, "docs/decisions/RETIRED", "D-001 a\n\nnot an id\n");
    const { problems } = stamp(root, frontmatterConfig());
    assert.equal(problems.length, 2, problems.join(" | "));
    assert.equal(problems.some((p) => /D-001 is in .*RETIRED and .*still holds it/.test(p)), true);
    assert.equal(problems.some((p) => /RETIRED line 3 does not start with an id/.test(p)), true);
  }));

// ---------------------------------------------------------------- --claim and the Record-claim
// exception in --check
const pendingRec = (slug, day = "02") => `---\nid: pending\nslug: ${slug}\ntitle: ${slug}\ndate: 2026-01-${day}\n---\n\nBody.\n`;

// main holds D-001. wt/lane adds a pending record `p`. `onMain` then moves main, and the repo
// ends on wt/lane.
function claimRepo(root, onMain) {
  initRepo(root);
  write(root, "docs/decisions/a.md", rec(1, "a"));
  commit(root, "main");
  git(root, "checkout", "-q", "-b", "wt/lane");
  write(root, "docs/decisions/p.md", pendingRec("p"));
  commit(root, "branch adds a pending record");
  if (onMain) {
    git(root, "checkout", "-q", "main");
    onMain(root);
    commit(root, "main moves");
    git(root, "checkout", "-q", "wt/lane");
  }
}

// What the merge tool does: claim, then commit with the trailer.
function claimCommit(root, message = "claim") {
  const r = claim(root, frontmatterConfig(), "main");
  commit(root, `${message}\n\nRecord-claim: ${r.assigned.map((a) => a.id).join(" ")}`);
  return r;
}

test("claim: the number is above the base tip's numbers, which --stamp alone would reuse", () =>
  withTempDir((root) => {
    claimRepo(root, (d) => write(d, "docs/decisions/e.md", rec(5, "e")));
    const c = claim(root, frontmatterConfig(), "main");
    assert.deepEqual(c.assigned.map((a) => a.id), ["D-006"]);
    assert.equal(read(root, "docs/decisions/p.md").includes("id: D-006"), true);
  }));

test("claim: a number in the base tip's RETIRED list is taken", () =>
  withTempDir((root) => {
    claimRepo(root, (d) => write(d, "docs/decisions/RETIRED", "D-009 gone\n"));
    assert.deepEqual(claim(root, frontmatterConfig(), "main").assigned.map((a) => a.id), ["D-010"]);
  }));

test("claim: a base that git cannot read is refused, and the tree stays pending", () =>
  withTempDir((root) => {
    claimRepo(root);
    assert.throws(() => claim(root, frontmatterConfig(), "no-such-ref"));
    assert.equal(read(root, "docs/decisions/p.md").includes("id: pending"), true);
  }));

test("claim, heading shape: the number is above the base tip's", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    commit(root, "branch adds a pending heading");
    git(root, "checkout", "-q", "main");
    write(root, "docs/decisions/D007-seven.md", "## D7 — Seven\n");
    commit(root, "main takes D7");
    git(root, "checkout", "-q", "wt/lane");
    assert.deepEqual(claim(root, headingConfig(), "main").assigned.map((a) => a.id), ["D8"]);
  }));

test("claim: runs the config's regenerate when something was claimed, and not otherwise", () =>
  withTempDir((root) => {
    claimRepo(root);
    const config = { ...frontmatterConfig(), regenerate: "echo ran >> regen.txt" };
    claim(root, config, "main");
    assert.equal(read(root, "regen.txt"), "ran\n");
    claim(root, config, "main"); // nothing pending now
    assert.equal(read(root, "regen.txt"), "ran\n");
  }));

test("config: regenerate must be a string", () =>
  withTempDir((root) => {
    const c = JSON.parse(readFileSync(join(HERE, "examples/frontmatter.stamp.json"), "utf8"));
    c.regenerate = ["make"];
    write(root, "c.json", JSON.stringify(c));
    assert.throws(() => loadConfig(join(root, "c.json")), /regenerate must be a string/);
  }));

test("claim CLI: needs --base, prints the trailer line, and exits 1 on an unreadable base", () =>
  withTempDir((root) => {
    claimRepo(root);
    const cfg = join(HERE, "examples/frontmatter.stamp.json");
    const run = (...a) => spawnSync("node", [join(HERE, "stamp.mjs"), "--claim", ...a, "--config", cfg], { cwd: root, encoding: "utf8" });
    assert.equal(run().status, 2);
    const bad = run("--base", "no-such-ref");
    assert.equal(bad.status, 1);
    assert.match(bad.stderr, /claim REFUSES/);
    const ok = run("--base", "main");
    assert.equal(ok.status, 0, ok.stderr);
    assert.match(ok.stdout, /^Record-claim: D-002$/m);
  }));

test("--check accepts a number a Record-claim commit added", () =>
  withTempDir((root) => {
    claimRepo(root);
    claimCommit(root);
    assert.deepEqual(check(root, frontmatterConfig(), LOCAL), []);
  }));

test("--check refuses a claimed number whose commit has no trailer", () =>
  withTempDir((root) => {
    claimRepo(root);
    claim(root, frontmatterConfig(), "main");
    commit(root, "claim, no trailer");
    const problems = check(root, frontmatterConfig(), LOCAL);
    assert.equal(problems.length, 1, problems.join(" | "));
    assert.match(problems[0], /D-002 on a branch/);
  }));

test("--check refuses a trailer that names another id, and a trailer commit that did not change the file", () =>
  withTempDir((root) => {
    claimRepo(root);
    claim(root, frontmatterConfig(), "main");
    commit(root, "claim\n\nRecord-claim: D-009");
    assert.equal(check(root, frontmatterConfig(), LOCAL).length, 1);
    write(root, "docs/decisions/note.md", "---\nid: D-003\nslug: note\ntitle: note\ndate: 2026-01-03\n---\n\nBody.\n");
    commit(root, "later\n\nRecord-claim: D-002 D-003");
    const problems = check(root, frontmatterConfig(), LOCAL);
    // D-003's file is changed by its trailer commit, so it passes. D-002's is not, so it stays refused.
    assert.equal(problems.some((p) => p.includes("p.md") && p.includes("D-002")), true, problems.join(" | "));
    assert.equal(problems.some((p) => p.includes("note.md")), false, problems.join(" | "));
  }));

test("--check refuses a claimed number that the base tip took after the claim", () =>
  withTempDir((root) => {
    claimRepo(root);
    claimCommit(root);
    git(root, "checkout", "-q", "main");
    write(root, "docs/decisions/e.md", rec(2, "e"));
    commit(root, "main takes D-002");
    git(root, "checkout", "-q", "wt/lane");
    const problems = check(root, frontmatterConfig(), LOCAL);
    assert.equal(problems.some((p) => p.includes("p.md") && p.includes("claimed on this branch") && p.includes("D-002")), true, problems.join(" | "));
  }));

test("heading --check accepts a number a Record-claim commit added", () =>
  withTempDir((root) => {
    initRepo(root);
    headingTree(root);
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    commit(root, "branch adds a pending heading");
    const r = claim(root, headingConfig(), "main");
    commit(root, `claim\n\nRecord-claim: ${r.assigned.map((a) => a.id).join(" ")}`);
    assert.deepEqual(check(root, headingConfig(), LOCAL), []);
  }));

// ---------------------------------------------------------------- run
let failed = 0;
for (const { name, fn } of tests) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`FAIL - ${name}`);
    console.error(err.stack ?? err);
  }
}
console.log(`${tests.length - failed} of ${tests.length} passed.`);
if (failed) process.exit(1);
