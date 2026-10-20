// The one home of the `typescript` import for the skill. It loads at the first use, not at import.
// `createRequire` resolves from this file's real path. Through the install link, that path is inside claude-settings,
// so the package comes from the `node_modules` of claude-settings (`npm ci` there), not from the host repository.
// A copy of the skill outside the clone has no `node_modules` beside it. The load fails, and the error says what to do.
// A module that imports `typescript` at the top would fail in a run that never parses code.
import { createRequire } from 'node:module';

let loaded;
const load = () => {
  try { return createRequire(import.meta.url)('typescript'); } catch (e) {
    if (e.code !== 'MODULE_NOT_FOUND') throw e;
    throw new Error(`The skill cannot load the typescript package from ${import.meta.url}. Run the skill from its install link in ~/.claude/skills/, or install typescript in the host repository.`);
  }
};
export default new Proxy({}, { get: (_, key) => (loaded ??= load())[key] });
