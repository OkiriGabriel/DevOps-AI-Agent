"""
Tests for Slack request signature verification on /slack/action.

The endpoint executes approved commands, so an unverified POST is remote
command execution. These tests pin the scheme documented at
https://api.slack.com/authentication/verifying-requests-from-slack
"""
import base64
import hashlib
import hmac
import json
import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# api.server constructs a DevOpsAgent at import time, which requires a key.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy-key-for-testing")

from api.server import app, verify_slack_signature  # noqa: E402

SIGNING_SECRET = "8f742231b10e8888abcd99yyyzzz85a5"


def _sign(body: bytes, timestamp: str, secret: str = SIGNING_SECRET) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()


def _approval_body(incident_id: str = "inc-123", cmd: str = "kubectl rollout restart deploy/api") -> bytes:
    """An approve_action interactive payload, form-encoded exactly as Slack posts it."""
    encoded_cmd = base64.b64encode(cmd.encode()).decode()
    payload = {
        "actions": [{
            "action_id": "approve_action",
            "value": f"{incident_id}:{encoded_cmd}",
        }]
    }
    from urllib.parse import urlencode
    return urlencode({"payload": json.dumps(payload)}).encode()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _post(client, body: bytes, headers: dict):
    return client.post(
        "/slack/action",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
    )


# ─── The helper, against Slack's own published fixture ────────────────────────

def test_known_slack_signature_fixture():
    """The exact worked example from Slack's verification docs."""
    timestamp = "1531420618"
    body = (
        b"token=xyzz0WbapA4vBCDEFasx0q6G&team_id=T1DC2JH3J&team_domain=testteamnow"
        b"&channel_id=G8PSS9T3V&channel_name=foobar&user_id=U2CERLKJA&user_name=roadrunner"
        b"&command=%2Fwebhook-collect&text=&response_url=https%3A%2F%2Fhooks.slack.com"
        b"%2Fcommands%2FT1DC2JH3J%2F397700885554%2F96rGlfmibIGlgcZRskXaIFfN"
        b"&trigger_id=398738663015.47445629121.803a0bc887a14d10d2c447fce8b6703c"
    )
    expected = "v0=a2114d57b48eac39b9ad189dd8316235a7b4a8d21a10bd27519666489c69b503"

    # Our own construction reproduces Slack's published digest.
    assert _sign(body, timestamp) == expected

    # And the helper accepts it, with the clock pinned inside the replay window.
    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.time.time", return_value=int(timestamp) + 5):
        assert verify_slack_signature(body, timestamp, expected) is True


def test_helper_rejects_non_numeric_timestamp():
    """A non-numeric timestamp must not slip past the window check."""
    body = b"payload=%7B%7D"
    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}):
        for bogus in ("not-a-number", "nan", "inf", ""):
            assert verify_slack_signature(body, bogus, _sign(body, bogus)) is False


# ─── The endpoint ─────────────────────────────────────────────────────────────

def test_valid_signature_is_accepted(client):
    body = _approval_body()
    timestamp = str(int(time.time()))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, body, {
            "X-Slack-Signature": _sign(body, timestamp),
            "X-Slack-Request-Timestamp": timestamp,
        })

    assert response.status_code == 200
    assert "Approved" in response.json()["text"]
    # The body survived signature verification intact and still parses as a form.
    execute.assert_called_once_with("inc-123", "kubectl rollout restart deploy/api")


def test_reject_action_requires_valid_signature(client):
    payload = {"actions": [{"action_id": "reject_action", "value": "inc-123"}]}
    from urllib.parse import urlencode
    body = urlencode({"payload": json.dumps(payload)}).encode()
    timestamp = str(int(time.time()))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}):
        ok = _post(client, body, {
            "X-Slack-Signature": _sign(body, timestamp),
            "X-Slack-Request-Timestamp": timestamp,
        })
        assert ok.status_code == 200
        assert "rejected" in ok.json()["text"]

        forged = _post(client, body, {
            "X-Slack-Signature": "v0=" + "0" * 64,
            "X-Slack-Request-Timestamp": timestamp,
        })
        assert forged.status_code == 401


