# 📊 Monitoring & Error Tracking Setup

## Overview

This document describes how to set up monitoring and error tracking for the Injaaz application.

---

## 🔍 **Current Monitoring**

### Health Check Endpoint
- **Endpoint:** `GET /health`
- **Returns:** Database status, timestamp
- **Use Case:** Load balancer health checks, uptime monitoring

### Logging
- **Location:** `logs/injaaz.log` (rotating, 10MB max, 5 backups)
- **Format:** Structured logging with timestamps, module names, function names
- **Levels:** INFO, WARNING, ERROR, DEBUG

---

## 🚀 **Recommended Monitoring Solutions**

### 1. **Sentry (Error Tracking)** ⭐ Recommended

**What it does:**
- Captures exceptions and errors automatically
- Provides stack traces and context
- Sends alerts for critical errors
- Tracks error frequency and trends

**Setup:**
```bash
pip install sentry-sdk[flask]
```

**Configuration:**
```python
# In Injaaz.py, add after create_app():
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

if app.config.get('FLASK_ENV') == 'production':
    sentry_sdk.init(
        dsn=os.environ.get('SENTRY_DSN'),
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,  # 10% of transactions
        environment='production'
    )
```

**Environment Variable:**
```env
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

**Benefits:**
- Free tier available
- Real-time error alerts
- Performance monitoring
- Release tracking

---

### 2. **Uptime Monitoring**

**Options:**
- **UptimeRobot** (Free) - Monitors `/health` endpoint
- **Pingdom** - Advanced monitoring
- **StatusCake** - Free tier available

**Setup:**
1. Create account
2. Add monitor for: `https://injaaz-app.onrender.com/health`
3. Set check interval (5 minutes recommended)
4. Configure alerts (email, SMS, Slack)

---

### 3. **Application Performance Monitoring (APM)**

**Options:**
- **Sentry Performance** (included with Sentry)
- **New Relic** (paid, free tier limited)
- **DataDog** (paid)
- **Render Built-in** (if using Render)

**What it tracks:**
- Request response times
- Database query performance
- External API calls (Cloudinary, Redis)
- Error rates

---

### 4. **Log Aggregation**

**Options:**
- **Render Logs** (built-in if using Render)
- **Papertrail** (free tier: 16MB/month)
- **Loggly** (free tier: 200MB/day)
- **ELK Stack** (self-hosted)

**Benefits:**
- Centralized log viewing
- Search and filter logs
- Alert on log patterns
- Long-term log retention

---

## 📈 **Metrics to Monitor**

### Application Metrics
- ✅ Response time (p50, p95, p99)
- ✅ Error rate (4xx, 5xx)
- ✅ Request rate (requests/second)
- ✅ Active users

### Infrastructure Metrics
- ✅ Database connection pool usage
- ✅ Redis memory usage
- ✅ Cloudinary API usage
- ✅ Disk space (if applicable)

### Business Metrics
- ✅ Submissions per day
- ✅ Reports generated per day
- ✅ Active users per day
- ✅ Failed job rate

---

## 🔔 **Alerting Recommendations**

### Critical Alerts (Immediate)
- Application down (health check fails)
- Database connection failures
- High error rate (>5% of requests)
- Cloudinary upload failures

### Warning Alerts
- Slow response times (>2 seconds)
- High database connection pool usage (>80%)
- Rate limit exceeded frequently
- Disk space low

---

## 🛠️ **Quick Setup (Sentry)**

### Step 1: Create Sentry Account
1. Go to https://sentry.io
2. Create free account
3. Create new project (Flask)
4. Copy DSN

### Step 2: Add to Requirements
```bash
echo "sentry-sdk[flask]==1.38.0" >> requirements-prods.txt
```

### Step 3: Configure in Application
Add to `Injaaz.py` after `create_app()`:
```python
# Sentry error tracking (optional)
if app.config.get('FLASK_ENV') == 'production':
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        
        sentry_dsn = os.environ.get('SENTRY_DSN')
        if sentry_dsn:
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                traces_sample_rate=0.1,
                environment='production'
            )
            logger.info("✓ Sentry error tracking enabled")
    except ImportError:
        logger.info("Sentry not installed - error tracking disabled")
    except Exception as e:
        logger.warning(f"Sentry setup failed: {e}")
```

### Step 4: Add Environment Variable
```env
SENTRY_DSN=https://your-dsn@sentry.io/project-id
```

---

## 📝 **Session Cleanup Setup**

### Manual Cleanup
Call the cleanup endpoint:
```bash
curl -X POST https://injaaz-app.onrender.com/admin/cleanup-sessions \
  -H "X-API-Key: your-cleanup-api-key"
```

### Automated Cleanup (Cron)
Set up a cron job or scheduled task:
```bash
# Daily at 2 AM
0 2 * * * curl -X POST https://injaaz-app.onrender.com/admin/cleanup-sessions -H "X-API-Key: $CLEANUP_API_KEY"
```

### Render Cron Jobs
If using Render, add a Cron Job service:
- **Command:** `curl -X POST https://injaaz-app.onrender.com/admin/cleanup-sessions -H "X-API-Key: $CLEANUP_API_KEY"`
- **Schedule:** `0 2 * * *` (daily at 2 AM)

**Environment Variable:**
```env
CLEANUP_API_KEY=your-secure-random-key-here
```

---

## ✅ **Monitoring Checklist**

- [ ] Health check endpoint working (`/health`)
- [ ] Logging configured and rotating
- [ ] Error tracking setup (Sentry or alternative)
- [ ] Uptime monitoring configured
- [ ] Alerts configured for critical issues
- [ ] Session cleanup scheduled
- [ ] Performance monitoring enabled (optional)

---

**Last Updated:** 2024-12-30

