import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-for-pricing-preview")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Database Models
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    address = db.Column(db.Text)
    aadhar_number = db.Column(db.String(12))
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    bills = db.relationship('Bill', backref='customer', lazy=True)
    payments = db.relationship('Payment', backref='customer', lazy=True)
    
    @property
    def outstanding_balance(self):
        from sqlalchemy import func
        total_bills = db.session.query(func.sum(Bill.total_amount)).filter(
            Bill.customer_id == self.id, 
            Bill.payment_status != 'paid'
        ).scalar() or 0
        
        total_payments = db.session.query(func.sum(Payment.amount)).filter(
            Payment.customer_id == self.id
        ).scalar() or 0
        
        return total_bills - total_payments

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    customer_name = db.Column(db.String(100))  # For cash customers without account
    
    # Bill details
    subtotal = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, nullable=False)
    
    # Payment details
    payment_mode = db.Column(db.String(20), nullable=False)  # cash, online, split, credit
    payment_status = db.Column(db.String(20), default='pending')  # paid, pending, partial
    
    # Staff and metadata
    generated_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('BillItem', backref='bill', lazy=True, cascade='all, delete-orphan')

class BillItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    # For weight-based items
    weight = db.Column(db.Float)
    price_per_kg = db.Column(db.Float)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True)
    
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(20), nullable=False)  # cash, online, upi, card
    reference_number = db.Column(db.String(50))  # For online payments
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    barcode = db.Column(db.String(50))
    category = db.Column(db.String(50))
    
    # Pricing
    price = db.Column(db.Float, nullable=False)
    price_per_kg = db.Column(db.Float)  # For weight-based items
    is_weight_based = db.Column(db.Boolean, default=False)
    
    # Inventory
    stock_quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=10)
    expiry_date = db.Column(db.Date)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables and seed data
with app.app_context():
    db.create_all()
    
    # Check if customers already exist
    if Customer.query.count() == 0:
        # Add sample customers with their records
        customers_data = [
            {'name': 'Rajesh Kumar', 'phone': '+91 98765 43210', 'address': 'Shop No. 15, Main Market'},
            {'name': 'Priya Sharma', 'phone': '+91 98765 43211', 'address': 'House No. 42, Gandhi Nagar'},
            {'name': 'Amit Singh', 'phone': '+91 98765 43212', 'address': 'Flat 3B, Sunrise Apartments'},
            {'name': 'Sunita Devi', 'phone': '+91 98765 43213', 'address': 'Village Rampur, Near Temple'},
            {'name': 'Ravi Patel', 'phone': '+91 98765 43214', 'address': 'Plot 25, Industrial Area'},
            {'name': 'Meera Gupta', 'phone': '+91 98765 43215', 'address': 'Lane 4, Civil Lines'},
            {'name': 'Arjun Reddy', 'phone': '+91 98765 43216', 'address': 'House 78, Nehru Colony'},
            {'name': 'Kavita Jain', 'phone': '+91 98765 43217', 'address': 'Shop 9, Commercial Complex'}
        ]
        
        for customer_data in customers_data:
            customer = Customer(**customer_data)
            db.session.add(customer)
        
        db.session.commit()
        
        # Add some sample bills and payments to create outstanding balances
        customers = Customer.query.all()
        
        # Create bills with outstanding amounts
        bills_data = [
            {'customer_id': 1, 'bill_number': 'KK-2024-001', 'subtotal': 2000, 'tax_amount': 360, 'total_amount': 2360, 'payment_mode': 'credit', 'payment_status': 'pending'},
            {'customer_id': 2, 'bill_number': 'KK-2024-002', 'subtotal': 750, 'tax_amount': 135, 'total_amount': 885, 'payment_mode': 'credit', 'payment_status': 'pending'},
            {'customer_id': 4, 'bill_number': 'KK-2024-003', 'subtotal': 1100, 'tax_amount': 198, 'total_amount': 1298, 'payment_mode': 'credit', 'payment_status': 'pending'},
            {'customer_id': 5, 'bill_number': 'KK-2024-004', 'subtotal': 450, 'tax_amount': 81, 'total_amount': 531, 'payment_mode': 'credit', 'payment_status': 'pending'},
            {'customer_id': 6, 'bill_number': 'KK-2024-005', 'subtotal': 680, 'tax_amount': 122, 'total_amount': 802, 'payment_mode': 'credit', 'payment_status': 'pending'},
            {'customer_id': 8, 'bill_number': 'KK-2024-006', 'subtotal': 1600, 'tax_amount': 288, 'total_amount': 1888, 'payment_mode': 'credit', 'payment_status': 'pending'}
        ]
        
        for bill_data in bills_data:
            bill = Bill(**bill_data, generated_by='System Admin')
            db.session.add(bill)
        
        # Add partial payments to reduce outstanding amounts
        payments_data = [
            {'customer_id': 1, 'amount': 210, 'payment_mode': 'cash'},  # Rajesh: 2360 - 210 = 2150
            {'customer_id': 2, 'amount': 35, 'payment_mode': 'cash'},   # Priya: 885 - 35 = 850
            {'customer_id': 4, 'amount': 98, 'payment_mode': 'online'}, # Sunita: 1298 - 98 = 1200
            {'customer_id': 5, 'amount': 31, 'payment_mode': 'cash'},   # Ravi: 531 - 31 = 500
            {'customer_id': 6, 'amount': 52, 'payment_mode': 'cash'},   # Meera: 802 - 52 = 750
            {'customer_id': 8, 'amount': 88, 'payment_mode': 'online'}  # Kavita: 1888 - 88 = 1800
        ]
        
        for payment_data in payments_data:
            payment = Payment(**payment_data)
            db.session.add(payment)
        
        db.session.commit()

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

@app.route('/add-item')
def add_item():
    """Serve the add new item page"""
    return render_template('add_item.html')

@app.route('/profile')
def profile():
    """Serve the user profile page"""
    return render_template('profile.html')

@app.route('/product-details')
def product_details():
    """Serve the product details page"""
    return render_template('product_details.html')

@app.route('/product-details-weight')
def product_details_weight():
    """Serve the weight-based product details page"""
    return render_template('product_details_weight.html')

@app.route('/customer-ledger')
def customer_ledger():
    """Serve the customer ledger page"""
    return render_template('customer_ledger.html')

@app.route('/receipt')
def receipt():
    """Serve the receipt page"""
    return render_template('receipt.html')

@app.route('/bill-generate')
def bill_generate():
    """Serve the bill generation page"""
    return render_template('bill_generate.html')

@app.route('/low-stock')
def low_stock():
    """Serve the low stock alert page"""
    return render_template('low_stock.html')

@app.route('/expiry-alert')
def expiry_alert():
    """Serve the expiry alert page"""
    return render_template('expiry_alert.html')

@app.route('/pending-credits')
def pending_credits():
    """Serve the pending credits page"""
    return render_template('pending_credits.html')

@app.route('/settings')
def settings():
    """Serve the settings page"""
    return render_template('settings.html')

@app.route('/refill-stock')
def refill_stock():
    """Serve the refill stock page"""
    return render_template('refill_stock.html')

@app.route('/staff')
def staff():
    """Serve the staff management page"""
    return render_template('staff.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
