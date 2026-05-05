# Injaaz App

This repository is the new, production-ready rewrite of the Injaaz site-visit application.

## 🚀 Getting Started

### Quick Start (5 minutes)
See [QUICK_START.md](QUICK_START.md) for a fast setup guide.

### Full Setup Guide
For detailed setup instructions, troubleshooting, and advanced configuration, see [SETUP.md](SETUP.md).

### Automated Setup (Windows)
Run the setup script to automate the entire setup process:
```powershell
.\setup.ps1
```

### Manual Setup
1. **Prerequisites**: Python 3.8+, Node.js 16+
2. **Install dependencies**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements-prods.txt
   npm install
   ```
3. **Configure environment**: Create `.env` file (see [SETUP.md](SETUP.md) for template)
4. **Initialize database**: `python scripts\init_db.py`
5. **Start application**: `python Injaaz.py` or `.\start.bat`
6. **Access**: Open http://localhost:5000
   - Default login: `admin` / `Admin@123` (change immediately!)

## 📚 Documentation

- **[docs/APPLICATION_OVERVIEW.md](docs/APPLICATION_OVERVIEW.md)** - High-level application overview (modules, architecture)
- **[SETUP.md](SETUP.md)** - Complete setup guide with troubleshooting
- **[QUICK_START.md](QUICK_START.md)** - Fast 5-minute setup
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - Codebase organization
- **[PROJECT_FLOW.md](PROJECT_FLOW.md)** - Application workflow
- **[CLOUD_ONLY_SETUP.md](CLOUD_ONLY_SETUP.md)** - Production deployment guide
- **[RENDER_DEPLOYMENT_PHASES.md](RENDER_DEPLOYMENT_PHASES.md)** - Render: Phase 1 (testing) and Phase 2 (production runbook)

## 🔒 Security Notes

- **Never commit `.env` file** - it contains sensitive information
- **Change default admin password** immediately after first login
- **Use strong SECRET_KEY and JWT_SECRET_KEY** in production
- Keep dependencies updated for security patches

## 🛠️ Tech Stack

- **Backend**: Flask (Python)
- **Database**: SQLite (dev) / PostgreSQL (production)
- **Frontend**: HTML, CSS, JavaScript
- **Mobile**: Capacitor (Android/iOS)
- **File Storage**: Cloudinary (production)
- **Authentication**: JWT (Flask-JWT-Extended)

## 📝 Notes

- Keep secrets out of the repo (use Render env vars or local `.env` not tracked)
- The application automatically initializes database tables on first run
- For production deployment, see [CLOUD_ONLY_SETUP.md](CLOUD_ONLY_SETUP.md)