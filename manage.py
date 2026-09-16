"""
Start the Flask server. Use kynvera.create_app so HR, HVAC, Civil, etc. are registered.
Running manage.py or kynvera.py should both serve the full app (including /hr/).
"""
import os

# Use full app from kynvera (includes HR, HVAC, Civil, Procurement, etc.)
from kynvera import create_app

config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)