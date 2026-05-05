"""
Start the Flask server. Use Injaaz.create_app so HR, HVAC, Civil, etc. are registered.
Running manage.py or Injaaz.py should both serve the full app (including /hr/).
"""
import os

# Use full app from Injaaz (includes HR, HVAC, Civil, Procurement, etc.)
from Injaaz import create_app

config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)