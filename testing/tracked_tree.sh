# shellcheck shell=sh
# testing/tracked_tree.sh: copy what git lists under named repo folders into a fixture tree, so no
# shell fixture lists files. The rules and the reason are in testing/tracked_tree.py; this is the
# same helper for POSIX sh and bash suites. Source it after setting TRACKED_ROOT to the repo:
#   TRACKED_ROOT=$REPO_ROOT; . "$REPO_ROOT/testing/tracked_tree.sh"
#   copy_tracked <dest-root> <folder>...      lands <dest-root>/<folder>/<path>
#   copy_folder <folder> <dest> [<skip>...]   lands <dest>/<path>; each <skip> is a path below the folder, with no space
# Each returns non-zero, with a line on stderr, when git cannot list a folder or lists nothing in it.
# Paths are read one per line with core.quotePath off, so a path that holds a newline is refused.

# bash 3.2 (macOS /bin/sh) misreads a case pattern's ")" inside $( ), so the suite test is its own function.
_tt_is_suite() {
  case $1 in test_*|*_test.py|*.test.*) return 0 ;; esac
  return 1
}

tracked_list() { # <folder>: one path per line, relative to the folder; suites and missing files left out
  _tt_folder=${1%/}
  [ -n "${TRACKED_ROOT:-}" ] || { echo "tracked_tree.sh: TRACKED_ROOT is not set" >&2; return 1; }
  _tt_out=$(git -C "$TRACKED_ROOT" -c core.quotePath=false ls-files --cached --others --exclude-standard -- "$_tt_folder/") ||
    { echo "tracked_tree.sh: git ls-files failed for $_tt_folder/ in $TRACKED_ROOT" >&2; return 1; }
  case $_tt_out in *'"'*) echo "tracked_tree.sh: a path under $_tt_folder/ needs quoting; use tracked_tree.py" >&2; return 1 ;; esac
  _tt_list=$(printf '%s\n' "$_tt_out" | sort -u | while IFS= read -r _tt_p; do
    [ -n "$_tt_p" ] || continue
    _tt_is_suite "${_tt_p##*/}" && continue
    if [ -f "$TRACKED_ROOT/$_tt_p" ]; then printf '%s\n' "${_tt_p#"$_tt_folder"/}"; fi
  done)
  [ -n "$_tt_list" ] || { echo "tracked_tree.sh: git lists no file under $_tt_folder/ in $TRACKED_ROOT" >&2; return 1; }
  printf '%s\n' "$_tt_list"
}

copy_folder() { # <folder> <dest> [<skip>...]
  _tt_src=${1%/}; _tt_dest=$2; shift 2
  _tt_names=$(tracked_list "$_tt_src") || return 1
  _tt_rc=0
  _tt_skips=$*
  while IFS= read -r _tt_rel; do
    _tt_keep=1
    for _tt_s in $_tt_skips; do [ "$_tt_s" = "$_tt_rel" ] && _tt_keep=0; done
    [ "$_tt_keep" = 1 ] || continue
    case $_tt_rel in */*) mkdir -p "$_tt_dest/${_tt_rel%/*}" || _tt_rc=1 ;; *) mkdir -p "$_tt_dest" || _tt_rc=1 ;; esac
    cp "$TRACKED_ROOT/$_tt_src/$_tt_rel" "$_tt_dest/$_tt_rel" || _tt_rc=1
  done <<EOF
$_tt_names
EOF
  return $_tt_rc
}

copy_tracked() { # <dest-root> <folder>...
  _tt_root=$1; shift
  for _tt_f in "$@"; do copy_folder "$_tt_f" "$_tt_root/${_tt_f%/}" || return 1; done
}
