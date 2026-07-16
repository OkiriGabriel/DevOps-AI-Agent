"""
DevOps AI Agent — FastAPI Webhook Server
Receives events from GitHub, Alertmanager, and manual triggers.
Durable queue + cloud storage for audit, logs, checkpoints, and org docs.
"""
import asyncio
import hashlib
import hmac
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import structlog
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.core import DevOpsAgent
from agent.classifier import classify_issue
from services.incident_queue import IncidentQueue
from services.incident_store import IncidentStore
from services.org_docs import OrgDocs
from services.escalation import EscalationService, parse_queue_timestamp
from services.pii_scrubber import scrub_dict, scrub_text
from tools.notify import SlackNotifier

load_dotenv()

log = structlog.get_logger()

agent = DevOpsAgent()
notifier = SlackNotifier()
incident_queue = IncidentQueue()
incident_store = IncidentStore()
org_docs = OrgDocs()
escalation_service = EscalationService()

_queue_worker_task: Optional[asyncio.Task] = None
_queue_running = False


def _org_id(context: dict, header_org: Optional[str] = None) -> str:
    return context.get("org_id") or header_org or os.getenv("ORG_ID", "default")


async def process_incident(entry: dict):
    """Process a single queued incident with checkpoint resume support."""
    incident_id = entry["incident_id"]
    org_id = entry["org_id"]
    context = entry.get("context", {})
    context["org_id"] = org_id
    context["incident_id"] = incident_id
    started_at = parse_queue_timestamp(entry)

    log.info("Processing incident", id=incident_id, org_id=org_id)
    result = None

    try:
        result = await agent.run(context, incident_id=incident_id, resume=True)

        decision = escalation_service.evaluate(
            incident_id, org_id, context, result, started_at
        )
        escalation_outcome = None
        if decision.should_escalate:
            escalation_outcome = await escalation_service.escalate(decision, incident_id, org_id)

        audit_entry = scrub_dict({
            "id": incident_id,
            "org_id": org_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident": context,
            "diagnosis": result.get("diagnosis"),
            "actions_taken": result.get("actions", []),
            "resolved": result.get("resolved", False),
            "fix_applied": result.get("fix_applied", False),
            "suggestions_only": result.get("suggestions_only", False),
            "suggested_fixes": result.get("suggested_fixes", []),
            "ai_reasoning": result.get("reasoning"),
            "grounding": result.get("grounding"),
            "steps": result.get("steps"),
            "duration_minutes": decision.duration_minutes,
            "escalated": decision.should_escalate,
            "escalation_reasons": decision.reasons,
            "escalation": escalation_outcome,
        })
        incident_store.save_audit(org_id, incident_id, audit_entry)
        incident_queue.mark_completed(org_id, incident_id, result)

        await notifier.send_resolution(incident_id, result)
        log.info(
            "Incident handled",
            id=incident_id,
            resolved=result.get("resolved"),
            escalated=decision.should_escalate,
        )

    except Exception as e:
        log.error("Incident handling failed", id=incident_id, error=str(e))
        decision = escalation_service.evaluate(
            incident_id, org_id, context, result, started_at, error=str(e)
        )
        escalation_outcome = None
        if decision.should_escalate:
            escalation_outcome = await escalation_service.escalate(decision, incident_id, org_id)

        incident_queue.mark_failed(org_id, incident_id, str(e))
        await notifier.send_error(incident_id, scrub_text(str(e)))

        incident_store.save_audit(org_id, incident_id, scrub_dict({
            "id": incident_id,
            "org_id": org_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident": context,
            "resolved": False,
            "error": scrub_text(str(e)),
            "escalated": decision.should_escalate,
            "escalation_reasons": decision.reasons,
            "escalation": escalation_outcome,
        }))


async def _queue_worker_loop():
    """Background worker — claims and processes incidents from cloud storage queue."""
    global _queue_running
    poll_interval = float(os.getenv("QUEUE_POLL_INTERVAL_SEC", "5"))
    _queue_running = True
    log.info("Queue worker started", poll_interval=poll_interval)

    while _queue_running:
        try:
            for org_id in incident_queue.list_pending_org_ids():
                incident_queue.recover_stale_processing(org_id)
                entry = incident_queue.claim_next(org_id)
                if entry:
                    await process_incident(entry)
        except Exception as e:
            log.error("Queue worker error", error=str(e))
        await asyncio.sleep(poll_interval)


