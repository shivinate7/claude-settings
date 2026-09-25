#!/usr/bin/env node
// Runnable self-test for stamp.mjs. `node actions/stamp/test_stamp.mjs`. No framework: each
// test is a function that throws via `node:assert` on failure. Every test builds its own
// throwaway directory under the OS temp dir and removes it when done, so tests never touch this
// repository's own tree and never share state with each other.

import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, readdirSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { stamp, check, loadConfig, currentBranch } from "./stamp.mjs";

// Each fixture builds its own git repo. A push run's GITHUB_REF names the runner's branch, not the fixture's.
delete process.env.GITHUB_REF;

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

// ---------------------------------------------------------------- format 1: frontmatter only,
// max_plus_one, merge order (q_max's own shape)
const qmaxConfig = () => loadConfig(join(HERE, "examples/qmax.stamp.json"));

test("frontmatter-only: pending records get distinct, sequential numbers in merge order", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/first.md", "---\nid: D-001\nslug: first\ntitle: First\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "add first");
    write(root, "docs/decisions/second.md", "---\nid: pending\nslug: second\ntitle: Second\ndate: 2026-01-02\n---\n\nCites [[third]].\n");
    write(root, "docs/decisions/third.md", "---\nid: pending\nslug: third\ntitle: Third\ndate: 2026-01-03\n---\n\nBody.\n");
    commit(root, "two branches merge in one run: second, then third");

    const config = qmaxConfig();
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

    const result = stamp(root, qmaxConfig());
    assert.equal(result.problems.length, 0);
    assert.equal(result.assigned[0].id, "D-047");
  }));

// ---------------------------------------------------------------- format 1: lowest_free
// (sharables' own shape)
const sharablesConfig = () => loadConfig(join(HERE, "examples/sharables.stamp.json"));

test("frontmatter-only, lowest_free: a gap in the taken numbers is filled before the max", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "decisions/one.md", "---\nid: D1\nslug: one\nkind: decision\nstatus: open\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "decisions/three.md", "---\nid: D3\nslug: three\nkind: decision\nstatus: open\ndate: 2026-01-02\n---\n\nBody.\n");
    write(root, "decisions/pending-one.md", "---\nid: pending\nslug: gap-fill\nkind: decision\nstatus: open\ndate: 2026-01-03\n---\n\nCited as D‹gap-fill›.\n");
    commit(root, "one, three, and a pending record");

    const result = stamp(root, sharablesConfig());
    assert.equal(result.problems.length, 0);
    assert.equal(result.assigned[0].id, "D2");
    // sharables' own cite rewrite writes the bare id, no gloss.
    assert.equal(read(root, "decisions/pending-one.md").includes("Cited as D2."), true);
  }));

test("frontmatter-only cite: a citation naming the wrong kind's letter is left unresolved", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "decisions/one.md", "---\nid: D1\nslug: shared-slug\nkind: decision\nstatus: open\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "findings/two.md", "---\nid: pending\nslug: other-slug\nkind: finding\nstatus: observed\ndate: 2026-01-02\n---\n\nCited wrongly as F‹shared-slug›.\n");
    commit(root, "mismatched prefix");

    stamp(root, sharablesConfig());
    // "shared-slug" is a D record. "F<shared-slug>" names the wrong letter, so it is left as
    // text rather than resolved to the D record's id.
    assert.equal(read(root, "findings/two.md").includes("Cited wrongly as F‹shared-slug›."), true);
  }));

// ---------------------------------------------------------------- format 2: frontmatter AND
// filename, lowest_free, date order (job-cost-reporting's own shape)
const jcrConfig = () => loadConfig(join(HERE, "examples/jcr.stamp.json"));

test("frontmatter+filename: a pending record is renamed and its cite gains its gloss", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/_2026-01-05-widgets.md",
      '---\nid:\nslug: widgets\ngloss: "widgets ship in v2"\ndate: 2026-01-05\n---\n\nBody.\n');
    write(root, "README.md", "See [[widgets]] for the plan.\n");
    commit(root, "add a pending jcr-shaped record");

    const result = stamp(root, jcrConfig());
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
    const result = stamp(root, jcrConfig());
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

    const problems = check(root, qmaxConfig());
    assert.equal(problems.some((p) => p.includes("duplicate id D-001")), true);
  }));

