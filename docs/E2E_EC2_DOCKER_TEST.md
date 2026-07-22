# E2E Test: EC2 + Docker Crash Loop

End-to-end guide: launch EC2, install Docker, run a broken container, trigger the agent, and verify the fix.

## Architecture options

| Setup | Agent location | Can auto-fix EC2 Docker? |
|-------|----------------|--------------------------|
| **A (recommended)** | Same EC2 as broken app | Yes — runs `docker` locally |
| **B** | Separate server + SSH | Yes — if SSH keys configured |
| **C** | Laptop only | Diagnosis only — include `raw_logs` in webhook |

This guide covers **Setup A** (agent on EC2) and **Setup B** (remote SSH).

---

## Part 1: Launch EC2

### AWS CLI

```bash
# Variables
export AWS_REGION=us-east-1
export KEY_NAME=my-keypair        # must exist in EC2
export SG_NAME=devops-agent-test

# Create security group (SSH + agent API)
aws ec2 create-security-group --group-name $SG_NAME --description "Agent E2E test" 2>/dev/null || true
SG_ID=$(aws ec2 describe-security-groups --group-names $SG_NAME --query 'Groups[0].GroupId' --output text)

MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr ${MY_IP}/32
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 8000 --cidr ${MY_IP}/32

# Launch Ubuntu 22.04
AMI_ID=$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type t3.small \
  --key-name $KEY_NAME \
  --security-group-ids $SG_ID \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=devops-agent-e2e}]' \
  --query 'Instances[0].InstanceId' --output text)

aws ec2 wait instance-running --instance-ids $INSTANCE_ID
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "EC2 ready: $INSTANCE_ID @ $PUBLIC_IP"
echo "SSH: ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
```

### AWS Console (alternative)

1. **EC2 → Launch instance**
2. AMI: Ubuntu 22.04 or Amazon Linux 2023
3. Type: `t3.small` (2 GB RAM — enough for agent + Docker)
4. Key pair: select or create
5. Security group: allow **SSH (22)** and **8000** from your IP
6. Launch → note **Public IP**

---

## Part 2: Install Docker + broken app on EC2

SSH into the instance:

```bash
ssh -i ~/.ssh/my-keypair.pem ubuntu@$PUBLIC_IP
```

Run the setup script (from the repo):

```bash
# Option 1: copy script from your laptop
scp -i ~/.ssh/my-keypair.pem scripts/ec2-docker-test-setup.sh ubuntu@$PUBLIC_IP:~/
ssh -i ~/.ssh/my-keypair.pem ubuntu@$PUBLIC_IP 'sudo bash ~/ec2-docker-test-setup.sh'

# Option 2: manual quick setup on EC2
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl start docker

sudo mkdir -p /opt/agent-docker-test && cd /opt/agent-docker-test
sudo tee docker-compose.yml <<'EOF'
services:
  broken-app:
    image: alpine:3.19
    container_name: broken-app
    restart: unless-stopped
    command: ["sh", "-c", "echo Starting; test -n \"$REQUIRED_ENV\" || { echo ERROR: REQUIRED_ENV not set; exit 1; }"]
EOF
sudo docker compose up -d
```

Verify the container is crash-looping:

```bash
sudo docker ps -a --filter name=broken-app
# STATUS should show "Restarting" or "Exited"

sudo docker logs broken-app --tail 10
# ERROR: REQUIRED_ENV not set
```

---

## Part 3: Deploy the agent on EC2 (Setup A — recommended)

On the **same EC2 instance**:

```bash
# Install Python + clone repo
sudo apt-get install -y python3 python3-pip python3-venv git
git clone https://github.com/open-devops-agent/open-devops-agent.git
cd devops-ai-agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # set at minimum:
```

**Minimum `.env` on EC2:**

```bash
ANTHROPIC_API_KEY=sk-ant-...
ORG_ID=acme-corp
STORAGE_PROVIDER=memory
AUTO_APPLY=true          # allows docker restart / compose fixes
SLACK_WEBHOOK_URL=...    # optional

ESCALATION_ENABLED=true
ESCALATION_TIMEOUT_MINUTES=10
ESCALATION_CHANNELS=slack,email
```

Start the agent (bind to all interfaces so your laptop can reach it):

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

From your **laptop**, verify:

```bash
curl http://$PUBLIC_IP:8000/health
```

---

## Part 4: Upload org runbook (optional but helps)