async def enqueue_incident(context: dict, incident_id: Optional[str] = None) -> str:
    org = _org_id(context)
    context = dict(context)
    context["org_id"] = org
    return incident_queue.enqueue(org, context, incident_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _queue_worker_task
    log.info("DevOps AI Agent starting", auto_apply=os.getenv("AUTO_APPLY", "false"))
    _queue_worker_task = asyncio.create_task(_queue_worker_loop())
    yield
    global _queue_running
    _queue_running = False
    if _queue_worker_task:
        _queue_worker_task.cancel()
        try:
            await _queue_worker_task
        except asyncio.CancelledError:
            pass
    log.info("DevOps AI Agent shutting down")


app = FastAPI(
    title="DevOps AI Agent",
    description="Autonomous incident diagnosis and remediation powered by Claude",
    version="1.1.0",
    lifespan=lifespan,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def verify_github_signature(payload: bytes, signature: str) -> bool:
    secret = os.getenv("WEBHOOK_SECRET", "").encode()
    expected = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# Slack's documented replay window: reject requests whose timestamp differs from
# local time by more than five minutes.
SLACK_TIMESTAMP_TOLERANCE_SEC = 60 * 5


def verify_slack_signature(payload: bytes, timestamp: str, signature: str) -> bool:
    """Verify an inbound Slack request signature.

    Implements https://api.slack.com/authentication/verifying-requests-from-slack:
    HMAC-SHA256 over "v0:{timestamp}:{raw body}" keyed with SLACK_SIGNING_SECRET,
    compared against the X-Slack-Signature header as "v0={hex digest}".

    Fails closed — a missing signing secret, a missing header, or a timestamp
    outside the replay window rejects the request.
    """
    secret = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    if not secret or not timestamp or not signature:
        return False

    # int() (not float()) on purpose: float("nan") would sail through the window
    # check below, since every comparison against NaN is False.
    try:
        request_age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if request_age > SLACK_TIMESTAMP_TOLERANCE_SEC:
        return False

    basestring = b"v0:" + timestamp.encode() + b":" + payload
    expected = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    # Compare as bytes: compare_digest raises TypeError on non-ASCII str, and the
    # signature is attacker-controlled. Constant-time either way.
    return hmac.compare_digest(expected.encode(), signature.encode())


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "auto_apply": os.getenv("AUTO_APPLY", "false"),
        "storage_provider": os.getenv("STORAGE_PROVIDER", "memory"),
        "org_id": os.getenv("ORG_ID", "default"),
        "queue_worker": _queue_running,
    }


@app.get("/audit")
async def get_audit(org_id: Optional[str] = None, limit: int = 50):
    """Return recent incident audit log from cloud storage (org-scoped)."""
    org = org_id or os.getenv("ORG_ID", "default")
    events = incident_store.list_audit(org, limit=limit)
    return {"org_id": org, "events": events, "total": len(events)}


class DocUploadBody(BaseModel):
    path: str
    content: str


@app.post("/orgs/{org_id}/docs")
async def upload_doc_text(org_id: str, body: DocUploadBody):
    """Upload org documentation (runbooks, policies, playbooks) as text."""
    try:
        key = org_docs.upload(org_id, body.path, body.content)
        return {"status": "uploaded", "org_id": org_id, "path": body.path, "storage_key": key}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/orgs/{org_id}/docs/upload")
async def upload_doc_file(
    org_id: str,
    path: str,
    file: UploadFile = File(...),
):
    """Upload org documentation from a file."""
    content = (await file.read()).decode("utf-8")
    try:
        key = org_docs.upload(org_id, path, content, file.content_type or "text/plain")
        return {"status": "uploaded", "org_id": org_id, "path": path, "storage_key": key}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orgs/{org_id}/docs")
async def list_org_docs(org_id: str, prefix: str = ""):
    """List org documentation files."""
    return {"org_id": org_id, "docs": org_docs.list_docs(org_id, prefix)}


@app.get("/orgs/{org_id}/docs/{doc_path:path}")
async def get_org_doc(org_id: str, doc_path: str):
    """Retrieve a single org documentation file."""
    content = org_docs.get(org_id, doc_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"org_id": org_id, "path": doc_path, "content": content}


@app.delete("/orgs/{org_id}/docs/{doc_path:path}")
async def delete_org_doc(org_id: str, doc_path: str):
    if not org_docs.delete(org_id, doc_path):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "org_id": org_id, "path": doc_path}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
    x_org_id: str = Header(None, alias="X-Org-ID"),
):
    body = await request.body()

    if os.getenv("WEBHOOK_SECRET"):
        if not x_hub_signature_256 or not verify_github_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    if x_github_event == "workflow_run":
        run = payload.get("workflow_run", {})
        if run.get("conclusion") == "failure":
            context = {
                "type": "cicd",
                "source": "github_actions",
                "org_id": x_org_id or os.getenv("GITHUB_ORG", os.getenv("ORG_ID", "default")),
                "repo": payload.get("repository", {}).get("full_name"),
                "run_id": run.get("id"),
                "workflow_name": run.get("name"),
                "branch": run.get("head_branch"),
                "commit": run.get("head_sha", "")[:8],
                "html_url": run.get("html_url"),
            }
            incident_id = await enqueue_incident(context)
            return {"status": "queued", "type": "cicd", "incident_id": incident_id}

    return {"status": "ignored", "event": x_github_event}


