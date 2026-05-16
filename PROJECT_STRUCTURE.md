# 📁 Injaaz Project Structure

## 🎯 Professional Project Organization

This document describes the professional structure of the Injaaz application.

---

## 📂 Directory Structure

```
Injaaz-App/
│
├── 📄 Core Files
│   ├── Injaaz.py              # Main Flask application factory
│   ├── config.py              # Application configuration
│   ├── wsgi.py                # WSGI entry point (for production)
│   ├── manage.py              # Management commands
│   ├── requirements.txt       # Python dependencies
│   ├── requirements-prods.txt # Production dependencies
│   ├── requirements-dev.txt   # Development dependencies
│   ├── .gitignore             # Git ignore rules
│   └── README.md              # Project documentation
│
├── 📁 app/                    # Core Application Package
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy database models
│   ├── config.py              # App-specific config
│   ├── extensions.py          # Flask extensions
│   ├── forms.py               # WTForms definitions
│   ├── form_schemas.py        # Form validation schemas
│   ├── middleware.py          # Custom middleware
│   ├── reports_api.py         # Reports API endpoints
│   ├── site_visit_form.py     # Site visit form logic
│   ├── tasks.py               # Background tasks
│   │
│   ├── 📁 auth/               # Authentication Module
│   │   ├── __init__.py
│   │   └── routes.py          # Login, register, JWT routes
│   │
│   ├── 📁 admin/              # Admin Module
│   │   ├── __init__.py
│   │   └── routes.py          # User management, access control
│   │
│   ├── 📁 modules/            # Additional modules
│   │   └── site_visit/
│   │
│   ├── 📁 services/           # Business logic services
│   │   ├── pdf_service.py
│   │   ├── excel_service.py
│   │   └── ...
│   │
│   └── 📁 tasks/              # Background job tasks
│       ├── generate_report.py
│       └── worker.py
│
├── 📁 module_hvac_mep/        # HVAC & MEP Module
│   ├── __init__.py
│   ├── routes.py              # HVAC form routes
│   ├── generator.py           # Report generators
│   ├── hvac_generators.py     # PDF/Excel generators
│   ├── dropdown_data.json      # Dropdown options
│   └── 📁 templates/
│       └── hvac_mep_form.html
│
├── 📁 module_civil/           # Civil Works Module
│   ├── __init__.py
│   ├── routes.py              # Civil form routes
│   ├── civil_generators.py    # Report generators
│   └── 📁 templates/
│       └── civil_form.html
│
├── 📁 module_cleaning/        # Cleaning Services Module
│   ├── __init__.py
│   ├── routes.py              # Cleaning form routes
│   ├── cleaning_generators.py # Report generators
│   └── 📁 templates/
│       └── cleaning_form.html
│
├── 📁 templates/              # Shared Templates
│   ├── dashboard.html          # Main dashboard
│   ├── login.html              # Login page
│   ├── register.html           # Registration page
│   ├── admin_dashboard.html    # Admin dashboard
│   ├── access_denied.html      # Access denied page
│   ├── offline.html            # PWA offline page
│   ├── pwa_meta.html           # PWA meta tags
│   └── ...
│
├── 📁 static/                 # Static Assets
│   ├── logo.png                # Application logo
│   ├── manifest.json           # PWA manifest
│   ├── service-worker.js       # PWA service worker
│   ├── pwa-install.js          # PWA installation
│   ├── mobile_responsive.css   # Mobile styles
│   ├── photo_upload_queue.js   # Photo upload system
│   ├── photo_queue_ui.js       # Photo UI management
│   ├── photo_upload_queue.css # Photo styles
│   ├── form.js                 # Form utilities
│   ├── main.js                 # Main JavaScript
│   ├── site_form.js            # Site form logic
│   ├── dropdown_init.js        # Dropdown initialization
│   ├── index.html              # Native app entry point
│   └── 📁 icons/               # PWA icons
│       ├── icon-72x72.png
│       ├── icon-192x192.png
│       ├── icon-512x512.png
│       └── ...
│
├── 📁 common/                 # Common Utilities
│   ├── db_utils.py            # Database utilities
│   ├── retry_utils.py         # Retry logic
│   ├── security.py            # Security utilities
│   ├── utils.py               # General utilities
│   └── validation.py          # Validation helpers
│
├── 📁 scripts/                # Utility Scripts
│   ├── create_admin.py        # Create admin user
│   ├── create_default_admin.py
│   ├── init_db.py             # Initialize database
│   ├── migrate_add_permissions.py
│   └── migrate_json_to_db.py
│
├── 📁 generated/              # Generated Reports (gitignored)
│   ├── *.pdf
│   └── *.xlsx
│
├── 📁 uploads/                # Uploaded Files (gitignored)
│
└── 📁 jobs/                   # Background Jobs (gitignored)
```

