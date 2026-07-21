---
name: run-chess-move-validator
description: Run, test, and validate the Chess Move Validator after any change — checks new behavior AND backward compatibility across infra (CloudFormation), the inline Lambda handlers, and the frontend. Use when asked to run, test, validate, verify, smoke-test, or screenshot this project, or "check nothing broke" after editing the template, a Lambda, the deploy script, or frontend/. Runs headless in a container; no AWS deploy.
---

# Run & validate the Chess Move Validator

This project has no locally-runnable "server" — it is AWS infrastructure
(`infrastructure/cmw-infra.yml`: S3 + DynamoDB + Lambda + API Gateway +
SES) plus a static `frontend/`. So "run it" means **drive every layer's
behavior locally and confirm the change works without regressing what shipped.**

The driver is the `tests/` folder. **After each development change, run:**

```bash
bash tests/run_all.sh
```

That one command sets up its own tooling on first run (a `tests/.venv` and Node
deps) and runs four suites in order, printing `PASS`/`FAIL` per suite and
exiting non-zero if any fail:

1. **deploy-script syntax** — `bash -n scripts/deploy-cmw-infra.sh`
2. **infrastructure** — `cfn-lint` + `aws cloudformation validate-template`
3. **lambda handlers** — behavioral tests of the inline Python handlers (boto3 mocked)
4. **frontend smoke** — headless Chromium loads `frontend/`, exercises the form, writes a screenshot

Paths below are relative to the repo root. The harness lives under `tests/`.

## Prerequisites

The harness needs **Python 3** (with `venv`), **Node.js + npm**, and — for the
service-side validation step only — the **AWS CLI v2**. All three are present in
this container. Confirm before running:

```bash
python3 --version && node --version && aws --version
```

On a bare Ubuntu machine, `python3-venv`, `nodejs`, and `npm` come from
`apt-get`; Node here is provided via `nvm`. The AWS CLI is optional — with no
credentials configured, `run_all.sh` still runs the offline `cfn-lint` and skips
only the `validate-template` call. AWS calls here are **read-only validation**;
the harness never deploys.

## Run (agent path) — the whole suite

```bash
bash tests/run_all.sh
```

Expected tail on success:

```
========== frontend smoke ==========
...
9 passed, 0 failed
>> frontend smoke: PASS

ALL SUITES PASSED
```

First run installs into `tests/.venv` and `tests/node_modules` and downloads a
Playwright Chromium (~115 MB); later runs reuse them and take a few seconds.

## Run one suite at a time

While iterating on a single layer, run just that suite (all from the repo root):

```bash
# infra only (offline lint + optional service validation)
AWS_REGION=eu-central-1 bash tests/validate_infra.sh

# Lambda handler behavior only
( cd tests && .venv/bin/python test_lambdas.py )

# frontend only — writes tests/screenshots/frontend.png
node tests/smoke_frontend.mjs
```

The frontend suite leaves a screenshot at `tests/screenshots/frontend.png` —
**open it** to eyeball the rendered UI, not just the assertion output.

## What each suite protects (feature + backward compatibility)

- **infra** — `cfn-lint` catches bad resource properties/runtimes; a genuinely
  broken template (e.g. an invalid Lambda `Runtime`) fails the suite with a
  non-zero exit, so a regression can't slip through.
- **lambda handlers** — `tests/test_lambdas.py` pulls each handler's source out
  of the template's `Code.ZipFile` (via `tests/extract_lambda.py`) and locks in
  the request-validation contract: email/content-type/size limits, path-
  traversal safety on the S3 key, and the `submissionId`/token guards. Add a
  new handler behavior → add a `check(...)`; the existing checks are your
  backward-compatibility net.
- **frontend** — asserts the form renders and that with the tracked placeholder
  `config.js` (`UPLOAD_API_URL === ''`) a submit surfaces the "not configured"
  error instead of hanging or throwing.

## Gotchas

- **Lambdas are inline in the template**, not separate files. Tests exec the
  extracted `ZipFile` source, so a Python syntax error inside the YAML block
  surfaces as a test-collection error, not a lint warning.
- **`extract_lambda.py` must ignore CloudFormation tags.** Stock PyYAML throws
  on `!Sub`/`!Ref`/`!GetAtt`; the loader registers a permissive multi-
  constructor that collapses every `!`-tag to a plain value. Reuse it if you
  parse the template elsewhere — don't switch to `yaml.safe_load`, it will
  raise.
- **The handlers build boto3 clients at import time** (`s3 = boto3.client(...)`
  at module scope). Tests inject a fake `boto3`/`botocore` into `sys.modules`
  _before_ exec'ing the source and set the handler's env vars. New env vars in a
  handler → add them to the matching `*_ENV` dict in `test_lambdas.py`.
- **`generate_presigned_url` params are nested under `Params`**, so the S3 key
  assertion reads `calls[-1][1]["Params"]["Key"]`, not `["Key"]`.
- **Playwright browser version drift.** The npm `playwright` package pins a
  browser build; if the cached one doesn't match you get _"Executable doesn't
  exist … run npx playwright install"_. `run_all.sh` runs
  `npx playwright install chromium` on setup to keep them in sync.
- **`tests/config.js` is not touched.** The smoke test serves the tracked
  placeholder `frontend/config.js` as-is; the real API URL is injected only at
  deploy time by `buildspec.yml`.

## Troubleshooting

- **`cfn-lint: command not found` from `validate_infra.sh`** — you ran it before
  the venv existed. Run `bash tests/run_all.sh` once (it creates `tests/.venv`),
  or `python3 -m venv tests/.venv && tests/.venv/bin/pip install -r tests/requirements.txt`.
- **`validate-template` step prints "No AWS credentials — skipping"** — expected
  without creds; the offline lint still ran and gates the suite. Configure the
  AWS CLI to enable the service-side check.
- **Frontend suite exits with a Playwright launch error** — run
  `( cd tests && npx playwright install chromium )` and retry.

## Not covered here

No suite deploys the stack or calls the live API/SES — that needs `.env` and a
real `./scripts/deploy-cmw-infra.sh` run, which per project rules happens only
when the user explicitly asks. These tests validate everything reachable
without deploying.
