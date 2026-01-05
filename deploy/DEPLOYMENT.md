# Cloud Deployment Guide

## Quick Start Options

### 1. Local Docker (Development)

```bash
# Build and run
docker-compose build
docker-compose run browser-agent learn https://example.com

# Or run interactively
docker-compose run browser-agent sessions
```

### 2. Google Cloud Run (Serverless)

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Create secrets
gcloud secrets create llm-api-key --data-file=- <<< "sk-your-key"
gcloud secrets create email-api-key --data-file=- <<< "re_your-key"

# Build and deploy
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/browser-learning-agent
gcloud run deploy browser-agent --image gcr.io/YOUR_PROJECT_ID/browser-learning-agent --region us-central1

# Invoke
gcloud run jobs execute browser-agent --args="learn,https://example.com"
```

### 3. AWS ECS Fargate

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Create repository
aws ecr create-repository --repository-name browser-learning-agent

# Build and push
docker build -t browser-learning-agent .
docker tag browser-learning-agent:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/browser-learning-agent:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/browser-learning-agent:latest

# Create secrets in AWS Secrets Manager
aws secretsmanager create-secret --name browser-agent/llm-api-key --secret-string "sk-your-key"
aws secretsmanager create-secret --name browser-agent/email-api-key --secret-string "re_your-key"

# Register task definition
aws ecs register-task-definition --cli-input-json file://deploy/ecs-task.json

# Run task
aws ecs run-task --cluster your-cluster --task-definition browser-learning-agent --launch-type FARGATE
```

### 4. Fly.io (Simple PaaS)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Initialize
fly launch --no-deploy

# Set secrets
fly secrets set LLM_API_KEY=sk-your-key EMAIL_API_KEY=re_your-key

# Deploy
fly deploy

# Run learning task
fly ssh console -C "python -m src.main learn https://example.com"
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | No | `anthropic` | `anthropic` or `openai` |
| `LLM_API_KEY` | **Yes** | - | API key for LLM provider |
| `LLM_MODEL` | No | `claude-sonnet-4-20250514` | Model to use |
| `EMAIL_PROVIDER` | No | `resend` | Email service provider |
| `EMAIL_API_KEY` | **Yes** | - | Email service API key |
| `NOTIFICATION_EMAIL` | No | `caique.rivero@gmail.com` | Where to send notifications |
| `HEADLESS` | No | `true` (cloud) | Run browser headlessly |
| `MAX_ITERATIONS` | No | `100` | Max learning iterations |
| `CONFIDENCE_THRESHOLD` | No | `0.85` | When to stop learning |

## Scaling Considerations

### Memory Requirements
- Minimum: 2GB RAM (Chromium + LLM responses)
- Recommended: 4GB RAM for complex sites

### CPU Requirements
- Minimum: 1 vCPU
- Recommended: 2 vCPUs for faster page rendering

### Storage
- Session data: ~1-5MB per session
- Screenshots: ~100KB-1MB each
- Mount persistent volume for data retention

### Timeouts
- Set container timeout to 15+ minutes for thorough learning
- Cloud Run: `timeoutSeconds: 900`
- ECS: Configure service with appropriate `stoppingTimeout`

## Security Best Practices

1. **Never commit API keys** - Use secrets management
2. **Run headless in production** - Set `HEADLESS=true`
3. **Limit network egress** - Allowlist only required domains
4. **Use private subnets** - Deploy containers in VPC
5. **Enable logging** - Collect logs for debugging
