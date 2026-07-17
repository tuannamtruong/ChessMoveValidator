# Chess Move Validator

## First deployment phase

This repository contains a static Hello World frontend and the CloudFormation
template that deploys it through CloudFront. A CodePipeline watches a GitHub
branch and invokes CodeBuild on each change. CodeBuild synchronizes
`frontend/` to the private origin bucket and creates a CloudFront invalidation.

### Prerequisite

Create and authorize an AWS CodeStar Connection to GitHub in the same AWS
Region as the stack. Use its ARN when deploying the stack.

### Deploy

```bash
aws cloudformation deploy \
  --template-file infrastructure/frontend-pipeline.yml \
  --stack-name chess-move-validator-frontend \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    GitHubConnectionArn=arn:aws:codestar-connections:REGION:ACCOUNT:connection/CONNECTION_ID \
    GitHubRepository=OWNER/REPOSITORY \
    GitHubBranch=main
```

After the initial stack deployment, commit and push changes to the configured
branch. The pipeline will redeploy `frontend/` automatically. Retrieve the
website address with:

```bash
aws cloudformation describe-stacks \
  --stack-name chess-move-validator-frontend \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" \
  --output text
```
