// Red proof: node --test testing/
import { test } from "node:test";
import assert from "node:assert/strict";
import { needEnv } from "./skip-locally-fail-in-ci.mjs";

const missing = () => { throw new Error("browser not found\nstack"); };
const fakeT = () => { const t = { skipped: null, skip(m) { t.skipped = m; } }; return t; };

test("missing dependency skips locally", async () => {
  const t = fakeT();
  assert.equal(await needEnv(t, "chromium", missing, {}), null);
  assert.match(t.skipped, /no chromium: browser not found/);
});
test("missing dependency fails when CI is set", async () => {
  const t = fakeT();
  await assert.rejects(needEnv(t, "chromium", missing, { CI: "true" }), /in CI this fails/);
  assert.equal(t.skipped, null);
});
test("present dependency is returned in both", async () => {
  assert.equal(await needEnv(fakeT(), "x", () => 7, { CI: "true" }), 7);
});
