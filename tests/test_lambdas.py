"""Behavioral tests for the inline Lambda handlers.

These lock in the request-validation contract of each handler — the part most
likely to break when a "new feature" is added, and the part a backward-
compatibility check must protect. The handlers create boto3 clients at import
time, so we inject a minimal fake `boto3` (and `botocore`) into sys.modules
before exec'ing each handler's source. The fakes record calls and return canned
data; we assert on the pure request/response logic, not on real AWS behavior.

Run: python tests/test_lambdas.py   (from the repo root, inside the venv)
"""
import json
import os
import sys
import types

from extract_lambda import lambda_sources


# --- fake botocore --------------------------------------------------------
class ClientError(Exception):
    def __init__(self, code="ClientError"):
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class _RaiseHeadObject:
    """s3.head_object that raises, to exercise the 'file not found' branch."""
    def __call__(self, *a, **k):
        raise ClientError("404")


class FakeClient:
    def __init__(self, name):
        self._name = name
        self.calls = []

    def generate_presigned_url(self, *a, **k):
        self.calls.append(("generate_presigned_url", k))
        return "https://s3.example/presigned"

    def head_object(self, *a, **k):
        self.calls.append(("head_object", k))
        return {}

    def send_email(self, *a, **k):
        self.calls.append(("send_email", k))
        return {"MessageId": "fake"}


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[Item["submissionId"]] = Item
        return {}

    def get_item(self, Key):
        item = self.items.get(Key["submissionId"])
        return {"Item": item} if item else {}

    def update_item(self, **k):
        return {"Attributes": {"email": "player@example.com"}}


class FakeResource:
    def __init__(self, name):
        self._table = FakeTable()

    def Table(self, name):
        return self._table


def _install_fakes():
    """Fresh fake boto3/botocore in sys.modules; return the module objects."""
    boto3 = types.ModuleType("boto3")
    boto3._clients = {}
    boto3._resource = None

    def client(name, **kw):
        c = FakeClient(name)
        boto3._clients[name] = c
        return c

    def resource(name, **kw):
        boto3._resource = FakeResource(name)
        return boto3._resource

    boto3.client = client
    boto3.resource = resource

    botocore = types.ModuleType("botocore")
    config_mod = types.ModuleType("botocore.config")
    config_mod.Config = lambda *a, **k: None
    exc_mod = types.ModuleType("botocore.exceptions")
    exc_mod.ClientError = ClientError

    for name, mod in [
        ("boto3", boto3), ("botocore", botocore),
        ("botocore.config", config_mod), ("botocore.exceptions", exc_mod),
    ]:
        sys.modules[name] = mod
    return boto3


def load_handler(logical_id, env):
    """Exec a handler's source with fakes + env; return (module_ns, boto3)."""
    os.environ.update(env)
    os.environ.setdefault("AWS_REGION", "eu-central-1")
    boto3 = _install_fakes()
    ns = {"__name__": logical_id}
    exec(compile(SOURCES[logical_id], f"<{logical_id}>", "exec"), ns)
    return ns, boto3


SOURCES = lambda_sources()

UPLOAD_ENV = {"UPLOAD_BUCKET": "b", "SUBMISSIONS_TABLE": "t", "COMPLETE_URL": "https://x/prod/upload-complete"}
COMPLETE_ENV = {"SUBMISSIONS_TABLE": "t", "UPLOAD_BUCKET": "b", "EMAIL_FROM": "from@x", "CONFIRM_URL": "https://x/prod/confirm", "CONFIRMATION_LINK_EXPIRY_HOURS": "24"}
CONFIRM_ENV = {"SUBMISSIONS_TABLE": "t", "UPLOAD_BUCKET": "b"}


# --- test registry --------------------------------------------------------
_passed, _failed = 0, 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}")


def api_event(body):
    return {"body": json.dumps(body)}


def test_upload_url():
    print("UploadFunction (upload-url):")
    ns, b = load_handler("UploadFunction", UPLOAD_ENV)
    h = ns["handler"]
    valid = {"email": "a@b.co", "fileName": "game.txt", "contentType": "text/plain", "size": 42}

    r = h(api_event(valid), None)
    body = json.loads(r["body"])
    check("valid request -> 200", r["statusCode"] == 200)
    check("returns submissionId + uploadUrl + completeUrl",
          {"submissionId", "uploadUrl", "completeUrl"} <= body.keys())
    check("CORS header present", r["headers"].get("Access-Control-Allow-Origin") == "*")

    check("rejects bad email", h(api_event({**valid, "email": "nope"}), None)["statusCode"] == 400)
    check("rejects empty filename", h(api_event({**valid, "fileName": ""}), None)["statusCode"] == 400)
    check("rejects bad content-type", h(api_event({**valid, "contentType": "notacontenttype"}), None)["statusCode"] == 400)
    check("rejects zero size", h(api_event({**valid, "size": 0}), None)["statusCode"] == 400)
    check("rejects non-int size", h(api_event({**valid, "size": "big"}), None)["statusCode"] == 400)
    check("rejects >10MB", h(api_event({**valid, "size": 10 * 1024 * 1024 + 1}), None)["statusCode"] == 400)
    check("rejects malformed JSON body", h({"body": "{not json"}, None)["statusCode"] == 400)

    # path-traversal filename must be reduced to a basename before keying S3
    h(api_event({**valid, "fileName": "../../etc/passwd"}), None)
    key = b._clients["s3"].calls[-1][1]["Params"]["Key"]
    check("filename basename-only (no path traversal in S3 key)", ".." not in key and "/etc/" not in key)


def test_upload_complete():
    print("UploadCompleteFunction (upload-complete):")
    ns, b = load_handler("UploadCompleteFunction", COMPLETE_ENV)
    h = ns["handler"]
    check("missing submissionId -> 400", h(api_event({}), None)["statusCode"] == 400)
    check("unknown submission -> 200 ERROR",
          json.loads(h(api_event({"submissionId": "ghost"}), None)["body"]).get("status") == "ERROR")


def test_confirm():
    print("ConfirmFunction (confirm):")
    ns, b = load_handler("ConfirmFunction", CONFIRM_ENV)
    h = ns["handler"]
    r = h({"queryStringParameters": None}, None)
    check("missing params -> 400 HTML", r["statusCode"] == 400 and "text/html" in r["headers"]["Content-Type"])
    r = h({"queryStringParameters": {"submissionId": "x", "token": "y"}}, None)
    check("unknown submission -> 400", r["statusCode"] == 400)


if __name__ == "__main__":
    for t in (test_upload_url, test_upload_complete, test_confirm):
        t()
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
