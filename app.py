import os
import logging
from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
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

# API Endpoints for Customer Management and Billing

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
        generated_by=data.get('generated_by', 'System')
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

@app.route('/export-business-data')
def export_business_data():
    """Export comprehensive business data as PDF"""
    try:
        # Create PDF buffer
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.75*inch, leftMargin=0.75*inch,
                              topMargin=0.75*inch, bottomMargin=0.75*inch)
        
        # Define custom styles
        styles = getSampleStyleSheet()
        
        # Company header style
        company_style = ParagraphStyle(
            'CompanyHeader',
            parent=styles['Title'],
            fontSize=24,
            spaceAfter=8,
            alignment=1,
            textColor=colors.HexColor('#1f2937'),
            fontName='Helvetica-Bold'
        )
        
        # Report title style
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            alignment=1,
            textColor=colors.HexColor('#2563eb'),
            fontName='Helvetica-Bold'
        )
        
        # Section heading style
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=8,
            spaceBefore=15,
            textColor=colors.HexColor('#1f2937'),
            fontName='Helvetica-Bold',
            borderWidth=0,
            borderColor=colors.HexColor('#e5e7eb'),
            borderPadding=8,
            backColor=colors.HexColor('#f9fafb')
        )
        
        # Summary box style
        summary_style = ParagraphStyle(
            'Summary',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#374151'),
            fontName='Helvetica'
        )
        
        # Story list to hold all content
        story = []
        
        # Company Header with logo placeholder
        story.append(Paragraph("KIRANA KONNECT", company_style))
        story.append(Paragraph("Complete Business Data Report", title_style))
        story.append(Paragraph(f"Report Generated: {datetime.now().strftime('%d %B %Y at %H:%M')}", summary_style))
        story.append(Spacer(1, 30))
        
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
        
        # Executive Summary Box
        summary_data = [
            ['Business Metric', 'Value', 'Status'],
            ['Total Products', str(total_products), '✓ Active'],
            ['Total Investment', f'₹{total_investment:,.2f}', '💰 Capital'],
            ['Total Sales Revenue', f'₹{total_sales:,.2f}', '📈 Revenue'],
            ['Active Customers', str(total_customers), '👥 Base'],
            ['Outstanding Amount', f'₹{total_outstanding:,.2f}', '⚠️ Pending']
        ]
        
        summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch, 1.2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])
        ]))
        
        story.append(Paragraph("📊 EXECUTIVE SUMMARY", heading_style))
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # 1. INVENTORY DATA
        story.append(Paragraph("🏪 INVENTORY OVERVIEW", heading_style))
        
        if products:
            inventory_data = [['Product Name', 'Category', 'Buy Price', 'Sell Price', 'Profit', 'Stock', 'Added']]
            inv_total_investment = 0
            inv_total_potential_revenue = 0
            
            for product in products:
                purchase_price = product.price_per_kg if product.is_weight_based else product.price
                sell_price = product.price_per_kg if product.is_weight_based else product.price
                profit_per_unit = sell_price - purchase_price if purchase_price else 0
                
                inv_total_investment += (purchase_price * product.stock_quantity) if purchase_price else 0
                inv_total_potential_revenue += (sell_price * product.stock_quantity) if sell_price else 0
                
                # Truncate long product names
                product_name = product.name[:20] + '...' if len(product.name) > 20 else product.name
                category = product.category[:15] if product.category else 'General'
                
                inventory_data.append([
                    product_name,
                    category,
                    f"₹{purchase_price:.0f}" if purchase_price else '-',
                    f"₹{sell_price:.0f}" if sell_price else '-',
                    f"₹{profit_per_unit:.0f}" if profit_per_unit else '-',
                    str(product.stock_quantity),
                    product.created_at.strftime('%d/%m/%y') if product.created_at else '-'
                ])
            
            inventory_table = Table(inventory_data, colWidths=[1.8*inch, 1*inch, 0.8*inch, 0.8*inch, 0.7*inch, 0.6*inch, 0.8*inch])
            inventory_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            story.append(inventory_table)
            
            # Investment Summary Box
            story.append(Spacer(1, 12))
            summary_box_data = [
                ['💰 Total Investment', f'₹{inv_total_investment:,.0f}'],
                ['💵 Potential Revenue', f'₹{inv_total_potential_revenue:,.0f}'],
                ['📈 Potential Profit', f'₹{inv_total_potential_revenue - inv_total_investment:,.0f}']
            ]
            
            summary_box = Table(summary_box_data, colWidths=[2.5*inch, 2*inch])
            summary_box.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#10b981')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
            ]))
            story.append(summary_box)
        else:
            story.append(Paragraph("📦 No inventory items found", summary_style))
        
        story.append(PageBreak())
        
        # 2. BILLS DATA
        story.append(Paragraph("💳 SALES TRANSACTIONS", heading_style))
        
        if bills:
            bills_data = [['Bill #', 'Customer', 'Amount', 'Mode', 'Status', 'Date']]
            bills_total_sales = 0
            
            for bill in bills[:50]:  # Limit to recent 50 bills for space
                customer_name = bill.customer_name or 'Walk-in'
                if len(customer_name) > 15:
                    customer_name = customer_name[:12] + '...'
                
                status_icon = '✅' if bill.payment_status == 'paid' else '⏳' if bill.payment_status == 'pending' else '🔄'
                
                bills_data.append([
                    bill.bill_number[:8] + '...' if len(bill.bill_number) > 8 else bill.bill_number,
                    customer_name,
                    f"₹{bill.total_amount:,.0f}",
                    bill.payment_mode.title()[:6],
                    f"{status_icon} {bill.payment_status.title()}",
                    bill.created_at.strftime('%d/%m/%y')
                ])
                bills_total_sales += bill.total_amount
            
            bills_table = Table(bills_data, colWidths=[1.2*inch, 1.5*inch, 1*inch, 0.8*inch, 1.2*inch, 0.8*inch])
            bills_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            story.append(bills_table)
            
            if len(bills) > 50:
                story.append(Paragraph(f"📋 Showing recent 50 bills out of {len(bills)} total transactions", summary_style))
            
            # Sales Summary Box
            story.append(Spacer(1, 12))
            sales_summary_data = [
                ['💰 Total Sales Revenue', f'₹{bills_total_sales:,.0f}'],
                ['📊 Total Transactions', f'{len(bills)} bills'],
                ['📈 Average Bill Value', f'₹{bills_total_sales/len(bills):,.0f}' if len(bills) > 0 else '₹0']
            ]
            
            sales_summary = Table(sales_summary_data, colWidths=[2.5*inch, 2*inch])
            sales_summary.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef3c7')),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#f59e0b')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
            ]))
            story.append(sales_summary)
        else:
            story.append(Paragraph("📋 No sales transactions found", summary_style))
        
        story.append(PageBreak())
        
        # 3. CUSTOMER DATA WITH OUTSTANDING BALANCES
        story.append(Paragraph("👥 CUSTOMER LEDGER", heading_style))
        
        if customers:
            customer_data = [['Customer', 'Phone', 'Outstanding', 'Total Bills', 'Payments', 'Since']]
            cust_total_outstanding = 0
            
            for customer in customers:
                outstanding = customer.outstanding_balance
                total_bills_amount = sum([bill.total_amount for bill in customer.bills])
                total_payments_amount = sum([payment.amount for payment in customer.payments])
                
                customer_name = customer.name[:18] + '...' if len(customer.name) > 18 else customer.name
                phone_display = customer.phone[-4:] if len(customer.phone) > 4 else customer.phone
                
                customer_data.append([
                    customer_name,
                    f"***{phone_display}",
                    f"₹{outstanding:,.0f}",
                    f"₹{total_bills_amount:,.0f}",
                    f"₹{total_payments_amount:,.0f}",
                    customer.created_at.strftime('%m/%y') if customer.created_at else '-'
                ])
                cust_total_outstanding += outstanding
            
            customer_table = Table(customer_data, colWidths=[1.8*inch, 1*inch, 1*inch, 1*inch, 1*inch, 0.7*inch])
            customer_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            story.append(customer_table)
            
            # Customer Summary Box
            story.append(Spacer(1, 12))
            customer_summary_data = [
                ['👥 Total Customers', f'{len(customers)} accounts'],
                ['💳 Outstanding Credit', f'₹{cust_total_outstanding:,.0f}'],
                ['🔄 Active Accounts', f'{len([c for c in customers if c.outstanding_balance > 0])} customers']
            ]
            
            customer_summary = Table(customer_summary_data, colWidths=[2.5*inch, 2*inch])
            customer_summary.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef2f2')),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ef4444')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
            ]))
            story.append(customer_summary)
        else:
            story.append(Paragraph("👤 No customer records found", summary_style))
        
        story.append(PageBreak())
        
        # 4. PAYMENT RECORDS
        story.append(Paragraph("💰 PAYMENT RECORDS", heading_style))
        
        if payments:
            payment_data = [['Date', 'Customer', 'Amount', 'Mode', 'Reference']]
            pay_total_payments = 0
            
            for payment in payments[:30]:  # Limit to recent 30 payments
                customer_name = payment.customer.name[:15] + '...' if payment.customer and len(payment.customer.name) > 15 else payment.customer.name if payment.customer else 'Unknown'
                reference = payment.reference_number[:12] + '...' if payment.reference_number and len(payment.reference_number) > 12 else payment.reference_number or '-'
                
                payment_data.append([
                    payment.created_at.strftime('%d/%m/%y'),
                    customer_name,
                    f"₹{payment.amount:,.0f}",
                    payment.payment_mode.title()[:8],
                    reference
                ])
                pay_total_payments += payment.amount
            
            payment_table = Table(payment_data, colWidths=[0.8*inch, 1.8*inch, 1*inch, 1*inch, 1.9*inch])
            payment_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            story.append(payment_table)
            
            if len(payments) > 30:
                story.append(Paragraph(f"💳 Showing recent 30 payments out of {len(payments)} total records", summary_style))
            
            # Payment Summary Box
            story.append(Spacer(1, 12))
            payment_summary_data = [
                ['💰 Total Payments', f'₹{sum([p.amount for p in payments]):,.0f}'],
                ['📊 Payment Count', f'{len(payments)} transactions'],
                ['📈 Average Payment', f'₹{sum([p.amount for p in payments])/len(payments):,.0f}' if len(payments) > 0 else '₹0']
            ]
            
            payment_summary = Table(payment_summary_data, colWidths=[2.5*inch, 2*inch])
            payment_summary.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#22c55e')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
            ]))
            story.append(payment_summary)
        else:
            story.append(Paragraph("💳 No payment records found", summary_style))
        
        # Final Summary Page
        story.append(PageBreak())
        story.append(Paragraph("📋 BUSINESS PERFORMANCE SUMMARY", heading_style))
        
        # Overall business metrics
        overall_summary_data = [
            ['Key Performance Indicator', 'Current Value', 'Performance'],
            ['Total Business Investment', f'₹{total_investment:,.0f}', '💰 Capital Base'],
            ['Total Revenue Generated', f'₹{total_sales:,.0f}', '📈 Income Stream'],
            ['Customer Base Size', f'{total_customers} customers', '👥 Market Reach'],
            ['Outstanding Receivables', f'₹{total_outstanding:,.0f}', '⚠️ Credit Risk'],
            ['Product Portfolio', f'{total_products} items', '📦 Inventory Size'],
            ['Profit Potential', f'₹{sum([(p.price * p.stock_quantity) for p in products if p.price]) - total_investment:,.0f}', '💡 Growth Opportunity']
        ]
        
        overall_table = Table(overall_summary_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        overall_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#1e40af')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        story.append(overall_table)
        
        # Footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("Generated by Kirana Konnect - Your Complete Business Management Solution", summary_style))
        
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
