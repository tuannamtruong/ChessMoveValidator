# Chess Move Validator — Agent Guide

## Scope

This repository currently implements the first deployment phase:

- `frontend/` contains the static web frontend.
- `infrastructure/frontend-pipeline.yml` defines the AWS infrastructure.
- `buildspec.yml` deploys `frontend/` to the frontend bucket and invalidates CloudFront.
- `scripts/deploy-frontend.sh` deploys the CloudFormation stack from local configuration.

## AWS configuration

- Deploy to `eu-central-1` only unless the user explicitly changes the target region.
- The GitHub source is `tuannamtruong/ChessMoveValidator`, branch `main`, unless changed by the user.
- Keep infrastructure changes in CloudFormation. Do not create or modify stack resources manually in the AWS console when the change can be represented in the template.
- Validate CloudFormation changes with:

  ```bash
  aws cloudformation validate-template \
    --region eu-central-1 \
    --template-body file://infrastructure/frontend-pipeline.yml
  ```

## Local configuration and secrets

- `.env` is local deployment configuration and is gitignored. Never add it to Git, quote its contents in documentation, or print it in command output.
- Use `.env.example` for documented configuration keys.
- `scripts/deploy-frontend.sh` loads `.env`; do not duplicate connection ARNs or account-specific values in tracked files.

## Frontend and delivery changes

- Keep the frontend dependency-free unless a user request requires a build tool or framework.
- Files deployed to the website must be under `frontend/`.
- Preserve the private S3 bucket and CloudFront Origin Access Control; do not enable public S3 website hosting.
- Changes to `frontend/` are deployed by the GitHub-connected CodePipeline after a push to `main`.

## Verification

- Run `git diff --check` after edits.
- Run `bash -n scripts/deploy-frontend.sh` after changing the deployment script.
- Do not run a real stack deployment, delete a stack, or modify AWS account resources unless the user explicitly asks for it.
