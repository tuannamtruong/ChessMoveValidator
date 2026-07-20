# Chess Move Validator

## First deployment phase

A static web UI accepts an email address and chess move text file; the backend stores the pending submission, sends a confirmation link, processes confirmed files asynchronously, records status/results, and emails the outcome.

A CodePipeline watches the `main` GitHub branch and invokes CodeBuild on each change. CodeBuild synchronizes `frontend/` to the private origin bucket and creates a CloudFront invalidation.

Deploy this phase in the AWS Frankfurt Region: `eu-central-1`.

### Prerequisite

Create and authorize an AWS CodeConnections connection to GitHub in `eu-central-1`. Verify the SES sender address that you set as `CONFIRMATION_EMAIL_FROM` (and, while SES is in its sandbox, verify any recipient addresses too). Copy `.env.example` to `.env`, then add the connection ARN, repository settings, and verified sender address. `.env` is deliberately excluded from Git.

After a successful upload, the page shows `AWAITING_CONFIRMATION` until the recipient uses the emailed link. Each link is bound to its submission, expires after 24 hours by default, and can only confirm that submission once; a repeated click reports that the same upload was already confirmed.

### Deploy

```bash
./scripts/deploy-frontend.sh
```

After the initial stack deployment, commit and push changes to the configured branch. The pipeline will redeploy `frontend/` automatically. Retrieve the website address with:

```bash
aws cloudformation describe-stacks \
  --region eu-central-1 \
  --stack-name chess-move-validator-frontend \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" \
  --output text
```