test("--check refuses a cite that points at no record", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "README.md", "See [[does-not-exist]].\n");
    commit(root, "a dangling cite");

    const problems = check(root, qmaxConfig());
    assert.equal(problems.some((p) => p.includes("does-not-exist")), true);
  }));

test("--check refuses a malformed record (neither pending nor numbered)", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: not-a-number\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a malformed record");

    const problems = check(root, qmaxConfig());
    assert.equal(problems.some((p) => p.includes("malformed record")), true);
  }));

test("--check is silent on a well-formed tree", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/a.md", "---\nid: D-001\nslug: a\ntitle: A\ndate: 2026-01-01\n---\n\nBody.\n");
    write(root, "README.md", "See D-001, A.\n");
    commit(root, "a clean tree");

    assert.deepEqual(check(root, qmaxConfig()), []);
  }));

// ---------------------------------------------------------------- --check, the branch question
// (D-478's own defect: a pending entry the stamp has not had its TURN on yet must not be
// refused, but one an older commit added — the stamp did not run, or its push was rejected — must)
test("--check on the default branch refuses a pending record older than HEAD", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/old.md", "---\nid: pending\nslug: old\ntitle: Old\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "add old, still pending");
    write(root, "docs/decisions/unrelated.md", "---\nid: D-001\nslug: unrelated\ntitle: Unrelated\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "an unrelated later commit");

    assert.equal(currentBranch(root), "main");
    const config = qmaxConfig(); // defaultBranch: "main"
    const problems = check(root, config);
    assert.equal(problems.some((p) => p.includes("docs/decisions/old.md") && p.includes("pending")), true);
  }));

test("--check on the default branch does not refuse a pending record HEAD itself just added", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/settled.md", "---\nid: D-001\nslug: settled\ntitle: Settled\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "a settled record");
    write(root, "docs/decisions/fresh.md", "---\nid: pending\nslug: fresh\ntitle: Fresh\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "fresh, waiting its turn");

    const problems = check(root, qmaxConfig());
    assert.equal(problems.length, 0);
  }));

test("--check off the default branch never asks the branch question", () =>
  withTempDir((root) => {
    initRepo(root);
    write(root, "docs/decisions/old.md", "---\nid: pending\nslug: old\ntitle: Old\ndate: 2026-01-01\n---\n\nBody.\n");
    commit(root, "add old, still pending");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/newer.md", "---\nid: pending\nslug: newer\ntitle: Newer\ndate: 2026-01-02\n---\n\nBody.\n");
    commit(root, "another pending record on a branch");

    assert.equal(currentBranch(root), "wt/lane");
    assert.deepEqual(check(root, qmaxConfig()), []);
  }));

// ---------------------------------------------------------------- format 3: the number in a
// heading, and for a split corpus in the filename too (banchi's own shape, read off its
// scripts/claim-ids.py). The fixture is a small tree of banchi's shape, never banchi's own tree.
const banchiConfig = () => loadConfig(join(HERE, "examples/banchi.stamp.json"));

// Python's json.dumps(indent=2), which is the byte shape banchi's ORDER.json holds.
const manifestText = (order) => JSON.stringify({ order }, null, 2) + "\n";

function banchiTree(root, { order = ["_preamble.md", "D001-one.md", "D003-three.md"] } = {}) {
  write(root, "docs/decisions/ORDER.json", manifestText(order));
  write(root, "docs/decisions/_preamble.md", "# Settled decisions\n");
  write(root, "docs/decisions/D001-one.md", "## D1 — One\n\nBody.\n");
  // D2 is a hole, on purpose: claim-ids.py never reuses one (its own D80 ruling).
  write(root, "docs/decisions/D003-three.md", "## D3 — Three\n\nBody.\n");
  write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\nBody.\n");
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
    banchiTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");
    write(root, "README.md", "See D-two-thing.\n");

    const result = stamp(root, banchiConfig());
    assert.deepEqual(result.problems, []);
    assert.equal(result.assigned[0].id, "D4");
    assert.equal(existsSync(join(root, "docs/decisions/D-two-thing.md")), false);
    assert.equal(read(root, "docs/decisions/D004-two-thing.md").split("\n")[0], "## D4 — Two thing");
    assert.equal(read(root, "README.md"), "See D4.\n");
  }));

