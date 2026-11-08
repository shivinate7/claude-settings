#!/usr/bin/env bash
# The ste-lint step. One home: actions/ste-lint/action.yml and bin/ste-changed both run it.
# Reads the env that action.yml sets; bin/ste-changed sets the same names.
set -euo pipefail
# Needs actions/checkout with fetch-depth 0: scope 'changed' diffs against the
# base branch, and a shallow clone would not carry that history.
LINTER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../lint/ste_lint.py"
STALE_CITES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../lint/stale_cites.py"

cd "$(git rev-parse --show-toplevel)"  # git diff prints root-relative paths; match them from any subdirectory

# Excludes: .ste-lint-exclude at the git top level of the repo being linted (one pathspec per line,
# '#' starts a comment), plus the EXCLUDE input (newline- or comma-separated). Trim each line, skip
# empty ones, turn each into ':(exclude,glob)<pattern>', so '**/' matches zero directories as in the include.
# The separating echo keeps a file with no final newline from joining its last line to the input's first.
EXCLUDE_PATTERNS=()
EXCLUDE_PATHSPECS=()
while IFS= read -r p || [ -n "$p" ]; do
  p="$(echo "$p" | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  case "$p" in ''|'#'*) continue ;; esac
  EXCLUDE_PATTERNS+=("$p")
  EXCLUDE_PATHSPECS+=(":(exclude,glob)$p")
done < <([ -f .ste-lint-exclude ] && cat .ste-lint-exclude; echo; printf '%s\n' "${EXCLUDE:-}" | tr ',' '\n')

RAW_FILES=()
FILES=()
NO_BASE=0
if [ "$SCOPE" = "all" ]; then
  # ':(glob)' turns on real double-star matching. Without it, git's default
  # pathspec needs a literal '/' for '**/', so a root file such as README.md
  # never matches '**/*.md' (measured).
  # -z on every list of names: git quotes a non-ASCII name ("caf\303\251.md") in a newline list.
  while IFS= read -r -d '' f; do
    RAW_FILES+=("$f")
  done < <(git ls-files -z -- ":(glob)$PATHS_GLOB")
  while IFS= read -r -d '' f; do
    FILES+=("$f")
  done < <(git ls-files -z -- ":(glob)$PATHS_GLOB" ${EXCLUDE_PATHSPECS[@]+"${EXCLUDE_PATHSPECS[@]}"})
else
  if [ -n "$BASE_REF" ]; then
    BASE="$BASE_REF"
  else
    BASE="$DEFAULT_BRANCH"
  fi
  if ! git rev-parse --verify -q "refs/remotes/origin/$BASE" >/dev/null; then
    git fetch origin "$BASE" --depth=1
  fi
  if [ -z "$BASE_REF" ] && [ "$REF_NAME" = "$BASE" ]; then
    # A push to the default branch itself has no other side to diff against.
    RANGE="HEAD~1..HEAD"
    FROM="HEAD~1"
  else
    RANGE="origin/$BASE...HEAD"
    FROM="$(git merge-base "origin/$BASE" HEAD 2>/dev/null)" || FROM=""
  fi
  UNTRACKED=()
  WORK=""
  if [ -z "$FROM" ]; then
    # No merge base (an unrelated history, or a shallow clone): the base is unknown, not a finding (decision
    # stale-cites-at-merge, rule verification-report-unknown-reads). No changed file is read and the exit stays 0.
    NO_BASE=1
    echo "ste-lint: unknown, no merge base between origin/$BASE and HEAD, so no changed file was read. Nothing was checked. Check out with fetch-depth 0 (actions/checkout) so the history is there."
  else
    # The one changed set, for both steps below: the diff from FROM to WORK, plus the files git does not track.
    # WORK is the commit `git stash create` builds from the tracked files as they are now, staged or not. It stores
    # no ref, leaves the index and the working tree alone, and writes only unreachable objects. For a clean tree,
    # as in CI, it prints nothing and WORK is HEAD. So one diff holds the commits and the working tree: a tracked
    # file edited, staged or removed and not yet committed counts, with its working-tree line numbers.
    # A new file that git does not track and .gitignore does not match is all new lines (UNTRACKED). The stale-cites
    # step reads committed trees, so it sees the removals in WORK but never reads an untracked file.
    WORK="$(git -c user.name=ste-lint -c user.email=ste-lint@localhost stash create)"
    [ -n "$WORK" ] || WORK="$(git rev-parse HEAD)"
    while IFS= read -r -d '' f; do
      UNTRACKED+=("$f")
    done < <(git ls-files -z --others --exclude-standard -- "$CHANGED_PATHS_GLOB")
    while IFS= read -r -d '' f; do
      [ -n "$f" ] && RAW_FILES+=("$f")
    done < <(git diff -z --name-only --diff-filter=AMR "$FROM" "$WORK" -- "$CHANGED_PATHS_GLOB"
             printf '%s\0' ${UNTRACKED[@]+"${UNTRACKED[@]}"})
    while IFS= read -r -d '' f; do
      FILES+=("$f")
    done < <(git diff -z --name-only --diff-filter=AMR "$FROM" "$WORK" -- "$CHANGED_PATHS_GLOB" ${EXCLUDE_PATHSPECS[@]+"${EXCLUDE_PATHSPECS[@]}"}
             git ls-files -z --others --exclude-standard -- "$CHANGED_PATHS_GLOB" ${EXCLUDE_PATHSPECS[@]+"${EXCLUDE_PATHSPECS[@]}"})
  fi
