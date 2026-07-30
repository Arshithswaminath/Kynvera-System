"""
Start the Flask server. Use kynver.create_app so HR, HVAC, Store, etc. are registered.
Running manage.py or kynver.py should both serve the full app (including /hr/).
"""
import os

from kynver import create_app

config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