def test_bad_signature_is_rejected(client):
    body = _approval_body()
    timestamp = str(int(time.time()))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, body, {
            "X-Slack-Signature": "v0=" + "a" * 64,
            "X-Slack-Request-Timestamp": timestamp,
        })

    assert response.status_code == 401
    execute.assert_not_called()


def test_signature_from_a_different_secret_is_rejected(client):
    """A well-formed signature under the wrong key must not authenticate."""
    body = _approval_body()
    timestamp = str(int(time.time()))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, body, {
            "X-Slack-Signature": _sign(body, timestamp, secret="an-attackers-secret"),
            "X-Slack-Request-Timestamp": timestamp,
        })

    assert response.status_code == 401
    execute.assert_not_called()


def test_non_ascii_signature_is_rejected_cleanly(client):
    """A junk signature must yield 401, not a 500 from compare_digest.

    Sent as raw bytes: headers arrive over the wire as bytes and Starlette
    decodes them latin-1, so a signature header can legitimately contain
    non-ASCII characters that hmac.compare_digest refuses to compare as str.
    """
    body = _approval_body()
    timestamp = str(int(time.time()))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, body, {
            "X-Slack-Signature": b"v0=\xff\xff",
            "X-Slack-Request-Timestamp": timestamp,
        })

    assert response.status_code == 401
    execute.assert_not_called()


def test_stale_timestamp_is_rejected(client):
    """A correctly signed request replayed outside the window must be refused."""
    body = _approval_body()
    stale = str(int(time.time()) - (60 * 5 + 30))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, body, {
            "X-Slack-Signature": _sign(body, stale),  # genuinely valid signature
            "X-Slack-Request-Timestamp": stale,
        })

    assert response.status_code == 401
    execute.assert_not_called()


def test_future_timestamp_is_rejected(client):
    body = _approval_body()
    future = str(int(time.time()) + (60 * 5 + 30))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}):
        response = _post(client, body, {
            "X-Slack-Signature": _sign(body, future),
            "X-Slack-Request-Timestamp": future,
        })

    assert response.status_code == 401


def test_timestamp_just_inside_window_is_accepted(client):
    """The window boundary should not reject legitimate, slightly-delayed requests."""
    body = _approval_body()
    recent = str(int(time.time()) - (60 * 5 - 30))

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action"):
        response = _post(client, body, {
            "X-Slack-Signature": _sign(body, recent),
            "X-Slack-Request-Timestamp": recent,
        })

    assert response.status_code == 200


def test_signature_over_a_different_body_is_rejected(client):
    """A signature lifted from a benign request must not authorize a different command."""
    signed_body = _approval_body(cmd="kubectl get pods")
    timestamp = str(int(time.time()))
    signature = _sign(signed_body, timestamp)

    tampered_body = _approval_body(cmd="rm -rf /")

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, tampered_body, {
            "X-Slack-Signature": signature,
            "X-Slack-Request-Timestamp": timestamp,
        })

    assert response.status_code == 401
    execute.assert_not_called()


@pytest.mark.parametrize("headers", [
    {},
    {"X-Slack-Signature": "v0=" + "a" * 64},
    {"X-Slack-Request-Timestamp": "1531420618"},
])
def test_missing_headers_are_rejected(client, headers):
    body = _approval_body()

    with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": SIGNING_SECRET}), \
            patch("api.server.agent.execute_approved_action") as execute:
        response = _post(client, body, headers)

    assert response.status_code == 401
    execute.assert_not_called()


def test_missing_signing_secret_fails_closed(client):
    """With no secret configured the endpoint must refuse, not fall open."""
    body = _approval_body()
    timestamp = str(int(time.time()))

    for secret in ("", "   "):
        with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": secret}), \
                patch("api.server.agent.execute_approved_action") as execute:
            response = _post(client, body, {
                "X-Slack-Signature": _sign(body, timestamp, secret=secret or SIGNING_SECRET),
                "X-Slack-Request-Timestamp": timestamp,
            })

        assert response.status_code == 401, f"secret={secret!r} should fail closed"
        execute.assert_not_called()