fi

# In-script fallback: a caller that passes a plain glob (no ':(exclude)' magic
# understanding needed) still gets it dropped here.
if [ ${#EXCLUDE_PATTERNS[@]} -gt 0 ] && [ ${#FILES[@]} -gt 0 ]; then
  KEPT=()
  for f in ${FILES[@]+"${FILES[@]}"}; do
    DROP=0
    for pattern in ${EXCLUDE_PATTERNS[@]+"${EXCLUDE_PATTERNS[@]}"}; do
      # SC2053: the exclude pattern is a glob on purpose, so the right side stays unquoted.
      # shellcheck disable=SC2053
      if [[ "$f" == $pattern ]]; then
        DROP=1
        break
      fi
    done
    [ "$DROP" -eq 0 ] && KEPT+=("$f")
  done
  FILES=(${KEPT[@]+"${KEPT[@]}"})
fi

EXCLUDED_COUNT=$((${#RAW_FILES[@]} - ${#FILES[@]}))

# Log + annotate findings. One home for both scopes. GitHub workflow-command
# escaping: data escapes % \r \n; a property also escapes : and ,.
EMIT_DIR="$(mktemp -d)"
cat > "$EMIT_DIR/ste_emit.py" <<'PYEOF'
def _esc(s, prop=False):
    s = str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return s.replace(":", "%3A").replace(",", "%2C") if prop else s

def emit(findings, out):
    for f in findings:
        line = f.get("line")
        where = "%s:%s" % (f["path"], line) if line is not None else f["path"]
        text = "%s %s" % (f["code"], f["message"])
        print("%s: %s" % (where, text.replace("\r", " ").replace("\n", " ")), file=out)
        cmd = "error" if f["severity"] == "error" else "warning"
        props = "file=%s" % _esc(f["path"], True)
        if line is not None:
            props += ",line=%s" % line
        print("::%s %s::%s" % (cmd, props, _esc(text)), file=out)
PYEOF
export PYTHONPATH="$EMIT_DIR${PYTHONPATH:+:$PYTHONPATH}"

SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
LOG_OUT="$(mktemp)"

# Stale prose (lint/stale_cites.py, decision stale-cites-at-merge): a Markdown line that names a path, or
# a Python name bound at module level, that this range removed. Scope changed only. It runs before the
# "no markdown changed" exit, so a code-only PR is checked. Its findings never go through the split
# script below: every stale line is untouched by the range, and the split makes an untouched line
# report-only. FAIL=false prints them and keeps the exit 0, as it does for the STE findings.
STALE_EXIT=0
if [ "$SCOPE" != "all" ]; then
  STALE_OUT="$(mktemp)"
  set +e
  # FROM..WORK is the changed set the STE step reads (above). With no merge base there is no FROM, and the
  # committed range makes stale_cites print its own unknown line.
  if [ "$NO_BASE" -eq 1 ]; then STALE_RANGE="$RANGE"; else STALE_RANGE="$FROM..$WORK"; fi
  python3 "$STALE_CITES" --range "$STALE_RANGE" > "$STALE_OUT"
  STALE_EXIT=$?
  set -e
  cat "$STALE_OUT"
  # The report lines (anchors that changed, decisions whose Home is a changed file) join the step summary, in
  # a fence so a `*` or `_` in a path stays literal. They never change the exit.
  if grep -q '^stale-cites: report, ' "$STALE_OUT"; then
    {
      echo "### Stale-cites report"
      echo
      echo '```text'
      grep '^stale-cites: report, ' "$STALE_OUT" | sed 's/^stale-cites: report, //'
      echo '```'
      echo
    } >> "$SUMMARY"
  fi
fi
# --tree (the tree-cites input) names stale cites on lines the range never touched, so it runs in both scopes.
if [ "${TREE_CITES:-false}" = "true" ]; then
  set +e
  python3 "$STALE_CITES" --tree
  TREE_EXIT=$?
  set -e
  [ "$TREE_EXIT" -ne 0 ] && STALE_EXIT="$TREE_EXIT"
fi
[ "${FAIL:-true}" = "true" ] || STALE_EXIT=0

if [ ${#FILES[@]} -eq 0 ]; then
  # An unknown merge base already printed its own line, and "no markdown changed" would be false: none was read.
  [ "$NO_BASE" -eq 1 ] || echo "ste-lint: no markdown changed"
  {
    echo "### STE lint"
    echo
    echo "No markdown changed."
    if [ "$EXCLUDED_COUNT" -gt 0 ]; then
      echo
      echo "Excluded: $EXCLUDED_COUNT file(s)."
    fi
  } >> "$SUMMARY"
  exit "$STALE_EXIT"
fi

echo "ste-lint: ${#FILES[@]} file(s) in scope, $EXCLUDED_COUNT excluded"
printf '  %s\n' ${FILES[@]+"${FILES[@]}"}

# decisions-dir: empty is the folder lint/layout.json names, "off" turns the gloss collapse off.
DECISIONS=()
case "${DECISIONS_DIR:-}" in
  "") ;;
  off) DECISIONS=(--decisions-dir "") ;;
  *) DECISIONS=(--decisions-dir "$DECISIONS_DIR") ;;
esac
JSON_OUT="$(mktemp)"
python3 "$LINTER" --no-color --format json --fail-on never \
  ${DECISIONS[@]+"${DECISIONS[@]}"} ${FILES[@]+"${FILES[@]}"} > "$JSON_OUT"

if [ "$SCOPE" = "all" ]; then
  # Report-mode audit: whole-file findings, never fails the build.
  # A script file in $EMIT_DIR, not `python3 -c`: -c puts the linted repo's root first on
  # sys.path, so a planted json.py or ste_emit.py there would run.
  AUDIT_PY="$EMIT_DIR/ste_audit.py"
  cat > "$AUDIT_PY" <<'PYEOF'
import json, sys
from ste_emit import emit
d = json.load(open(sys.argv[1]))
s = d["summary"]
excluded = int(sys.argv[2])
print("### STE lint")
print()
print("Files checked: %d. Excluded: %d. Errors: %d. Warnings: %d." % (d["files"], excluded, s["error"], s["warning"]))
print()
print("| File | Line | Rule | Message |")
print("| --- | --- | --- | --- |")
for f in d["findings"][:50]:
    print("| %s | %d | %s | %s |" % (f["path"], f["line"], f["code"], f["message"].replace("|", "\\|").replace("\n", " ")))
with open(sys.argv[3], "w") as o:
    emit(d["findings"], o)
    print("ste-lint: audit, %d error(s), %d warning(s), report only" % (s["error"], s["warning"]), file=o)
PYEOF
  python3 "$AUDIT_PY" "$JSON_OUT" "$EXCLUDED_COUNT" "$LOG_OUT" >> "$SUMMARY"
  cat "$LOG_OUT"
  exit "$STALE_EXIT"  # 0 unless tree-cites found a stale cite
fi

# Decision 4: changed lines only. Build a map of file -> added line numbers from a
# zero-context unified diff, "@@ -a,b +c,d @@" giving c..c+d-1 (d defaults to 1, d
# of 0 means the hunk added no lines). Written to a script file, not a `python3 -c`
# multi-line string, so the YAML block scalar's own indentation never lands inside
# the Python source (an indented top-level statement is a Python syntax error).
HUNK_MAP_PY="$(mktemp)"
cat > "$HUNK_MAP_PY" <<'PYEOF'
import re, sys
cur = None
out = []
header = re.compile(r"^\+\+\+ b/(.*)$")
hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
for path in sys.argv[1:]:  # an untracked file: every line is new
    with open(path, encoding="utf-8", errors="replace") as f:
        out.extend("%s\t%d" % (path, n) for n, _ in enumerate(f, 1))
for line in sys.stdin:
    line = line.rstrip("\n")
    m = header.match(line)
    if m:
        cur = m.group(1)
        continue
    m = hunk.match(line)
    if m and cur is not None:
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        for n in range(start, start + count):
            out.append("%s\t%d" % (cur, n))
print("\n".join(out))
PYEOF

HUNKS="$(mktemp)"
git -c core.quotepath=off diff -U0 "$FROM" "$WORK" -- ${FILES[@]+"${FILES[@]}"} | python3 "$HUNK_MAP_PY" ${UNTRACKED[@]+"${UNTRACKED[@]}"} > "$HUNKS"

# Split findings into in-hunk (can fail the job) and out-of-hunk (pre-existing, report only).
# A finding without a line number counts as in-hunk.
SPLIT_PY="$(mktemp)"
cat > "$SPLIT_PY" <<'PYEOF'
import json, sys
from ste_emit import emit
json_path, hunks_path, excluded, fail, log_path, failed_path = sys.argv[1:7]
d = json.load(open(json_path))
added = set()
with open(hunks_path, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        path, n = line.rsplit("\t", 1)
        added.add((path, int(n)))
in_hunk, out_hunk = [], []
for finding in d["findings"]:
    line = finding.get("line")
    if line is None or (finding["path"], line) in added:
        in_hunk.append(finding)
    else:
        out_hunk.append(finding)

def sev_count(items, sev):
    return sum(1 for f in items if f["severity"] == sev)

def table(items):
    print("| File | Line | Rule | Message |")
    print("| --- | --- | --- | --- |")
    for f in items[:50]:
        print("| %s | %s | %s | %s |" % (
            f["path"], f.get("line", ""), f["code"],
            f["message"].replace("|", "\\|").replace("\n", " ")))

print("### STE lint")
print()
print("Files checked: %d. Excluded: %d." % (d["files"], int(excluded)))
print("Can fail the job, changed lines: %d error(s), %d warning(s)."
      % (sev_count(in_hunk, "error"), sev_count(in_hunk, "warning")))
print("Pre-existing, report only: %d error(s), %d warning(s)."
      % (sev_count(out_hunk, "error"), sev_count(out_hunk, "warning")))
print()
table(in_hunk)
if out_hunk:
    print()
    print("#### Pre-existing, report only")
    print()
    table(out_hunk)

failing = fail == "true" and sev_count(in_hunk, "error") > 0
with open(log_path, "w") as o:
    emit(in_hunk, o)
    print("ste-lint: %s, %d error(s), %d warning(s) on changed lines"
          % ("FAIL" if failing else "PASS", sev_count(in_hunk, "error"),
             sev_count(in_hunk, "warning")), file=o)
# The paths with an error on a changed line, NUL-separated, so the caller can tell which of them are untracked.
with open(failed_path, "w", encoding="utf-8") as o:
    o.write("".join(p + "\0" for p in sorted({f["path"] for f in in_hunk if f["severity"] == "error"})))
sys.exit(1 if failing else 0)
PYEOF

FAILED_PATHS="$(mktemp)"
set +e
python3 "$SPLIT_PY" "$JSON_OUT" "$HUNKS" "$EXCLUDED_COUNT" "$FAIL" "$LOG_OUT" "$FAILED_PATHS" >> "$SUMMARY"
CHECK_EXIT=$?
set -e
cat "$LOG_OUT"
# An untracked file that fails the lint may be a scratch file. One line names the way out, once.
if [ "$CHECK_EXIT" -ne 0 ] && [ ${#UNTRACKED[@]} -gt 0 ]; then
  while IFS= read -r -d '' failed; do
    for u in "${UNTRACKED[@]}"; do
      if [ "$failed" = "$u" ]; then
        echo "ste-lint: $failed is untracked. A scratch file that is not for the repo goes in .gitignore or .ste-lint-exclude, and is then not linted."
        break 2
      fi
    done
  done < "$FAILED_PATHS"
fi

[ "$STALE_EXIT" -ne 0 ] && CHECK_EXIT="$STALE_EXIT"
exit "$CHECK_EXIT"