```bash
curl -X POST http://$PUBLIC_IP:8000/orgs/acme-corp/docs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "runbooks/docker-restart-loop.md",
    "content": "# Docker Restart Loop\n1. Run docker ps -a and docker logs <container>\n2. Check for missing env vars or exit code 1\n3. Fix docker-compose.yml environment section\n4. docker compose up -d --build\n5. Verify with docker ps"
  }'
```

---

## Part 5: Trigger the agent

### Option A — Agent on same EC2 (local diagnosis)

```bash
curl -X POST http://$PUBLIC_IP:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "server",
    "description": "Docker container broken-app keeps restarting on EC2",
    "service": "broken-app",
    "node": "'"$PUBLIC_IP"'",
    "alertname": "DockerContainerRestarting"
  }'
```

Response:

```json
{"status": "queued", "incident_id": "INC-..."}
```

### Option B — Agent on laptop, SSH to EC2

Add to agent `.env` on laptop:

```bash
# Ensure SSH works without password: ssh ubuntu@$PUBLIC_IP
```

Trigger with `host`:

```bash
curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "server",
    "host": "'"$PUBLIC_IP"'",
    "description": "Docker container broken-app keeps restarting",
    "service": "broken-app"
  }'
```

The agent will run `ssh ubuntu@$PUBLIC_IP 'docker logs ...'` via `run_shell_command`.

### Option C — Logs only (no SSH)

```bash
# On EC2, capture logs:
LOGS=$(ssh ubuntu@$PUBLIC_IP 'sudo docker logs broken-app --tail 30 2>&1')

curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg logs "$LOGS" \
    '{
      type: "server",
      org_id: "acme-corp",
      description: "broken-app Docker container crash loop",
      service: "broken-app",
      raw_logs: $logs
    }')"
```

---

## Part 6: Monitor and verify

### Poll audit log (~30–90 seconds)

```bash
curl -s "http://$PUBLIC_IP:8000/audit?org_id=acme-corp" | python3 -m json.tool
```

Look for:

- `actions_taken` with `docker logs`, `docker ps`, `docker inspect`
- `diagnosis` with **Evidence:** section citing log output
- `resolved: true` if fix applied
- `escalated: true` if agent could not fix (check Slack/email/Jira)

### Verify container is healthy (on EC2)

```bash
ssh ubuntu@$PUBLIC_IP 'sudo docker ps -a --filter name=broken-app'
# STATUS should be "Up" after fix

ssh ubuntu@$PUBLIC_IP 'sudo docker logs broken-app --tail 5'
```

### Manual fix (if agent escalated instead)

The broken app needs `REQUIRED_ENV=ok` in docker-compose:

```bash
ssh ubuntu@$PUBLIC_IP
cd /opt/agent-docker-test
sudo sed -i '/broken-app:/a\    environment:\n      REQUIRED_ENV: ok' docker-compose.yml
sudo docker compose up -d
```

---

## Part 7: Simulate with Postman

1. Import `postman/DevOps-AI-Agent.postman_collection.json`
2. Set environment `baseUrl` = `http://<EC2_PUBLIC_IP>:8000`
3. Run **Upload Doc (JSON)** with docker runbook
4. Run **Manual Trigger — Server** with broken-app description
5. Wait 60s → **Get Audit Log**

---

## Expected agent behavior

```text
1. Webhook queued
2. Server collector runs: docker ps -a, docker logs (local)
3. Claude calls run_shell_command:
   - docker logs broken-app
   - docker inspect broken-app
4. Diagnosis: "REQUIRED_ENV not set" (Evidence from logs)
5. Fix attempt (if AUTO_APPLY=true):
   - Edit compose or docker run with env var
   - docker compose up -d / docker restart
6. notify_slack with summary
7. Audit entry saved
```

If unresolved after 10 min → **escalation** to Slack/email/Jira.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Agent can't reach EC2 API | Open port 8000 in security group |
| `docker` permission denied | Agent user in `docker` group, or use `sudo` in commands |
| SSH host fails | Copy SSH key, use `ubuntu@ip`, disable StrictHostKeyChecking |
| `resolved: false` | Set `AUTO_APPLY=true` for docker restart fixes |
| No tool evidence | Agent needs real logs — use Setup A or include `raw_logs` |
| Escalation only | Check audit `escalation_reasons`; fix manually or tune prompts |

---

## Cleanup

```bash
aws ec2 terminate-instances --instance-ids $INSTANCE_ID
aws ec2 delete-security-group --group-name $SG_NAME
```

---

## Related

- [Getting Started](GETTING_STARTED.md)
- [API Testing](API_TESTING.md)
- [Escalation](ESCALATION.md)
- `scripts/ec2-docker-test-setup.sh`
- `scripts/test_api_flow.sh`
