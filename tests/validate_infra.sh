#!/usr/bin/env bash
# Validate the CloudFormation template: lint offline (cfn-lint) and, when AWS
# credentials are available, run the service-side validate-template call.
# Catches infra regressions and keeps existing resources/routes well-formed
# (backward compatibility) whenever the template changes.
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
template="$repo_root/infrastructure/cmw-infra.yml"
region="${AWS_REGION:-eu-central-1}"

# Use the tests venv's cfn-lint if present, else whatever is on PATH.
cfn_lint="$repo_root/tests/.venv/bin/cfn-lint"
[ -x "$cfn_lint" ] || cfn_lint="$(command -v cfn-lint || true)"

echo "== cfn-lint =="
if [ -n "$cfn_lint" ]; then
  "$cfn_lint" --region "$region" -- "$template"
  echo "cfn-lint: OK"
else
  echo "cfn-lint not found (run tests/run_all.sh to set up the venv)" >&2
  exit 1
fi

echo "== aws cloudformation validate-template =="
if aws sts get-caller-identity >/dev/null 2>&1; then
  aws cloudformation validate-template \
    --region "$region" \
    --template-body "file://$template" \
    --query 'Parameters[].ParameterKey' --output text
  echo "validate-template: OK"
else
  echo "No AWS credentials — skipping service-side validate-template (offline lint still ran)."
fi
