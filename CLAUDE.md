# CLAUDE.md

## Scope

This repository currently implements the first deployment phase:

- `frontend/` contains the static web frontend.
- `infrastructure/` defines the AWS infrastructure.
- `buildspec.yml` deploys `frontend/` to the frontend bucket and invalidates CloudFront.
- `scripts/deploy-cmw-infra.sh` deploys the CloudFormation stack from local configuration.

## AWS configuration

- Deploy to `eu-central-1` by default.
- The GitHub source is `tuannamtruong/ChessMoveValidator`, branch `main`.
- Keep infrastructure changes in CloudFormation. Do not create or modify stack resources manually in the AWS console when the change can be represented in the template.
- Validate CloudFormation changes with:

  ```bash
  aws cloudformation validate-template \
    --region eu-central-1 \
    --template-body file://infrastructure/cmw-infra.yml
  ```

## Local configuration and secrets

- `.env` is local deployment configuration and is gitignored.
- Use `.env.example` for documented configuration keys.
- `scripts/deploy-cmw-infra.sh` loads `.env`; do not duplicate connection ARNs or account-specific values in tracked files.

## Frontend and delivery changes

- Keep the frontend dependency-free unless a user request requires a build tool or framework.
- Files deployed to the website must be under `frontend/`.
- Preserve the private S3 bucket and CloudFront Origin Access Control; do not enable public S3 website hosting.
- Changes to `frontend/` are deployed by the GitHub-connected CodePipeline after a push to `main`.

## Deploy

- `./scripts/deploy-cmw-infra.sh` deploys the CloudFormation stack (`chess-move-validator-stack`) from `.env`. Only run a real deployment when the user explicitly asks.
- Set `DEPLOYMENT_VERSION=<git-sha>` when the API (Lambda/API Gateway) changed: it passes `ApiDeploymentVersion` and, after the stack update, forces a fresh API Gateway deployment onto the `prod` stage.
- Pushing to `main` triggers CodePipeline, which runs `buildspec.yml` to sync `frontend/` and invalidate CloudFront. This deploys frontend only — not infrastructure.

## Gotchas

- **`frontend/config.js` is generated at deploy time** by `buildspec.yml` (it writes `window.UPLOAD_API_URL`). The tracked file is an empty placeholder — do not hardcode the API URL into it.
- **Deploy packages before deploying.** `deploy-cmw-infra.sh` runs `aws cloudformation package` (uploading `functions/` code to a per-account `${STACK_NAME}-art-<accountId>` bucket, created once if missing; override with `PACKAGE_BUCKET`) and deploys the rewritten template. `aws cloudformation deploy` alone does **not** package local code.

## Verify

- `bash -n scripts/deploy-cmw-infra.sh` after changing the deploy script.
- `aws cloudformation validate-template --region eu-central-1 --template-body file://infrastructure/cmw-infra.yml` after template changes.
- Do not run a real stack deployment, delete a stack, or modify AWS account resources unless the user explicitly asks for it.
