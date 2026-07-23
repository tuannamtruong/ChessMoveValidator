# CMV AWS Serverless Infrastructure Plan

## Architecture and Flow

1. CloudFront serves the single-page web UI from a private S3 bucket.
2. The UI calls API Gateway to create a submission, obtain a short-lived presigned S3 upload URL, report that the direct upload has completed, and query submission status.
3. The submission Lambda creates the DynamoDB record with status `UPLOADING` and returns the presigned URL. After the UI reports the upload, a Lambda records `UPLOADED`, transitions it to `AWAITING_CONFIRMATION`, and sends an SES email containing a single-use token link.
4. The confirmation route in API Gateway validates the token, verifies the uploaded object, atomically marks the submission confirmed, and starts a Step Functions workflow.
5. The workflow invokes separate Lambda functions for move-file evaluation and completion handling. Completion persists the final status/result in DynamoDB and sends the result email through SES; invalid move-file evaluation produces `FAILED`, while operational failures produce `ERROR`.
6. The UI displays only submission status: `UPLOADING` while the file is being transferred, `UPLOADED` after transfer completes, `AWAITING_CONFIRMATION` until the email link is clicked, `FAILED` for an invalid move file, and `ERROR` for system, upload, or delivery failures. Detailed evaluation output is delivered by email.

## Sequence Diagram

```mermaid
sequenceDiagram
    actor Player
    participant UI as Web UI
    participant API as API Gateway
    participant Lambda as Lambda
    participant DB as DynamoDB
    participant S3 as S3
    participant SES as Amazon SES
    participant SFN as Step Functions

    Player->>UI: Select move file and enter email
    UI->>API: POST /submissions
    API->>Lambda: Create submission
    Lambda->>DB: Store submission (UPLOADING)
    Lambda-->>UI: Submission ID and presigned upload URL
    UI->>S3: PUT move file using presigned URL
    UI->>API: POST /submissions/{id}/uploaded
    API->>Lambda: Record upload completion
    Lambda->>DB: Set UPLOADED, then AWAITING_CONFIRMATION
    Lambda->>SES: Send single-use confirmation link
    SES-->>Player: Confirmation email

    alt Confirmation link is accepted
        Player->>API: GET /confirm?token=...
        API->>Lambda: Validate confirmation token
        Lambda->>S3: Verify uploaded object

        alt Uploaded object is valid
            Lambda->>DB: Atomically consume token and mark confirmed
            Lambda->>SFN: Start evaluation workflow
            Lambda-->>Player: Confirmation received page
            SFN->>Lambda: Evaluate move file
            Lambda->>S3: Read move file

            alt Invalid move file
                Lambda->>DB: Set FAILED
            else Evaluation succeeds
                Lambda->>DB: Store result
            else Operational failure
                SFN->>Lambda: Handle failure
                Lambda->>DB: Set ERROR
            end
            Lambda->>SES: Send result email
            SES-->>Player: Result email
        else Uploaded object is invalid or unavailable
            Lambda->>DB: Set ERROR
            Lambda-->>Player: Confirmation error page
        end
    else Confirmation link is invalid, expired, or reused
        Lambda-->>Player: Confirmation error page
    end
```

## API

- `POST /submissions`: accepts email and file metadata; returns submission ID and a presigned upload URL.
- `POST /submissions/{id}/uploaded`: records upload completion and initiates the confirmation-email step.
- `GET /confirm?token=...`: consumes the confirmation token, returns a minimal confirmation page/response, and starts processing.
- `GET /submissions/{id}/status`: returns only the UI lifecycle status: `UPLOADING`, `UPLOADED`, `AWAITING_CONFIRMATION`, `FAILED`, or `ERROR`.
- The move evaluator remains an isolated Lambda contract: input is an S3 object key and submission ID; output is final position, game result, move count, or a structured processing error. Chess validation rules are deliberately deferred.