test("heading: ORDER.json gets the new name in the old name's own place", () =>
  withTempDir((root) => {
    banchiTree(root, { order: ["_preamble.md", "D001-one.md", "D-two-thing.md", "D003-three.md"] });
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");

    stamp(root, banchiConfig());
    assert.equal(read(root, "docs/decisions/ORDER.json"),
      manifestText(["_preamble.md", "D001-one.md", "D004-two-thing.md", "D003-three.md"]));
  }));

test("heading: an unlisted entry leaves ORDER.json alone, for regenerate to append", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");
    const before = read(root, "docs/decisions/ORDER.json");

    stamp(root, banchiConfig());
    assert.equal(read(root, "docs/decisions/ORDER.json"), before);
  }));

test("heading: a gap in the sequence is never reused", () =>
  withTempDir((root) => {
    banchiTree(root); // D1 and D3, no D2
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n\nBody.\n");
    write(root, "docs/decisions/D-zed-thing.md", "## D-zed-thing — Zed thing\n\nBody.\n");

    const result = stamp(root, banchiConfig());
    assert.deepEqual(result.assigned.map((a) => a.id), ["D4", "D5"]);
    assert.equal(existsSync(join(root, "docs/decisions/D002-two-thing.md")), false);
  }));

test("heading: a pending heading in the flat corpus is numbered in place, and cites follow", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\n## C-new-code — New code\n\nBody.\n");
    write(root, "docs/specs/a.md",
      "C-new-code, C-new-code-longer, and `docs/decisions/D-two-thing.md` by path. D-two-thing too.\n");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "node_modules/x.md", "C-new-code\n");
    write(root, ".github/x.md", "C-new-code\n");
    write(root, "docs/x.csv", "C-new-code\n");

    const result = stamp(root, banchiConfig());
    assert.deepEqual(result.problems, []);
    assert.equal(read(root, "docs/CODES-DECISIONS.md"), "# Codes\n\n## C1 — First\n\n## C2 — New code\n\nBody.\n");
    assert.equal(read(root, "docs/specs/a.md"), "C2, C-new-code-longer, and D4 by path. D4 too.\n");
    // Not walked, by claim-ids.py's own rules: a SKIP dir, a dot dir, a suffix outside its set.
    assert.equal(read(root, "node_modules/x.md"), "C-new-code\n");
    assert.equal(read(root, ".github/x.md"), "C-new-code\n");
    assert.equal(read(root, "docs/x.csv"), "C-new-code\n");
  }));

test("heading: a malformed pending heading is refused and nothing is written", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "docs/decisions/D-Bad_Slug.md", "## D-Bad_Slug — Mixed case and an underscore\n");
    write(root, "README.md", "See D-two-thing and D-Bad_Slug.\n");
    const before = snapshot(root);

    const result = stamp(root, banchiConfig());
    assert.equal(result.problems.some((p) => p.includes("malformed pending heading") && p.includes("D-Bad_Slug")), true);
    assert.equal(result.assigned.length, 0);
    assert.deepEqual(snapshot(root), before);
  }));

test("heading --check refuses a record numbered on a branch", () =>
  withTempDir((root) => {
    initRepo(root);
    banchiTree(root);
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D004-four.md", "## D4 — Four, numbered on the branch\n");
    write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\n## C2 — Numbered here too\n");
    commit(root, "a branch that numbered its own records");

    const problems = check(root, banchiConfig());
    assert.equal(problems.some((p) => p.includes("docs/decisions/D004-four.md") && p.includes("on a branch")), true);
    assert.equal(problems.some((p) => p.includes("C2") && p.includes("on a branch")), true);
  }));

test("heading --check is silent on a branch that only adds pending records", () =>
  withTempDir((root) => {
    initRepo(root);
    banchiTree(root);
    commit(root, "main");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D-four-thing.md", "## D-four-thing — Four\n");
    write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\n## C-two-code — Two\n");
    commit(root, "a branch that writes slugs");

    assert.deepEqual(check(root, banchiConfig()), []);
  }));