@app.post("/webhook/alertmanager")
async def alertmanager_webhook(
    request: Request,
    x_org_id: str = Header(None, alias="X-Org-ID"),
):
    payload = await request.json()
    queued = []

    for alert in payload.get("alerts", []):
        if alert.get("status") != "firing":
            continue

        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alertname = labels.get("alertname", "")
        issue_type = _classify_alert(alertname, labels)

        context = {
            "type": issue_type,
            "source": "alertmanager",
            "org_id": x_org_id or labels.get("org_id") or os.getenv("ORG_ID", "default"),
            "alertname": alertname,
            "severity": labels.get("severity", "warning"),
            "namespace": labels.get("namespace"),
            "pod": labels.get("pod"),
            "service": labels.get("service"),
            "node": labels.get("node"),
            "summary": annotations.get("summary", ""),
            "description": annotations.get("description", ""),
            "labels": labels,
        }
        incident_id = await enqueue_incident(context)
        queued.append(incident_id)

    return {"status": "queued", "incident_ids": queued}


@app.post("/webhook/manual")
async def manual_trigger(
    request: Request,
    x_org_id: str = Header(None, alias="X-Org-ID"),
):
    context = await request.json()
    if "type" not in context:
        raise HTTPException(status_code=400, detail="'type' field required")

    context["source"] = "manual"
    if x_org_id:
        context["org_id"] = x_org_id
    incident_id = await enqueue_incident(context)
    return {"status": "queued", "incident_id": incident_id, "context": context}


@app.post("/slack/action")
async def slack_action(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_signature: str = Header(None),
    x_slack_request_timestamp: str = Header(None),
):
    # Read the raw bytes before parsing — the signature covers the body exactly
    # as Slack sent it, so a re-serialized form would not reproduce the HMAC.
    body = await request.body()

    if not verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
        log.warning("Rejected unverified Slack action request")
        raise HTTPException(status_code=401, detail="Invalid signature")

    form = await request.form()
    payload = __import__("json").loads(form.get("payload", "{}"))

    action = payload.get("actions", [{}])[0]
    action_id = action.get("action_id", "")
    value = action.get("value", "")

    if action_id == "approve_action":
        incident_id, encoded_cmd = value.split(":", 1)
        import base64
        cmd = base64.b64decode(encoded_cmd).decode()
        background_tasks.add_task(agent.execute_approved_action, incident_id, cmd)
        return JSONResponse({"text": f"✅ Approved. Executing: `{cmd}`"})

    elif action_id == "reject_action":
        return JSONResponse({"text": "❌ Action rejected. Incident escalated to on-call."})

    return JSONResponse({"text": "Unknown action"})


def _classify_alert(alertname: str, labels: dict) -> str:
    return classify_issue(alertname, labels)
