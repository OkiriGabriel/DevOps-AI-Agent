# API Reference

Base URL: `http://localhost:8000` (local) or your deployed agent URL.

All incident data is **org-scoped** and stored in cloud object storage (S3, MinIO, GCS, or Azure Blob).

---

## Authentication

| Endpoint group | Auth |
|----------------|------|
| `/health`, `/audit` | None (restrict in production via network policy) |
| `/orgs/*` | None by default — add API gateway auth in production |
| `/webhook/github` | `X-Hub-Signature-256` when `WEBHOOK_SECRET` is set |
| `/webhook/manual`, `/webhook/alertmanager` | Optional `X-Org-ID` header |
| `/slack/action` | Called by Slack (configure in Slack app settings) |

---

## Org scoping

Set the organization in one of three ways (priority order):

1. `X-Org-ID` request header
2. `org_id` field in webhook JSON body
3. `ORG_ID` environment variable on the server (default: `default`)

All storage paths are prefixed with `{org_id}/`:

```text
{org_id}/audit/...
{org_id}/logs/...
{org_id}/docs/...
{org_id}/queue/...
{org_id}/checkpoints/...
```

---

## Endpoints

### `GET /health`

Health check and runtime status.

**Response 200:**

```json
{
  "status": "ok",
  "auto_apply": "false",
  "storage_provider": "memory",
  "org_id": "acme-corp",
  "queue_worker": true
}
```

---

### `GET /audit`

Returns org-scoped incident audit history from cloud storage.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `org_id` | string | `ORG_ID` env | Organization to query |
| `limit` | int | `50` | Max events returned |

**Response 200:**

```json
{
  "org_id": "acme-corp",
  "events": [
    {
      "id": "INC-20260617120000-a1b2c3",
      "org_id": "acme-corp",
      "timestamp": "2026-06-17T12:00:00+00:00",
      "incident": { "type": "k8s", "namespace": "default" },
      "diagnosis": "Evidence: get_k8s_context showed OOMKilled...",
      "actions_taken": [{ "tool": "get_k8s_context", "result": {} }],
      "resolved": true,
      "grounding": { "grounded": true, "has_tool_evidence": true },
      "steps": 3,
      "escalated": false,
      "escalation_reasons": [],
      "duration_minutes": 4.2
    }
  ],
  "total": 1
}
```

When the agent cannot resolve an incident, audit entries include escalation metadata:

```json
{
  "escalated": true,
  "escalation_reasons": ["timeout_unresolved", "unresolved", "database_issue"],
  "duration_minutes": 12.5,
  "escalation": {
    "channels": {
      "slack": { "sent": true },
      "email": { "sent": true },
      "jira": { "created": true, "key": "OPS-456", "url": "https://..." },
      "zoho": { "created": true, "id": "12345" }
    }
  }
}
```

See [ESCALATION.md](ESCALATION.md) for configuration.

---

## Organization documentation

Org docs (runbooks, policies, playbooks) are loaded into the agent context during incidents.

**Allowed file extensions:** `.md`, `.txt`, `.yaml`, `.yml`, `.json`, `.rst`

### `POST /orgs/{org_id}/docs`

Upload documentation as JSON.

**Request body:**

```json
{
  "path": "runbooks/k8s-oom.md",
  "content": "# OOM Runbook\n1. Check pod logs\n2. Increase memory limits"
}
```

**Response 200:**

```json
{
  "status": "uploaded",
  "org_id": "acme-corp",
  "path": "runbooks/k8s-oom.md",
  "storage_key": "acme-corp/docs/runbooks/k8s-oom.md"
}
```

**Response 400:** Invalid path or unsupported extension.

---

### `POST /orgs/{org_id}/docs/upload`

Upload documentation from a file (multipart form).

**Query parameters:**

| Param | Required | Description |
|-------|----------|-------------|
| `path` | Yes | Storage path, e.g. `runbooks/k8s-oom.md` |

**Form field:**

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | Document content |

**Example:**

```bash
curl -X POST "http://localhost:8000/orgs/acme-corp/docs/upload?path=runbooks/k8s-oom.md" \
  -F "file=@./runbooks/k8s-oom.md"
```

---

### `GET /orgs/{org_id}/docs`

List documentation files.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `prefix` | string | Filter by path prefix (optional) |

**Response 200:**

```json
{
  "org_id": "acme-corp",
  "docs": [
    { "path": "runbooks/k8s-oom.md", "key": "acme-corp/docs/runbooks/k8s-oom.md" }
  ]
}
```

---

### `GET /orgs/{org_id}/docs/{doc_path}`

Retrieve a single document.

**Response 200:**

```json
{
  "org_id": "acme-corp",
  "path": "runbooks/k8s-oom.md",
  "content": "# OOM Runbook\n..."
}
```

**Response 404:** Document not found.

---

### `DELETE /orgs/{org_id}/docs/{doc_path}`

Delete a document.

**Response 200:**