test("heading --check on the default branch refuses a pending heading older than HEAD", () =>
  withTempDir((root) => {
    initRepo(root);
    banchiTree(root);
    write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\n## C-old-code — Old\n");
    commit(root, "a pending code entry the stamp never claimed");
    write(root, "docs/decisions/D-fresh-thing.md", "## D-fresh-thing — Fresh\n");
    commit(root, "a pending decision, waiting its turn");

    const problems = check(root, banchiConfig());
    assert.equal(problems.some((p) => p.includes("C-old-code") && p.includes("added before HEAD")), true);
    assert.equal(problems.some((p) => p.includes("D-fresh-thing")), false);
  }));

test("heading: a pending slug main already claimed under a number is refused", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/decisions/D004-two-thing.md", "## D4 — Two thing\n");
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");

    const result = stamp(root, banchiConfig());
    assert.equal(result.problems.some((p) => p.includes("already claimed as D4")), true);
  }));

test("heading --check refuses a branch number that main took after the cut", () =>
  withTempDir((root) => {
    initRepo(root);
    banchiTree(root);
    commit(root, "main, at the cut");
    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D004-four.md", "## D4 — Four, numbered on the branch\n");
    write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\n## C2 — Numbered on the branch\n");
    commit(root, "the branch numbers D4 and C2");
    // main moves: it takes D4 (same filename) and C2 for other records after the cut. Measured
    // against main's TIP, both numbers read as "already there" and the defect hides.
    git(root, "checkout", "-q", "main");
    write(root, "docs/decisions/D004-four.md", "## D4 — Four, claimed on main\n");
    write(root, "docs/CODES-DECISIONS.md", "# Codes\n\n## C1 — First\n\n## C2 — Claimed on main\n");
    commit(root, "main takes D4 and C2");
    git(root, "checkout", "-q", "wt/lane");

    const problems = check(root, banchiConfig());
    assert.equal(problems.some((p) => p.includes("docs/decisions/D004-four.md") && p.includes("on a branch")), true);
    assert.equal(problems.some((p) => p.includes("C2") && p.includes("on a branch")), true);
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

    const result = stamp(root, banchiConfig());
    assert.equal(result.problems.some((p) => p.includes("docs/decisions/D002-extra.md") && p.includes("already exists")), true);
    assert.equal(result.assigned.length, 0);
    assert.deepEqual(snapshot(root), before);
  }));

test("heading: ORDER.json is written with Python json.dumps's escapes, U+007F included", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/decisions/ORDER.json",
      '{\n  "order": [\n    "_preamble.md",\n    "ghost\\u007f \\u00e9\\ud83d\\ude00.md",\n    "D-two-thing.md"\n  ]\n}\n');
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");

    stamp(root, banchiConfig());
    // The bytes Python 3 prints for json.dumps({"order": [...]}, indent=2) on the same data.
    assert.equal(read(root, "docs/decisions/ORDER.json"),
      '{\n  "order": [\n    "_preamble.md",\n    "ghost\\u007f \\u00e9\\ud83d\\ude00.md",\n    "D004-two-thing.md"\n  ]\n}\n');
  }));

test("heading: a duplicate pending slug is refused with the one true message", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n");
    write(root, "docs/decisions/D-two-thing-copy.md", "## D-two-thing — Two thing, again\n");
    const before = snapshot(root);

    const result = stamp(root, banchiConfig());
    assert.deepEqual(result.problems.filter((p) => !p.startsWith("duplicate pending slug D-two-thing")), []);
    assert.equal(result.problems.length, 1);
    assert.deepEqual(snapshot(root), before);
  }));

test("heading --check reads a non-ASCII filename git added, on and off the default branch", () =>
  withTempDir((root) => {
    initRepo(root);
    banchiTree(root);
    commit(root, "main");
    write(root, "docs/decisions/D-two-thing-café.md", "## D-two-thing — Two thing\n");
    commit(root, "HEAD adds a pending record with a non-ASCII filename");
    // On main: HEAD itself added it, so it waits its turn and is not refused.
    assert.deepEqual(check(root, banchiConfig()), []);

    git(root, "checkout", "-q", "-b", "wt/lane");
    write(root, "docs/decisions/D004-café.md", "## D4 — Numbered on the branch\n");
    commit(root, "a branch numbers a record with a non-ASCII filename");
    const problems = check(root, banchiConfig());
    assert.equal(problems.some((p) => p.includes("D004-café.md") && p.includes("on a branch")), true);
  }));

