from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

DB_FILE = 'bookmate.db'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database setup and helper functions ---
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            subject TEXT,
            price REAL NOT NULL,
            photo TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender INTEGER NOT NULL,
            receiver INTEGER NOT NULL,
            text TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender) REFERENCES users(id),
            FOREIGN KEY(receiver) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- User registration ---
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, password))
        conn.commit()
        user_id = cursor.lastrowid
        return jsonify({'message': 'User registered', 'userId': user_id, 'email': email})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Email already registered'}), 400
    finally:
        conn.close()

# --- User login ---
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, password FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    if not row or row['password'] != password:
        return jsonify({'error': 'Invalid email or password'}), 401
    return jsonify({'userId': row['id'], 'email': email})

# --- Upload book ---
@app.route('/upload_book', methods=['POST'])
def upload_book():
    user_id = request.form.get('userId')
    name = request.form.get('name')
    subject = request.form.get('subject')
    price = request.form.get('price')
    photo = request.files.get('photo')

    if not user_id or not name or not price or not photo:
        return jsonify({'error': 'Missing required fields'}), 400
    try:
        price_val = float(price)
    except ValueError:
        return jsonify({'error': 'Invalid price'}), 400

    filename = secure_filename(photo.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    photo.save(filepath)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO books (user_id, name, subject, price, photo)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, name, subject, price_val, '/' + filepath))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Book uploaded successfully'})

# --- Get books with optional search query ---
@app.route('/books')
def get_books():
    q = request.args.get('q', '').strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    if q:
        cursor.execute('''
            SELECT books.*, users.email AS sellerEmail FROM books
            JOIN users ON books.user_id = users.id
            WHERE LOWER(books.name) LIKE ?
            ORDER BY books.id DESC
        ''', ('%' + q + '%',))
    else:
        cursor.execute('''
            SELECT books.*, users.email AS sellerEmail FROM books
            JOIN users ON books.user_id = users.id
            ORDER BY books.id DESC
        ''')
    rows = cursor.fetchall()
    conn.close()
    books = []
    for r in rows:
        books.append({
            'id': r['id'],
            'name': r['name'],
            'subject': r['subject'],
            'price': r['price'],
            'photoURL': r['photo'],
            'sellerEmail': r['sellerEmail']
        })
    return jsonify(books)

# --- Serve uploaded images ---
@app.route('/uploads/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Get users (for chat user list), exclude current user ---
@app.route('/users')
def get_users():
    user_id = request.args.get('userId')
    conn = get_db()
    cursor = conn.cursor()
    if user_id:
        cursor.execute('SELECT id, email FROM users WHERE id != ?', (user_id,))
    else:
        cursor.execute('SELECT id, email FROM users')
    rows = cursor.fetchall()
    conn.close()
    users = [{'id': r['id'], 'email': r['email']} for r in rows]
    return jsonify(users)

# --- Send chat message ---
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    sender = data.get('sender')
    receiver = data.get('receiver')
    text = data.get('text')
    if not sender or not receiver or not text:
        return jsonify({'error': 'Missing fields'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)', (sender, receiver, text))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Message sent'})

# --- Get messages between two users ---
@app.route('/get_messages')
def get_messages():
    user1 = request.args.get('user1')
    user2 = request.args.get('user2')
    if not user1 or not user2:
        return jsonify([])
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages WHERE
        (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
        ORDER BY timestamp ASC
    ''', (user1, user2, user2, user1))
    rows = cursor.fetchall()
    conn.close()
    messages = [{'id': r['id'], 'sender': r['sender'], 'receiver': r['receiver'], 'text': r['text']} for r in rows]
    return jsonify(messages)

if __name__ == '__main__':
    app.run(debug=True)
