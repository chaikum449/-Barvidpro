# app.py - BarVid Pro (with Login System)

from flask import Flask, render_template, request, jsonify, send_from_directory, make_response, session, redirect, url_for, flash
import os
import datetime
import json
import pandas as pd
import io
import hashlib
from functools import wraps

app = Flask(__name__, static_folder='uploads')
app.secret_key = 'your_super_secret_key_for_barvid_pro_sessions_12345'

# --- File Paths ---
UPLOAD_FOLDER = 'uploads'
PRODUCTS_FILE = 'products.json'
USERS_FILE = 'users.json'
STOCK_LOG_FILE = 'stock_log.json' 
PARCELS_FILE = 'parcels.json'

# --- Initial Setup ---
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Database Helper Functions ---
def load_data(filepath, default_type=dict):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = default_type()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return data

def save_data(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def log_stock_change(log_type, barcode, product_name, change, new_quantity):
    logs = load_data(STOCK_LOG_FILE, default_type=list)
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(), "type": log_type,
        "barcode": barcode, "product_name": product_name,
        "quantity_change": change, "new_quantity": new_quantity
    }
    logs.insert(0, log_entry)
    save_data(STOCK_LOG_FILE, logs)

# --- Login required decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users = load_data(USERS_FILE)
        user_data = users.get(username)

        if user_data and user_data['password_hash'] == hash_password(password):
            session['logged_in'] = True
            session['username'] = username
            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            return redirect(url_for('pack_record_page'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    return make_response(render_template('login.html'))

@app.route('/logout')
def logout():
    session.clear()
    flash('คุณออกจากระบบแล้ว', 'info')
    return redirect(url_for('login'))

# --- Page Routes (Protected) ---
@app.route('/')
@login_required
def pack_record_page():
    return make_response(render_template('pack_record.html'))

@app.route('/manage')
@login_required
def manage_products_page():
    return make_response(render_template('manage_products.html'))

@app.route('/stock_in')
@login_required
def stock_in_page():
    return make_response(render_template('stock_in.html'))

@app.route('/search')
@login_required
def search_page():
    return make_response(render_template('search.html'))

@app.route('/reports')
@login_required
def reports_page():
    return make_response(render_template('reports.html'))

# --- API Endpoints ---
# (Pasting all APIs from Warehouse Edition here for completeness)
@app.route('/api/products', methods=['GET', 'POST'])
@login_required
def handle_products():
    products = load_data(PRODUCTS_FILE)
    if request.method == 'GET':
        return jsonify(products)
    if request.method == 'POST':
        data = request.get_json()
        barcode = data.get('barcode','').strip()
        name = data.get('name','').strip()
        original_barcode = data.get('original_barcode')
        if not barcode or not name: return jsonify({"message": "ข้อมูลไม่ครบถ้วน"}), 400
        if not original_barcode and barcode in products:
            return jsonify({"message": f"บาร์โค้ด '{barcode}' มีอยู่แล้ว"}), 409
        if original_barcode and original_barcode != barcode and barcode in products:
            return jsonify({"message": f"บาร์โค้ด '{barcode}' ซ้ำกับสินค้าอื่น"}), 409
        quantity = products.get(original_barcode, {}).get('quantity', 0)
        product_data = {"name": name, "quantity": quantity}
        if original_barcode and original_barcode in products and original_barcode != barcode:
            del products[original_barcode]
        products[barcode] = product_data
        save_data(PRODUCTS_FILE, products)
        if not original_barcode:
             log_stock_change("manual-adjust", barcode, name, 0, 0)
        return jsonify({"message": "บันทึกข้อมูลสินค้าสำเร็จ"}), 200

@app.route('/api/products/<barcode>', methods=['DELETE'])
@login_required
def delete_product(barcode):
    products = load_data(PRODUCTS_FILE)
    if barcode in products:
        del products[barcode]
        save_data(PRODUCTS_FILE, products)
        return jsonify({"message": "ลบสินค้าสำเร็จ"}), 200
    return jsonify({"message": "ไม่พบสินค้า"}), 404

@app.route('/api/stock_in', methods=['POST'])
@login_required
def stock_in():
    data = request.get_json()
    barcode = data.get('barcode')
    quantity = data.get('quantity')
    if not barcode or quantity is None: return jsonify({"message": "ข้อมูลไม่ครบถ้วน"}), 400
    products = load_data(PRODUCTS_FILE)
    if barcode not in products: return jsonify({"message": "ไม่พบสินค้านี้ในระบบ"}), 404
    try:
        qty_to_add = int(quantity)
        if qty_to_add <= 0: raise ValueError
    except ValueError:
        return jsonify({"message": "จำนวนต้องเป็นตัวเลขที่มากกว่า 0"}), 400
    products[barcode]['quantity'] += qty_to_add
    save_data(PRODUCTS_FILE, products)
    log_stock_change("stock-in", barcode, products[barcode]['name'], qty_to_add, products[barcode]['quantity'])
    return jsonify({"message": f"รับสินค้า '{products[barcode]['name']}' เข้าสต็อก {qty_to_add} ชิ้นสำเร็จ"}), 200

@app.route('/api/check_item/<barcode>', methods=['GET'])
@login_required
def check_item(barcode):
    products = load_data(PRODUCTS_FILE)
    if barcode in products:
        return jsonify(products[barcode])
    return jsonify({"message": "ไม่พบสินค้า"}), 404

@app.route('/upload_pack_video', methods=['POST'])
@login_required
def upload_pack_video():
    try:
        if 'video' not in request.files or 'transport_barcode' not in request.form or 'scanned_items' not in request.form:
            return jsonify({"status": "error", "message": "ข้อมูลไม่ครบถ้วน"}), 400
        video_file = request.files['video']
        transport_barcode = request.form['transport_barcode']
        scanned_items = json.loads(request.form['scanned_items'])
        products = load_data(PRODUCTS_FILE)
        parcels = load_data(PARCELS_FILE)
        scanned_items_barcodes = [item['barcode'] for item in scanned_items]
        for item_barcode in scanned_items_barcodes:
            if item_barcode in products and products[item_barcode]['quantity'] > 0:
                products[item_barcode]['quantity'] -= 1
                log_stock_change("stock-out", item_barcode, products[item_barcode]['name'], -1, products[item_barcode]['quantity'])
        save_data(PRODUCTS_FILE, products)
        filename = f"{transport_barcode}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        video_file.save(filepath)
        parcels[transport_barcode] = {
            "video_filename": filename,
            "scanned_products": scanned_items,
            "timestamp": datetime.datetime.now().isoformat()
        }
        save_data(PARCELS_FILE, parcels)
        return jsonify({"status": "success", "filename": filename}), 200
    except Exception as e:
        print(f"--- SERVER ERROR on upload_pack_video ---: {e}")
        return jsonify({"status": "error", "message": "เกิดข้อผิดพลาดร้ายแรงบนเซิร์ฟเวอร์"}), 500

@app.route('/api/inventory', methods=['GET'])
@login_required
def get_inventory():
    products = load_data(PRODUCTS_FILE)
    return jsonify(products)

@app.route('/api/parcels', methods=['GET'])
@login_required
def get_parcels():
    parcels = load_data(PARCELS_FILE)
    parcel_list = []
    for key, value in parcels.items():
        value['transport_barcode'] = key
        parcel_list.append(value)
    parcel_list.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(parcel_list)

@app.route('/api/parcels/<transport_barcode>', methods=['DELETE'])
@login_required
def delete_parcel(transport_barcode):
    parcels = load_data(PARCELS_FILE)
    if transport_barcode not in parcels:
        return jsonify({"message": "ไม่พบข้อมูลพัสดุ"}), 404
    parcel_to_delete = parcels.pop(transport_barcode)
    video_filename = parcel_to_delete.get('video_filename')
    if video_filename:
        try:
            filepath = os.path.join(UPLOAD_FOLDER, video_filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting video file {video_filename}: {e}")
    save_data(PARCELS_FILE, parcels)
    return jsonify({"message": f"ลบข้อมูลพัสดุ '{transport_barcode}' สำเร็จ"}), 200

@app.route('/uploads/<filename>')
@login_required
def get_video_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/reports/dashboard_summary')
@login_required
def get_dashboard_summary():
    today_str = datetime.date.today().isoformat()
    products = load_data(PRODUCTS_FILE)
    logs = load_data(STOCK_LOG_FILE, default_type=list)
    total_stock = sum(p.get('quantity', 0) for p in products.values())
    today_stock_in = sum(log.get('quantity_change', 0) for log in logs if log['timestamp'].startswith(today_str) and log.get('quantity_change', 0) > 0)
    today_stock_out = abs(sum(log.get('quantity_change', 0) for log in logs if log['timestamp'].startswith(today_str) and log['type'] == 'stock-out'))
    return jsonify({"total_stock": total_stock, "today_stock_in": today_stock_in, "today_stock_out": today_stock_out})

@app.route('/api/reports/daily_log')
@login_required
def report_daily_log():
    date_str = request.args.get('date')
    log_type = request.args.get('type')
    logs = load_data(STOCK_LOG_FILE, default_type=list)
    if log_type == 'stock-in':
        daily_logs = [log for log in logs if log['timestamp'].startswith(date_str) and log['quantity_change'] > 0]
    elif log_type == 'stock-out':
        daily_logs = [log for log in logs if log['timestamp'].startswith(date_str) and log['type'] == 'stock-out']
    else: daily_logs = []
    return jsonify(daily_logs)

@app.route('/api/users/add_user', methods=['POST'])
@login_required
def add_user():
    data = request.get_json()
    new_username = data.get('new_username', '').strip()
    new_password = data.get('new_password', '').strip()
    if not all([new_username, new_password]):
        return jsonify({"message": "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"}), 400
    users = load_data(USERS_FILE)
    if new_username in users:
        return jsonify({"message": "ชื่อผู้ใช้นี้มีอยู่แล้ว"}), 409
    users[new_username] = {"password_hash": hash_password(new_password)}
    save_data(USERS_FILE, users)
    return jsonify({"message": f"เพิ่มผู้ใช้ '{new_username}' สำเร็จ"}), 201
    
@app.route('/api/users/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    username = session.get('username')
    if not all([current_password, new_password, username]):
        return jsonify({"message": "ข้อมูลไม่ครบถ้วน"}), 400
    users = load_data(USERS_FILE)
    user_data = users.get(username)
    if not user_data or user_data['password_hash'] != hash_password(current_password):
        return jsonify({"message": "รหัสผ่านปัจจุบันไม่ถูกต้อง"}), 403
    users[username]['password_hash'] = hash_password(new_password)
    save_data(USERS_FILE, users)
    return jsonify({"message": "เปลี่ยนรหัสผ่านสำเร็จ"}), 200


if __name__ == '__main__':
    if not os.path.exists(USERS_FILE):
        initial_users = { "admin": { "password_hash": hash_password("1234") } }
        save_data(USERS_FILE, initial_users)
    app.run(debug=True, host='0.0.0.0', port=5001)