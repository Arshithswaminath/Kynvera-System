# 🚀 Injaaz Application - Local Development Setup Guide

This guide will help you set up the Injaaz application on your new laptop for local development.

## 📋 Prerequisites

Before you begin, make sure you have the following installed:

### Required Software

1. **Python 3.8+** 
   - Download from: https://www.python.org/downloads/
   - ✅ Check installation: `python --version`
   - Make sure to check "Add Python to PATH" during installation

2. **Node.js 16+ and npm**
   - Download from: https://nodejs.org/
   - ✅ Check installation: `node --version` and `npm --version`

3. **Git** (if cloning from repository)
   - Download from: https://git-scm.com/downloads
   - ✅ Check installation: `git --version`

### Optional (for mobile app development)

4. **Android Studio** (if developing Android app)
   - Required for Capacitor Android development
   - Download from: https://developer.android.com/studio

5. **Java JDK 11+** (required for Android development)
   - Usually comes with Android Studio

---

## 🔧 Step-by-Step Setup Instructions

### Step 1: Clone or Navigate to Project Directory

If you're using Git:
```powershell
git clone <your-repository-url>
cd Injaaz-App
```

If you already have the project files, just navigate to the project directory:
```powershell
cd D:\Injaaz-Application\Injaaz-App
```

### Step 2: Create a Python Virtual Environment

It's recommended to use a virtual environment to isolate project dependencies:

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# If you get an execution policy error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

After activation, you should see `(venv)` in your terminal prompt.

### Step 3: Install Python Dependencies

```powershell
# Make sure virtual environment is activated (you should see (venv) in prompt)
pip install --upgrade pip
pip install -r requirements-prods.txt

# If you want to run tests, also install dev dependencies:
pip install -r requirements-dev.txt
```

### Step 4: Install Node.js Dependencies

```powershell
# Install Capacitor and other Node.js dependencies
npm install
```

### Step 5: Create Environment Configuration File

Create a `.env` file in the project root directory. You can use the provided `.env.example` as a template:

```powershell
# Copy the example file (if it exists)
Copy-Item .env.example .env

# Or create a new .env file manually
```

Edit the `.env` file with your configuration. For **local development**, you can use minimal settings:

```env
# Flask Environment
FLASK_ENV=development
DEBUG=true

# Secret Keys (IMPORTANT: Change these in production!)
SECRET_KEY=your-secret-key-change-this-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-this

# Database (SQLite for local development)
# The app will use SQLite automatically if DATABASE_URL is not set
# DATABASE_URL=sqlite:///injaaz.db

# Cloudinary (Optional for local dev, but recommended)
# Get these from: https://cloudinary.com/console
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# Application URL
APP_BASE_URL=http://localhost:5000

# Redis (Optional for local dev - only needed for rate limiting)
# REDIS_URL=redis://localhost:6379

# Email Settings (Optional)
# MAIL_SERVER=smtp.gmail.com
# MAIL_PORT=587
# MAIL_USERNAME=your-email@gmail.com
# MAIL_PASSWORD=your-app-password
# MAIL_USE_TLS=true
# MAIL_DEFAULT_SENDER=noreply@injaaz.com
```

**Important Notes:**
- For local development, you can skip Cloudinary, Redis, and Email settings initially
- The app will use SQLite database automatically if `DATABASE_URL` is not set
- Generate secure random keys for `SECRET_KEY` and `JWT_SECRET_KEY` (you can use Python: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)

### Step 6: Initialize the Database

```powershell
# Run the database initialization script
python scripts\init_db.py
```

This will:
- Create all necessary database tables
- Create a default admin user with credentials:
  - Username: `admin`
  - Password: `Admin@123`
  - **⚠️ IMPORTANT: Change this password immediately after first login!**

### Step 7: Start the Application

You can start the application in two ways:

#### Option A: Using the provided batch script (Recommended for Windows)
```powershell
.\start.bat
```

#### Option B: Manual start
```powershell
python Injaaz.py
```

The application will start on `http://localhost:5000`

### Step 8: Access the Application

1. Open your browser and go to: `http://localhost:5000`
2. You should see the login page
3. Login with the default admin credentials:
   - Username: `admin`
   - Password: `Admin@123`
4. **Change the admin password immediately after first login!**

---

## 📱 Mobile App Setup (Optional)

If you want to develop the mobile app components:

### For Android Development:

1. **Install Android Studio** (if not already installed)
2. **Open Android project:**
   ```powershell
   npm run android
   ```
   This will open Android Studio with the Capacitor Android project

3. **Sync Capacitor** (whenever you make changes):
   ```powershell
   npm run sync
   ```

### For iOS Development (macOS only):

1. **Install Xcode** from Mac App Store
2. **Open iOS project:**
   ```powershell
   npm run ios
   ```

---

## 🔍 Verification Checklist

After setup, verify everything is working:

- [ ] Python virtual environment is activated
- [ ] All Python dependencies installed (`pip list` shows required packages)
- [ ] Node.js dependencies installed (`npm list` shows packages)
- [ ] `.env` file created with required variables
- [ ] Database initialized (should see `injaaz.db` file in project root)
- [ ] Application starts without errors
- [ ] Can access `http://localhost:5000` in browser
- [ ] Can login with admin credentials

---

## 🐛 Troubleshooting

### Issue: `python` command not found
**Solution:** Make sure Python is installed and added to PATH. Try `py` instead of `python` on Windows.

### Issue: Virtual environment activation fails
**Solution:** 
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: `pip install` fails
**Solution:** 
- Make sure virtual environment is activated
- Upgrade pip: `python -m pip install --upgrade pip`
- Try installing packages individually if one fails

### Issue: Database initialization fails
**Solution:**
- Check that you have write permissions in the project directory
- Make sure all Python dependencies are installed
- Check the error message for specific issues

### Issue: Application won't start
**Solution:**
- Check that port 5000 is not already in use
- Verify `.env` file exists and has required variables
- Check the console output for specific error messages
- Make sure database is initialized (`injaaz.db` file exists)

### Issue: Module import errors
**Solution:**
- Make sure virtual environment is activated
- Reinstall dependencies: `pip install -r requirements-prods.txt`
- Check that you're in the correct directory

### Issue: Capacitor sync fails
**Solution:**
- Make sure Node.js dependencies are installed: `npm install`
- Check that you have Android Studio installed (for Android)
- Try: `npx cap sync` manually

---

## 📚 Additional Resources

- **Flask Documentation:** https://flask.palletsprojects.com/
- **Capacitor Documentation:** https://capacitorjs.com/docs
- **Project Structure:** See `PROJECT_STRUCTURE.md`
- **Project Flow:** See `PROJECT_FLOW.md`

---

## 🔐 Security Notes

1. **Never commit `.env` file to Git** - it contains sensitive information
2. **Change default admin password** immediately after first login
3. **Use strong SECRET_KEY and JWT_SECRET_KEY** in production
4. **Keep dependencies updated** for security patches

---

## 🎯 Next Steps

After successful setup:

1. Change the admin password
2. Explore the dashboard at `/dashboard`
3. Create test users via admin panel
4. Test form submissions
5. Review the codebase structure in `PROJECT_STRUCTURE.md`

---

**Need Help?** Check the troubleshooting section or review the error logs in the console.
