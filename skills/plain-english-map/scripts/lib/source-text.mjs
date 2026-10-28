// The one home of the source-text readers the check and the tests share.
//
// A LEAF: it imports nothing, so a check and a test can both import it with no side effect.

/**
 * Source with comments removed — by a scanner, not by regexes, and the difference was MEASURED.
 *
 * The old form stripped block comments first with a regex, so a `/*` INSIDE a line comment opened a
 * phantom block that ate everything to the next `*\u002F`. server.ts line 52 says "data/*.xlsx" in a
 * line comment, and that one token swallowed 7,778 characters — 169 lines, a quarter of the file —
 * from every check that read the server through this helper. Found when a brand-new assertion failed
 * on a line that verifiably existed. A helper this many checks stand on has to parse, not
 * pattern-match: the scanner walks the source once, honouring line comments, block comments, single
 * and double quotes with escapes, and template literals.
 *
 * A regex literal is read as a regex: a `/` opens one unless the last significant token is an
 * identifier, a number, a string, `)`, `]` or `<` (a keyword such as `return` still allows one). Its
 * body honours `\` escapes and `[...]` classes, and is blanked like string text. JSX text is not
 * tokenised, so a `/` after `}` in JSX can open a regex that runs to the end of its line.
 *
 * Stated limitation: a template literal is kept whole, so a comment inside `${...}` is kept as text.
 */
export const stripComments = (src) => scanSource(src, { keepLength: false, blankStrings: false });

/**
 * Source with every comment blanked to spaces, so each offset still points at the same character of
 * the file. Strings are kept. A newline is kept, so a line number is kept too.
 */
export const blankComments = (src) => scanSource(src, { keepLength: true, blankStrings: false });

/**
 * Source with every comment AND the text inside every string blanked to spaces, at the same offsets as
 * the file. The quote marks stay. A reader that counts brackets reads this form, because a lone `}` in
 * a string is text, not a bracket. A template literal is blanked whole, its `${...}` too: the brackets
 * inside an interpolation are balanced, so a count over the blanked form still closes in the right place.
 */
export const blankCommentsAndStrings = (src) => scanSource(src, { keepLength: true, blankStrings: true });

/**
 * Source with comments removed AND the text of every string blanked. A quote, a newline and the
 * length of each string stay, so an index into this text is the same index into `stripComments(src)`.
 * Use it when a check counts brackets or braces after it finds its place in `stripComments`: a `{` or
 * a `[` inside a string is text, not syntax. JSX text is not a string, so an apostrophe in JSX text
 * opens a single-quote string that blanks the rest of that line.
 */
export const stripCommentsAndStrings = (src) => scanSource(src, { keepLength: false, blankStrings: true });

// Sticky: reads only the whitespace run after a brace, never the rest of the file.
const SPREAD = /\s*\.\.\./y;
// A `/` after one of these words opens a regex, not a division.
const REGEX_KEYWORDS = new Set(["return", "typeof", "case", "in", "of", "void", "delete", "throw", "new", "else", "do", "yield", "await", "instanceof"]);

/** The one scanner behind the four readers above. */
const scanSource = (src, { keepLength, blankStrings }) => {
  const blank = (ch) => (ch === "\n" ? "\n" : " ");
  let out = "";
  const tpl = []; // open `${` substitutions: the count of unclosed `{` in each
  // Code inside a `${...}` is read, so a nested string or template ends where it should, but it is blanked like template text.
  const put = (t) => { out += blankStrings && tpl.length ? t.replace(/[^\n]/g, " ") : t; };
  let prev2 = "";
  let i = 0;
  let state = "code";
  let inClass = false;
  let last = ""; // last significant char in code; "v" after a string, template or regex
  let word = ""; // the identifier that ends at `last`
  let gap = false;
  const isId = (ch) => /[\w$]/.test(ch);
  // A `{` after `=` or before `...` opens a JSX attr or an object, so its `}` ends a value: a following `/>` closes a tag.
  const braces = [];
  let valueEnd = false; // the last token is the `}` of such a value
  const regexOk = (nx) => !(nx === ">" && valueEnd) && !((last === "+" || last === "-") && prev2 === last) && (last === "" || (!isId(last) && last !== ")" && last !== "]" && last !== "v" && last !== "<")
    || (isId(last) && REGEX_KEYWORDS.has(word)));
  const n = src.length;
  if (src.startsWith("#!")) { // a hashbang line is kept as text: its `/usr/` is not a regex
    while (i < n && src[i] !== "\n") i++;
    put(src.slice(0, i));
  }
  while (i < n) {
    const c = src[i];
    const d = i + 1 < n ? src[i + 1] : "";
    if (state === "code") {
      if (c === "/" && d === "/") { state = "line"; if (keepLength) put("  "); i += 2; continue; }
      if (c === "/" && d === "*") { state = "block"; if (keepLength) put("  "); i += 2; continue; }
      if (c === "'") { state = "single"; last = "v"; put(c); i++; continue; }
      if (c === '"') { state = "double"; last = "v"; put(c); i++; continue; }
      if (c === "`") { state = "template"; last = "v"; put(c); i++; continue; }
      if (c === "/" && regexOk(d)) { state = "regex"; inClass = false; last = "v"; put(c); i++; continue; }
      if (c === "{") braces.push(last === "=" || (SPREAD.lastIndex = i + 1, SPREAD.test(src)));
      if (tpl.length && c === "{") tpl[tpl.length - 1]++;
      if (tpl.length && c === "}") {
        if (tpl[tpl.length - 1] === 0) { tpl.pop(); state = "template"; last = "v"; out += blankStrings ? " " : "}"; i++; continue; }
        tpl[tpl.length - 1]--;
      }
      if (/\s/.test(c)) gap = true;
      else { valueEnd = c === "}" && braces.pop() === true; prev2 = last; word = isId(c) ? (gap || !isId(last) ? c : word + c) : ""; last = c; gap = false; }
      put(c); i++; continue;
    }
    if (state === "line") {
      if (c === "\n") { state = "code"; put(c); } else if (keepLength) put(" ");
      i++; continue;
    }
    if (state === "block") {
      if (c === "*" && d === "/") { state = "code"; if (keepLength) put("  "); i += 2; }
      else { if (keepLength) put(blank(c)); i++; }
      continue;
    }
    if (state === "regex") {
      if (c === "\\" && i + 1 < n && src[i + 1] !== "\n") {
        put(blankStrings ? "  " : c + src[i + 1]);
        i += 2; continue;
      }
      if (c === "[") inClass = true; else if (c === "]") inClass = false;
      const ends = c === "\n" || (c === "/" && !inClass);
      put(blankStrings && !ends ? " " : c);
      if (ends) state = "code";
      i++; continue;
    }
    if (state === "template" && c === "$" && d === "{") {
      tpl.push(0); state = "code"; last = ""; gap = false; put("${"); i += 2; continue;
    }
    // A string state keeps its text verbatim (or blanks it) and honours escapes, so a quote inside a
    // string cannot end it and a comment marker inside a string is text, not a comment.
    if (c === "\\" && i + 1 < n) {
      put(blankStrings ? " " + blank(src[i + 1]) : c + src[i + 1]);
      i += 2; continue;
    }
    const closes = (state === "single" && (c === "'" || c === "\n"))
      || (state === "double" && (c === '"' || c === "\n"))
      || (state === "template" && c === "`");
    put(blankStrings && !closes ? blank(c) : c);
    if (closes) state = "code";
    i++;
  }
  return out;
};
