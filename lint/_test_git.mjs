// The JS twin of lint/_test_git.py, the test-run commit-signing opt-out. A JS test suite or helper
// that commits, merges or tags in a fixture repo imports this module once, near the top. The import
// appends commit.gpgsign=false and tag.gpgsign=false to process.env through GIT_CONFIG_COUNT /
// GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n, keeps keys already set, and adds nothing on a second import.
// A child started with a fresh env object passes it through apply(env).

// The same two pairs as OPT_OUT in lint/_test_git.py: a JS module cannot import a Python constant.
export const OPT_OUT = [['commit.gpgsign', 'false'], ['tag.gpgsign', 'false']];

export function apply(environ) {
  let count = Number.parseInt(environ.GIT_CONFIG_COUNT || '0', 10);
  if (!Number.isInteger(count) || count < 0) count = 0;
  const last = new Map(); // git applies entries in order, so the last value for a key wins
  for (let index = 0; index < count; index += 1) {
    last.set(String(environ[`GIT_CONFIG_KEY_${index}`] || '').toLowerCase(), environ[`GIT_CONFIG_VALUE_${index}`] || '');
  }
  for (const [key, value] of OPT_OUT) {
    if (last.get(key) === value) continue;
    environ[`GIT_CONFIG_KEY_${count}`] = key;
    environ[`GIT_CONFIG_VALUE_${count}`] = value;
    count += 1;
  }
  environ.GIT_CONFIG_COUNT = String(count);
  return environ;
}

apply(process.env);
