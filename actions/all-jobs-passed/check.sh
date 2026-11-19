#!/usr/bin/env bash
# Fails unless NEEDS (toJSON(needs)) is non-empty and every job's result is success.
# failure, cancelled and skipped all fail: a skipped required job must not read as green.
# SCOPE_SKIPS, when set, is one JSON object {job: [scope flag, ...]}. A skipped job passes only when it is a key of that object,
# its flag list is not empty, the scope job succeeded, and each listed flag in needs.scope.outputs is exactly "false".
# A records-only run (the scope job succeeded and its records_only_skip output is exactly "true") also passes every skipped job: the run
# started no job but the decision jobs, and a failed or cancelled job still fails it. Only a set SCOPE_SKIPS opts in.
# A proof run also passes every skipped job: the push-skip job succeeded and its outputs are skip exactly "true" with proof_run all digits
# (the number of the run that proved this tree). A failed or cancelled job still fails it. The run's number is printed.
# Unset or empty, no skip passes. A SCOPE_SKIPS that is not JSON fails the check (jq exits non-zero under set -e).
set -euo pipefail
echo "$NEEDS" | jq -r 'to_entries[] | "\(.key): \(.value.result)"'
# The one definition of a proof: the push-skip job succeeded, read skip "true", and proof_run is a string of digits only.
PROOF_DEF='def proof_run($needs): $needs["push-skip"] as $p
  | ($p.result == "success") and ($p.outputs.skip == "true")
    and (($p.outputs.proof_run | type) == "string") and ($p.outputs.proof_run | test("\\A[0-9]+\\z"));'
if [ -z "${SCOPE_SKIPS:-}" ]; then
  echo "$NEEDS" | jq -e 'length > 0 and all(.[]; .result == "success")' >/dev/null
else
  echo "$NEEDS" | jq -e --argjson skips "$SCOPE_SKIPS" "$PROOF_DEF"'
    . as $needs
    | def named_skip($name): ($skips | type) == "object" and ($skips[$name] | type) == "array" and ($skips[$name] | length) > 0
        and $needs.scope.result == "success"
        and all($skips[$name][]; . as $flag | $needs.scope.outputs[$flag] == "false");
    def records_only: $needs.scope.result == "success" and $needs.scope.outputs.records_only_skip == "true";
    length > 0 and all(to_entries[]; .value.result == "success" or (.value.result == "skipped" and (named_skip(.key) or records_only or proof_run($needs))))' >/dev/null
  if echo "$NEEDS" | jq -e "${PROOF_DEF}"' proof_run(.)' >/dev/null 2>&1; then
    echo "proof run: $(echo "$NEEDS" | jq -r '.["push-skip"].outputs.proof_run')"
  fi
fi
