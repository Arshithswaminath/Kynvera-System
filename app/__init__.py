import os
from flask import Flask
from .config import config_by_name
from .extensions import init_extensions

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    app = Flask(__name__, static_folder='../static', template_folder='templates')
    app.config.from_object(config_by_name[config_name])

    # Initialize extensions (db, jwt, bcrypt, etc.)
    init_extensions(app)

    # Register blueprints (auth and site_visit will be created later)
    try:
        from .auth.routes import auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')
    except Exception:
        pass

    try:
        from .modules.site_visit import site_visit_bp
        app.register_blueprint(site_visit_bp, url_prefix='/site-visit')
    except Exception:
        pass

    @app.route('/')
    def health():
        return "Amaan App — OK"

    return app