from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Configure Flask for development
app.config['DEBUG'] = True
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Sample data for demonstration
sample_products = [
    {
        'id': 1,
        'name': 'Aashirvaad Atta',
        'category': 'Grains',
        'price': 120,
        'price_per_kg': 45,
        'stock_quantity': 5,
        'unit': 'Bag',
        'is_weight_based': False,
        'is_low_stock': True,
        'is_expired': False,
        'expiry_date': '01/09/2025',
        'barcode': '8901030875466'
    },
    {
        'id': 2,
        'name': 'Basmati Rice',
        'category': 'Grains',
        'price_per_kg': 110,
        'stock_quantity': 25.5,
        'unit': 'Kg',
        'is_weight_based': True,
        'is_low_stock': False,
        'is_expired': False,
        'expiry_date': '15/03/2027',
        'barcode': '8901030875499'
    },
    {
        'id': 3,
        'name': 'Coconut Oil',
        'category': 'Oils',
        'price': 180,
        'stock_quantity': 25,
        'unit': 'Bottle',
        'is_weight_based': False,
        'is_low_stock': False,
        'is_expired': False,
        'expiry_date': '15/02/2027',
        'barcode': '8901030567890'
    }
]

sample_customers = [
    {
        'id': 1,
        'name': 'Rajesh Kumar',
        'phone': '+91 9876543210',
        'outstanding_balance': 2150.0,
        'address': 'Main Street, Delhi',
        'created_at': '2024-01-15'
    },
    {
        'id': 2,
        'name': 'Priya Sharma',
        'phone': '+91 9876543211',
        'outstanding_balance': 850.0,
        'address': 'Market Road, Delhi',
        'created_at': '2024-02-20'
    }
]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/splash')
def splash():
    return render_template('splash.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/signin')
def signin():
    return render_template('signin.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/inventory')
def inventory():
    return render_template('inventory.html')

@app.route('/add-item')
def add_item():
    return render_template('add_item.html')

@app.route('/cart')
def cart():
    return render_template('cart.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/product-details')
def product_details():
    return render_template('product_details.html')

@app.route('/product-details-weight')
def product_details_weight():
    return render_template('product_details_weight.html')

@app.route('/refill-stock')
def refill_stock():
    return render_template('refill_stock.html')

@app.route('/refill-stock-weight')
def refill_stock_weight():
    return render_template('refill_stock_weight.html')

@app.route('/customer-ledger')
def customer_ledger():
    return render_template('customer_ledger.html')

@app.route('/pending-credits')
def pending_credits():
    return render_template('pending_credits.html')

@app.route('/low-stock')
def low_stock():
    return render_template('low_stock.html')

@app.route('/expiry-alert')
def expiry_alert():
    return render_template('expiry_alert.html')

@app.route('/notifications')
def notifications():
    return render_template('notifications.html')

@app.route('/staff')
def staff():
    return render_template('staff.html')

@app.route('/sales-report')
def sales_report():
    return render_template('sales_report.html')

@app.route('/receipt')
def receipt():
    return render_template('receipt.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

# API Routes
@app.route('/api/products')
def api_products():
    return jsonify(sample_products)

@app.route('/api/customers/search')
def api_customers_search():
    return jsonify(sample_customers)

@app.route('/api/search-customers')
def api_search_customers():
    query = request.args.get('q', '').lower()
    filtered_customers = [
        customer for customer in sample_customers 
        if query in customer['name'].lower() or query in customer['phone']
    ]
    return jsonify({'customers': filtered_customers})

@app.route('/api/sales-data')
def api_sales_data():
    period = request.args.get('period', 'weekly')
    
    # Sample sales data
    sales_data = {
        'success': True,
        'data': {
            'period': period,
            'totalRevenue': 45280,
            'totalProfit': 8450,
            'totalInvestment': 36830,
            'totalCombinedInvestment': 100000,
            'remainingInvestment': 70000,
            'chartData': {
                'dates': ['2025-01-09', '2025-01-10', '2025-01-11', '2025-01-12', '2025-01-13', '2025-01-14', '2025-01-15'],
                'investment': [5000, 3000, 4500, 2000, 6000, 3500, 4000],
                'profit': [1200, 800, 1500, 600, 1800, 1000, 1200]
            },
            'topItems': [
                {'name': 'Aashirvaad Atta', 'quantity': 15, 'amount': 2000, 'profit': 300, 'investment': 1700, 'product_id': 1},
                {'name': 'Tata Salt', 'quantity': 12, 'amount': 800, 'profit': 150, 'investment': 650, 'product_id': 2},
                {'name': 'Amul Milk', 'quantity': 10, 'amount': 500, 'profit': 80, 'investment': 420, 'product_id': 3}
            ]
        }
    }
    
    return jsonify(sales_data)

@app.route('/api/notifications')
def api_notifications():
    notifications_data = {
        'success': True,
        'notifications': [
            {
                'id': 1,
                'type': 'expiry',
                'priority': 'urgent',
                'title': '5 items expired',
                'message': 'Remove from inventory immediately',
                'time_ago': '2 hours ago',
                'is_read': False
            },
            {
                'id': 2,
                'type': 'inventory',
                'priority': 'medium',
                'title': '10 items low stock',
                'message': 'Reorder soon to avoid stockouts',
                'time_ago': '4 hours ago',
                'is_read': False
            },
            {
                'id': 3,
                'type': 'payment',
                'priority': 'medium',
                'title': '₹1,500 pending credits',
                'message': 'From 3 customers - follow up required',
                'time_ago': '6 hours ago',
                'is_read': False
            }
        ],
        'count': 3
    }
    
    return jsonify(notifications_data)

@app.route('/api/low-stock-products')
def api_low_stock_products():
    low_stock_data = {
        'success': True,
        'products': [
            {
                'id': 1,
                'name': 'Wheat Flour',
                'category': 'Grains',
                'stock_quantity': 2,
                'reorder_level': 5,
                'unit': 'Kg',
                'price_display': '₹50/Kg',
                'level': 'critical',
                'level_color': 'red',
                'level_text': 'Critical',
                'progress': 20,
                'suggested_reorder': 25
            }
        ]
    }
    
    return jsonify(low_stock_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)