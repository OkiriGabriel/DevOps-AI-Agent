# Escalation & Ticketing

The agent automatically escalates incidents to your team when it cannot resolve them safely.

## When escalation triggers

| Trigger | Config flag | Description |
|---------|-------------|-------------|
| **Timeout** | `ESCALATION_ON_UNRESOLVED` | Incident not resolved after `ESCALATION_TIMEOUT_MINUTES` (default **10**) |
| **Unresolved** | `ESCALATION_ON_UNRESOLVED` | Agent finished but `resolved: false` |
| **Database issue** | `ESCALATION_ON_DB_ISSUES` | RDS/SQL/Redis alerts, or blocked DB collector access |
| **AI failure** | `ESCALATION_ON_AI_FAILURE` | Agent crash, API error, max steps, not grounded |

## Notification channels

Set `ESCALATION_CHANNELS` (comma-separated):

```bash
ESCALATION_CHANNELS=slack,email,jira,zoho,pagerduty
```

| Channel | What happens |
|---------|--------------|
| `slack` | Critical escalation message to `SLACK_WEBHOOK_URL` |
| `email` | Escalation email to `EMAIL_TO` recipients |
| `jira` | Creates Jira issue in `JIRA_PROJECT_KEY` |
| `zoho` | Creates Zoho Desk ticket |
| `pagerduty` | Creates PagerDuty incident on `PAGERDUTY_SERVICE_ID` |

A channel whose credentials are missing is skipped, and a failing third-party
call is caught rather than raised — one failing channel never stops the others.

## Configuration

```bash
# Enable/disable escalation
ESCALATION_ENABLED=true
ESCALATION_TIMEOUT_MINUTES=10   # use 5 for faster escalation

# Which scenarios escalate
ESCALATION_ON_DB_ISSUES=true
ESCALATION_ON_UNRESOLVED=true
ESCALATION_ON_AI_FAILURE=true

# Channels
ESCALATION_CHANNELS=slack,email,jira

# Jira
JIRA_ENABLED=true
JIRA_URL=https://yourorg.atlassian.net
JIRA_EMAIL=agent@company.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=OPS

# Zoho Desk
ZOHO_ENABLED=true
ZOHO_DESK_ORG_ID=123456789
ZOHO_ACCESS_TOKEN=your-oauth-token
ZOHO_DEPARTMENT_ID=your-dept-id
ZOHO_CONTACT_EMAIL=devops@company.com

# PagerDuty
PAGERDUTY_ENABLED=true
PAGERDUTY_TOKEN=your-rest-api-key
PAGERDUTY_SERVICE_ID=PSERVICE1
PAGERDUTY_FROM_EMAIL=agent@company.com   # must be a valid PagerDuty user
PAGERDUTY_URL=https://api.pagerduty.com  # https://api.eu.pagerduty.com for EU
```

The incident is created with `incident_key` set to the agent's incident id, so
repeat escalations of one incident carry a single deduplication key rather than
an unrelated key per attempt.

## Database issues

When `ENABLE_DATABASE_COLLECTION=false` (default), the agent **cannot** query RDS, Cloud SQL, Redis, etc. These incidents are **always escalated** so a human/DBA can investigate.

Detected by:
- Alert names containing `rds`, `sql`, `database`, `redis`, `dynamodb`, etc.
- `resource_type` like `rds`, `cloud_sql`, `sql`, `cosmosdb`
- Tool results with `blocked: true` and database error message

## Audit trail

Escalation details are stored in the audit entry:

```json
{
  "escalated": true,
  "escalation_reasons": ["timeout_unresolved", "unresolved"],
  "duration_minutes": 12.4,
  "escalation": {
    "channels": {
      "slack": {"sent": true},
      "jira": {"created": true, "key": "OPS-123", "url": "..."}
    }
  }
}
```

Query via: `GET /audit?org_id=acme-corp`

## Testing escalation

### Simulate unresolved incident (fast timeout for testing)

```bash
# In .env set ESCALATION_TIMEOUT_MINUTES=1 for testing

curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{"type": "k8s", "namespace": "default", "pod": "missing-pod-xyz"}'

# Wait for processing, then check audit:
curl "http://localhost:8000/audit?org_id=acme-corp" | python3 -m json.tool
# Look for "escalated": true
```

### Simulate database issue

```bash
curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "cloud_aws",
    "resource_type": "rds",
    "resource_id": "prod-db-01",
    "description": "RDS connection timeout"
  }'
```

Expected: immediate escalation with `database_issue` reason (even if processing is fast).

## Related

- [API Reference](API_REFERENCE.md)
- [Security Policy](SECURITY_POLICY.md)
- [`.env.example`](../.env.example)
