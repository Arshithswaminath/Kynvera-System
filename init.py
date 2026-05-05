# DEPRECATED: This file is not used. The main application factory is in Injaaz.py
# This file is kept for reference only and should not be imported.
# 
# The active application factories are:
# - Injaaz.py (used by wsgi.py for production)
# - app/__init__.py (used by manage.py for local development)

# app/__init__.py
import os
from flask import Flask
from .models import db
from .forms import bp as forms_bp

def create_app():
    app = Flask(__name__, static_folder="../static", template_folder="../templates")

    # Basic config from environment
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///injaaz.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['CLOUDINARY_CLOUD_NAME'] = os.environ.get('CLOUDINARY_CLOUD_NAME')
    app.config['CLOUDINARY_API_KEY'] = os.environ.get('CLOUDINARY_API_KEY')
    app.config['CLOUDINARY_API_SECRET'] = os.environ.get('CLOUDINARY_API_SECRET')

    db.init_app(app)

    # Register blueprints
    app.register_blueprint(forms_bp)

    # lightweight root
    @app.route("/health")
    def health():
        return "OK", 200

    return app