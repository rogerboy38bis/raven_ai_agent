# Raven AI Agent - Deployment Guide

This document provides comprehensive deployment instructions for the Raven AI Agent system, covering three environments, rollout strategies, and rollback procedures.

## Table of Contents

1. [Environment Overview](#environment-overview)
2. [Environment Configuration](#environment-configuration)
3. [Prerequisites](#prerequisites)
4. [Deployment Procedures](#deployment-procedures)
5. [Rollout Strategy](#rollout-strategy)
6. [Rollback Procedures](#rollback-procedures)
7. [Post-Deployment Verification](#post-deployment-verification)
8. [Known Issues](#known-issues)

---

## Environment Overview

The Raven AI Agent system consists of three primary environments:

| Environment | Purpose | URL | Database |
|-------------|---------|-----|----------|
| Development | Local development and testing | localhost:8000 | Local Frappe bench |
| Staging | Pre-production validation | staging.erp.sysmayal2.cloud | Staging DB |
| Production | Live production system | erp.sysmayal2.cloud | Production DB |

### Component Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Alexa Skill  │────▶│  Frappe Bench    │────▶│   ERPNext      │
│  (Voice Input) │     │ (raven_ai_agent)│     │  (ERP System)  │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │  Raven Channel   │
                        │ (Message Output) │
                        └──────────────────┘
```

### Environment Tiers

| Tier | Component | Description |
|------|-----------|-------------|
| Frontend | Alexa Custom Skill | Voice interface for users |
| Middleware | Frappe Bench + raven_ai_agent | Core processing logic |
| Backend | ERPNext | ERP database and business logic |
| LLM | OpenAI / Claude | AI decision making |

---

## Environment Configuration

### Development Environment

**Location:** Local machine running Frappe bench

```bash
# Directory structure
~/frappe-bench/
├── apps/
│   └── raven_ai_agent/     # Development copy
├── sites/
│   └── dev.site.com/       # Development site
└── .env                    # Development environment variables
```

**Configuration:**

```bash
# Environment variables (.env)
FRAPPE_SITE=dev.site.com
ALEXA_VERIFY_TOKEN=dev_verify_token
LLM_PROVIDER=openai
LLM_API_KEY=sk-dev-xxxxx
ALEXA_MODE=development
LOG_LEVEL=DEBUG
RATE_LIMIT_PER_MINUTE=10
```

**Features:**
- Debug logging enabled
- Relaxed rate limiting
- Test Alexa payloads accepted
- Full error stack traces
- Local file-based logging

### Staging Environment

**Location:** Staging server at staging.erp.sysmayal2.cloud

```bash
# Directory structure
/staging/frappe-bench/
├── apps/
│   └── raven_ai_agent/     # Staging copy
├── sites/
│   └── staging.erp.sysmayal2.cloud/
└── .env                    # Staging environment variables
```

**Configuration:**

```bash
# Environment variables
FRAPPE_SITE=staging.erp.sysmayal2.cloud
ALEXA_VERIFY_TOKEN=staging_verify_token
LLM_PROVIDER=openai
LLM_API_KEY=sk-stag-xxxxx
ALEXA_MODE=staging
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=30
```

**Features:**
- Production-like configuration
- Real ERPNext staging data (sanitized)
- Full logging to staging logs
- Slack/email alerts enabled
- Performance monitoring active

### Production Environment

**Location:** Production server at erp.sysmayal2.cloud

```bash
# Directory structure
/prod/frappe-bench/
├── apps/
│   └── raven_ai_agent/     # Production copy
├── sites/
│   └── erp.sysmayal2.cloud/
└── .env                    # Production environment variables
```

**Configuration:**

```bash
# Environment variables (.env)
FRAPPE_SITE=erp.sysmayal2.cloud
ALEXA_VERIFY_TOKEN=prod_verify_token_secure
LLM_PROVIDER=openai
LLM_API_KEY=sk-prod-xxxxx
ALEXA_MODE=production
LOG_LEVEL=WARNING
RATE_LIMIT_PER_MINUTE=100
ALEXA_AUTH_ENABLED=true
SAFETY_GUARDRAILS_ENABLED=true
```

**Features:**
- Strict rate limiting
- Full safety guardrails
- Audit logging enabled
- Minimal error exposure
- High availability configuration

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| RAM | 4 GB | 8 GB |
| CPU | 2 cores | 4 cores |
| Disk | 20 GB | 50 GB |
| Frappe Bench | v14+ | v15+ |

### Required Accounts and Keys

1. **Frappe/ERPNext Account**
   - Administrator access to the site
   - API key and secret for bench

2. **LLM Provider**
   - OpenAI API key (production) or
   - Anthropic Claude API key

3. **Alexa Developer**
   - Amazon Developer account
   - Custom Skill configuration
   - ASK CLI installed (for deployment)

4. **Monitoring (Optional)**
   - Sentry DSN for error tracking
   - Slack webhook for alerts

### Pre-Deployment Checklist

- [ ] All unit tests passing (86+ tests)
- [ ] Integration tests passing
- [ ] Safety guardrails verified
- [ ] Database backups verified
- [ ] Rollback plan documented
- [ ] Stakeholders notified
- [ ] Maintenance window scheduled

---

## Deployment Procedures

### Step 1: Pre-Deployment Verification

```bash
# Run full test suite
cd ~/frappe-bench/apps/raven_ai_agent
python -m pytest tests/ -v

# Expected: 0 failed, 84+ passed
```

### Step 2: Database Backup

```bash
# On Frappe bench
cd ~/frappe-bench

# Create database backup
bench --site erp.sysmayal2.cloud backup --with-files

# Verify backup location
ls -la ~/frappe-bench/sites/erp.sysmayal2.cloud/private/backups/
```

### Step 3: Pull Latest Code

```bash
cd ~/frappe-bench/apps/raven_ai_agent

# Fetch latest changes
git fetch origin
git checkout v11.0.0-clean
git pull origin v11.0.0-clean

# Verify version
git log --oneline -1
```

### Step 4: Install Dependencies

```bash
cd ~/frappe-bench/apps/raven_ai_agent

# Install any new Python dependencies
pip install -r requirements.txt

# Clear cache
bench --site erp.sysmayal2.cloud clear-cache
```

### Step 5: Run Database Migrations

```bash
cd ~/frappe-bench

# Run any pending migrations
bench --site erp.sysmayal2.cloud migrate

# Verify app is installed
bench --site erp.sysmayal2.cloud list-apps
```

### Step 6: Restart Services

```bash
cd ~/frappe-bench

# Restart workers
bench restart

# Verify services
bench status
```

### Step 7: Post-Deployment Tests

```bash
# Run health check script
python scripts/health_check.py --env production

# Verify Alexa endpoint
curl -X POST https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "alexa_verify_token": "..."}'
```

---

## Rollout Strategy

### Canary Deployment (Recommended)

The recommended rollout strategy uses a canary approach to minimize risk:

```
Week 1: 10% of traffic ──────────────────────────▶
Week 2: 25% of traffic ────────────────────────────▶
Week 3: 50% of traffic ─────────────────────────────▶
Week 4: 100% of traffic ──────────────────────────────▶
```

#### Phase 1: Internal Testing (10%)

1. Deploy to staging
2. Enable for internal Alexa users only
3. Monitor error rates and latency
4. Collect feedback from internal users

**Success Criteria:**
- Error rate < 1%
- P95 latency < 10 seconds
- No critical errors in logs

#### Phase 2: Limited Production (25%)

1. Deploy to production
2. Enable for 25% of production users
3. Continue monitoring
4. Prepare rollback plan

**Success Criteria:**
- Error rate < 0.5%
- P95 latency < 8 seconds
- No data corruption or lost messages

#### Phase 3: Expanded Rollout (50%)

1. Expand to 50% of users
2. Enable full monitoring
3. Continue error tracking

**Success Criteria:**
- Error rate < 0.2%
- P95 latency < 8 seconds
- User satisfaction maintained

#### Phase 4: Full Production (100%)

1. Deploy to all users
2. Monitor for 48 hours
3. Document any issues

**Success Criteria:**
- Error rate < 0.1%
- P95 latency < 8 seconds
- Full operational stability

### Blue-Green Deployment (Alternative)

For environments requiring instant rollback capability:

1. **Blue Environment:** Current production
2. **Green Environment:** New version

```
[Traffic] ─▶ [Blue v1]     [Green v2 - inactive]
                    │
                    ▼ (if v2 healthy)
              Switch traffic ─▶
```

**Procedure:**

```bash
# Deploy to green environment
cd ~/frappe-bench-green
git pull origin v11.0.0-clean
bench --site green.erp.sysmayal2.cloud migrate

# Test green environment
curl https://green.erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven

# Switch traffic (DNS or load balancer)
# Monitor green environment

# If issues: Switch back to blue
# If healthy: Deploy to blue, retire green
```

### Feature Flags

For granular control over specific features:

```python
# In raven_ai_agent/hooks.py or configuration
FEATURE_FLAGS = {
    "enable_new_workflow": False,
    "enable_llm_v2": False,
    "enable_advanced_safety": True,
    "enable_websocket_realtime": False,  # Known issue - disabled
}
```

---

## Rollback Procedures

### Automatic Rollback Triggers

Rollback should be triggered automatically if any of these conditions are met:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Error Rate | > 5% for 5 min | Alert + Review |
| Error Rate | > 10% for 1 min | Auto-rollback |
| P95 Latency | > 30 seconds | Alert + Review |
| Failed Requests | > 50 in 1 min | Auto-rollback |
| Database Errors | Any | Alert + Review |

### Manual Rollback Procedure

#### Step 1: Confirm Rollback Need

```bash
# Check error rates
tail -n 1000 ~/frappe-bench/logs/worker.error.log | grep ERROR

# Check response times
curl -w "%{time_total}s" -o /dev/null -s https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven
```

#### Step 2: Stop Incoming Traffic (Optional)

```bash
# Disable Alexa skill in Amazon Developer Console
# OR set maintenance mode in Frappe
bench --site erp.sysmayal2.cloud set-maintenance-mode on
```

#### Step 3: Revert Code

```bash
cd ~/frappe-bench/apps/raven_ai_agent

# Find last known good version
git log --oneline --all | head -20

# Revert to previous version (e.g., v11.0.0-clean~1)
git checkout v11.0.0-clean~1
git checkout -b hotfix/rollback-vX.X.X

# Or use git revert for specific commits
git revert <commit-hash>
```

#### Step 4: Restore Database (If Needed)

```bash
# List available backups
ls -la ~/frappe-bench/sites/erp.sysmayal2.cloud/private/backups/

# Restore from backup
bench --site erp.sysmayal2.cloud backup/restore \
  /path/to/backup-file.sql.gz
```

#### Step 5: Restart Services

```bash
cd ~/frappe-bench
bench restart

# Clear any cached data
bench --site erp.sysmayal2.cloud clear-cache
```

#### Step 6: Verify Rollback

```bash
# Check version
cd ~/frappe-bench/apps/raven_ai_agent
git log --oneline -1

# Run tests
python -m pytest tests/ -v

# Test endpoint
curl -X POST https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -H "Content-Type: application/json" \
  -d '{"text": "test"}'
```

### Rollback Decision Matrix

| Issue Severity | Description | Rollback Timeframe |
|----------------|-------------|-------------------|
| Critical | Data loss, security breach | Immediate |
| High | >10% error rate, system down | < 15 minutes |
| Medium | 5-10% error rate, degraded | < 1 hour |
| Low | Minor issues, workaround available | Next maintenance window |

---

## Post-Deployment Verification

### Health Check Script

Run the health check script after deployment:

```bash
python scripts/health_check.py --env production
```

Expected output:
```
=== Raven AI Agent Health Check ===
Timestamp: 2024-01-15T10:30:00Z
Environment: production

✓ Frappe API: OK (200)
✓ Raven Bot: OK (responding)
✓ LLM Endpoint: OK (latency: 1.2s)
⚠ WebSocket: DEGRADED (intermittent)

Overall Status: HEALTHY (with known issue)
```

### Smoke Tests

```bash
# Test 1: Alexa endpoint
curl -X POST https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat ~/.frappe_token)" \
  -d '{"text": "what is the status of sales order SO-001"}'

# Test 2: Sales order creation
curl -X POST https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat ~/.frappe_token)" \
  -d '{"text": "create sales order for test customer"}'

# Test 3: Safety guardrails
curl -X POST https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat ~/.frappe_token)" \
  -d '{"text": "delete all sales orders"}'
```

### Monitoring Dashboard

Access the monitoring dashboard at:
- **Production:** https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.get_dashboard

Key metrics to monitor:
- Request count per hour
- Success/failure ratio
- Average response time
- LLM token usage
- Error breakdown by type

---

## Known Issues

### WebSocket Realtime Events

**Issue:** WebSocket realtime events intermittently fail in production.

**Impact:** Users may not receive real-time updates on Raven channel.

**Workaround:** Messages are still delivered; realtime updates are optional.

**Status:** Known issue - documented in [MONITORING_ALERTING.md](./MONITORING_ALERTING.md)

**Troubleshooting:**
```bash
# Check WebSocket service
bench --site erp.sysmayal2.cloud补充
```

### Rate Limiting on Staging

**Issue:** Staging environment may hit rate limits during testing.

**Impact:** Requests may be rejected during load testing.

**Workaround:** Adjust RATE_LIMIT_PER_MINUTE in staging config.

---

## Contact Information

| Role | Contact | Escalation |
|------|---------|------------|
| On-Call Dev | Internal Slack #raven-support | - |
| DevOps Lead | devops@company.com | 2nd line |
| Security | security@company.com | Critical issues |

---

## Appendix: Quick Reference

### Common Commands

```bash
# Deploy new version
git pull && bench restart

# Check status
bench status

# View logs
tail -f ~/frappe-bench/logs/worker.log

# Rollback
git checkout <previous-tag> && bench restart
```

### Version Tags

Use semantic versioning:
- v11.0.0-clean - Current stable
- v11.0.1-hotfix - Bug fix release
- v12.0.0-beta - Major update

---

*Last Updated: 2024-01-15*
*Version: 1.0*
*Maintainer: Development Team*
