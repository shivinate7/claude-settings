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
 * body honours `\` escapes and `[...]` classes, and is blanked like string text. JSX is read too: the text
 * between a tag's `>` and the next `<` or `{` is text, so a quote, a `//` or a `/` in it opens nothing. JSX text
 * is kept as written, never blanked. A `{...}` in JSX is code again.
 *
 * Stated limitation: a template literal is kept whole, so a comment inside `${...}` is kept as text.
 */
export const stripComments = (src, file) => scanSource(src, { keepLength: false, blankStrings: false }, file);

/**
 * Source with every comment blanked to spaces, so each offset still points at the same character of
 * the file. Strings are kept. A newline is kept, so a line number is kept too.
 */
export const blankComments = (src, file) => scanSource(src, { keepLength: true, blankStrings: false }, file);

/**
 * Source with every comment AND the text inside every string blanked to spaces, at the same offsets as
 * the file. The quote marks stay. A reader that counts brackets reads this form, because a lone `}` in
 * a string is text, not a bracket. A template literal is blanked whole, its `${...}` too: the brackets
 * inside an interpolation are balanced, so a count over the blanked form still closes in the right place.
 */
export const blankCommentsAndStrings = (src, file) => scanSource(src, { keepLength: true, blankStrings: true }, file);

/**
 * Source with comments removed AND the text of every string blanked. A quote, a newline and the
 * length of each string stay, so an index into this text is the same index into `stripComments(src)`.
 * Use it when a check counts brackets or braces after it finds its place in `stripComments`: a `{` or
 * a `[` inside a string is text, not syntax. JSX text is not a string, so an apostrophe in JSX text
 * opens nothing.
 */
export const stripCommentsAndStrings = (src, file) => scanSource(src, { keepLength: false, blankStrings: true }, file);

// Sticky: reads only the whitespace run after a brace, never the rest of the file.
const SPREAD = /\s*\.\.\./y;
// A `<` that opens a JSX tag: a tag name that ends at a space, a `/`, a `>` or the `<` of a type argument, or the `>` of a fragment.
// A name that `extends`, `,`, `=` or `>(` follows is a generic, as in `<T extends X>(a) =>`, `<T,>`, `<T = unknown>` and `<T>(a) =>`: no tag.
// A `const` modifier opens a generic too, as in `<const T,>(a) =>`.
const TAG_START = /<(?:(?!const\s|[A-Za-z_$][\w$.:-]*(?:\s+extends\b|\s*,|\s*=(?!=)|>\())[A-Za-z_$][\w$.:-]*(?=[\s/><])|(?=>))/y;
// A `/` after one of these words opens a regex, not a division.
const REGEX_KEYWORDS = new Set(["return", "typeof", "case", "in", "of", "void", "delete", "throw", "new", "else", "do", "yield", "await", "instanceof"]);

/**
 * The one scanner behind the four readers above. It reads JSX, so a `<` that opens a tag starts a run of tag, text and `{...}` code.
 * Only a file name that ends in `.tsx` or `.jsx` holds JSX. Any other name, and a call with no name, is read with no JSX.
 * A file that leaves a tag open at its end held no JSX: its `<` was a type assertion, as in `<T>x`. The scan then runs again with no JSX.
 * Stated limit: in a `.tsx` file, JSX text `<span>(Don't)</span>` reads as a generic arrow, as `>(` does in `<T>(x: T) => T`.
 */
const scanSource = (src, opts, file) => {
  if (!/\.[jt]sx$/.test(file ?? "")) return scan(src, opts, false).out;
  const read = scan(src, opts, true);
  return read.open ? scan(src, opts, false).out : read.out;
};

const scan = (src, { keepLength, blankStrings }, jsx) => {
  const blank = (ch) => (ch === "\n" ? "\n" : " ");
  let out = "";
  // Open `${` and JSX `{` substitutions, the innermost last. `n` counts the unclosed `{` inside it, `e` is the count of open JSX
  // elements of the code around it, and `back`, `closing` and `ang` hold the tag state that a JSX `{` returns to.
  const ctx = [];
  let tplN = 0; // the `${` substitutions in `ctx`
  // Code inside a `${...}` is read, so a nested string or template ends where it should, but it is blanked like template text.
  const put = (t) => { out += blankStrings && tplN ? t.replace(/[^\n]/g, " ") : t; };
  let depth = 0; // open JSX elements in the code that is read now
  let closing = false; // the tag that is read now is a closing tag
  let ang = 0; // the `<` of a type argument, as in `<Foo<string> a="b">`, that its `>` has not closed
  let attr = false; // the string that is read now is a JSX attribute: no escapes, and it may span lines
  let after = "code"; // the state that the comment read now returns to: a comment between the attributes of a tag returns to the tag
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
  const afterOperator = () => last === "" || (!isId(last) && last !== ")" && last !== "]" && last !== "v" && last !== "<");
  const regexOk = (nx) => !(nx === ">" && valueEnd) && !((last === "+" || last === "-") && prev2 === last) && afterOperator()
    || (isId(last) && REGEX_KEYWORDS.has(word));
  // The JSX `{` that a tag or a text opens. Its code is read until the `}` that closes it.
  const openExpression = (back) => {
    ctx.push({ t: "jsx", n: 0, e: depth, back, closing, ang });
    depth = 0; state = "code"; last = "{"; word = ""; gap = false; valueEnd = false;
  };
  const startsTag = (at) => { TAG_START.lastIndex = at; return TAG_START.test(src); };
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
      if (jsx && c === "<" && (afterOperator() || (isId(last) && REGEX_KEYWORDS.has(word))) && startsTag(i)) {
        state = "tag"; closing = false; ang = 0; put(c); i++; continue;
      }
      if (c === "{") braces.push(last === "=" || (SPREAD.lastIndex = i + 1, SPREAD.test(src)));
      if (ctx.length && c === "{") ctx[ctx.length - 1].n++;
      if (ctx.length && c === "}") {
        const top = ctx[ctx.length - 1];
        if (top.n === 0) {
          ctx.pop(); depth = top.e;
          if (top.t === "tpl") { tplN--; state = "template"; last = "v"; out += blankStrings ? " " : "}"; }
          else { state = top.back; closing = top.closing; ang = top.ang; last = "v"; word = ""; gap = false; valueEnd = false; put(c); }
          i++; continue;
        }
        top.n--;
      }
      if (/\s/.test(c)) gap = true;
      else { valueEnd = c === "}" && braces.pop() === true; prev2 = last; word = isId(c) ? (gap || !isId(last) ? c : word + c) : ""; last = c; gap = false; }
      put(c); i++; continue;
    }
    // A JSX tag: the name and the attributes, from the `<` to the `>`. A string in it is an attribute, and a `{` in it is code.
    if (state === "tag") {
      if (c === '"' || c === "'") { state = c === "'" ? "single" : "double"; attr = true; put(c); i++; continue; }
      if (c === "{") { put(c); i++; openExpression("tag"); continue; }
      if (c === "/" && (d === "/" || d === "*")) { state = d === "/" ? "line" : "block"; after = "tag"; if (keepLength) put("  "); i += 2; continue; }
      if (c === "<") ang++;
      else if (c === ">" && ang > 0) ang--;
      else if (c === ">" || (c === "/" && d === ">")) {
        const self = c === "/";
        put(self ? "/>" : ">"); i += self ? 2 : 1;
        if (!self) depth += closing ? -1 : 1;
        state = depth > 0 ? "jsxtext" : "code";
        last = "v"; word = ""; gap = false; valueEnd = false;
        continue;
      }
      put(c); i++; continue;
    }
    // JSX text, from a tag's `>` to the next `<` or `{`. It is text, so a quote, a comment opener and a `/` in it open nothing. It stays as written.
    if (state === "jsxtext") {
      if (c === "{") { put(c); i++; openExpression("jsxtext"); continue; }
      if (c === "<" && (d === "/" || startsTag(i))) { state = "tag"; closing = d === "/"; ang = 0; put(closing ? "</" : c); i += closing ? 2 : 1; continue; }
      put(c); i++; continue;
    }
    if (state === "line") {
      if (c === "\n") { state = after; after = "code"; put(c); } else if (keepLength) put(" ");
      i++; continue;
    }
    if (state === "block") {
      if (c === "*" && d === "/") { state = after; after = "code"; if (keepLength) put("  "); i += 2; }
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
      ctx.push({ t: "tpl", n: 0, e: depth }); tplN++; depth = 0; state = "code"; last = ""; gap = false; put("${"); i += 2; continue;
    }
    // A string state keeps its text verbatim (or blanks it) and honours escapes, so a quote inside a
    // string cannot end it and a comment marker inside a string is text, not a comment.
    if (c === "\\" && i + 1 < n && !attr) {
      put(blankStrings ? " " + blank(src[i + 1]) : c + src[i + 1]);
      i += 2; continue;
    }
    const closes = (state === "single" && (c === "'" || (c === "\n" && !attr)))
      || (state === "double" && (c === '"' || (c === "\n" && !attr)))
      || (state === "template" && c === "`");
    put(blankStrings && !closes ? blank(c) : c);
    if (closes) { state = attr ? "tag" : "code"; attr = false; }
    i++;
  }
  return { out, open: depth !== 0 || state === "tag" || state === "jsxtext" || ctx.some((x) => x.t === "jsx") };
};
