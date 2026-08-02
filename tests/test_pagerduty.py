"""PagerDuty incident creation — mocked HTTP, no real network calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.escalation import EscalationDecision, EscalationService
from tools.pagerduty_tools import PagerDutyClient

CREATED_RESPONSE = {
    "incident": {
        "id": "PABC123",
        "incident_number": 42,
        "html_url": "https://acme.pagerduty.com/incidents/PABC123",
    }
}


def _configure(monkeypatch):
    monkeypatch.setenv("PAGERDUTY_ENABLED", "true")
    monkeypatch.setenv("PAGERDUTY_TOKEN", "pd-token-123")
    monkeypatch.setenv("PAGERDUTY_SERVICE_ID", "PSERVICE1")
    monkeypatch.setenv("PAGERDUTY_FROM_EMAIL", "oncall@yourcompany.com")


def _mock_response(status_code, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _patch_post(post_mock):
    """Patch httpx.AsyncClient so `async with ... as client` yields our mock."""
    client = MagicMock()
    client.post = post_mock
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch("tools.pagerduty_tools.httpx.AsyncClient", return_value=client)


class TestPagerDutyClientCreateIncident:
    @pytest.mark.asyncio
    async def test_creates_incident_with_expected_request(self, monkeypatch):
        _configure(monkeypatch)
        post = AsyncMock(return_value=_mock_response(201, CREATED_RESPONSE))

        with _patch_post(post):
            result = await PagerDutyClient().create_incident(
                title="[DevOps Agent] Pod CrashLoopBackOff (INC-1)",
                description="Agent could not resolve. Contact sre@yourcompany.com",
                priority="critical",
                incident_key="INC-1",
            )

        assert result == {
            "created": True,
            "id": "PABC123",
            "number": 42,
            "url": "https://acme.pagerduty.com/incidents/PABC123",
        }

        post.assert_awaited_once()
        url = post.await_args.args[0]
        payload = post.await_args.kwargs["json"]
        headers = post.await_args.kwargs["headers"]

        assert url == "https://api.pagerduty.com/incidents"

        incident = payload["incident"]
        assert incident["type"] == "incident"
        assert incident["title"] == "[DevOps Agent] Pod CrashLoopBackOff (INC-1)"
        assert incident["service"] == {"id": "PSERVICE1", "type": "service_reference"}
        assert incident["urgency"] == "high"
        assert incident["body"]["type"] == "incident_body"
        assert incident["incident_key"] == "INC-1"

        assert headers["Authorization"] == "Token token=pd-token-123"
        assert headers["Accept"] == "application/vnd.pagerduty+json;version=2"
        assert headers["Content-Type"] == "application/json"
        assert headers["From"] == "oncall@yourcompany.com"

    @pytest.mark.asyncio
    async def test_scrubs_pii_from_incident_body(self, monkeypatch):
        _configure(monkeypatch)
        post = AsyncMock(return_value=_mock_response(201, CREATED_RESPONSE))

        with _patch_post(post):
            await PagerDutyClient().create_incident(
                title="Alert for admin@yourcompany.com",
                description="Reported by sre@yourcompany.com",
            )

        incident = post.await_args.kwargs["json"]["incident"]
        assert "admin@yourcompany.com" not in incident["title"]
        assert "sre@yourcompany.com" not in incident["body"]["details"]
        assert "[REDACTED_EMAIL]" in incident["body"]["details"]

    @pytest.mark.asyncio
    async def test_low_priority_maps_to_low_urgency(self, monkeypatch):
        _configure(monkeypatch)
        post = AsyncMock(return_value=_mock_response(201, CREATED_RESPONSE))

        with _patch_post(post):
            await PagerDutyClient().create_incident("t", "d", priority="low")

        assert post.await_args.kwargs["json"]["incident"]["urgency"] == "low"

    @pytest.mark.asyncio
    async def test_omits_incident_key_when_not_given(self, monkeypatch):
        _configure(monkeypatch)
        post = AsyncMock(return_value=_mock_response(201, CREATED_RESPONSE))

        with _patch_post(post):
            await PagerDutyClient().create_incident("t", "d")

        assert "incident_key" not in post.await_args.kwargs["json"]["incident"]

    @pytest.mark.asyncio
    async def test_honours_custom_base_url(self, monkeypatch):
        _configure(monkeypatch)
        monkeypatch.setenv("PAGERDUTY_URL", "https://api.eu.pagerduty.com/")
        post = AsyncMock(return_value=_mock_response(201, CREATED_RESPONSE))

        with _patch_post(post):
            await PagerDutyClient().create_incident("t", "d")

        assert post.await_args.args[0] == "https://api.eu.pagerduty.com/incidents"


class TestPagerDutyClientFailures:
    @pytest.mark.asyncio
    async def test_error_response_is_reported_not_raised(self, monkeypatch):
        _configure(monkeypatch)
        post = AsyncMock(
            return_value=_mock_response(
                400, text='{"error":{"message":"Invalid service"}}'
            )
        )

        with _patch_post(post):
            result = await PagerDutyClient().create_incident("t", "d")

        assert result["created"] is False
        assert result["status"] == 400
        assert "Invalid service" in result["error"]

    @pytest.mark.asyncio
    async def test_network_timeout_is_reported_not_raised(self, monkeypatch):
        _configure(monkeypatch)
        post = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))

        with _patch_post(post):
            result = await PagerDutyClient().create_incident("t", "d")

        assert result == {"created": False, "error": "timed out"}


class TestPagerDutyClientConfiguration:
    @pytest.mark.asyncio
    async def test_skips_when_credentials_absent(self, monkeypatch):
        for key in (
            "PAGERDUTY_ENABLED",
            "PAGERDUTY_TOKEN",
            "PAGERDUTY_SERVICE_ID",
            "PAGERDUTY_FROM_EMAIL",
        ):
            monkeypatch.delenv(key, raising=False)
        post = AsyncMock()

        with _patch_post(post):
            result = await PagerDutyClient().create_incident("t", "d")

        assert result == {"skipped": True, "reason": "PagerDuty not configured"}
        post.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "missing",
        ["PAGERDUTY_TOKEN", "PAGERDUTY_SERVICE_ID", "PAGERDUTY_FROM_EMAIL"],
    )
    async def test_skips_when_a_credential_is_blank(self, monkeypatch, missing):
        _configure(monkeypatch)
        monkeypatch.setenv(missing, "")
        post = AsyncMock()

        with _patch_post(post):
            result = await PagerDutyClient().create_incident("t", "d")

        assert result["skipped"] is True
        post.assert_not_awaited()

    def test_skips_when_disabled_though_credentials_present(self, monkeypatch):
        _configure(monkeypatch)
        monkeypatch.setenv("PAGERDUTY_ENABLED", "false")
        assert PagerDutyClient().is_configured() is False


class TestEscalationPagerDutyChannel:
    def _decision(self):
        return EscalationDecision(
            should_escalate=True,
            reasons=["unresolved"],
            priority="critical",
            summary="[DevOps Agent] Agent could not resolve the incident — k8s (INC-9)",
            description="Full incident description",
        )

    @pytest.mark.asyncio
    async def test_creates_incident_when_channel_enabled(self, monkeypatch):
        monkeypatch.setenv("ESCALATION_CHANNELS", "pagerduty")
        svc = EscalationService()
        svc.pagerduty.create_incident = AsyncMock(
            return_value={"created": True, "id": "PABC123"}
        )

        outcomes = await svc.escalate(self._decision(), "INC-9", "acme")

        svc.pagerduty.create_incident.assert_awaited_once_with(
            title="[DevOps Agent] Agent could not resolve the incident — k8s (INC-9)",
            description="Full incident description",
            priority="critical",
            incident_key="INC-9",
        )
        assert outcomes["channels"]["pagerduty"] == {"created": True, "id": "PABC123"}

    @pytest.mark.asyncio
    async def test_skips_channel_when_not_configured(self, monkeypatch):
        monkeypatch.setenv("ESCALATION_CHANNELS", "email")
        svc = EscalationService()
        svc.email.send_escalation_ticket = MagicMock(return_value=False)
        svc.pagerduty.create_incident = AsyncMock()

        outcomes = await svc.escalate(self._decision(), "INC-9", "acme")

        svc.pagerduty.create_incident.assert_not_awaited()
        assert "pagerduty" not in outcomes["channels"]
