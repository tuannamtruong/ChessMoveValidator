# Chess Move Validator

## First deployment phase

This repository contains a static Hello World frontend and the CloudFormation
template that deploys it through CloudFront. A CodePipeline watches a GitHub
branch and invokes CodeBuild on each change. CodeBuild synchronizes
`frontend/` to the private origin bucket and creates a CloudFront invalidation.

Deploy this phase in the AWS Frankfurt Region: `eu-central-1`.

### Prerequisite

Create and authorize an AWS CodeConnections connection to GitHub in
`eu-central-1`. Copy `.env.example` to `.env`, then add the connection ARN and
the repository settings. `.env` is deliberately excluded from Git.

### Deploy

```bash
./scripts/deploy-frontend.sh
```

After the initial stack deployment, commit and push changes to the configured
branch. The pipeline will redeploy `frontend/` automatically. Retrieve the
website address with:

```bash
aws cloudformation describe-stacks \
  --region eu-central-1 \
  --stack-name chess-move-validator-frontend \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" \
  --output text
```
