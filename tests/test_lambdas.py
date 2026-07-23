"""Behavioral tests for the inline Lambda handlers.

These lock in the request-validation contract of each handler — the part most
likely to break when a "new feature" is added, and the part a backward-
compatibility check must protect. The handlers create boto3 clients at import
time, so we inject a minimal fake `boto3` (and `botocore`) into sys.modules
before exec'ing each handler's source. The fakes record calls and return canned
data; we assert on the pure request/response logic, not on real AWS behavior.

Run: python tests/test_lambdas.py   (from the repo root, inside the venv)
"""
import glob
import io
import json
import os
import sys
import types

from extract_lambda import lambda_sources

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVE_FILE_DIR = os.path.join(REPO_ROOT, "move_file")


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

    def get_object(self, *a, **k):
        self.calls.append(("get_object", k))
        return {"Body": io.BytesIO(getattr(self, "body", b""))}

    def invoke(self, *a, **k):
        self.calls.append(("invoke", k))
        return {"StatusCode": 202}

    def send_email(self, *a, **k):
        self.calls.append(("send_email", k))
        return {"MessageId": "fake"}

    def send_raw_email(self, *a, **k):
        self.calls.append(("send_raw_email", k))
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


def _exec_source(src, name, env):
    """Exec handler source with fresh fakes + env; return (module_ns, boto3)."""
    os.environ.update(env)
    os.environ.setdefault("AWS_REGION", "eu-central-1")
    boto3 = _install_fakes()
    ns = {"__name__": name}
    exec(compile(src, name, "exec"), ns)
    return ns, boto3


def load_handler(logical_id, env):
    """Load an inline handler (extracted from the template's Code.ZipFile)."""
    return _exec_source(SOURCES[logical_id], f"<{logical_id}>", env)


def load_file_handler(rel_path, env):
    """Load a packaged handler that lives as a real source file under functions/."""
    src_path = os.path.join(REPO_ROOT, "functions", rel_path)
    # The real Lambda runtime puts the handler's own directory on sys.path, so a
    # sibling module import like `from board_image import ...` resolves. Mirror
    # that here so exec of the handler source can import its neighbours.
    src_dir = os.path.dirname(src_path)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    with open(src_path) as fh:
        return _exec_source(fh.read(), rel_path, env)


SOURCES = lambda_sources()

UPLOAD_ENV = {"UPLOAD_BUCKET": "b", "SUBMISSIONS_TABLE": "t", "COMPLETE_URL": "https://x/prod/upload-complete"}
COMPLETE_ENV = {"SUBMISSIONS_TABLE": "t", "UPLOAD_BUCKET": "b", "EMAIL_FROM": "from@x", "CONFIRM_URL": "https://x/prod/confirm", "CONFIRMATION_LINK_EXPIRY_HOURS": "24"}
CONFIRM_ENV = {"SUBMISSIONS_TABLE": "t", "UPLOAD_BUCKET": "b", "EVALUATOR_FUNCTION": "evaluate-moves"}
EVAL_ENV = {"SUBMISSIONS_TABLE": "t", "UPLOAD_BUCKET": "b", "EMAIL_FROM": "from@x"}


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


def _move_file(name):
    with open(os.path.join(MOVE_FILE_DIR, name)) as fh:
        return fh.read()


# name -> (expected valid, expected winner). winner None means "no decisive winner".
# For the long valid games we only assert validity (winner intentionally unchecked = ...).
EXPECTED_GAMES = {
    "01_gueltig_schachmatt_schwarz.txt": (True, "b"),
    "02_gueltig_schachmatt_weiss.txt": (True, "w"),
    "03_gueltig_unvollstaendig.txt": (True, None),
    "04_ungueltig_leeres_startfeld.txt": (False, None),
    "05_ungueltig_falsche_farbe.txt": (False, None),
    "06_ungueltig_figur_blockiert.txt": (False, None),
    "07_ungueltig_bauer_seitwaerts.txt": (False, None),
    "08_ungueltig_zug_nach_schachmatt.txt": (False, None),
    "09_gueltig_lang_50_zuege.txt": (True, ...),
    "10_gueltig_lang_60_zuege.txt": (True, ...),
    "11_gueltig_lang_70_zuege.txt": (True, ...),
    "12_gueltig_remis_dreifache_stellungswiederholung.txt": (True, None),
}


def test_inline_size_guard():
    print("Inline ZipFile size guard:")
    # CloudFormation caps inline Code.ZipFile at 4096 characters. Handlers that
    # outgrow it must move to a packaged source file under functions/ (see the
    # evaluator). This guard fails before a real deploy would.
    for name, src in sorted(SOURCES.items()):
        check("{} inline code within 4096-char limit ({} chars)".format(name, len(src)), len(src) <= 4096)


