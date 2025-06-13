import os
import logging
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.units import inch
from io import BytesIO

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
    cost_price = db.Column(db.Float, default=0)  # Purchase/cost price
    price_per_kg = db.Column(db.Float)  # For weight-based items
    is_weight_based = db.Column(db.Boolean, default=False)
    
    # Inventory
    stock_quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=10)
    expiry_date = db.Column(db.Date)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)  # subscription, backup, inventory, payment, system
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, urgent
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Optional references
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)

# Notification helper functions
def create_notification(title, message, notification_type, priority='medium', customer_id=None, bill_id=None, product_id=None):
    """Create a new notification in the database"""
    try:
        notification = Notification(
            title=title,
            message=message,
            type=notification_type,
            priority=priority,
            customer_id=customer_id,
            bill_id=bill_id,
            product_id=product_id
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception as e:
        app.logger.error(f"Failed to create notification: {e}")
        db.session.rollback()
        return None

def check_subscription_expiry():
    """Check if subscription is expiring and create notification"""
    # For production, this would check actual subscription status
    # Currently creating demo notification for UI
    try:
        existing = Notification.query.filter_by(type='subscription', is_read=False).first()
        if not existing:
            create_notification(
                "Subscription Expiring Soon",
                "Your Kirana Konnect subscription expires in 3 days. Renew now to continue using all features.",
                "subscription",
                "high"
            )
    except Exception as e:
        app.logger.error(f"Error checking subscription: {e}")

def check_backup_status():
    """Check backup status and create notification if needed"""
    try:
        # Always create backup notification since we don't have real backup status tracking
        # In production, this would check actual backup configuration
        existing = Notification.query.filter_by(type='backup', is_read=False).first()
        if not existing:
            create_notification(
                "Enable Data Backup",
                "Protect your business data by enabling automatic cloud backup in settings.",
                "backup",
                "high"
            )
    except Exception as e:
        app.logger.error(f"Error checking backup status: {e}")

@app.route('/api/backup/disable', methods=['POST'])
def disable_backup():
    """API endpoint to handle backup disable and create notification"""
    try:
        # Remove existing backup notifications
        existing_notifications = Notification.query.filter_by(type='backup', is_read=False).all()
        for notif in existing_notifications:
            db.session.delete(notif)
        
        # Create new backup warning notification
        create_notification(
            "Data Backup Disabled!",
            "Your business data backup is disabled. Enable backup immediately to prevent data loss.",
            "backup",
            "urgent"
        )
        
        return jsonify({'success': True, 'message': 'Backup disabled, notification created'})
    except Exception as e:
        app.logger.error(f"Error handling backup disable: {e}")
        return jsonify({'error': 'Failed to process backup disable'}), 500

@app.route('/api/backup/enable', methods=['POST'])
def enable_backup():
    """API endpoint to handle backup enable and remove notifications"""
    try:
        # Remove backup notifications when backup is enabled
        existing_notifications = Notification.query.filter_by(type='backup', is_read=False).all()
        for notif in existing_notifications:
            db.session.delete(notif)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Backup enabled, notifications cleared'})
    except Exception as e:
        app.logger.error(f"Error handling backup enable: {e}")
        return jsonify({'error': 'Failed to process backup enable'}), 500

def check_low_stock():
    """Check for low stock items and create notifications"""
    try:
        low_stock_products = Product.query.filter(Product.stock_quantity <= Product.reorder_level).all()
        for product in low_stock_products:
            # Check if notification already exists for this product
            existing = Notification.query.filter_by(
                type='inventory', 
                product_id=product.id, 
                is_read=False
            ).first()
            
            if not existing:
                create_notification(
                    f"Low Stock Alert: {product.name}",
                    f"Only {product.stock_quantity} units left. Reorder level: {product.reorder_level}",
                    "inventory",
                    "high",
                    product_id=product.id
                )
    except Exception as e:
        app.logger.error(f"Error checking low stock: {e}")

def check_expiring_products():
    """Check for products expiring soon and create notifications"""
    try:
        from datetime import date, timedelta
        expiry_threshold = date.today() + timedelta(days=7)
        
        expiring_products = Product.query.filter(
            Product.expiry_date.isnot(None),
            Product.expiry_date <= expiry_threshold
        ).all()
        
        for product in expiring_products:
            # Check if notification already exists for this product
            existing = Notification.query.filter_by(
                type='expiry', 
                product_id=product.id, 
                is_read=False
            ).first()
            
            if not existing:
                days_to_expiry = (product.expiry_date - date.today()).days
                create_notification(
                    f"Product Expiring: {product.name}",
                    f"Expires in {days_to_expiry} days on {product.expiry_date.strftime('%d/%m/%Y')}",
                    "expiry",
                    "urgent" if days_to_expiry <= 3 else "high",
                    product_id=product.id
                )
    except Exception as e:
        app.logger.error(f"Error checking expiring products: {e}")

# Simplified database initialization - only create tables
def init_db():
    """Initialize database tables without heavy seeding"""
    try:
        db.create_all()
        app.logger.info("Database tables created successfully")
    except Exception as e:
        app.logger.error(f"Database initialization error: {e}")

# Initialize database tables and add sample products
def ensure_sample_products():
    """Add sample products with real barcodes for scanner functionality"""
    try:
        # Check if products already exist
        if Product.query.count() > 0:
            return
        
        from datetime import date, timedelta
        
        sample_products = [
            {
                'name': 'Fortune Sunflower Oil',
                'barcode': '8901030870391',
                'category': 'oils',
                'price': 180.0,
                'cost_price': 165.0,
                'is_weight_based': False,
                'stock_quantity': 25,
                'reorder_level': 5,
                'expiry_date': date.today() + timedelta(days=365)
            },
            {
                'name': 'Aashirvaad Atta',
                'barcode': '8901030827604',
                'category': 'grains',
                'price': 120.0,
                'cost_price': 110.0,
                'is_weight_based': False,
                'stock_quantity': 15,
                'reorder_level': 3,
                'expiry_date': date.today() + timedelta(days=180)
            },
            {
                'name': 'Basmati Rice',
                'barcode': '8901030870384',
                'category': 'grains',
                'price': 85.0,
                'price_per_kg': 85.0,
                'cost_price': 75.0,
                'is_weight_based': True,
                'stock_quantity': 50,
                'reorder_level': 10,
                'expiry_date': date.today() + timedelta(days=120)
            },
            {
                'name': 'Maggi Noodles',
                'barcode': '8901030875099',
                'category': 'snacks',
                'price': 14.0,
                'cost_price': 12.0,
                'is_weight_based': False,
                'stock_quantity': 100,
                'reorder_level': 20,
                'expiry_date': date.today() + timedelta(days=90)
            },
            {
                'name': 'Tata Salt',
                'barcode': '8901030821015',
                'category': 'household',
                'price': 22.0,
                'cost_price': 20.0,
                'is_weight_based': False,
                'stock_quantity': 30,
                'reorder_level': 8,
                'expiry_date': date.today() + timedelta(days=730)
            }
        ]
        
        for product_data in sample_products:
            product = Product(
                name=product_data['name'],
                barcode=product_data['barcode'],
                category=product_data['category'],
                price=product_data['price'],
                price_per_kg=product_data.get('price_per_kg'),
                cost_price=product_data['cost_price'],
                is_weight_based=product_data['is_weight_based'],
                stock_quantity=product_data['stock_quantity'],
                reorder_level=product_data['reorder_level'],
                expiry_date=product_data['expiry_date']
            )
            db.session.add(product)
        
        db.session.commit()
        app.logger.info("Sample products added to database")
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding sample products: {e}")

# Initialize database tables once at startup
try:
    with app.app_context():
        db.create_all()
        ensure_sample_products()
        app.logger.info("Database initialized successfully")
except Exception as e:
    app.logger.error(f"Database initialization failed: {e}")

def ensure_db_initialized():
    # Database is already initialized at startup
    pass

@app.route('/')
def index():
    """Serve the Kirana Konnect splash screen"""
    ensure_db_initialized()
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

@app.route('/notifications')
def notifications():
    """Serve the notifications page"""
    return render_template('notifications.html')

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

@app.route('/refill-stock-weight')
def refill_stock_weight():
    """Serve the weight-based refill stock page"""
    return render_template('refill_stock_weight.html')

@app.route('/staff')
def staff():
    """Serve the staff management page"""
    return render_template('staff.html')

# API Endpoints for Customer Management and Billing

@app.route('/api/products')
def get_products():
    """Get all products for inventory display"""
    products = Product.query.all()
    
    results = []
    for product in products:
        # Check if product is low stock or expired
        is_low_stock = product.stock_quantity <= product.reorder_level
        is_expired = product.expiry_date and product.expiry_date < datetime.utcnow().date()
        
        results.append({
            'id': str(product.id),
            'name': product.name,
            'barcode': product.barcode,
            'category': product.category or 'general',
            'price': product.price,
            'price_per_kg': product.price_per_kg,
            'is_weight_based': product.is_weight_based,
            'stock_quantity': product.stock_quantity,
            'reorder_level': product.reorder_level,
            'expiry_date': product.expiry_date.strftime('%d/%m/%Y') if product.expiry_date else None,
            'is_low_stock': is_low_stock,
            'is_expired': is_expired,
            'unit': 'kg' if product.is_weight_based else 'Piece'
        })
    
    return jsonify({'products': results})

@app.route('/api/dashboard/stats')
def get_dashboard_stats():
    """Get dashboard statistics including today's profit"""
    today = datetime.utcnow().date()
    
    # Calculate today's sales
    today_bills = Bill.query.filter(
        db.func.date(Bill.created_at) == today,
        Bill.payment_status == 'paid'
    ).all()
    
    total_sales = sum(bill.total_amount for bill in today_bills)
    transaction_count = len(today_bills)
    
    # Calculate actual cost of goods sold based on products sold today
    actual_cost = 0
    total_revenue = 0
    
    for bill in today_bills:
        bill_items = BillItem.query.filter_by(bill_id=bill.id).all()
        for item in bill_items:
            # Get product cost from database
            product = Product.query.filter_by(name=item.item_name).first()
            if product and product.cost_price > 0:
                # Use actual cost price from database
                if product.is_weight_based and item.weight:
                    # For weight-based items, calculate based on weight
                    item_cost = (product.cost_price / 1000) * item.weight if product.price_per_kg else product.cost_price * item.quantity
                else:
                    # For regular items
                    item_cost = product.cost_price * item.quantity
                actual_cost += item_cost
                total_revenue += item.total_price
            elif product:
                # Fallback if cost price not set
                item_cost = item.unit_price * 0.65 * item.quantity
                actual_cost += item_cost
                total_revenue += item.total_price
    
    today_profit = total_revenue - actual_cost
    
    # Get yesterday's sales for comparison
    yesterday = today - timedelta(days=1)
    yesterday_bills = Bill.query.filter(
        db.func.date(Bill.created_at) == yesterday,
        Bill.payment_status == 'paid'
    ).all()
    
    yesterday_sales = sum(bill.total_amount for bill in yesterday_bills)
    
    # Calculate yesterday's actual profit using same method
    yesterday_cost = 0
    yesterday_revenue = 0
    
    for bill in yesterday_bills:
        bill_items = BillItem.query.filter_by(bill_id=bill.id).all()
        for item in bill_items:
            product = Product.query.filter_by(name=item.item_name).first()
            if product and product.cost_price > 0:
                if product.is_weight_based and item.weight:
                    item_cost = (product.cost_price / 1000) * item.weight if product.price_per_kg else product.cost_price * item.quantity
                else:
                    item_cost = product.cost_price * item.quantity
                yesterday_cost += item_cost
                yesterday_revenue += item.total_price
            elif product:
                item_cost = item.unit_price * 0.65 * item.quantity
                yesterday_cost += item_cost
                yesterday_revenue += item.total_price
    
    yesterday_profit = yesterday_revenue - yesterday_cost
    
    # Calculate profit growth
    profit_growth = 0
    if yesterday_profit > 0:
        profit_growth = ((today_profit - yesterday_profit) / yesterday_profit) * 100
    elif yesterday_profit == 0 and today_profit > 0:
        profit_growth = 100  # 100% increase from zero
    elif yesterday_profit == 0 and today_profit == 0:
        profit_growth = 0    # No change when both are zero
    
    # Get outstanding credit amounts
    outstanding_customers = Customer.query.all()
    total_outstanding = sum(customer.outstanding_balance for customer in outstanding_customers)
    customers_with_credit = len([c for c in outstanding_customers if c.outstanding_balance > 0])
    
    # Get inventory stats
    all_products = Product.query.all()
    total_products = len(all_products)
    expired_products = len([p for p in all_products if p.expiry_date and p.expiry_date < today])
    low_stock_products = len([p for p in all_products if p.stock_quantity <= p.reorder_level])
    
    return jsonify({
        'today_profit': round(today_profit, 2),
        'profit_growth': round(profit_growth, 1),
        'total_sales': round(total_sales, 2),
        'actual_cost': round(actual_cost, 2),
        'total_revenue': round(total_revenue, 2),
        'transaction_count': transaction_count,
        'outstanding_amount': round(total_outstanding, 2),
        'customers_with_credit': customers_with_credit,
        'total_products': total_products,
        'expired_products': expired_products,
        'low_stock_products': low_stock_products
    })

@app.route('/api/customers/search')
def search_customers():
    """Search customers by name or phone number"""
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return jsonify([])
    
    customers = Customer.query.filter(
        db.or_(
            Customer.name.ilike(f'%{query}%'),
            Customer.phone.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    results = []
    for customer in customers:
        outstanding = customer.outstanding_balance
        results.append({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'outstanding': f'₹{outstanding:.0f}' if outstanding > 0 else 'No Outstanding',
            'outstanding_amount': outstanding
        })
    
    return jsonify(results)

@app.route('/api/customers', methods=['POST'])
def create_customer():
    """Create a new customer"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name') or not data.get('phone'):
            return jsonify({'error': 'Name and phone are required'}), 400
        
        customer = Customer(
            name=data['name'],
            phone=data['phone'],
            address=data.get('address', ''),
            aadhar_number=data.get('aadhar_number', ''),
            email=data.get('email', '')
        )
        
        db.session.add(customer)
        db.session.commit()
        
        return jsonify({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'message': 'Customer created successfully'
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error creating customer: {e}")
        return jsonify({'error': 'Failed to create customer'}), 500

@app.route('/api/bills', methods=['POST'])
def create_bill():
    """Generate a new bill and save it to database"""
    data = request.get_json()
    
    # Generate bill number
    import random
    bill_number = f"KK-{datetime.now().year}-{random.randint(1000, 9999)}"
    
    # Create the bill
    bill = Bill(
        bill_number=bill_number,
        customer_id=data.get('customer_id'),
        customer_name=data.get('customer_name'),
        subtotal=data['subtotal'],
        tax_amount=data.get('tax_amount', 0),
        discount_amount=data.get('discount_amount', 0),
        total_amount=data['total_amount'],
        payment_mode=data['payment_mode'],
        payment_status='pending' if data['payment_mode'] == 'credit' else 'paid',
        generated_by=data.get('generated_by', 'System'),
        include_dates=data.get('include_dates', True)
    )
    
    db.session.add(bill)
    db.session.flush()  # Get the bill ID
    
    # Add bill items
    for item_data in data.get('items', []):
        bill_item = BillItem(
            bill_id=bill.id,
            item_name=item_data['name'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            total_price=item_data['total_price'],
            weight=item_data.get('weight'),
            price_per_kg=item_data.get('price_per_kg')
        )
        db.session.add(bill_item)
    
    # If payment is made, create payment record
    if data['payment_mode'] != 'credit' and data.get('customer_id'):
        payment = Payment(
            customer_id=data['customer_id'],
            bill_id=bill.id,
            amount=data['total_amount'],
            payment_mode=data['payment_mode'],
            reference_number=data.get('reference_number')
        )
        db.session.add(payment)
    
    db.session.commit()
    
    return jsonify({
        'bill_id': bill.id,
        'bill_number': bill.bill_number,
        'message': 'Bill generated successfully'
    })

@app.route('/api/customers/<int:customer_id>/ledger')
def api_customer_ledger(customer_id):
    """Get customer's ledger with bills and payments"""
    customer = Customer.query.get_or_404(customer_id)
    
    bills = Bill.query.filter_by(customer_id=customer_id).order_by(Bill.created_at.desc()).all()
    payments = Payment.query.filter_by(customer_id=customer_id).order_by(Payment.created_at.desc()).all()
    
    bill_data = []
    for bill in bills:
        bill_data.append({
            'id': bill.id,
            'bill_number': bill.bill_number,
            'amount': bill.total_amount,
            'payment_status': bill.payment_status,
            'created_at': bill.created_at.strftime('%Y-%m-%d %H:%M'),
            'items': [{'name': item.item_name, 'quantity': item.quantity, 'total': item.total_price} 
                     for item in bill.items]
        })
    
    payment_data = []
    for payment in payments:
        payment_data.append({
            'id': payment.id,
            'amount': payment.amount,
            'payment_mode': payment.payment_mode,
            'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M'),
            'reference_number': payment.reference_number
        })
    
    return jsonify({
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'outstanding_balance': customer.outstanding_balance
        },
        'bills': bill_data,
        'payments': payment_data
    })

@app.route('/api/bills/<bill_number>')
def api_get_bill(bill_number):
    """Get bill details by bill number"""
    try:
        bill = Bill.query.filter_by(bill_number=bill_number).first()
        if not bill:
            return jsonify({'success': False, 'error': 'Bill not found'}), 404
        
        # Get bill items
        items = BillItem.query.filter_by(bill_id=bill.id).all()
        
        return jsonify({
            'success': True,
            'bill_number': bill.bill_number,
            'customer_name': bill.customer_name,
            'subtotal': bill.subtotal,
            'tax_amount': bill.tax_amount,
            'discount_amount': bill.discount_amount,
            'total_amount': bill.total_amount,
            'payment_mode': bill.payment_mode,
            'payment_status': bill.payment_status,
            'generated_by': bill.generated_by,
            'created_at': bill.created_at.isoformat(),
            'include_dates': bill.include_dates,
            'items': [{
                'item_name': item.item_name,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total_price': item.total_price,
                'weight': item.weight,
                'price_per_kg': item.price_per_kg
            } for item in items]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/payments', methods=['POST'])
def create_payment():
    """Record a payment for a customer"""
    try:
        data = request.get_json()
        
        customer_id = data.get('customer_id')
        amount = data.get('amount')
        payment_mode = data.get('payment_mode', 'cash')
        reference_number = data.get('reference_number', '')
        notes = data.get('notes', '')
        
        if not customer_id or not amount:
            return jsonify({'error': 'Customer ID and amount are required'}), 400
        
        # Create new payment record
        payment = Payment(
            customer_id=customer_id,
            amount=amount,
            payment_mode=payment_mode,
            reference_number=reference_number,
            notes=notes,
            created_at=datetime.utcnow()
        )
        
        db.session.add(payment)
        db.session.commit()
        
        return jsonify({'message': 'Payment recorded successfully', 'payment_id': payment.id}), 201
        
    except Exception as e:
        logging.error(f"Error creating payment: {str(e)}")
        return jsonify({'error': 'Failed to record payment'}), 500

@app.route('/api/notifications')
def get_notifications():
    """Get all notifications from database"""
    try:
        # Initialize database tables if needed
        ensure_db_initialized()
        
        # Run notification checks to ensure latest data
        try:
            check_subscription_expiry()
            check_backup_status()
            check_low_stock()
            check_expiring_products()
        except Exception as check_error:
            app.logger.warning(f"Error running notification checks: {check_error}")
        
        # Fetch all unread notifications, ordered by priority and creation time
        notifications = Notification.query.filter_by(is_read=False).order_by(
            Notification.created_at.desc()
        ).all()
        
        notification_data = []
        for notif in notifications:
            try:
                notification_data.append({
                    'id': notif.id,
                    'title': notif.title,
                    'message': notif.message,
                    'type': notif.type,
                    'priority': notif.priority,
                    'created_at': notif.created_at.isoformat(),
                    'time_ago': get_time_ago(notif.created_at)
                })
            except Exception as item_error:
                app.logger.warning(f"Error processing notification {notif.id}: {item_error}")
                continue
        
        return jsonify({
            'notifications': notification_data,
            'count': len(notification_data)
        })
        
    except Exception as e:
        app.logger.error(f"Error fetching notifications: {e}")
        # Return empty response instead of error to prevent frontend issues
        return jsonify({
            'notifications': [],
            'count': 0
        })

@app.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        notification = Notification.query.get_or_404(notification_id)
        notification.is_read = True
        db.session.commit()
        
        return jsonify({'message': 'Notification marked as read'})
        
    except Exception as e:
        app.logger.error(f"Error marking notification as read: {e}")
        return jsonify({'error': 'Failed to update notification'}), 500

def get_time_ago(datetime_obj):
    """Calculate human-readable time difference"""
    now = datetime.utcnow()
    diff = now - datetime_obj
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

@app.route('/export-business-data')
def export_business_data():
    """Export comprehensive business data as PDF"""
    try:
        # Create PDF buffer
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.75*inch, leftMargin=0.75*inch,
                              topMargin=0.75*inch, bottomMargin=0.75*inch)
        
        # Define simple, clean styles
        styles = getSampleStyleSheet()
        
        # Company header style with logo placeholder
        company_style = ParagraphStyle(
            'CompanyHeader',
            parent=styles['Title'],
            fontSize=20,
            spaceAfter=5,
            alignment=1,
            textColor=colors.HexColor('#2563eb'),
            fontName='Helvetica-Bold'
        )
        
        # Simple title style
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=15,
            alignment=1,
            textColor=colors.HexColor('#1f2937'),
            fontName='Helvetica'
        )
        
        # Clean section heading
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading3'],
            fontSize=12,
            spaceAfter=10,
            spaceBefore=20,
            textColor=colors.HexColor('#1f2937'),
            fontName='Helvetica-Bold',
            backColor=colors.HexColor('#f8fafc'),
            borderWidth=1,
            borderColor=colors.HexColor('#e2e8f0'),
            leftIndent=10,
            rightIndent=10,
            topPadding=6,
            bottomPadding=6
        )
        
        # Normal text style
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            fontName='Helvetica'
        )
        
        # Simple summary style
        summary_style = ParagraphStyle(
            'Summary',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#6b7280'),
            fontName='Helvetica',
            alignment=1
        )
        
        # Story list to hold all content
        story = []
        
        # Professional Header with branding
        header_table = Table([
            ['🏪 KIRANA KONNECT', 'Business Report'],
            ['Your Store Management Solution', f'Generated: {datetime.now().strftime("%d-%m-%Y")}']
        ], colWidths=[3*inch, 3*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, 0), 16),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (1, 0), 14),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, 1), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15)
        ]))
        story.append(header_table)
        story.append(Spacer(1, 25))
        
        # Calculate summary metrics first
        products = Product.query.all()
        bills = Bill.query.all()
        customers = Customer.query.all()
        payments = Payment.query.all()
        
        total_products = len(products)
        total_investment = sum([(p.price * p.stock_quantity) for p in products if p.price])
        total_sales = sum([b.total_amount for b in bills])
        total_customers = len(customers)
        total_outstanding = sum([c.outstanding_balance for c in customers])
        
        # Simple Business Summary
        story.append(Paragraph("BUSINESS SUMMARY", heading_style))
        
        summary_data = [
            ['Total Products in Store', str(total_products)],
            ['Money Invested', f'₹{total_investment:,.0f}'],
            ['Total Sales Made', f'₹{total_sales:,.0f}'],
            ['Number of Customers', str(total_customers)],
            ['Money to Collect', f'₹{total_outstanding:,.0f}']
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12)
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # 1. INVENTORY DATA
        story.append(Paragraph("MY PRODUCTS", heading_style))
        
        if products:
            inventory_data = [['Product Name', 'Buy Price', 'Sell Price', 'Stock']]
            
            for product in products[:20]:  # Show only first 20 products for simplicity
                product_name = product.name[:25] + '...' if len(product.name) > 25 else product.name
                buy_price = product.price if product.price else 0
                sell_price = product.price if product.price else 0
                
                inventory_data.append([
                    product_name,
                    f"₹{buy_price:.0f}",
                    f"₹{sell_price:.0f}",
                    str(product.stock_quantity)
                ])
            
            inventory_table = Table(inventory_data, colWidths=[3*inch, 1.2*inch, 1.2*inch, 1*inch])
            inventory_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6)
            ]))
            story.append(inventory_table)
            
            if len(products) > 20:
                story.append(Paragraph(f"Showing 20 out of {len(products)} products", summary_style))
        else:
            story.append(Paragraph("No products found", normal_style))
        
        story.append(PageBreak())
        
        # 2. SALES DATA
        story.append(Paragraph("MY SALES", heading_style))
        
        if bills:
            bills_data = [['Bill Number', 'Customer', 'Amount', 'Date']]
            
            for bill in bills[:15]:  # Show only recent 15 bills
                customer_name = bill.customer_name or 'Cash Sale'
                if len(customer_name) > 20:
                    customer_name = customer_name[:17] + '...'
                
                bills_data.append([
                    bill.bill_number,
                    customer_name,
                    f"₹{bill.total_amount:,.0f}",
                    bill.created_at.strftime('%d-%m-%Y')
                ])
            
            bills_table = Table(bills_data, colWidths=[1.8*inch, 2*inch, 1.2*inch, 1.4*inch])
            bills_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6)
            ]))
            story.append(bills_table)
            
            if len(bills) > 15:
                story.append(Paragraph(f"Showing recent 15 out of {len(bills)} total sales", summary_style))
                
            story.append(Spacer(1, 15))
            story.append(Paragraph(f"Total Sales Made: ₹{sum([b.total_amount for b in bills]):,.0f}", normal_style))
        else:
            story.append(Paragraph("No sales found", normal_style))
        
        story.append(PageBreak())
        
        # 3. MY CUSTOMERS
        story.append(Paragraph("MY CUSTOMERS", heading_style))
        
        if customers:
            customer_data = [['Customer Name', 'Phone', 'Money to Collect']]
            
            for customer in customers[:15]:  # Show only first 15 customers
                outstanding = customer.outstanding_balance
                customer_name = customer.name[:25] + '...' if len(customer.name) > 25 else customer.name
                
                customer_data.append([
                    customer_name,
                    customer.phone,
                    f"₹{outstanding:,.0f}" if outstanding > 0 else "Paid"
                ])
            
            customer_table = Table(customer_data, colWidths=[2.5*inch, 1.8*inch, 1.5*inch])
            customer_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6)
            ]))
            story.append(customer_table)
            
            if len(customers) > 15:
                story.append(Paragraph(f"Showing 15 out of {len(customers)} customers", summary_style))
                
            story.append(Spacer(1, 15))
            story.append(Paragraph(f"Total Money to Collect: ₹{sum([c.outstanding_balance for c in customers]):,.0f}", normal_style))
        else:
            story.append(Paragraph("No customers found", normal_style))
        
        # Add branded footer
        story.append(Spacer(1, 50))
        
        # Footer with company branding
        footer_table = Table([
            ['Thank you for using Kirana Konnect', 'Report End'],
            ['© 2024 Kirana Konnect Inc.', f'Page Generated: {datetime.now().strftime("%d-%m-%Y")}']
        ], colWidths=[3*inch, 3*inch])
        footer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#374151')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, 1), 8),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb'))
        ]))
        story.append(footer_table)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'kirana_business_data_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logging.error(f"Error generating business data export: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to generate export'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
