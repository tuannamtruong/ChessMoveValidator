#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
env_file="$repo_root/.env"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Copy .env.example to .env and set its values." >&2
  exit 1
fi

set -a
. "$env_file"
set +a

: "${AWS_REGION:?AWS_REGION must be set in .env}"
: "${STACK_NAME:?STACK_NAME must be set in .env}"
: "${GITHUB_CONNECTION_ARN:?GITHUB_CONNECTION_ARN must be set in .env}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set in .env}"
: "${GITHUB_BRANCH:?GITHUB_BRANCH must be set in .env}"
: "${CONFIRMATION_EMAIL_FROM:?CONFIRMATION_EMAIL_FROM must be set in .env}"

params=(
  "GitHubConnectionArn=$GITHUB_CONNECTION_ARN"
  "GitHubRepository=$GITHUB_REPOSITORY"
  "GitHubBranch=$GITHUB_BRANCH"
  "ConfirmationEmailFrom=$CONFIRMATION_EMAIL_FROM"
)

if [ -n "${DEPLOYMENT_VERSION:-}" ]; then
  echo "API bumped"
  params+=("ApiDeploymentVersion=$DEPLOYMENT_VERSION")
else
  echo "No change in API"
fi


# The evaluator Lambda's source is too large for an inline Code.ZipFile (the
# 4096-char CloudFormation limit), so it lives under functions/ and is uploaded
# by `aws cloudformation package`, which rewrites its Code to an S3 reference.
# Packaging needs a bucket that already exists (the stack's own ArtifactBucket
# can't be used — it doesn't exist yet on the first deploy), so derive a stable
# per-account bucket name and create it once if missing.
account_id="$(aws sts get-caller-identity --query Account --output text)"
package_bucket="${PACKAGE_BUCKET:-${STACK_NAME}-art-${account_id}}"

if ! aws s3api head-bucket --bucket "$package_bucket" >/dev/null 2>&1; then
  echo "Creating packaging bucket $package_bucket"
  aws s3api create-bucket \
    --bucket "$package_bucket" \
    --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  aws s3api put-public-access-block \
    --bucket "$package_bucket" \
    --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

packaged_template="$(mktemp)"
trap 'rm -f "$packaged_template"' EXIT

aws cloudformation package \
  --region "$AWS_REGION" \
  --template-file "$repo_root/infrastructure/frontend-pipeline.yml" \
  --s3-bucket "$package_bucket" \
  --output-template-file "$packaged_template"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --template-file "$packaged_template" \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides "${params[@]}"

# CloudFormation does not re-snapshot an AWS::ApiGateway::Deployment when only
# its properties change, so a stack update that adds or changes API routes can
# leave the prod stage serving a stale deployment. Force a fresh deployment of
# the current API onto the stage whenever the API was bumped.
if [ -n "${DEPLOYMENT_VERSION:-}" ]; then
  api_id="$(aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='UploadApiId'].OutputValue" \
    --output text)"

  if [ -z "$api_id" ] || [ "$api_id" = "None" ]; then
    echo "Could not read UploadApiId from stack outputs; skipping stage redeployment." >&2
    exit 1
  fi

  echo "Forcing prod stage redeployment for API $api_id"
  aws apigateway create-deployment \
    --region "$AWS_REGION" \
    --rest-api-id "$api_id" \
    --stage-name prod \
    --description "deploy-frontend.sh $DEPLOYMENT_VERSION" \
    --no-cli-pager >/dev/null
fi