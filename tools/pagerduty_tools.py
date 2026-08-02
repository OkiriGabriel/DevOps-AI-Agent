"""PagerDuty incident creation for escalated incidents."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
import structlog

from services.pii_scrubber import scrub_text

log = structlog.get_logger()


class PagerDutyClient:
    def __init__(self):
        self.enabled = os.getenv("PAGERDUTY_ENABLED", "false").lower() == "true"
        self.base_url = os.getenv("PAGERDUTY_URL", "https://api.pagerduty.com").rstrip(
            "/"
        )
        self.token = os.getenv("PAGERDUTY_TOKEN", "")
        self.service_id = os.getenv("PAGERDUTY_SERVICE_ID", "")
        # POST /incidents requires a From header naming a valid PagerDuty user.
        self.from_email = os.getenv("PAGERDUTY_FROM_EMAIL", "")
        self.urgency_map = {
            "critical": os.getenv("PAGERDUTY_URGENCY_CRITICAL", "high"),
            "high": os.getenv("PAGERDUTY_URGENCY_HIGH", "high"),
            "medium": os.getenv("PAGERDUTY_URGENCY_MEDIUM", "low"),
            "low": os.getenv("PAGERDUTY_URGENCY_LOW", "low"),
        }

    def is_configured(self) -> bool:
        return self.enabled and bool(self.token and self.service_id and self.from_email)

    async def create_incident(
        self,
        title: str,
        description: str,
        priority: str = "high",
        incident_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            return {"skipped": True, "reason": "PagerDuty not configured"}

        url = f"{self.base_url}/incidents"
        incident: Dict[str, Any] = {
            "type": "incident",
            "title": scrub_text(title)[:1024],
            "service": {"id": self.service_id, "type": "service_reference"},
            "urgency": self.urgency_map.get(priority, "high"),
            "body": {
                "type": "incident_body",
                "details": scrub_text(description)[:32000],
            },
        }
        # Deduplication key — ties repeat escalations of one incident together.
        if incident_key:
            incident["incident_key"] = incident_key

        headers = {
            "Authorization": f"Token token={self.token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
            "From": self.from_email,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    url, json={"incident": incident}, headers=headers
                )
                if resp.status_code in (200, 201):
                    data = resp.json().get("incident", {})
                    incident_id = data.get("id")
                    log.info("PagerDuty incident created", incident_id=incident_id)
                    return {
                        "created": True,
                        "id": incident_id,
                        "number": data.get("incident_number"),
                        "url": data.get("html_url"),
                    }
                return {
                    "created": False,
                    "error": resp.text,
                    "status": resp.status_code,
                }
            except Exception as e:
                log.error("PagerDuty incident creation failed", error=str(e))
                return {"created": False, "error": str(e)}
