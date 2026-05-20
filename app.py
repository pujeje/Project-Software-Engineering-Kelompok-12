from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import re
from PIL import Image
import pytesseract
from flask_migrate import Migrate


pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'fintrack-secret'

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# Setup Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login dulu!'

# =====================
# MODEL DATABASE
# =====================

class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    email    = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

class Transaction(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    title    = db.Column(db.String(100), nullable=False)
    amount   = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    type     = db.Column(db.String(10), nullable=False)
    date     = db.Column(db.DateTime, default=datetime.utcnow)
    note     = db.Column(db.String(200), nullable=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Budget(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    period     = db.Column(db.String(10), nullable=False)  # 'daily', 'weekly', 'monthly'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =====================
# AUTH ROUTES
# =====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name     = request.form['name']
        email    = request.form['email']
        password = request.form['password']
        confirm  = request.form['confirm']

        if password != confirm:
            flash('Password tidak cocok!', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar!', 'danger')
            return redirect(url_for('register'))

        hashed = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed)
        db.session.add(new_user)
        db.session.commit()

        flash('Akun berhasil dibuat! Silakan login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash('Email atau password salah!', 'danger')
            return redirect(url_for('login'))

        login_user(user)
        flash(f'Selamat datang, {user.name}!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Berhasil logout!', 'success')
    return redirect(url_for('login'))


# =====================
# MAIN ROUTES
# =====================

@app.route('/')
@login_required
def index():
    transactions = Transaction.query.filter_by(user_id=current_user.id)\
                              .order_by(Transaction.date.desc()).all()

    total_income  = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance       = total_income - total_expense
    budget_status = get_budget_status(current_user.id)
    budget        = Budget.query.filter_by(user_id=current_user.id).first()

    return render_template('index.html',
                            transactions=transactions,
                            total_income=total_income,
                            total_expense=total_expense,
                            balance=balance,
                            budget_status=budget_status,
                            budget=budget)


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        title    = request.form['title']
        amount   = float(request.form['amount'])
        category = request.form['category']
        tipe     = request.form['type']
        note     = request.form.get('note', '')
        date_str = request.form.get('date', '')

        if date_str:
            tanggal = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            tanggal = datetime.utcnow()

        new_transaction = Transaction(
            title=title,
            amount=amount,
            category=category,
            type=tipe,
            note=note,
            date=tanggal,
            user_id=current_user.id
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Transaksi berhasil ditambahkan!', 'success')
        return redirect(url_for('index'))

    today = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('add_transaction.html', today=today)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    transaction = Transaction.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        transaction.title    = request.form['title']
        transaction.amount   = float(request.form['amount'])
        transaction.category = request.form['category']
        transaction.type     = request.form['type']
        transaction.note     = request.form.get('note', '')
        transaction.date     = datetime.strptime(request.form['date'], '%Y-%m-%d')

        db.session.commit()
        flash('Transaksi berhasil diperbarui!', 'success')
        return redirect(url_for('index'))

    return render_template('edit_transaction.html', transaction=transaction)


@app.route('/delete/<int:id>')
@login_required
def delete_transaction(id):
    transaction = Transaction.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaksi berhasil dihapus!', 'danger')
    return redirect(url_for('index'))


@app.route('/report')
@login_required
def report():
    transactions = Transaction.query.filter_by(user_id=current_user.id)\
                            .order_by(Transaction.date.asc()).all()

    category_data = {}
    for t in transactions:
        if t.type == 'expense':
            category_data[t.category] = category_data.get(t.category, 0) + t.amount

    monthly_data = {}
    for t in transactions:
        key = t.date.strftime('%b %Y')
        if key not in monthly_data:
            monthly_data[key] = {'income': 0, 'expense': 0}
        monthly_data[key][t.type] += t.amount

    total_income  = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance       = total_income - total_expense

    return render_template('report.html',
                            category_data=category_data,
                            monthly_data=monthly_data,
                            total_income=total_income,
                            total_expense=total_expense,
                            balance=balance)


@app.route('/scan', methods=['GET', 'POST'])
@login_required
def scan():
    if request.method == 'POST':
        if 'receipt' not in request.files:
            flash('Tidak ada file yang diupload!', 'danger')
            return redirect(url_for('scan'))

        file = request.files['receipt']
        if file.filename == '':
            flash('Pilih file dulu!', 'danger')
            return redirect(url_for('scan'))

        img    = Image.open(file.stream)
        text   = pytesseract.image_to_string(img, lang='ind+eng')
        amount = 0
        lines  = text.split('\n')

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in ['total', 'grand total', 'jumlah', 'bayar']):
                numbers = re.findall(r'[\d.,]+', line)
                for num in reversed(numbers):
                    clean = num.replace('.', '').replace(',', '')
                    if clean.isdigit() and int(clean) > 1000:
                        amount = int(clean)
                        break
                if amount > 0:
                    break

        title = 'Belanja'
        for line in lines[:5]:
            line = line.strip()
            if len(line) > 3 and not line.isdigit():
                title = line.title()
                break

        note_lines = [l.strip() for l in lines if len(l.strip()) > 3]
        note  = ', '.join(note_lines[:5])
        today = datetime.utcnow().strftime('%Y-%m-%d')

        result = {
            'title'   : title,
            'amount'  : amount,
            'category': 'Belanja',
            'date'    : today,
            'note'    : note
        }

        return render_template('scan.html', result=result)

    return render_template('scan.html', result=None)

@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        period = request.form['period']

        # Kalau sudah ada budget, update. Kalau belum, buat baru
        existing = Budget.query.filter_by(user_id=current_user.id).first()
        if existing:
            existing.amount = amount
            existing.period = period
        else:
            new_budget = Budget(
                user_id=current_user.id,
                amount=amount,
                period=period
            )
            db.session.add(new_budget)

        db.session.commit()
        flash('Budget berhasil disimpan!', 'success')
        return redirect(url_for('index'))

    return redirect(url_for('index'))


def get_budget_status(user_id):
    budget = Budget.query.filter_by(user_id=user_id).first()
    if not budget:
        return None

    now = datetime.utcnow()

    # Filter transaksi sesuai periode
    if budget.period == 'daily':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = 'Hari Ini'
    elif budget.period == 'weekly':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = 'Minggu Ini'
    else:  # monthly
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_label = 'Bulan Ini'

    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.type == 'expense',
        Transaction.date >= start
    ).all()

    total_expense = sum(t.amount for t in transactions)
    percentage    = (total_expense / budget.amount) * 100 if budget.amount > 0 else 0
    remaining     = budget.amount - total_expense

    # Tentukan status warning
    if percentage >= 100:
        status = 'danger'
        message = f'Budget {period_label} sudah habis! Pengeluaran melebihi Rp {budget.amount:,.0f}'
    elif percentage >= 90:
        status = 'warning'
        message = f'Hampir habis! Sisa budget {period_label} tinggal Rp {remaining:,.0f}'
    else:
        status = 'safe'
        message = None

    return {
        'amount'       : budget.amount,
        'period'       : budget.period,
        'period_label' : period_label,
        'total_expense': total_expense,
        'remaining'    : remaining,
        'percentage'   : min(percentage, 100),
        'status'       : status,
        'message'      : message
    }


# =====================
# JALANKAN APP
# =====================

if __name__ == '__main__':
    with app.app_context():
        print("Database siap!")
    app.run(debug=True)