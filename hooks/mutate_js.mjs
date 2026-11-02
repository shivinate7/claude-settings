// The mutant maker for JavaScript and TypeScript files. hooks/mutate_shared.py (`js_mutants`) runs it:
//   node hooks/mutate_js.mjs <file> [--lines 3,7]
// It prints a JSON list of {label, line, text}: one mutant per site, `text` being the whole file with
// that one edit. The kinds are the kinds of `_sites` in hooks/mutate_shared.py, so a report reads the
// same on both languages. A parse error exits 1 with the message on stderr.
//
// The sites come from the TypeScript parse tree, never from a text scan: a string, a template literal,
// a comment or a JSX text that holds `a === b` is no node, so it gets no mutant. Each edit replaces a
// span of the original text and leaves every other byte, so a mutant differs from the source by that
// one edit and nothing else. typescript loads through the one loader of the plain-english-map skill.
import { readFileSync } from 'node:fs';
import { extname } from 'node:path';
import ts from '../skills/plain-english-map/scripts/lib/lazy-typescript.mjs';

const KIND_OF_EXTENSION = {
  '.js': 'JS', '.cjs': 'JS', '.mjs': 'JS', '.jsx': 'JSX',
  '.ts': 'TS', '.mts': 'TS', '.cts': 'TS', '.tsx': 'TSX',
};

// Same pairs as `_SWAPS` in hooks/mutate_shared.py, in the JavaScript operator names.
const COMPARE_SWAPS = {
  '===': '!==', '!==': '===', '==': '!=', '!=': '==', '<': '>=', '>=': '<', '>': '<=', '<=': '>',
};

class UsageError extends Error {}

const parseArguments = (argv) => {
  const [file, ...rest] = argv;
  if (!file || file.startsWith('--')) throw new UsageError('usage: node mutate_js.mjs <file> [--lines 3,7]');
  let lines = null;
  if (rest.length) {
    const numbers = rest[0] === '--lines' && rest.length === 2 ? rest[1].split(',') : null;
    if (!numbers || !numbers.every((n) => /^[1-9]\d*$/.test(n))) {
      throw new UsageError('usage: node mutate_js.mjs <file> [--lines 3,7]');
    }
    lines = new Set(numbers.map(Number));
  }
  return { file, lines };
};

const parse = (file, text) => {
  const kind = KIND_OF_EXTENSION[extname(file).toLowerCase()];
  if (!kind) throw new UsageError(`unsupported file extension: ${extname(file) || '(none)'}`);
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind[kind]);
  // parseDiagnostics holds the syntax errors of this one file. ts.createSourceFile does not throw on them.
  const errors = source.parseDiagnostics ?? [];
  if (errors.length) {
    const first = errors[0];
    const { line, character } = source.getLineAndCharacterOfPosition(first.start ?? 0);
    throw new Error(`${file}:${line + 1}:${character + 1}: ${ts.flattenDiagnosticMessageText(first.messageText, '\n')}`);
  }
  return source;
};

// Every site, in source order: {line, what, start, end, replacement}. The edit swaps text[start, end) for
// the replacement. `line` is the line the site's node starts on, like `lineno` in the ast engine.
const findSites = (source, text) => {
  const sites = [];
  // Count "\n" in the text, not the TypeScript line map: that map also breaks at U+2028 and U+2029, which sit
  // inside a string as plain characters, so a later site would get the wrong line.
  const lineOf = (node) => text.slice(0, node.getStart(source)).split('\n').length;
  const add = (node, what, start, end, replacement) => sites.push({ line: lineOf(node), what, start, end, replacement });
  const K = ts.SyntaxKind;

  const visit = (node) => {
    if (ts.isBinaryExpression(node)) {
      const operator = node.operatorToken;
      const span = [operator.getStart(source), operator.getEnd()];
      const symbol = text.slice(...span);
      if (operator.kind === K.AmpersandAmpersandToken || operator.kind === K.BarBarToken) {
        const swapped = symbol === '&&' ? '||' : '&&';
        add(node, `bool ${symbol} -> ${swapped}`, ...span, swapped);
      } else if (Object.hasOwn(COMPARE_SWAPS, symbol)) {
        add(node, `compare ${symbol} -> ${COMPARE_SWAPS[symbol]}`, ...span, COMPARE_SWAPS[symbol]);
      }
    } else if (ts.isPrefixUnaryExpression(node) && node.operator === K.ExclamationToken) {
      add(node, 'not dropped', node.getStart(source), node.operand.getStart(source), '');
    } else if (node.kind === K.TrueKeyword || node.kind === K.FalseKeyword) {
      const was = node.kind === K.TrueKeyword;
      add(node, `${was} -> ${!was}`, node.getStart(source), node.getEnd(), String(!was));
    } else if (ts.isIfStatement(node) || ts.isWhileStatement(node)) {
      const test = node.expression;
      const kind = ts.isIfStatement(node) ? 'if' : 'while';
      add(node, `${kind} test negated`, test.getStart(source), test.getEnd(), `!(${test.getText(source)})`);
    } else if (ts.isReturnStatement(node)) {
      const value = node.expression;
      if (value && !(ts.isIdentifier(value) && value.text === 'undefined')) {
        add(node, 'return value -> undefined', value.getStart(source), value.getEnd(), 'undefined');
      }
      // A lone `;` keeps `if (x) return 1; else ...` valid, where an empty replacement would not.
      add(node, 'return dropped', node.getStart(source), node.getEnd(), ';');
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return sites;
};

const mutants = (file, wanted) => {
  const text = readFileSync(file, 'utf8');
  const source = parse(file, text);
  const found = [];
  for (const site of findSites(source, text)) {
    if (wanted && !wanted.has(site.line)) continue;
    const mutated = text.slice(0, site.start) + site.replacement + text.slice(site.end);
    if (mutated !== text) found.push({ label: `L${site.line} ${site.what}`, line: site.line, text: mutated });
  }
  return found;
};

try {
  const { file, lines } = parseArguments(process.argv.slice(2));
  // exitCode, not exit(): a large list on a pipe must finish writing before the process ends.
  process.stdout.write(JSON.stringify(mutants(file, lines)));
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = error instanceof UsageError ? 2 : 1;
}
