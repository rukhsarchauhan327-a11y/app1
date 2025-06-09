import os
import logging
from flask import Flask, render_template

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-for-pricing-preview")

@app.route('/')
def index():
    """Serve the Kirana Konnect splash screen"""
    return render_template('splash.html')

@app.route('/pricing')
def pricing():
    """Serve the pricing plans page"""
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
