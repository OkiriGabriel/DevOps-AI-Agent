# Integration tests

These tests require live credentials and real cloud/Kubernetes infrastructure.
They are **not** run in CI — execute them manually in a configured environment.

## Prerequisites

- `ANTHROPIC_API_KEY` — Anthropic API key
- `GITHUB_TOKEN` — GitHub personal access token
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — for S3 tests
- `GCP_PROJECT_ID` + Application Default Credentials — for GCS tests
- `AZURE_STORAGE_CONNECTION_STRING` — for Azure tests
- A reachable Kubernetes cluster (`~/.kube/config` or `KUBECONFIG`)

## Running

```bash
pytest tests/integration/ -v
```
