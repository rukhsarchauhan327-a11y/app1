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

@app.route('/signup')
def signup():
    """Serve the signup page"""
    return render_template('signup.html')

@app.route('/signin')
@app.route('/login')
def signin():
    """Serve the signin page"""
    return render_template('signin.html')

@app.route('/dashboard')
def dashboard():
    """Serve the main dashboard page"""
    return render_template('dashboard.html')

@app.route('/cart')
def cart():
    """Serve the cart/billing page"""
    return render_template('cart.html')

@app.route('/inventory')
def inventory():
    """Serve the inventory management page"""
    return render_template('inventory.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