// ---------------------------------------------------------------- unclaimed: deferred/banchi-build-steps.md.
// A pending Banchi build step (`0. \`step <slug>\`` under docs/gates/steps/) has no rule to copy
// from claim-ids.py (it is stale for steps — see decisions/one-shared-record-stamp.md, "Left out,
// on purpose"). This engine never numbers one. It only refuses, in both modes, naming the file
// and the slug.
const pendingStep = "# Steps\n\n0. `step add-widget`\n";

test("unclaimed: --check refuses a pending build step, naming the file and its slug", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/gates/steps/some-file.md", pendingStep);

    const problems = check(root, banchiConfig());
    assert.equal(problems.some((p) =>
      p.includes("docs/gates/steps/some-file.md") &&
      p.includes("add-widget") &&
      p.includes("deferred/banchi-build-steps.md")), true);
  }));

test("unclaimed: --stamp refuses a pending build step, and writes nothing", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/gates/steps/some-file.md", pendingStep);
    write(root, "docs/decisions/D-two-thing.md", "## D-two-thing — Two thing\n"); // would stamp, if not refused first
    const before = snapshot(root);

    const result = stamp(root, banchiConfig());
    assert.equal(result.problems.some((p) => p.includes("docs/gates/steps/some-file.md") && p.includes("add-widget")), true);
    assert.equal(result.assigned.length, 0);
    assert.deepEqual(snapshot(root), before);
  }));

test("unclaimed: a numbered line, a number ending in 0, an indented marker, and prose, all stay silent", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/gates/steps/numbered.md", "# Steps\n\n2. `step add-widget`\n");
    // The anchor is "^0\.", not "0\.": a number that merely ENDS in 0 must not match either.
    write(root, "docs/gates/steps/numbered-ten.md", "# Steps\n\n10. `step add-widget`\n");
    // The anchor is line START, not "somewhere on the line after leading space".
    write(root, "docs/gates/steps/indented.md", "# Steps\n\n   0. `step add-gadget`\n");
    write(root, "docs/gates/steps/prose.md", "# Steps\n\nSee step add-widget for details.\n");

    assert.deepEqual(check(root, banchiConfig()), []);
    assert.deepEqual(stamp(root, banchiConfig()).problems, []);
  }));

test("unclaimed: a config without the key stays silent on the same tree", () =>
  withTempDir((root) => {
    banchiTree(root);
    write(root, "docs/gates/steps/some-file.md", pendingStep);
    const config = banchiConfig();
    delete config.unclaimed;

    assert.deepEqual(check(root, config), []);
    assert.deepEqual(stamp(root, config).problems, []);
  }));

test("unclaimed: a config entry whose pattern has no \"slug\" group is a config error, before any tree read", () =>
  withTempDir((root) => {
    write(root, "actions/stamp/examples/bad.stamp.json", JSON.stringify({
      ...JSON.parse(readFileSync(join(HERE, "examples/banchi.stamp.json"), "utf8")),
      unclaimed: [{ folder: "docs/gates/steps", pattern: "^0\\.(\\s+`step ([a-z-]+)`)", message: "x" }],
    }));
    assert.throws(() => loadConfig(join(root, "actions/stamp/examples/bad.stamp.json")), /named group.*slug/);
  }));

test("unclaimed: a config entry with an invalid regex pattern is a config error", () =>
  withTempDir((root) => {
    write(root, "actions/stamp/examples/bad.stamp.json", JSON.stringify({
      ...JSON.parse(readFileSync(join(HERE, "examples/banchi.stamp.json"), "utf8")),
      unclaimed: [{ folder: "docs/gates/steps", pattern: "(unterminated", message: "x" }],
    }));
    assert.throws(() => loadConfig(join(root, "actions/stamp/examples/bad.stamp.json")), /not a valid regex/);
  }));

test("unclaimed: a config entry missing a required field is a config error", () =>
  withTempDir((root) => {
    write(root, "actions/stamp/examples/bad.stamp.json", JSON.stringify({
      ...JSON.parse(readFileSync(join(HERE, "examples/banchi.stamp.json"), "utf8")),
      unclaimed: [{ folder: "docs/gates/steps", pattern: "^0\\.(?<slug>x)" }], // no "message"
    }));
    assert.throws(() => loadConfig(join(root, "actions/stamp/examples/bad.stamp.json")), /missing "message"/);
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
