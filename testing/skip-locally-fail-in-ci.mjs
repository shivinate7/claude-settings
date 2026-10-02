// Env-dependent test helper (node:test). A missing dependency, such as a browser, skips the test
// on a laptop and FAILS it when CI is set: a skip in CI passes the proof without running it.
//
//   import { needEnv } from "./skip-locally-fail-in-ci.mjs";
//   test("renders", async (t) => {
//     const browser = await needEnv(t, "chromium", () => launchBrowser());
//     if (!browser) return;           // skipped locally
//     ...
//   });
//
// `probe` returns the dependency or throws. Returns the dependency, or null after t.skip().
export async function needEnv(t, name, probe, env = process.env) {
  try {
    return await probe();
  } catch (e) {
    const why = `no ${name}: ${String(e && e.message).split("\n")[0]}`;
    if (env.CI) throw new Error(`${why}; in CI this fails, a skip would pass the test unrun`);
    t.skip(why);
    return null;
  }
}
