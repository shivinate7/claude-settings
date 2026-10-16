// The one home of the `typescript` import for the skill. It loads at the first use, not at import.
// `createRequire` resolves from this file's real path. Through the install link, that path is inside claude-settings,
// so the package comes from the `node_modules` of claude-settings (`npm ci` there), never from the host repository.
// A module that imports `typescript` at the top would fail in a run that never parses code.
import { createRequire } from 'node:module';

let loaded;
export default new Proxy({}, { get: (_, key) => (loaded ??= createRequire(import.meta.url)('typescript'))[key] });
