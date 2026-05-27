# app/site_visit_form.py
# Minimal blueprint to serve the site visit form and inject Cloudinary values.

import os
from flask import Blueprint, render_template, current_app

bp = Blueprint('site_visit_form', __name__, template_folder='../templates', static_folder='../static')

@bp.route('/site-visit/form')
def site_visit_form():
    # Try to read Cloudinary settings from Flask config/env
    cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME') or os.environ.get('CLOUDINARY_CLOUD_NAME') or ''
    upload_preset = current_app.config.get('CLOUDINARY_UPLOAD_PRESET') or os.environ.get('CLOUDINARY_UPLOAD_PRESET') or ''
    return render_template('site_visit_form.html',
                           cloud_name=cloud_name,
                           upload_preset=upload_preset)