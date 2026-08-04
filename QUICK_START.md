# ⚡ Quick Start Guide

Get up and running in 5 minutes!

## 🚀 Automated Setup (Recommended)

Run the setup script:

```powershell
.\setup.ps1
```

This will:
- ✅ Check prerequisites (Python, Node.js)
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Create .env file with generated keys
- ✅ Initialize database

## 🛠️ Manual Setup

### 1. Create and activate virtual environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies
```powershell
pip install -r requirements-prods.txt
npm install
```

### 3. Create .env file
Create a `.env` file in the project root with at minimum:
```env
FLASK_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here
APP_BASE_URL=http://localhost:5000
```

Generate secure keys:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Initialize database
```powershell
python scripts\init_db.py
```

### 5. Start the application
```powershell
python Injaaz.py
```

Or use the batch file:
```powershell
.\start.bat
```

## 🌐 Access the Application

1. Open browser: http://localhost:5000
2. Login with:
   - **Username:** `Kynvera`
   - **Password:** `Arshith&Taha@2026`

## 📋 Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] Node.js 16+ installed
- [ ] Git (if cloning repository)

## ❓ Need More Help?

See the detailed [SETUP.md](SETUP.md) guide for:
- Detailed explanations
- Troubleshooting
- Advanced configuration
- Mobile app setup

---

**That's it! You're ready to develop.** 🎉
