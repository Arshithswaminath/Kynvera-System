# ☁️ Cloud-Only Setup Guide

This application is configured to run **fully online** without local filesystem dependencies in production.

## ✅ Cloud-Only Requirements

### Required Environment Variables (Production)

1. **Database (PostgreSQL)**
   ```env
   DATABASE_URL=postgresql://user:password@host:port/database
   ```
   - ✅ **Required in production**
   - ❌ SQLite is **NOT allowed** in production
   - Application will fail to start if DATABASE_URL is missing

2. **Cloudinary (File Storage)**
   ```env
   CLOUDINARY_CLOUD_NAME=your-cloud-name
   CLOUDINARY_API_KEY=your-api-key
   CLOUDINARY_API_SECRET=your-api-secret
   ```
   - ✅ **Required in production**
   - All files (photos, signatures, reports) are stored in Cloudinary
   - Application will fail to start if Cloudinary credentials are missing

3. **Application Settings**
   ```env
   FLASK_ENV=production
   SECRET_KEY=your-32-character-minimum-secret-key
   JWT_SECRET_KEY=your-jwt-secret-key
   ```

### Optional (Recommended)

```env
REDIS_URL=redis://host:port  # For rate limiting and background jobs
APP_BASE_URL=https://your-domain.com  # For generating absolute URLs
```

## 🔒 Production Restrictions

### What's NOT Allowed in Production

1. **SQLite Database**
   - ❌ Will cause application startup failure
   - ✅ Must use PostgreSQL

2. **Local File Storage**
   - ❌ Files cannot be served from local filesystem
   - ✅ All files must be uploaded to Cloudinary
   - ✅ All file URLs must be Cloudinary URLs

3. **Local File Serving Routes**
   - ❌ `/generated/<filename>` routes return 404 in production
   - ✅ Use Cloudinary URLs directly

4. **Job State in JSON Files**
   - ❌ Job state is stored in database, not JSON files
   - ✅ All job tracking uses PostgreSQL

## 📁 File Storage Strategy

### Development Mode
- Files can be stored locally as fallback
- Local file serving routes work
- SQLite database allowed

### Production Mode
- **All files MUST be in Cloudinary**
- No local file storage fallback
- All file URLs are Cloudinary URLs
- Reports are generated temporarily, uploaded to cloud, then deleted locally

## 🔄 How It Works

### File Upload Flow
1. User uploads file → Uploaded to Cloudinary immediately
2. Cloudinary URL stored in database
3. Local temp file deleted after upload

### Report Generation Flow
1. Report generated in temporary directory
2. Excel uploaded to Cloudinary → Cloud URL stored
3. PDF uploaded to Cloudinary → Cloud URL stored
4. Temporary files deleted
5. Job marked complete with cloud URLs

### File Access Flow
1. Frontend receives Cloudinary URLs
2. Files accessed directly from Cloudinary
3. No local file serving required

## ✅ Verification Checklist

Before deploying to production, verify:

- [ ] `DATABASE_URL` is set to PostgreSQL (not SQLite)
- [ ] `CLOUDINARY_CLOUD_NAME` is set
- [ ] `CLOUDINARY_API_KEY` is set
- [ ] `CLOUDINARY_API_SECRET` is set
- [ ] `FLASK_ENV=production`
- [ ] `SECRET_KEY` is set (min 32 characters)
- [ ] `JWT_SECRET_KEY` is set
- [ ] Application starts without errors
- [ ] Health check endpoint returns healthy
- [ ] File uploads work and return Cloudinary URLs
- [ ] Reports are generated and accessible via Cloudinary URLs

## 🚨 Common Issues

### Issue: "DATABASE_URL not configured"
**Solution:** Set `DATABASE_URL` environment variable to PostgreSQL connection string

### Issue: "CLOUDINARY_CLOUD_NAME not configured"
**Solution:** Set all three Cloudinary environment variables

### Issue: "SQLite is not allowed in production"
**Solution:** Change `DATABASE_URL` from SQLite to PostgreSQL

### Issue: Files not accessible after upload
**Solution:** Ensure files are uploaded to Cloudinary (check logs for cloud URLs)

### Issue: Reports not downloadable
**Solution:** Ensure reports are uploaded to Cloudinary during generation (check job logs)

## 📝 Notes

- The `generated/`, `uploads/`, and `jobs/` directories are only used temporarily in production
- Files in these directories are deleted after cloud upload
- Job state is stored in PostgreSQL `jobs` table, not JSON files
- All file references in database use Cloudinary URLs

---

**Last Updated:** 2024-12-30

