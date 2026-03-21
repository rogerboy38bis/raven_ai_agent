# Raven AI Agent - Monitoring and Alerting Guide

This document provides comprehensive monitoring and alerting guidelines for the Raven AI Agent system, including Frappe/middleware/LLM monitoring, alert thresholds, and troubleshooting for known issues.

## Table of Contents

1. [Monitoring Overview](#monitoring-overview)
2. [Frappe Monitoring](#frappe-monitoring)
3. [Middleware Monitoring](#middleware-monitoring)
4. [LLM Monitoring](#llm-monitoring)
5. [WebSocket Monitoring](#websocket-monitoring)
6. [Alert Thresholds](#alert-thresholds)
7. [Alert Configuration](#alert-configuration)
8. [Known Issues](#known-issues)
9. [Troubleshooting Guide](#troubleshooting-guide)

---

## Monitoring Overview

### System Architecture and Monitoring Points

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RAVEN AI AGENT MONITORING                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐              │
│  │    Alexa    │     │   Frappe     │     │   ERPNext    │              │
│  │   Skill     │────▶│    Bench     │────▶│   Database   │              │
│  │  (External) │     │ (Middleware) │     │   (Backend)  │              │
│  └──────────────┘     └──────┬───────┘     └──────────────┘              │
│                              │                                             │
│                              ▼                                             │
│                      ┌──────────────┐                                     │
│                      │     LLM      │                                     │
│                      │  (OpenAI/    │                                     │
│                      │   Claude)    │                                     │
│                      └──────────────┘                                     │
│                              │                                             │
│                              ▼                                             │
│                      ┌──────────────┐     ┌──────────────┐              │
│                      │   WebSocket │     │    Raven     │              │
│                      │   (Realtime)│────▶│   Channel    │              │
│                      └──────────────┘     └──────────────┘              │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  MONITORING Tiers:                                                        │
│  • Frappe API     - Request/Response monitoring                           │
│  • Middleware     - Business logic, agent execution                        │
│  • LLM            - API calls, tokens, latency                             │
│  • WebSocket      - Real-time message delivery                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Metrics Categories

| Category | Metrics | Priority |
|----------|---------|----------|
| Availability | Uptime, endpoint health | Critical |
| Performance | Latency, throughput | High |
| Reliability | Error rate, success rate | Critical |
| Usage | Request count, token usage | Medium |
| Safety | Blocked requests, guardrail triggers | High |

---

## Frappe Monitoring

### API Endpoint Monitoring

The Frappe API serves as the primary entry point for Alexa requests.

#### Monitored Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/method/raven_ai_agent.api.alexa_to_raven` | POST | Main Alexa entry point |
| `/api/method/raven_ai_agent.api.get_dashboard` | GET | Dashboard data |
| `/api/method/raven_ai_agent.api.health_check` | GET | Health check |

#### Configuration

```python
# In raven_ai_agent/hooks.py or monitoring config
FRAPPE_MONITORING = {
    "enabled": True,
    "log_requests": True,
    "log_responses": True,
    "log_level": "INFO",
    "slow_request_threshold": 5.0,  # seconds
}
```

#### Metrics Collection

```bash
# Check Frappe request logs
tail -f ~/frappe-bench/logs/web.log | grep raven_ai_agent

# Check worker logs
tail -f ~/frappe-bench/logs/worker.log | grep raven_ai_agent

# Monitor specific endpoint
curl -w "%{http_code}\n%{time_total}s\n" \
  https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -X POST -H "Content-Type: application/json" -d '{}'
```

### Database Monitoring

Monitor database performance and health for the raven_ai_agent tables.

#### Key Tables to Monitor

| Table | Purpose | Monitor For |
|-------|---------|-------------|
| `tabRaven Message` | Message storage | Write latency |
| `tabRaven CI` | Channel integration | Query performance |
| `tabRaven AI Settings` | Configuration | Access patterns |
| `tabRaven User` | User mapping | Growth |

#### Query Performance

```sql
-- Check slow queries on Raven tables
SELECT
    name,
    modified,
    AVG(DATEDIFF(second, creation, modified)) as avg_processing_time
FROM tabRaven Message
WHERE creation > DATEADD(day, -1, GETDATE())
GROUP BY name, modified
ORDER BY avg_processing_time DESC;

-- Check message backlog
SELECT COUNT(*) as pending_messages
FROM tabRaven Message
WHERE
    creation > DATEADD(hour, -1, GETDATE())
    AND (content IS NULL OR content = '');
```

### Bench Services Monitoring

```bash
# Check bench status
bench status

# Check Redis queue
redis-cli -h localhost -p 12397 info | grep raven

# Check socketio connections
curl -s http://localhost:9000/socket.io/ | head -20
```

---

## Middleware Monitoring

### Agent Execution Monitoring

The middleware layer handles agent orchestration and business logic.

#### Agent Performance Metrics

| Metric | Description | Normal Range |
|--------|-------------|--------------|
| Agent Execution Time | Time from request to response | 1-10 seconds |
| Agent Success Rate | Percentage of successful executions | > 95% |
| Agent Retry Count | Number of retries per execution | 0-2 |
| Tool Call Success | Percentage of successful tool calls | > 90% |

#### Logging Configuration

```python
# In agent code for detailed logging
import logging
import time

logger = logging.getLogger(__name__)

def execute_agent(request):
    start_time = time.time()
    logger.info(f"Agent execution started: {request.id}")
    
    try:
        result = agent.process(request)
        execution_time = time.time() - start_time
        
        logger.info(
            f"Agent execution completed",
            extra={
                "request_id": request.id,
                "execution_time": execution_time,
                "success": True
            }
        )
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(
            f"Agent execution failed",
            extra={
                "request_id": request.id,
                "execution_time": execution_time,
                "error": str(e)
            }
        )
        raise
```

#### Middleware Health Checks

```bash
# Test agent responsiveness
curl -X POST https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven \
  -H "Content-Type: application/json" \
  -d '{"text": "help"}' \
  -w "\nHTTP Status: %{http_code}\nTime: %{time_total}s\n"

# Check agent logs
tail -f ~/frappe-bench/logs/worker.log | grep -E "(ERROR|WARN|raven)"
```

### Rate Limiting Monitoring

```python
# Rate limiter configuration
RATE_LIMIT_CONFIG = {
    "default_limit": 100,  # requests per minute
    "development_limit": 10,
    "staging_limit": 30,
    "production_limit": 100,
}

# Monitor rate limit headers
curl -I https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 95
# X-RateLimit-Reset: 1640995200
```

---

## LLM Monitoring

### API Call Monitoring

Monitor all LLM API calls for performance, cost, and quality.

#### Key LLM Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| API Latency | Time for LLM API response | < 5 seconds |
| Token Count | Input + Output tokens | Configurable |
| API Cost | Cost per request | Budget tracking |
| Error Rate | Failed API calls | < 1% |
| Rate Limit Hits | Times rate limit reached | < 5% |

#### OpenAI Monitoring

```python
# In LLM client code
import openai
import time
from datetime import datetime

class LLMMonitor:
    def __init__(self):
        self.metrics = []
    
    def call_llm(self, prompt, model="gpt-4"):
        start_time = time.time()
        
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            
            latency = time.time() - start_time
            tokens = response.usage.total_tokens
            
            self.metrics.append({
                "timestamp": datetime.utcnow().isoformat(),
                "model": model,
                "latency": latency,
                "tokens": tokens,
                "success": True,
                "cost": self.calculate_cost(tokens, model)
            })
            
            return response
            
        except Exception as e:
            latency = time.time() - start_time
            self.metrics.append({
                "timestamp": datetime.utcnow().isoformat(),
                "model": model,
                "latency": latency,
                "success": False,
                "error": str(e)
            })
            raise
    
    def calculate_cost(self, tokens, model):
        # Example cost calculation (update with current pricing)
        pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},  # per 1K tokens
            "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002}
        }
        return (tokens / 1000) * pricing.get(model, {}).get("input", 0)

llm_monitor = LLMMonitor()
```

#### LLM Cost Tracking

```bash
# Track daily LLM costs
grep -h "LLM" ~/frappe-bench/logs/*.log | \
  jq -s 'group_by(.date) | map({date: .[0].date, total_cost: (map(.cost) | add)})'

# Monitor token usage
tail -f ~/frappe-bench/logs/worker.log | grep "tokens"
```

#### Claude (Anthropic) Monitoring

```python
# Claude monitoring configuration
ANTHROPIC_CONFIG = {
    "model": "claude-3-sonnet-20240229",
    "max_tokens": 1024,
    "monitoring": {
        "log_prompts": True,
        "log_completions": False,  # Privacy
        "track_token_usage": True,
    }
}
```

---

## WebSocket Monitoring

### Realtime Message Delivery

WebSocket connections enable real-time message delivery to the Raven channel.

#### WebSocket Architecture

```
Client (Browser/App)
       │
       ▼ WebSocket
┌──────────────────┐
│  Frappe SocketIO │ ───▶ Message Queue ───▶ Raven Channel
│   (port 9000)    │
└──────────────────┘
       │
       ▼
  Event: "raven_message"
```

#### WebSocket Metrics

| Metric | Description | Normal Range |
|--------|-------------|--------------|
| Connection Count | Active WebSocket connections | 10-100 |
| Message Rate | Messages per second | 0-10 |
| Latency | Time from server to client | < 1 second |
| Reconnect Rate | Client reconnection frequency | < 5% |

#### WebSocket Health Check

```bash
# Check socketio service
curl -s http://localhost:9000/socket.io/ | head -5

# Check WebSocket upgrade
curl -I -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  https://erp.sysmayal2.cloud/socket.io/

# Monitor socketio logs
tail -f ~/frappe-bench/logs/socketio.log
```

---

## Alert Thresholds

### Critical Alerts (P1 - Immediate Response)

| Alert | Condition | Action |
|-------|-----------|--------|
| Service Down | Frappe API returns 5xx | Call on-call immediately |
| Error Rate Spike | > 10% errors for 1 minute | Investigate immediately |
| Database Unavailable | Cannot connect to DB | Call DBA immediately |
| LLM API Down | All LLM calls failing | Check API status |

### High Priority Alerts (P2 - Within 15 Minutes)

| Alert | Condition | Action |
|-------|-----------|--------|
| Error Rate Elevated | 5-10% errors for 5 minutes | Investigate |
| High Latency | P95 > 30 seconds for 5 min | Check system load |
| Rate Limit Exceeded | Rate limit hit > 10 times | Check for abuse |
| Disk Space Low | < 10% free | Clean up logs |

### Medium Priority Alerts (P3 - Within 1 Hour)

| Alert | Condition | Action |
|-------|-----------|--------|
| Latency Elevated | P95 > 15 seconds | Monitor |
| Error Rate Moderate | 1-5% errors | Investigate during business hours |
| LLM Cost Spike | > 150% of daily average | Review usage |
| WebSocket Degraded | Connection issues | Monitor |

### Low Priority Alerts (P4 - Next Business Day)

| Alert | Condition | Action |
|-------|-----------|--------|
| Usage Spike | > 120% of normal | Review trends |
| Warning in Logs | WARNING level logs > 10/min | Review during next day |
| Minor Errors | Non-critical errors < 5/hour | Weekly review |

### Performance Thresholds

| Metric | Green (OK) | Yellow (Warning) | Red (Critical) |
|--------|------------|------------------|----------------|
| API Latency (P95) | < 5s | 5-15s | > 15s |
| API Latency (P99) | < 10s | 10-30s | > 30s |
| Error Rate | < 1% | 1-5% | > 5% |
| Success Rate | > 99% | 95-99% | < 95% |
| LLM Latency | < 3s | 3-8s | > 8s |
| WebSocket Latency | < 500ms | 500ms-2s | > 2s |

---

## Alert Configuration

### Frappe Alert Setup

```python
# In raven_ai_agent/hooks.py or custom app
def get_alert_config():
    return {
        "email_recipients": [
            "devops@company.com",
            "raven-team@company.com"
        ],
        "slack_webhook": "https://hooks.slack.com/services/xxx",
        "alert_rules": [
            {
                "name": "High Error Rate",
                "condition": "error_rate > 0.1",  # 10%
                "duration": "1m",
                "severity": "critical",
                "action": "page_oncall"
            },
            {
                "name": "High Latency",
                "condition": "p95_latency > 30",
                "duration": "5m",
                "severity": "high",
                "action": "notify_team"
            }
        ]
    }
```

### Prometheus Metrics (Optional)

```python
# If using Prometheus
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
requests_total = Counter(
    'raven_requests_total',
    'Total requests',
    ['endpoint', 'status']
)

request_latency = Histogram(
    'raven_request_latency_seconds',
    'Request latency',
    ['endpoint']
)

# LLM metrics
llm_tokens_total = Counter(
    'raven_llm_tokens_total',
    'Total LLM tokens used',
    ['model']
)

# WebSocket metrics
websocket_connections = Gauge(
    'raven_websocket_connections',
    'Active WebSocket connections'
)
```

### Logging Alert Configuration

```python
import logging
import json
from logging.handlers import HTTPHandler

class AlertHandler(logging.Handler):
    def __init__(self, webhook_url):
        super().__init__()
        self.webhook_url = webhook_url
    
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            alert = {
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
                "timestamp": record.created
            }
            # Send to alert system
            self.send_alert(alert)

# Configure alert logger
alert_handler = AlertHandler("https://alerts.company.com/webhook")
alert_logger = logging.getLogger("raven_alerts")
alert_logger.addHandler(alert_handler)
alert_logger.setLevel(logging.ERROR)
```

---

## Known Issues

### WebSocket Realtime Events Intermittently Fail

**Issue ID:** KNOWN-001

**Description:** WebSocket realtime events intermittently fail in production, causing some users to not receive real-time updates on the Raven channel.

**Impact:** Medium - Messages are still delivered via REST API; realtime updates are optional enhancement.

**Affected Version:** v11.0.0+

**Workaround:** Messages are delivered reliably; users can refresh to see updates.

**Status:** Known issue - under investigation.

**Troubleshooting:**

```bash
# Check socketio service status
bench --site erp.sysmayal2.cloud socketio status

# Check socketio logs for errors
tail -f ~/frappe-bench/logs/socketio.log | grep -i error

# Restart socketio
bench --site erp.sysmayal2.cloud socketio restart

# Verify WebSocket connectivity
curl -v -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  https://erp.sysmayal2.cloud/socket.io/?EIO=4&transport=websocket
```

**Known Root Causes:**

1. High load on socketio server causing connection drops
2. Network latency between client and server
3. Browser/app WebSocket implementation issues
4. Frappe realtime module compatibility

**Recommended Actions:**

1. Monitor WebSocket connection stability
2. Implement client-side reconnection logic
3. Consider alternative realtime solutions if critical
4. Document in deployment guide

---

## Troubleshooting Guide

### Quick Diagnostics

```bash
#!/bin/bash
# Quick health check script

echo "=== Raven AI Agent Quick Diagnostics ==="
echo ""

echo "1. Checking Frappe API..."
curl -s -o /dev/null -w "Status: %{http_code}\n" \
  https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.alexa_to_raven

echo ""
echo "2. Checking worker status..."
bench status 2>&1 | grep -E "(worker|redis)"

echo ""
echo "3. Checking recent errors..."
tail -50 ~/frappe-bench/logs/worker.error.log | grep -E "(ERROR|CRITICAL)" | tail -5

echo ""
echo "4. Checking LLM connectivity..."
python3 -c "
import openai
openai.api_key = 'test'
try:
    openai.Model.list()
    print('OpenAI: OK')
except Exception as e:
    print(f'OpenAI: FAILED - {e}')
"

echo ""
echo "5. Checking WebSocket..."
curl -s -o /dev/null -w "WebSocket: %{http_code}\n" \
  https://erp.sysmayal2.cloud/socket.io/
```

### Common Issues and Solutions

#### Issue: High Latency on Alexa Requests

**Symptoms:** Requests taking > 10 seconds

**Diagnosis:**
```bash
# Check which step is slow
tail -f ~/frappe-bench/logs/worker.log | grep "alexa_to_raven"
```

**Solutions:**
1. Check LLM API latency
2. Check database query performance
3. Review agent execution logs
4. Consider caching responses

#### Issue: Error Rate Spike

**Symptoms:** > 5% of requests failing

**Diagnosis:**
```bash
# Check error types
grep ERROR ~/frappe-bench/logs/worker.log | \
  awk '{print $NF}' | sort | uniq -c | sort -rn
```

**Solutions:**
1. Check LLM API status
2. Verify database connectivity
3. Review recent deployments
4. Check rate limits

#### Issue: Messages Not Delivered to Raven

**Symptoms:** Alexa processes successfully but no message in Raven

**Diagnosis:**
```bash
# Check message creation
tail -f ~/frappe-bench/logs/worker.log | grep "create_message"

# Check Raven API
curl -s "https://erp.sysmayal2.cloud/api/method/raven.api.get_all_channel_members"
```

**Solutions:**
1. Verify Raven channel exists
2. Check user permissions
3. Review message creation logs
4. Test Raven API directly

---

## Dashboard Integration

### Frappe Dashboard

Access the Raven AI dashboard at:
```
https://erp.sysmayal2.cloud/api/method/raven_ai_agent.api.get_dashboard
```

**Dashboard Metrics:**
- Total requests (24h)
- Success rate
- Average latency
- Top commands
- Error breakdown

### Custom Grafana Dashboard (Optional)

For advanced monitoring, create Grafana dashboards:

```json
{
  "title": "Raven AI Agent Dashboard",
  "panels": [
    {
      "title": "Request Rate",
      "type": "graph",
      "targets": [
        {
          "expr": "rate(raven_requests_total[5m])",
          "legendFormat": "{{endpoint}}"
        }
      ]
    },
    {
      "title": "Latency P95",
      "type": "graph",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(raven_request_latency_seconds_bucket[5m]))",
          "legendFormat": "P95"
        }
      ]
    }
  ]
}
```

---

## Appendix: Monitoring Checklist

### Daily Checks

- [ ] Review alert inbox for P1/P2 alerts
- [ ] Check dashboard for anomalies
- [ ] Verify error rate < 1%
- [ ] Check LLM costs within budget

### Weekly Checks

- [ ] Review trend charts
- [ ] Check capacity utilization
- [ ] Review failed requests
- [ ] Update monitoring rules if needed

### Monthly Checks

- [ ] Review monthly cost report
- [ ] Analyze performance trends
- [ ] Update alerting thresholds
- [ ] Review and update documentation

---

*Last Updated: 2024-01-15*
*Version: 1.0*
*Maintainer: Development Team*
