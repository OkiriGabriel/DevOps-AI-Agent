# Usage Guide - Common DevOps Fixes

This guide shows how to install the DevOps AI Agent and how it automatically handles common DevOps tasks, so your team can focus on complex problems.

---

## Table of Contents

1. [Installation](#installation)
2. [Platform Features](#platform-features)
3. [API & Webhooks](#api--webhooks)
4. [Org Documentation & Storage](#org-documentation--storage)
5. [Escalation & Ticketing](#escalation--ticketing)
6. [Deployment Models](#deployment-models)
7. [Testing](#testing)
8. [Cloud Services (AWS, GCP, Azure)](#cloud-services-aws-gcp-azure)
9. [Web Servers](#web-servers)
10. [Nginx Issues](#nginx-issues)
11. [Apache Issues](#apache-issues)
12. [Timeout Problems](#timeout-problems)
13. [Server Performance](#server-performance)
14. [SSL/TLS Issues](#ssltls-issues)
15. [Load Balancer Problems](#load-balancer-problems)
16. [Database Connection Issues](#database-connection-issues)
17. [Disk Space Problems](#disk-space-problems)
18. [Memory Issues](#memory-issues)
19. [Configure and Connect](#configure-and-connect)
20. [Documentation Index](#documentation-index)

---

## Installation

Install the agent before connecting monitoring or enabling automated fixes.

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | Required |
| pip + venv | Latest | Required |
| Git | Any recent | Required for source install |
| kubectl | Latest | Required for Kubernetes fixes |
| Docker | 20+ | Optional (container install) |
| aws / gcloud / az CLI | Latest | Optional (cloud diagnostics) |

```bash
# Verify prerequisites
python --version    # Should be 3.9+
pip --version
git --version
kubectl version --client   # Optional, for K8s
```

---

### Option 1: Install from Source (Recommended)

Use this for local development, Linux servers, RHEL, and Windows (with Python installed).

```bash
# 1. Clone the repository
git clone https://github.com/open-devops-agent/open-devops-agent.git
cd devops-ai-agent

# 2. Create and activate a virtual environment
python -m venv venv

# Linux / macOS / RHEL
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# 3. Install core Python packages
pip install --upgrade pip
pip install -r requirements.txt

# 4. (Optional) Install development tools for testing
pip install -r requirements-dev.txt
```

**Install optional cloud packages** (only what you use):

```bash
# AWS
pip install boto3 botocore

# GCP
pip install google-cloud-compute google-cloud-container \
            google-cloud-run google-cloud-functions \
            google-cloud-logging google-cloud-sql

# Azure
pip install azure-identity azure-mgmt-compute \
            azure-mgmt-containerservice azure-mgmt-web \
            azure-mgmt-sql azure-mgmt-monitor
```

---

### Option 2: Use the Install Script

The project includes an interactive installer that installs core dependencies and prompts for cloud providers.

```bash
git clone https://github.com/open-devops-agent/open-devops-agent.git
cd devops-ai-agent

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

chmod +x scripts/install_dependencies.sh
./scripts/install_dependencies.sh
```

Follow the prompts to select AWS, GCP, Azure, or all cloud providers.

---

### Option 3: Install with Docker

See **`docs/BUILD_AND_USAGE.md`** for full Docker build and run instructions.

```bash
chmod +x scripts/build_docker.sh
./scripts/build_docker.sh

docker run -d --name devops-ai-agent -p 8000:8000 --env-file .env devops-ai-agent:latest
```

---

### Option 4: Install as Python Package (wheel)

See **`docs/BUILD_AND_USAGE.md`** for full package build and publish instructions.

```bash
chmod +x scripts/build_package.sh
./scripts/build_package.sh

pip install dist/devops_ai_agent-*.whl
devops-agent serve
```

---

### Option 5: Install on Kubernetes

For organization-wide deployment:

```bash
# Create namespace
kubectl create namespace devops-agent

# Create secrets from your .env values
kubectl create secret generic agent-secrets \
  --namespace devops-agent \
  --from-literal=ANTHROPIC_API_KEY=your-key \
  --from-literal=EMAIL_SMTP_PASSWORD=your-password

# Deploy (see docs/DEPLOYMENT.md for full manifests)
kubectl apply -f k8s/ -n devops-agent
```

See `docs/DEPLOYMENT.md` for AWS ECS, GCP Cloud Run, and Azure Container Instances.

---

### Configure After Install

```bash
# Copy example configuration
cp .env.example .env

# Edit with your credentials
nano .env   # or vim, code, notepad, etc.
```

**Minimum required settings:**

```bash
# AI provider (required)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Email alerts (required for dangerous operation notifications)
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.yourcompany.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=devops-agent@yourcompany.com
EMAIL_SMTP_PASSWORD=your-app-password
EMAIL_FROM=devops-agent@yourcompany.com
EMAIL_TO=sre-team@yourcompany.com

# Org & storage (recommended)
ORG_ID=acme-corp
STORAGE_PROVIDER=memory   # production: s3, minio, gcs, azure

# Escalation when agent cannot resolve
ESCALATION_ENABLED=true
ESCALATION_TIMEOUT_MINUTES=10
ESCALATION_CHANNELS=slack,email   # add jira, zoho as needed

# Safety (keep these for production)
AUTO_APPLY=false
ENABLE_SECURITY_SCANNING=true
ENABLE_COMPLIANCE_CHECKS=true
AGENT_EMERGENCY_STOP=false
ENABLE_DATABASE_COLLECTION=false
```

See `.env.example` for all options (Slack, GitHub, cloud credentials, ArgoCD, etc.).

---

### Start the Agent

**Local / server (Python package CLI):**

```bash
source venv/bin/activate   # if not already active

# Start API server (after pip install or editable install)
devops-agent serve

# Or with uvicorn directly
uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 2
```

**Background process (Linux/RHEL):**

```bash
nohup uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 2 \
  > logs/agent.log 2>&1 &
```

---

### Verify Installation

```bash
# 1. Health check
curl http://localhost:8000/health
# Expected: {"status":"ok","queue_worker":true,"storage_provider":"memory",...}

# 2. Run setup verification script
chmod +x scripts/verify_setup.sh
./scripts/verify_setup.sh

# 3. Upload an org runbook (optional)
curl -X POST http://localhost:8000/orgs/acme-corp/docs \
  -H "Content-Type: application/json" \
  -d '{"path":"runbooks/test.md","content":"# Test runbook"}'

# 4. Queue a test incident (async — processed by background worker)
curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "server",
    "description": "Installation test alert",
    "service": "nginx"
  }'
# Expected: {"status":"queued","incident_id":"INC-..."}

# 5. Poll org-scoped audit log (wait ~30s after step 4)
curl "http://localhost:8000/audit?org_id=acme-corp"

# 6. Or run automated API test
./scripts/test_api_flow.sh
```

If health check passes and the webhook returns `status: queued`, the agent is installed correctly.

---

### Install Checklist

- [ ] Python 3.9+ installed
- [ ] Repository cloned
- [ ] Virtual environment created and activated
- [ ] `pip install -r requirements.txt` completed
- [ ] Cloud/storage packages installed (if needed: `boto3`, `google-cloud-storage`)
- [ ] `.env` configured from `.env.example` (`ORG_ID`, `ANTHROPIC_API_KEY`, storage)
- [ ] Email and/or Slack configured
- [ ] Escalation channels configured (`ESCALATION_CHANNELS`)
- [ ] Agent started (`uvicorn api.server:app`)
- [ ] Health check passes (`GET /health`)
- [ ] Test incident queued and appears in `GET /audit?org_id=`
- [ ] Monitoring webhook connected (Prometheus Alertmanager, GitHub, etc.)
- [ ] SSH keys configured (if centralized agent fixes remote servers)

---

## Platform Features

| Feature | Description | Config |
|---------|-------------|--------|
| **Durable queue** | Webhooks survive restarts; background worker processes incidents | `QUEUE_POLL_INTERVAL_SEC` |
| **Cloud storage** | Audit, logs, checkpoints, org docs per org | `STORAGE_PROVIDER`, `STORAGE_BUCKET` |
| **PII scrubbing** | Redacts emails, tokens, secrets before Claude/Slack/storage | Automatic |
| **Anti-hallucination** | Requires tool evidence + Evidence section in diagnosis | `agent/grounding.py` |
| **Checkpoints** | Resume mid-incident after agent crash | Automatic in storage |
| **Org documentation** | Upload runbooks via API; injected into agent context | `POST /orgs/{org}/docs` |
| **Auto-escalation** | Jira, Zoho, email, Slack when unresolved or DB issue | `ESCALATION_*`, `JIRA_*`, `ZOHO_*` |
| **Claude retry** | Exponential backoff on API failures | `CLAUDE_API_RETRIES` |

---

## API & Webhooks

Base URL: `http://localhost:8000` (or your deployed agent).

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Agent and queue worker status |
| `GET` | `/audit?org_id=` | Org-scoped incident audit history |
| `POST` | `/orgs/{org}/docs` | Upload runbooks/policies (JSON) |
| `GET` | `/orgs/{org}/docs` | List org documentation |
| `POST` | `/webhook/manual` | Manually queue an incident |
| `POST` | `/webhook/alertmanager` | Prometheus Alertmanager |
| `POST` | `/webhook/github` | GitHub Actions failures |

**Org scoping:** Pass `X-Org-ID` header or set `ORG_ID` in `.env`. All data stored under `{org_id}/` in cloud storage.

**Async processing:** Webhooks return immediately with `incident_id`. Poll `/audit` after 30–60 seconds.

Full reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)  
Postman: import [postman/DevOps-AI-Agent.postman_collection.json](postman/DevOps-AI-Agent.postman_collection.json)

### Example: remote EC2 Docker crash (centralized agent)

```bash
curl -X POST http://agent.internal:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "server",
    "host": "ubuntu@10.0.1.50",
    "service": "broken-app",
    "description": "Docker container keeps restarting"
  }'
```

Requires SSH from agent server → target EC2. See [docs/CENTRALIZED_DEPLOYMENT.md](docs/CENTRALIZED_DEPLOYMENT.md).

---

## Org Documentation & Storage

### Upload runbooks

```bash
curl -X POST http://localhost:8000/orgs/acme-corp/docs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "runbooks/nginx-502.md",
    "content": "# Nginx 502\n1. Check upstream\n2. Restart php-fpm\n3. nginx -t && systemctl reload nginx"
  }'
```

### Storage providers

```bash
STORAGE_PROVIDER=memory   # local dev
STORAGE_PROVIDER=s3        # AWS
STORAGE_PROVIDER=minio     # MinIO / S3-compatible
STORAGE_PROVIDER=gcs       # Google Cloud Storage
STORAGE_PROVIDER=azure     # Azure Blob
STORAGE_BUCKET=devops-agent
AUDIT_RETENTION_DAYS=90
```

Storage layout per org:

```text
{org_id}/audit/          incident summaries
{org_id}/logs/           tool output, conversations
{org_id}/docs/           runbooks and policies
{org_id}/queue/          durable incident queue
{org_id}/checkpoints/    resume state
```

---

## Escalation & Ticketing

The agent auto-escalates when it **cannot resolve** within the timeout, hits a **database issue**, or **lacks evidence** to act safely.

```bash
ESCALATION_ENABLED=true
ESCALATION_TIMEOUT_MINUTES=10    # use 5 for faster escalation
ESCALATION_CHANNELS=slack,email,jira,zoho
ESCALATION_ON_DB_ISSUES=true

# Jira (optional)
JIRA_ENABLED=true
JIRA_URL=https://yourorg.atlassian.net
JIRA_EMAIL=agent@company.com
JIRA_API_TOKEN=...
JIRA_PROJECT_KEY=OPS
```

Database incidents are escalated to humans/DBA by default (`ENABLE_DATABASE_COLLECTION=false`).

Full guide: [docs/ESCALATION.md](docs/ESCALATION.md)

---

## Deployment Models

| Model | Agent location | Best for |
|-------|----------------|----------|
| **Co-located** | Same EC2/VM as the app | Docker/server fixes on that host |
| **Centralized** | Dedicated agent server | Production — one agent, many targets |
| **Kubernetes** | Cluster deployment | EKS/GKE/AKS incidents via API |
| **Docker Compose** | With MinIO for durable storage | Local/staging with persistence |

- Centralized + remote EC2: [docs/CENTRALIZED_DEPLOYMENT.md](docs/CENTRALIZED_DEPLOYMENT.md)
- EC2 Docker E2E test: [docs/E2E_EC2_DOCKER_TEST.md](docs/E2E_EC2_DOCKER_TEST.md)
- Production deploy: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

## Testing

```bash
# Unit tests
pytest tests/ -v

# API smoke test
./scripts/test_api_flow.sh

# Simulate incidents (no cloud creds needed)
python scripts/simulate_incident.py k8s
python scripts/simulate_incident.py cicd

# EC2 Docker crash-loop setup (run on target EC2)
sudo bash scripts/ec2-docker-test-setup.sh
```

Postman: [docs/API_TESTING.md](docs/API_TESTING.md)

---

## Cloud Services (AWS, GCP, Azure)

The agent supports all major cloud compute, container, and Kubernetes services across the three clouds.

**Full registry:** `collectors/cloud_registry.py`

> **Database services optional (default: off):** RDS, Cloud SQL, Azure SQL, DynamoDB, Cosmos DB, Redis/Memorystore.
> Set `ENABLE_DATABASE_COLLECTION=true` only after security approval. See `collectors/database_policy.py`.

### Kubernetes (EKS, GKE, AKS)

| Cloud | Service | Resource Type | Example |
|-------|---------|---------------|---------|
| AWS | Amazon EKS | `eks` | `collect("eks", "prod-cluster")` |
| AWS | EKS Node Group | `eks_nodegroup` | `collect("eks_nodegroup", "ng-1", cluster="prod", nodegroup="ng-1")` |
| GCP | Google GKE | `gke` | `collect("gke", "prod", cluster="prod", zone="us-central1-a")` |
| GCP | GKE Node Pool | `gke_nodepool` | `collect("gke_nodepool", "default-pool", cluster="prod", zone="us-central1-a")` |
| Azure | Azure AKS | `aks` | `collect("aks", "prod-aks", resource_group="prod-rg")` |

For pod-level issues inside any cluster, the agent delegates to the Kubernetes collector.

### Virtual Machines

| Cloud | Service | Resource Type | Example |
|-------|---------|---------------|---------|
| AWS | EC2 | `ec2` | `collect("ec2", "i-0abc123")` |
| GCP | Compute Engine | `gce` or `compute` | `collect("gce", "web-01", zone="us-central1-a")` |
| Azure | Virtual Machine | `vm` | `collect("vm", "web-vm", resource_group="prod-rg")` |
| Azure | VM Scale Set | `vmss` | `collect("vmss", "web-vmss", resource_group="prod-rg")` |
| AWS | Auto Scaling | `autoscaling` | `collect("autoscaling", "web-asg")` |

### Containers

| Cloud | Service | Resource Type | Example |
|-------|---------|---------------|---------|
| AWS | ECS / Fargate | `ecs` or `fargate` | `collect("ecs", task_arn, cluster="prod")` |
| AWS | ECR | `ecr` | `collect("ecr", "my-app")` |
| AWS | App Runner | `apprunner` | `collect("apprunner", service_arn)` |
| GCP | Cloud Run | `cloud_run` | `collect("cloud_run", "api", region="us-central1")` |
| GCP | Artifact Registry | `artifact_registry` | `collect("artifact_registry", "my-repo", location="us")` |
| Azure | Container Instances | `aci` | `collect("aci", "api-group", resource_group="prod-rg")` |
| Azure | Container Apps | `container_apps` | `collect("container_apps", "api", resource_group="prod-rg")` |
| Azure | Container Registry | `acr` | `collect("acr", "myregistry", resource_group="prod-rg")` |

### Install Cloud SDK Packages

```bash
# AWS (all services)
pip install boto3 botocore

# GCP (all services)
pip install google-cloud-compute google-cloud-container google-cloud-run \
            google-cloud-functions google-cloud-logging google-cloud-sql \
            google-cloud-storage google-cloud-pubsub

# Azure (all services)
pip install azure-identity azure-mgmt-compute azure-mgmt-containerservice \
            azure-mgmt-containerinstance azure-mgmt-appcontainers \
            azure-mgmt-containerregistry azure-mgmt-web azure-mgmt-sql \
            azure-mgmt-network azure-mgmt-storage
```

Or use the interactive installer:

```bash
./scripts/install_dependencies.sh
```

### Webhook Example (Cloud Alert)

```bash
curl -X POST http://localhost:8000/webhook/manual \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: acme-corp" \
  -d '{
    "type": "cloud_aws",
    "resource_type": "eks",
    "resource_id": "prod-cluster",
    "labels": {"severity": "critical", "alertname": "EKSNodegroupUnhealthy"}
  }'
```

---

## Web Servers

### Common Issues the Agent Fixes Automatically

#### 1. Service Not Running

**Problem:** Web server stopped responding

**Agent Detection:**
```
Alert: WebServerDown
Service: nginx/apache not responding
Port: 80/443 not listening
```

**Agent Fix:**
```bash
# Linux/RHEL
systemctl status nginx
systemctl restart nginx
systemctl enable nginx

# Windows
Restart-Service -Name W3SVC
```

**Verification:**
- Service status = Running
- Port 80/443 listening
- Health check returns 200 OK

**Documentation Generated:**
- Runbook: "Web Server Restart Procedure"
- Postmortem: Root cause analysis
- KB Article: "Service restart steps"

---

## Nginx Issues

### 1. Nginx Configuration Error

**Problem:** Nginx won't start due to configuration error

**Agent Detection:**
```
Alert: NginxConfigError
Error: nginx: configuration file /etc/nginx/nginx.conf test failed
```

**Agent Analysis:**
```bash
# Test configuration
nginx -t

# Common issues detected:
# - Missing semicolon
# - Invalid directive
# - Wrong file path
# - Duplicate server block
```

**Agent Fix:**
```bash
# Backup current config
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup

# Restore last known good config
cp /etc/nginx/nginx.conf.bak /etc/nginx/nginx.conf

# Test configuration
nginx -t

# Reload nginx
systemctl reload nginx
```

**Manual Steps (if needed):**
```bash
# Check syntax
nginx -t

# View error details
journalctl -u nginx -n 50

# Edit config
vim /etc/nginx/nginx.conf

# Reload
nginx -s reload
```

---

### 2. Nginx High Connection Count

**Problem:** Too many connections, server slow

**Agent Detection:**
```
Alert: NginxHighConnections
Active Connections: 5000
Worker Connections: 1024 (limit)
```

**Agent Fix:**
```bash
# Increase worker connections
# Edit /etc/nginx/nginx.conf

events {
    worker_connections 4096;
}

# Reload nginx
nginx -s reload
```

**Agent Recommendations:**
```
- Increase worker_processes to match CPU cores
- Enable connection keepalive
- Add rate limiting
- Consider load balancer
```

---

### 3. Nginx 502 Bad Gateway

**Problem:** Upstream server not responding

**Agent Detection:**
```
Alert: Nginx502Error
Status: 502 Bad Gateway
Upstream: PHP-FPM / Application server timeout
```

**Agent Analysis:**
```bash
# Check upstream service
systemctl status php-fpm
systemctl status uwsgi
systemctl status gunicorn

# Check upstream connectivity
curl http://localhost:9000
netstat -tlnp | grep 9000

# Check nginx error log
tail -f /var/log/nginx/error.log
```

**Agent Fix:**
```bash
# Restart upstream service
systemctl restart php-fpm

# Increase timeout in nginx
# /etc/nginx/sites-available/default

location / {
    proxy_pass http://backend;
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}

# Reload nginx
nginx -s reload
```

---

### 4. Nginx 504 Gateway Timeout

**Problem:** Request taking too long

**Agent Detection:**
```
Alert: Nginx504Error
Status: 504 Gateway Timeout
Request Time: > 60 seconds
```

**Agent Fix:**
```bash
# Increase timeouts in /etc/nginx/nginx.conf

http {
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    fastcgi_read_timeout 300s;
}

# Reload nginx
nginx -s reload
```

---

## Apache Issues

### 1. Apache Not Starting

**Problem:** Apache service failed to start

**Agent Detection:**
```
Alert: ApacheDown
Service: apache2/httpd not running
Error: Address already in use
```

**Agent Analysis:**
```bash
# Check what's using port 80
netstat -tlnp | grep :80
lsof -i :80

# Check apache config
apachectl configtest

# Check error log
tail -f /var/log/apache2/error.log
```

**Agent Fix:**
```bash
# If port conflict, kill process
kill <PID>

# Test config
apachectl configtest

# Start apache
systemctl restart apache2

# Enable on boot
systemctl enable apache2
```

---

### 2. Apache High Memory Usage

**Problem:** Apache consuming too much memory

**Agent Detection:**
```
Alert: ApacheHighMemory
Memory Usage: 80% (high)
Apache Processes: 150+
```

**Agent Fix:**
```bash
# Edit /etc/apache2/mods-available/mpm_prefork.conf

<IfModule mpm_prefork_module>
    StartServers 5
    MinSpareServers 5
    MaxSpareServers 10
    MaxRequestWorkers 150
    MaxConnectionsPerChild 3000
</IfModule>

# Restart apache
systemctl restart apache2
```

**Agent Recommendations:**
```
- Use mpm_event instead of mpm_prefork
- Enable caching
- Optimize application code
- Add more memory or scale horizontally
```

---

### 3. Apache 500 Internal Server Error

**Problem:** Application error

**Agent Detection:**
```
Alert: Apache500Error
Status: 500 Internal Server Error
```

**Agent Analysis:**
```bash
# Check apache error log
tail -f /var/log/apache2/error.log

# Check application logs
tail -f /var/www/app/logs/error.log

# Check PHP errors (if applicable)
tail -f /var/log/php/error.log

# Check permissions
ls -la /var/www/html/
```

**Agent Fix:**
```bash
# Fix permissions
chown -R www-data:www-data /var/www/html/
chmod -R 755 /var/www/html/

# If .htaccess error, disable
mv .htaccess .htaccess.bak

# Restart apache
systemctl restart apache2
```

---

## Timeout Problems

### 1. Application Timeout

**Problem:** Requests timing out

**Agent Detection:**
```
Alert: ApplicationTimeout
Error: Gateway Timeout
Response Time: > 30 seconds
```

**Agent Fixes by Layer:**

**Nginx:**
```nginx
# /etc/nginx/nginx.conf
proxy_read_timeout 300;
proxy_connect_timeout 300;
proxy_send_timeout 300;
```

**Apache:**
```apache
# /etc/apache2/apache2.conf
Timeout 300
```

**PHP-FPM:**
```ini
# /etc/php/7.4/fpm/pool.d/www.conf
request_terminate_timeout = 300
```

**PHP:**
```ini
# /etc/php/7.4/fpm/php.ini
max_execution_time = 300
```

**Application (Node.js):**
```javascript
// server.js
server.timeout = 300000; // 5 minutes
```

---

### 2. Database Query Timeout

**Problem:** Database queries taking too long

**Agent Detection:**
```
Alert: SlowQuery
Query Time: > 10 seconds
Database: MySQL/PostgreSQL
```

**Agent Analysis:**
```sql
-- MySQL
SHOW FULL PROCESSLIST;
SHOW ENGINE INNODB STATUS;

-- PostgreSQL
SELECT * FROM pg_stat_activity WHERE state = 'active';
```

**Agent Recommendations:**
```
- Add missing indexes
- Optimize query
- Increase connection pool
- Add query caching
- Scale database
```

---

### 3. Connection Pool Timeout

**Problem:** Application can't get database connection

**Agent Detection:**
```
Alert: ConnectionPoolExhausted
Error: Cannot get connection from pool
Active Connections: 100/100 (max)
```

**Agent Fix:**
```javascript
// Node.js example
pool: {
    max: 200,  // Increased from 100
    min: 10,
    acquire: 60000,
    idle: 10000
}
```

```python
# Python example
DATABASES = {
    'default': {
        'CONN_MAX_AGE': 600,
        'OPTIONS': {
            'MAX_CONNS': 200
        }
    }
}
```

---

## Server Performance

### 1. High CPU Usage

**Problem:** CPU usage above 80%

**Agent Detection:**
```
Alert: HighCPU
CPU Usage: 95%
Top Process: nginx/apache/node
```

**Agent Analysis:**
```bash
# Find CPU hogs
top -b -n 1 | head -20
ps aux --sort=-%cpu | head -10

# Check specific process
pidstat -u -p <PID> 1 10
```

**Agent Fix:**
```bash
# If single process causing issue
# Restart the service
systemctl restart nginx

# If too many workers
# Reduce worker processes in config

# If application issue
# Agent notifies team for code optimization
```

---

### 2. High Memory Usage

**Problem:** Memory usage above 80%

**Agent Detection:**
```
Alert: HighMemory
Memory Usage: 90%
Swap Usage: 50%
```

**Agent Analysis:**
```bash
# Check memory consumers
ps aux --sort=-%mem | head -10
free -h

# Check for memory leaks
top -b -n 1 -o %MEM | head -20
```

**Agent Fix:**
```bash
# Clear cache (safe)
sync && echo 3 > /proc/sys/vm/drop_caches

# Restart memory-hogging service
systemctl restart <service>

# If chronic issue, agent recommends:
# - Add more memory
# - Fix memory leaks in code
# - Add swap space
```

---

### 3. Disk I/O Bottleneck

**Problem:** Slow disk performance

**Agent Detection:**
```
Alert: HighDiskIO
Disk Utilization: 95%
I/O Wait: 40%
```

**Agent Analysis:**
```bash
# Check disk I/O
iostat -x 1 10

# Find processes doing I/O
iotop -o

# Check disk usage
df -h
du -sh /* | sort -h
```

**Agent Recommendations:**
```
- Move to faster storage (SSD)
- Optimize database queries
- Add caching layer (Redis)
- Clean up old logs
```

---

## SSL/TLS Issues

### 1. SSL Certificate Expired

**Problem:** HTTPS not working due to expired certificate

**Agent Detection:**
```
Alert: SSLCertificateExpired
Certificate: example.com
Expiry Date: Yesterday
```

**Agent Fix (if Let's Encrypt):**
```bash
# Renew certificate
certbot renew --force-renewal

# Reload web server
systemctl reload nginx

# Verify
curl -I https://example.com
openssl s_client -connect example.com:443 -servername example.com
```

**Agent Notification:**
```
If manual certificate renewal needed:
- Email sent to SRE team
- Instructions provided
- Deadline highlighted
```

---

### 2. SSL Certificate Mismatch

**Problem:** Certificate doesn't match domain

**Agent Detection:**
```
Alert: SSLMismatch
Certificate: *.example.com
Domain: api.different.com
```

**Agent Recommendations:**
```
- Obtain correct certificate
- Update DNS
- Use wildcard certificate
- Add SAN (Subject Alternative Name)
```

---

## Load Balancer Problems

### 1. Backend Unhealthy

**Problem:** Load balancer marks backend as unhealthy

**Agent Detection:**
```
Alert: LoadBalancerBackendDown
Backend: web-server-01
Health Check: Failed
```

**Agent Fix:**
```bash
# Check backend service
systemctl status nginx

# Restart if needed
systemctl restart nginx

# Verify health endpoint
curl http://backend-ip/health

# Check network connectivity
ping backend-ip
telnet backend-ip 80
```

---

### 2. Uneven Load Distribution

**Problem:** One server getting all traffic

**Agent Detection:**
```
Alert: UnbalancedLoad
Server1: 1000 req/s
Server2: 10 req/s
```

**Agent Analysis:**
```
Check load balancer algorithm:
- Round Robin
- Least Connections
- IP Hash
```

**Agent Recommendations:**
```
- Verify all backends healthy
- Check load balancer config
- Ensure servers have same capacity
- Review session affinity settings
```

---

## Database Connection Issues

> **Security note:** Direct database access is **optional and disabled by default**.
> Set `ENABLE_DATABASE_COLLECTION=true` in `.env` only if your security team approves.
>
> With the default (`false`), the agent will **not** query RDS, Cloud SQL, Azure SQL, DynamoDB,
> Cosmos DB, Redis, or ElastiCache. It can still help with:
> - Application connection pool settings
> - Service restarts and scaling
> - Network / firewall / timeout issues
> - Notifying your DBA team with manual steps

### 1. Too Many Connections

**Problem:** Database refuses new connections

**Agent Detection:**
```
Alert: DatabaseConnectionLimit
Error: Too many connections
Current: 151/150 (max)
```

**Agent Fix (when ENABLE_DATABASE_COLLECTION=true only):**
```sql
-- MySQL: Increase max connections
SET GLOBAL max_connections = 300;

-- Make permanent in /etc/mysql/my.cnf
[mysqld]
max_connections = 300

-- Restart MySQL
systemctl restart mysql
```

```postgresql
-- PostgreSQL: Increase max connections
-- Edit /etc/postgresql/13/main/postgresql.conf
max_connections = 300

-- Restart PostgreSQL
systemctl restart postgresql
```

---

### 2. Connection Leak

**Problem:** Application not closing connections

**Agent Detection:**
```
Alert: ConnectionLeak
Open Connections: Steadily increasing
Timeouts: Frequent
```

**Agent Analysis:**
```sql
-- MySQL: Show open connections
SHOW FULL PROCESSLIST;

-- PostgreSQL: Show connections
SELECT * FROM pg_stat_activity;
```

**Agent Recommendations:**
```
- Fix application code to close connections
- Set connection timeout
- Use connection pooling
- Restart application to clear
```

---

## Disk Space Problems

### 1. Disk Full

**Problem:** Disk usage at 100%

**Agent Detection:**
```
Alert: DiskFull
Usage: 100%
Partition: /var
```

**Agent Fix:**
```bash
# Find large files
du -sh /* | sort -h | tail -10
du -sh /var/* | sort -h | tail -10

# Clean common culprits
# 1. Old logs
find /var/log -type f -name "*.log" -mtime +30 -delete
journalctl --vacuum-time=7d

# 2. Package cache (safe)
apt-get clean          # Ubuntu/Debian
yum clean all          # RHEL/CentOS

# 3. Docker images/containers
docker system prune -a

# 4. Old kernels (Ubuntu/Debian)
apt-get autoremove --purge

# 5. Temp files
rm -rf /tmp/*
rm -rf /var/tmp/*
```

**Agent NEVER does (sends email instead):**
```
- rm -rf on user data
- Delete database files
- Remove application files
- Format partitions
```

---

### 2. Log Files Growing

**Problem:** Log files consuming disk space

**Agent Detection:**
```
Alert: LogFilesGrowing
File: /var/log/nginx/access.log
Size: 50GB
```

**Agent Fix:**
```bash
# Rotate logs immediately
logrotate -f /etc/logrotate.conf

# Configure log rotation
# /etc/logrotate.d/nginx
/var/log/nginx/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}

# For application logs
# Add to /etc/logrotate.d/myapp
/var/www/myapp/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

---

## Memory Issues

### 1. Out of Memory (OOM)

**Problem:** Process killed by OOM killer

**Agent Detection:**
```
Alert: OOMKilled
Process: nginx/java/node
Reason: Out of memory
```

**Agent Analysis:**
```bash
# Check OOM events
dmesg | grep -i "out of memory"
grep -i "out of memory" /var/log/kern.log

# Check memory usage
free -h
ps aux --sort=-%mem | head -10

# Check for memory leaks
top -b -n 1 -o %MEM
```

**Agent Fix:**
```bash
# Restart affected service
systemctl restart <service>

# If Java application, reduce heap
export JAVA_OPTS="-Xmx2g -Xms512m"

# If Node.js, increase limit
node --max-old-space-size=4096 app.js

# Long-term recommendations:
# - Add more RAM
# - Fix memory leaks
# - Optimize application
# - Add swap space
```

---

### 2. Swap Thrashing

**Problem:** System using swap heavily, very slow

**Agent Detection:**
```
Alert: SwapThrashing
Swap Usage: 95%
I/O Wait: High
System: Unresponsive
```

**Agent Analysis:**
```bash
# Check swap usage
free -h
swapon -s

# Check processes
ps aux --sort=-%mem | head -10
```

**Agent Recommendations:**
```
Immediate:
- Kill non-critical processes
- Restart services

Long-term:
- Add more RAM
- Optimize application memory usage
- Reduce memory-hungry services
```

---

## Common Scenarios

### Scenario 1: After Deployment

**Common Issues:**
- Service not restarted
- Configuration not reloaded
- Old cache not cleared
- Health check fails

**Agent Actions:**
```bash
# Restart service
systemctl restart nginx

# Clear cache
redis-cli FLUSHALL

# Verify health
curl http://localhost/health

# Check logs
tail -f /var/log/nginx/error.log
```

---

### Scenario 2: Traffic Spike

**Common Issues:**
- High CPU/Memory
- Connection pool exhausted
- Slow response times
- 503 errors

**Agent Actions:**
```bash
# Scale up workers
# Increase connection limits
# Enable caching
# Monitor closely

# If critical, agent emails:
"Traffic spike detected. Consider scaling horizontally."
```

---

### Scenario 3: Database Migration

**Common Issues:**
- Connection string wrong
- Permissions missing
- Schema mismatch
- Slow queries

**Agent Actions:**
```bash
# Test connectivity
mysql -h new-db-host -u user -p

# Verify schema
show tables;

# Check permissions
SHOW GRANTS FOR 'user'@'%';

# Monitor slow queries
```

---

## What the Agent WILL Do (Safe)

1. Restart services (nginx, apache, etc.)
2. Reload configurations
3. Clear cache (Redis, application cache)
4. Rotate logs
5. Clean package cache
6. Remove temporary files
7. Increase resource limits
8. Fix file permissions
9. Test configurations
10. Collect diagnostics

## What the Agent WILL NEVER Do (Dangerous)

1. Delete databases
2. Format disks
3. Remove user data
4. Delete production files
5. Drop tables
6. Truncate data
7. Recursive delete on root
8. Modify production data

**For dangerous operations, agent sends email with:**
- What needs to be done
- Why it's needed
- Manual commands to run
- Verification steps

---

## Example: Complete Fix Flow

### Problem: Nginx 502 Error

**1. Detection (5 seconds):**
```
Alert: Nginx502Error
Time: 2026-06-12 13:00:00
Source: Prometheus
Severity: High
```

**2. Analysis (10 seconds):**
```bash
# Agent collects:
- Nginx status: Running
- Error logs: "upstream timed out"
- Upstream service: PHP-FPM stopped
- Root cause: PHP-FPM crashed
```

**3. Fix (15 seconds):**
```bash
# Agent executes:
systemctl restart php-fpm
systemctl status php-fpm  # Verify
curl http://localhost/health  # Test
```

**4. Verification (5 minutes):**
```
- Immediate: Service running ✓
- 30s: Health check OK ✓
- 1m: No errors in logs ✓
- 5m: Stable, no restarts ✓
```

**5. Documentation (generated):**
- Runbook: "PHP-FPM Restart Procedure"
- Postmortem: "PHP-FPM Crash Analysis"
- KB Article: "Nginx 502 - Upstream Service Failure"

**Total Time: 5 minutes 30 seconds**
**Manual Time: 15-30 minutes**

---

## Benefits

### Time Saved

| Issue | Manual Time | Agent Time | Savings |
|-------|-------------|------------|---------|
| Service Restart | 15 min | 30 sec | 14.5 min |
| Config Error | 30 min | 2 min | 28 min |
| Disk Cleanup | 20 min | 1 min | 19 min |
| Timeout Fix | 25 min | 3 min | 22 min |
| Memory Issue | 40 min | 5 min | 35 min |

**Average: 70% time savings per incident**

### DevOps Focus

**Before Agent:**
- 60% time on repetitive tasks
- 40% time on complex problems

**After Agent:**
- 20% time on simple tasks (review)
- 80% time on complex problems

---

## Configure and Connect

After installation, connect monitoring systems and upload org runbooks.

### 1. Set organization and storage

```bash
# .env
ORG_ID=acme-corp
STORAGE_PROVIDER=s3          # or minio, gcs, azure, memory
STORAGE_BUCKET=devops-agent
```

### 2. Upload org runbooks

```bash
curl -X POST http://$AGENT_URL/orgs/acme-corp/docs \
  -H "Content-Type: application/json" \
  -d '{"path":"runbooks/k8s-oom.md","content":"# OOM runbook\n..."}'
```

### 3. Connect Prometheus Alertmanager

```yaml
receivers:
  - name: devops-ai-agent
    webhook_configs:
      - url: 'http://devops-agent:8000/webhook/alertmanager'
        send_resolved: true
```

Add labels for org and remote host:

```yaml
labels:
  org_id: acme-corp
  host: ubuntu@10.0.1.50   # for centralized SSH to EC2
```

### 4. Connect GitHub Actions

Repository → Settings → Webhooks:

- URL: `https://agent.company.com/webhook/github`
- Events: Workflow runs
- Header: `X-Org-ID: acme-corp` (if supported) or set `GITHUB_ORG` in `.env`

### 5. Centralized agent — SSH to remote servers

On the agent server:

```bash
ssh-copy-id ubuntu@target-ec2-ip
ssh ubuntu@target-ec2-ip 'docker ps'   # must work without password
```

Trigger with `"host": "ubuntu@target-ec2-ip"` in webhook body.

### 6. Review agent activity

```bash
# Org-scoped audit (persistent in cloud storage)
curl "http://localhost:8000/audit?org_id=acme-corp" | python3 -m json.tool

# Agent process logs
tail -f logs/agent.log

# List uploaded org docs
curl http://localhost:8000/orgs/acme-corp/docs
```

---

## Safety Guarantees

1. **No Data Loss**
   - Never deletes user data
   - Never drops databases
   - Never formats disks

2. **Email Before Danger**
   - All risky operations require approval
   - Clear instructions provided
   - Manual commands given

3. **Complete Audit Trail**
   - Every action logged
   - Every decision documented
   - Full traceability

4. **Verification Required**
   - Every fix is verified
   - Success rate tracked
   - Rollback if failure

---

## Documentation Index

| Topic | Document |
|-------|----------|
| **Quick start** | [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) |
| **API reference** | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| **API testing (Postman)** | [docs/API_TESTING.md](docs/API_TESTING.md) |
| **Centralized deployment** | [docs/CENTRALIZED_DEPLOYMENT.md](docs/CENTRALIZED_DEPLOYMENT.md) |
| **EC2 + Docker E2E test** | [docs/E2E_EC2_DOCKER_TEST.md](docs/E2E_EC2_DOCKER_TEST.md) |
| **Escalation & ticketing** | [docs/ESCALATION.md](docs/ESCALATION.md) |
| **Security** | [SECURITY_GUARANTEES.md](SECURITY_GUARANTEES.md) |
| **Deployment** | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| **Build Docker/package** | [docs/BUILD_AND_USAGE.md](docs/BUILD_AND_USAGE.md) |
| **Platform support** | [docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md) |
| **Organization rollout** | [docs/ORGANIZATIONAL_GUIDE.md](docs/ORGANIZATIONAL_GUIDE.md) |
| **Architecture** | [ARCHITECTURE.md](ARCHITECTURE.md) |
| **All docs** | [docs/README.md](docs/README.md) |
| **Postman collection** | [postman/](postman/) |

---

## Support

**Questions?**
- [README.md](README.md) — project overview
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — 15-minute setup
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) — all endpoints
- [SECURITY_GUARANTEES.md](SECURITY_GUARANTEES.md) — safety before production

**Need help?**
- Check `GET /audit?org_id=` for incident history
- Review escalation entries (`escalated: true` in audit)
- Contact your DevOps/SRE team

---

**Let the AI handle simple tasks. Your team focuses on complex problems.**

---

Last Updated: June 17, 2026
