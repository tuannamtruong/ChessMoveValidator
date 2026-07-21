#!/usr/bin/env bash
# One command to run after each change: validates the new behavior AND
# backward compatibility across every layer of this project.
#
#   1. deploy-script syntax   (bash -n)
#   2. infra                  (cfn-lint + aws validate-template)
#   3. Lambda handlers        (behavioral tests, boto3 mocked)
#   4. frontend               (headless Chromium smoke + screenshot)
#
# First run sets up tests/.venv and installs Node deps; later runs reuse them.
# Usage: bash tests/run_all.sh
set -uo pipefail

here="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "$here/.." && pwd)"
region="${AWS_REGION:-eu-central-1}"
venv="$here/.venv"
py="$venv/bin/python"

echo "== setup: python venv =="
if [ ! -x "$py" ]; then
  python3 -m venv "$venv"
  "$venv/bin/pip" install --quiet --upgrade pip
  "$venv/bin/pip" install --quiet -r "$here/requirements.txt"
fi
echo "venv ready: $("$py" --version)"

echo "== setup: node deps =="
if [ ! -d "$here/node_modules/playwright" ]; then
  ( cd "$here" && npm install --no-audit --no-fund --silent )
fi
# Ensure the Playwright browser matching the installed package is present.
( cd "$here" && npx --yes playwright install chromium >/dev/null 2>&1 ) || true
echo "node deps ready"

fail=0
run() { # run <label> <command...>
  local label="$1"; shift
  echo
  echo "========== $label =========="
  if "$@"; then
    echo ">> $label: PASS"
  else
    echo ">> $label: FAIL"
    fail=1
  fi
}

run "deploy-script syntax" bash -n "$repo_root/scripts/deploy-cmw-infra.sh"
run "infrastructure"       env AWS_REGION="$region" bash "$here/validate_infra.sh"
run "lambda handlers"      bash -c "cd '$here' && '$py' test_lambdas.py"
run "frontend smoke"       node "$here/smoke_frontend.mjs"

echo
if [ "$fail" -eq 0 ]; then
  echo "ALL SUITES PASSED"
else
  echo "ONE OR MORE SUITES FAILED"
fi
exit "$fail"
