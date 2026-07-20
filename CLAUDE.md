# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Team conventions live in AGENTS.md — read it first:

@AGENTS.md

## Deploy

- `./scripts/deploy-frontend.sh` deploys the CloudFormation stack (`chess-move-validator-frontend`) from `.env`. Only run a real deployment when the user explicitly asks.
- Set `DEPLOYMENT_VERSION=<git-sha>` when the API (Lambda/API Gateway) changed: it passes `ApiDeploymentVersion` and, after the stack update, forces a fresh API Gateway deployment onto the `prod` stage.
- Pushing to `main` triggers CodePipeline, which runs `buildspec.yml` to sync `frontend/` and invalidate CloudFront. This deploys frontend only — not infrastructure.

## Gotchas

- **`frontend/config.js` is generated at deploy time** by `buildspec.yml` (it writes `window.UPLOAD_API_URL`). The tracked file is an empty placeholder — do not hardcode the API URL into it.
- **API Gateway stale deployments:** CloudFormation does not re-snapshot `AWS::ApiGateway::Deployment` when only its properties change, so adding/changing API routes can leave the `prod` stage serving old routes (symptom: `403` on `OPTIONS` preflight for a new route). `deploy-frontend.sh` calls `aws apigateway create-deployment --stage-name prod` when `DEPLOYMENT_VERSION` is set to force a fresh snapshot.
- All Lambda code is inline in `infrastructure/frontend-pipeline.yml` (`ZipFile`), not in separate source files.

## Verify

- `bash -n scripts/deploy-frontend.sh` after changing the deploy script.
- `aws cloudformation validate-template --region eu-central-1 --template-body file://infrastructure/frontend-pipeline.yml` after template changes.
- `git diff --check` after edits.
