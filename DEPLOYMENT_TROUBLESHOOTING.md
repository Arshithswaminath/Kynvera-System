# 🔧 Deployment Troubleshooting Guide

## Current Issue: Deployment Failed

The logs show the Docker build completed successfully, but deployment failed during the startup phase.

---

## 🔍 Analysis

### What We Know:
1. ✅ Docker build succeeded
2. ✅ Image pushed to registry
3. ✅ Deployment started
4. ❌ Deployment failed (logs cut off)

### Potential Issues:

#### 1. **Build Command in render.yaml**
The `render.yaml` has a `buildCommand`:
```yaml
buildCommand: bash build.sh && python scripts/init_db.py
```

**Problem:** This runs during build, but if `init_db.py` fails or takes too long, deployment fails.

**Check:** Look for errors in Render logs related to:
- `build.sh` execution
- `scripts/init_db.py` execution
- Database connection during build

#### 2. **Database Connection During Build**
`init_db.py` tries to connect to the database during build, but:
- Database might not be accessible during build phase
- Database credentials might not be available yet

**Solution:** Database initialization should happen at **runtime**, not during build.

#### 3. **Missing Environment Variables**
If required environment variables are missing, `create_app()` will raise `RuntimeError`.

**Check:** Ensure all variables are set in Render:
- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

---

## ✅ Recommended Fixes

### Fix 1: Remove Database Init from Build Command

**File:** `render.yaml`

**Change:**
```yaml
# OLD (WRONG):
buildCommand: bash build.sh && python scripts/init_db.py

# NEW (CORRECT):
buildCommand: bash build.sh
```

**Why:** Database initialization should happen at runtime (in `create_app()`), not during build.

### Fix 2: Ensure Database Init Happens at Runtime

The `Injaaz.py` already has database initialization in `create_app()` (lines 119-243), so this should work automatically.

**Verify:** Check that database tables are created in `create_app()` function.

### Fix 3: Check Build Script

**File:** `build.sh`

Ensure it doesn't fail. Common issues:
- Missing dependencies
- Permission errors
- Path issues

---

## 🔍 How to Debug

### Step 1: Check Full Render Logs

1. Go to Render Dashboard
2. Click on your service
3. Go to **Logs** tab
4. Look for errors after "==> Deploying..."
5. Common error patterns:
   - `RuntimeError: ...`
   - `NameError: ...`
   - `ImportError: ...`
   - `Database connection failed`
   - `Configuration validation failed`

### Step 2: Check Build Logs

Look for errors in:
- `build.sh` execution
- `scripts/init_db.py` execution
- Any Python import errors

### Step 3: Verify Environment Variables

In Render Dashboard → Your Service → Environment:
- All required variables are set
- No typos in variable names
- Values are correct

### Step 4: Test Locally

Test the same command Render uses:
```bash
# Test build
bash build.sh

# Test app creation
python -c "from Injaaz import create_app; app = create_app(); print('✅ App created successfully')"
```

---

## 🚀 Quick Fix

**Most Likely Issue:** `buildCommand` includes database initialization which fails.

**Quick Fix:** Remove `python scripts/init_db.py` from `buildCommand`:

```yaml
buildCommand: bash build.sh
```

The database will be initialized automatically when `create_app()` runs at startup.

---

## 📝 Next Steps

1. **Check Render Logs** for the actual error message
2. **Update render.yaml** to remove database init from build
3. **Redeploy** and monitor logs
4. **Verify** service starts successfully

---

**Last Updated:** 2024-12-30