```json
{
  "status": "deleted",
  "org_id": "acme-corp",
  "path": "runbooks/k8s-oom.md"
}
```

---

## Webhooks

All webhooks **enqueue** incidents asynchronously. The response is immediate; processing happens in the background queue worker.

Poll `GET /audit` after ~10–60 seconds to see results.

### `POST /webhook/manual`

Manually trigger an incident.

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Org-ID` | No | Organization ID |

**Request body:**

| Field | Required | Description |
|-------|----------|-------------|
| `type` | **Yes** | `k8s`, `cicd`, `server`, `dockerfile`, `argocd`, `helm`, `terraform`, `cloud_aws`, `cloud_gcp`, `cloud_azure` |
| `namespace` | No | K8s namespace |
| `pod` | No | Pod name |
| `repo` | No | GitHub repo (`owner/repo`) |
| `run_id` | No | CI/CD run ID |
| `app_name` | No | ArgoCD application name |
| `description` | No | Human-readable description |
| `raw_logs` | No | Pre-collected logs |

**Example — K8s:**

```bash
curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "k8s",
    "namespace": "production",
    "pod": "api-7d4f8b9c-xk2lp",
    "description": "Pod CrashLoopBackOff"
  }'
```

**Response 200:**

```json
{
  "status": "queued",
  "incident_id": "INC-20260617120000-a1b2c3",
  "context": { "type": "k8s", "org_id": "acme-corp", ... }
}
```

**Response 400:** Missing `type` field.

---

### `POST /webhook/alertmanager`

Receive Prometheus Alertmanager alerts.

**Headers:** `X-Org-ID` (optional)

**Request body:** Standard Alertmanager webhook JSON.

**Example:**

```bash
curl -X POST http://localhost:8000/webhook/alertmanager \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "PodCrashLooping",
        "namespace": "production",
        "pod": "api-xyz"
      },
      "annotations": {
        "summary": "Pod is crash looping"
      }
    }]
  }'
```

**Response 200:**

```json
{
  "status": "queued",
  "incident_ids": ["INC-20260617120000-a1b2c3"]
}
```

---

### `POST /webhook/github`

Receive GitHub Actions webhooks.

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `X-GitHub-Event` | Yes | Must be `workflow_run` |
| `X-Hub-Signature-256` | If `WEBHOOK_SECRET` set | HMAC SHA-256 signature |
| `X-Org-ID` | No | Organization ID |

Only processes `workflow_run` events where `conclusion` is `failure`.

**Response 200 (queued):**

```json
{
  "status": "queued",
  "type": "cicd",
  "incident_id": "INC-20260617120000-a1b2c3"
}
```

**Response 200 (ignored):**

```json
{
  "status": "ignored",
  "event": "push"
}
```

**Response 401:** Invalid webhook signature.

---

### `POST /slack/action`

Slack interactive button callback for approval workflow.

**Content-Type:** `application/x-www-form-urlencoded`

**Form field:** `payload` — JSON string from Slack.

Normally configured in your Slack app as the Interactivity Request URL.

---

## Incident types

| `type` value | Use case |
|--------------|----------|
| `k8s` | Pod crashes, OOM, ImagePullBackOff |
| `cicd` | Pipeline/build failures |
| `server` | CPU, memory, disk, nginx/systemd |
| `dockerfile` | Docker build failures |
| `argocd` | GitOps sync/health issues |
| `cloud_aws` | AWS resource issues |
| `cloud_gcp` | GCP resource issues |
| `cloud_azure` | Azure resource issues |

---

## Async processing model

```text
Webhook received
       │
       ▼
Enqueue to {org_id}/queue/pending/
       │
       ▼
Background worker claims incident
       │
       ▼
Agent runs (with checkpoint resume)
       │
       ├── Logs → {org_id}/logs/{year}/{month}/{incident_id}/
       ├── Audit → {org_id}/audit/{year}/{month}/{incident_id}.json
       └── Slack notification
```

**Queue worker settings** (`.env`):

```bash
QUEUE_POLL_INTERVAL_SEC=5
ORG_ID=acme-corp
ORG_IDS=acme-corp,beta-corp   # multi-tenant worker
```

---

## Storage configuration

```bash
STORAGE_PROVIDER=memory   # dev: memory | s3 | minio | gcs | azure
STORAGE_BUCKET=devops-agent
ORG_ID=acme-corp
AUDIT_RETENTION_DAYS=90
```

See `.env.example` for provider-specific settings — including the MinIO
(`STORAGE_ENDPOINT_URL`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`) and Azure
(`AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_ACCOUNT_URL`) credentials.
It lists every variable the server reads, and
`tests/test_env_example_coverage.py` keeps it that way.

---

## Related docs

- [API Testing Guide](API_TESTING.md) — Postman and curl test procedures
- [Postman collection](../postman/DevOps-AI-Agent.postman_collection.json)
- [Getting Started](GETTING_STARTED.md)
