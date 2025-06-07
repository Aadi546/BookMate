from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import jwt
import smtplib
from email.mime.text import MIMEText
from functools import wraps

# Configuration
SECRET_KEY = 'your-very-secret-key'
DB_FILE = 'bookmate.db'
UPLOAD_FOLDER = 'uploads'
TOKEN_EXPIRATION_HOURS = 24

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = SECRET_KEY
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Email Config (Replace with real credentials in production)
EMAIL_SENDER = 'your_email@example.com'
EMAIL_PASSWORD = 'your_email_password'
SMTP_SERVER = 'smtp.example.com'
SMTP_PORT = 587

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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(book_id) REFERENCES books(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- JWT Helpers ---
def encode_auth_token(user_id):
    try:
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRATION_HOURS),
            'iat': datetime.datetime.utcnow(),
            'sub': user_id
        }
        return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    except Exception:
        return None

def decode_auth_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['sub']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers.get('Authorization').split(" ")[1]
        if not token:
            return jsonify({'error': 'Token is missing!'}), 401
        user_id = decode_auth_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid or expired token'}), 401
        return f(user_id, *args, **kwargs)
    return decorated

# --- Auth Routes ---
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    hashed_password = generate_password_hash(password)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, hashed_password))
        conn.commit()
        user_id = cursor.lastrowid
        token = encode_auth_token(user_id)
        return jsonify({'message': 'User registered', 'userId': user_id, 'email': email, 'token': token})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Email already registered'}), 400
    finally:
        conn.close()

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
    if not row or not check_password_hash(row['password'], password):
        return jsonify({'error': 'Invalid email or password'}), 401
    token = encode_auth_token(row['id'])
    return jsonify({'userId': row['id'], 'email': email, 'token': token})

# --- Book Upload ---
@app.route('/upload_book', methods=['POST'])
@token_required
def upload_book(user_id):
    name = request.form.get('name')
    subject = request.form.get('subject')
    price = request.form.get('price')
    photo = request.files.get('photo')

    if not name or not price or not photo:
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

# --- Buy Book ---
@app.route('/buy_book/<int:book_id>', methods=['POST'])
@token_required
def buy_book(buyer_id, book_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT books.*, users.email as seller_email FROM books JOIN users ON books.user_id = users.id WHERE books.id = ?', (book_id,))
    book = cursor.fetchone()

    if not book:
        return jsonify({'error': 'Book not found'}), 404

    seller_email = book['seller_email']
    book_name = book['name']

    # Remove the book from the marketplace after purchase
    cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))

    try:
        msg = MIMEText(f"Your book '{book_name}' has been purchased on Bookmate.")
        msg['Subject'] = 'Book Sold Notification'
        msg['From'] = EMAIL_SENDER
        msg['To'] = seller_email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, seller_email, msg.as_string())
    except Exception as e:
        print('Email send error:', e)

    cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()

    return jsonify({'message': f"Book '{book_name}' bought successfully. Seller notified."})

# --- Book Retrieval ---
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
    conn.close()
    return jsonify(books)

# --- Serve Image ---
@app.route('/uploads/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Users for Chat ---
@app.route('/users')
@token_required
def get_users(current_user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, email FROM users WHERE id != ?', (current_user_id,))
    rows = cursor.fetchall()
    conn.close()
    users = [{'id': r['id'], 'email': r['email']} for r in rows]
    return jsonify(users)

# --- Send Message ---
@app.route('/send_message', methods=['POST'])
@token_required
def send_message(sender):
    data = request.get_json()
    receiver = data.get('receiver')
    text = data.get('text')
    if not receiver or not text:
        return jsonify({'error': 'Missing fields'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)', (sender, receiver, text))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Message sent'})

# --- Get Messages ---
@app.route('/get_messages')
@token_required
def get_messages(current_user_id):
    user2 = request.args.get('user2')
    if not user2:
        return jsonify({'error': 'Missing user2 parameter'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages WHERE
        (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
        ORDER BY timestamp ASC
    ''', (current_user_id, user2, user2, current_user_id))
    rows = cursor.fetchall()
    conn.close()
    messages = [{'id': r['id'], 'sender': r['sender'], 'receiver': r['receiver'], 'text': r['text']} for r in rows]
    return jsonify(messages)

# --- Reviews ---
@app.route('/submit_review', methods=['POST'])
@token_required
def submit_review(user_id):
    data = request.get_json()
    book_id = data.get('bookId')
    rating = data.get('rating')
    comment = data.get('comment', '')

    if not book_id or not rating:
        return jsonify({'error': 'Book ID and rating required'}), 400
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError()
    except ValueError:
        return jsonify({'error': 'Rating must be an integer between 1 and 5'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM books WHERE id = ?', (book_id,))
    if cursor.fetchone() is None:
        conn.close()
        return jsonify({'error': 'Book not found'}), 404

    cursor.execute('''
        INSERT INTO reviews (book_id, user_id, rating, comment)
        VALUES (?, ?, ?, ?)
    ''', (book_id, user_id, rating, comment))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Review submitted'})

@app.route('/get_reviews/<int:book_id>')
def get_reviews(book_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT reviews.*, users.email AS reviewerEmail FROM reviews
        JOIN users ON reviews.user_id = users.id
        WHERE reviews.book_id = ?
        ORDER BY reviews.timestamp DESC
    ''', (book_id,))
    rows = cursor.fetchall()
    conn.close()
    reviews = [{
        'id': r['id'],
        'rating': r['rating'],
        'comment': r['comment'],
        'reviewerEmail': r['reviewerEmail'],
        'timestamp': r['timestamp']
    } for r in rows]
    return jsonify(reviews)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