def test_evaluator_engine():
    print("EvaluatorFunction (chess engine, sample games):")
    ns, _ = load_file_handler("evaluate_moves/index.py", EVAL_ENV)
    validate_game = ns["validate_game"]

    seen = {os.path.basename(p) for p in glob.glob(os.path.join(MOVE_FILE_DIR, "*.txt"))
            if not p.endswith("Zone.Identifier")}
    check("all sample move files are covered by an expectation", seen == set(EXPECTED_GAMES))

    for name, (want_valid, want_winner) in EXPECTED_GAMES.items():
        res = validate_game(_move_file(name))
        check("{}: valid={}".format(name, want_valid), res["valid"] is want_valid)
        check("{}: returns an end-position board".format(name), res.get("board") is not None)
        if want_winner is not ...:
            check("{}: winner={}".format(name, want_winner), res["winner"] == want_winner)
        if not want_valid:
            check("{}: gives a failure reason".format(name), bool(res["reason"]))

    # The board renderer produces a valid PNG (magic bytes) for the start position.
    from board_image import render_board_png
    png = render_board_png(ns["initial_board"]())
    check("render_board_png returns PNG bytes", png[:8] == b"\x89PNG\r\n\x1a\n")


def _confirmed_item(sid="s1"):
    return {"submissionId": sid, "email": "player@example.com",
            "objectKey": "uploads/s1.txt", "status": "CONFIRMED"}


def test_evaluator_handler():
    print("EvaluatorFunction (handler DONE/FAILED/idempotency):")

    # Valid game -> DONE, result email states the winner.
    ns, b = load_file_handler("evaluate_moves/index.py", EVAL_ENV)
    b._resource._table.items["s1"] = _confirmed_item()
    b._clients["s3"].body = _move_file("01_gueltig_schachmatt_schwarz.txt").encode()
    r = ns["handler"]({"submissionId": "s1"}, None)
    check("valid game -> DONE", r["status"] == "DONE")
    check("valid game -> winner black", r["winner"] == "black")
    sent = [c for c in b._clients["ses"].calls if c[0] == "send_raw_email"]
    check("DONE sends exactly one result email", len(sent) == 1)
    raw = sent[0][1]["RawMessage"]["Data"]
    check("DONE email subject says DONE", "Subject: Your Chess Move Validator result: DONE" in raw)
    check("DONE email names the winner", "Black" in raw)
    check("DONE email attaches the end-position image",
          "image/png" in raw and "end_position.png" in raw)

    # Invalid game -> FAILED, email states the reason.
    ns, b = load_file_handler("evaluate_moves/index.py", EVAL_ENV)
    b._resource._table.items["s1"] = _confirmed_item()
    b._clients["s3"].body = _move_file("04_ungueltig_leeres_startfeld.txt").encode()
    r = ns["handler"]({"submissionId": "s1"}, None)
    check("invalid game -> FAILED", r["status"] == "FAILED")
    sent = [c for c in b._clients["ses"].calls if c[0] == "send_raw_email"]
    check("FAILED sends exactly one email", len(sent) == 1)
    fraw = sent[0][1]["RawMessage"]["Data"]
    check("FAILED email subject says FAILED", "Subject: Your Chess Move Validator result: FAILED" in fraw)
    check("FAILED email includes a reason (empty start square)", "empty" in fraw)
    check("FAILED email attaches the position image",
          "image/png" in fraw and "end_position.png" in fraw)

    # Guard: only CONFIRMED submissions are evaluated (no double-processing).
    ns, b = load_file_handler("evaluate_moves/index.py", EVAL_ENV)
    b._resource._table.items["s1"] = {**_confirmed_item(), "status": "DONE"}
    r = ns["handler"]({"submissionId": "s1"}, None)
    check("already-DONE submission is not re-evaluated", r["status"] == "DONE")
    check("no email sent when not CONFIRMED",
          not [c for c in b._clients["ses"].calls if c[0] == "send_raw_email"])

    # Missing/unknown submission is handled without raising.
    ns, b = load_file_handler("evaluate_moves/index.py", EVAL_ENV)
    check("missing submissionId -> ERROR", ns["handler"]({}, None)["status"] == "ERROR")
    check("unknown submission -> ERROR", ns["handler"]({"submissionId": "ghost"}, None)["status"] == "ERROR")


if __name__ == "__main__":
    for t in (test_upload_url, test_upload_complete, test_confirm,
              test_inline_size_guard, test_evaluator_engine, test_evaluator_handler):
        t()
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
