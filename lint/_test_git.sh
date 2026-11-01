# shellcheck shell=sh
# The shell twin of lint/_test_git.py, the test-run commit-signing opt-out. A shell test suite that
# commits, merges or tags in a fixture repo sources this file once, near the top. It appends
# commit.gpgsign=false and tag.gpgsign=false through GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n /
# GIT_CONFIG_VALUE_n, keeps keys already set, and adds nothing when sourced again.
# It runs under POSIX sh, `set -e` and `set -u`.

_test_git_apply() {
    _test_git_count=${GIT_CONFIG_COUNT:-0}
    case $_test_git_count in '' | *[!0-9]*) _test_git_count=0 ;; esac
    # The same two keys as OPT_OUT in lint/_test_git.py: a sourced POSIX shell file cannot import
    # a Python constant or find its own path to read a shared data file.
    for _test_git_key in commit.gpgsign tag.gpgsign; do
        _test_git_last=
        _test_git_i=0 _test_git_k='' _test_git_v=''
        while [ "$_test_git_i" -lt "$_test_git_count" ]; do
            eval "_test_git_k=\${GIT_CONFIG_KEY_$_test_git_i:-} _test_git_v=\${GIT_CONFIG_VALUE_$_test_git_i:-}"
            case $(printf '%s' "$_test_git_k" | tr '[:upper:]' '[:lower:]') in
                "$_test_git_key") _test_git_last=$_test_git_v ;;
            esac
            _test_git_i=$((_test_git_i + 1))
        done
        if [ "$_test_git_last" != false ]; then
            export "GIT_CONFIG_KEY_$_test_git_count=$_test_git_key" "GIT_CONFIG_VALUE_$_test_git_count=false"
            _test_git_count=$((_test_git_count + 1))
        fi
    done
    export GIT_CONFIG_COUNT="$_test_git_count"
    unset _test_git_count _test_git_key _test_git_last _test_git_i _test_git_k _test_git_v
}
_test_git_apply
unset -f _test_git_apply
