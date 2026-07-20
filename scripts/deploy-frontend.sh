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

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --template-file "$repo_root/infrastructure/frontend-pipeline.yml" \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "GitHubConnectionArn=$GITHUB_CONNECTION_ARN" \
    "GitHubRepository=$GITHUB_REPOSITORY" \
    "GitHubBranch=$GITHUB_BRANCH" \
    "ConfirmationEmailFrom=$CONFIRMATION_EMAIL_FROM"