---

## 📋 File Categories

### ✅ Essential Files (Never Delete)

**Core Application:**
- `Injaaz.py` - Main application
- `config.py` - Configuration
- `requirements*.txt` - Dependencies

**Application Code:**
- All `app/` subdirectories
- All `module_*/` directories
- All `templates/` files
- All `static/` files (except generated)

**Configuration:**
- `.gitignore`
- `README.md`

### 🗑️ Temporary Files (Can Delete)

**Documentation:**
- `*_GUIDE.md` (except this file)
- `*_CHECKLIST.md`
- `*_SUMMARY.md`
- `*_COMPLETE.md`

**Development:**
- `__pycache__/` folders
- `*.pyc` files
- IDE folders (`.vscode/`, `.idea/`)

**Build Artifacts:**
- `generated/` (recreated on use)
- `uploads/` (recreated on use)
- `jobs/` (recreated on use)

**Node.js (if not using Android Studio):**
- `node_modules/`
- `package.json`
- `package-lock.json`
- `android/`
- `ios/`
- `capacitor.config.ts`

---

## 🎯 Module Organization

### Each Module Follows This Structure:

```
module_name/
├── __init__.py           # Package initialization
├── routes.py             # Flask routes
├── *_generators.py       # Report generation
└── templates/
    └── *_form.html      # Form template
```

### Benefits:
- ✅ Clear separation of concerns
- ✅ Easy to add new modules
- ✅ Maintainable codebase
- ✅ Scalable architecture

---

## 📝 Naming Conventions

### Files:
- **Python:** `snake_case.py`
- **Templates:** `snake_case.html`
- **JavaScript:** `snake_case.js`
- **CSS:** `snake_case.css`

### Directories:
- **Modules:** `module_name/`
- **Templates:** `templates/`
- **Static:** `static/`

### Classes:
- **Python:** `PascalCase`
- **JavaScript:** `PascalCase`

### Functions/Variables:
- **Python:** `snake_case`
- **JavaScript:** `camelCase`

---

## 🔄 Workflow

### Development:
1. Edit code in modules
2. Test locally
3. Commit changes
4. Push to repository

### Deployment:
1. Pull latest code
2. Install dependencies
3. Run migrations (if any)
4. Deploy to Render

### Adding New Module:
1. Create `module_name/` directory
2. Add `__init__.py`
3. Create `routes.py`
4. Create `templates/` folder
5. Add form template
6. Register in `Injaaz.py`

---

## ✅ Best Practices

1. **Keep modules separate** - Don't mix module code
2. **Use templates folder** - All HTML in templates
3. **Static assets in static/** - All CSS/JS in static
4. **Document as you go** - Add comments in code
5. **Version control** - Commit frequently
6. **Clean structure** - Remove temporary files
7. **Follow conventions** - Use naming standards

---

## 📚 Documentation Files

### Keep:
- `README.md` - Main project documentation
- `PROJECT_STRUCTURE.md` - This file
- `PROJECT_CLEANUP_GUIDE.md` - Cleanup instructions

### Can Remove (recreate if needed):
- All other `*.md` files

---

**This structure ensures a professional, maintainable codebase!** 🎯

