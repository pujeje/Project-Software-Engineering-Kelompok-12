# ============================================================
# FINTRACK — app.py
# ============================================================

from flask import (Flask, render_template, request,
                   redirect, url_for, flash)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin,
                         login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from translations import get_translation
import secrets
import os
import re
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# ============================================================
# APP CONFIG
# ============================================================

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI']      = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY']                   = 'fintrack-secret'
app.config['UPLOAD_FOLDER']                = 'static/uploads'
app.config['MAX_CONTENT_LENGTH']           = 2 * 1024 * 1024  # 2 MB

os.makedirs('static/uploads', exist_ok=True)

db           = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view    = 'login'
login_manager.login_message = 'Silakan login dulu!'


# ============================================================
# MODELS
# ============================================================

class User(UserMixin, db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(100), unique=True, nullable=False)
    password     = db.Column(db.String(200), nullable=False)
    photo        = db.Column(db.String(200), nullable=True)
    language     = db.Column(db.String(5),  default='id')
    theme        = db.Column(db.String(10), default='light')
    notif_popup  = db.Column(db.Boolean,    default=True)
    timezone     = db.Column(db.String(50), default='Asia/Jakarta')
    created_at   = db.Column(db.DateTime,   default=datetime.utcnow)
    transactions = db.relationship('Transaction', backref='user', lazy=True)


class LoginHistory(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ip_address   = db.Column(db.String(50),  nullable=True)
    user_agent   = db.Column(db.String(200), nullable=True)
    logged_in_at = db.Column(db.DateTime, default=datetime.utcnow)
    user         = db.relationship('User', backref='login_histories')


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    category = db.Column(db.String(50))
    type = db.Column(db.String(10))   # income / expense
    amount = db.Column(db.Integer)
    date = db.Column(db.DateTime)

    # Foreign key ke User
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))



class Budget(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount     = db.Column(db.Float,      nullable=False)
    period     = db.Column(db.String(10), nullable=False)  # daily / weekly / monthly
    created_at = db.Column(db.DateTime,   default=datetime.utcnow)


class Group(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    code      = db.Column(db.String(10), unique=True, nullable=False)
    created_at= db.Column(db.DateTime, default=datetime.utcnow)
    members   = db.relationship('GroupMember', backref='group', lazy=True)
    funds     = db.relationship('Fund', backref='group', lazy=True)
    transactions = db.relationship('GroupTransaction', backref='group', lazy=True)


class GroupMember(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    role     = db.Column(db.String(20), default='member')
    user     = db.relationship('User')


class Fund(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    target      = db.Column(db.Float, default=0)
    group_id    = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    transactions= db.relationship('GroupTransaction', backref='fund_ref', lazy=True)


class GroupTransaction(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    title    = db.Column(db.String(100), nullable=False)
    amount   = db.Column(db.Float, nullable=False)
    type     = db.Column(db.String(10), nullable=False)  # income / expense
    category = db.Column(db.String(50), nullable=False)
    date     = db.Column(db.DateTime, default=datetime.utcnow)
    note     = db.Column(db.String(200))
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    fund_id  = db.Column(db.Integer, db.ForeignKey('fund.id'), nullable=True)
    user     = db.relationship('User')
    fund     = db.relationship('Fund')


class ActivityLog(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    group_id   = db.Column(db.Integer, db.ForeignKey('group.id'),  nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'),   nullable=False)
    action     = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)
    user       = db.relationship('User', backref='activity_logs')


class SplitBill(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(100), nullable=False)
    total_amount= db.Column(db.Float, nullable=False)
    note        = db.Column(db.String(200))
    group_id    = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    created_by  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    splits      = db.relationship('SplitDetail', backref='bill', lazy=True)


class SplitDetail(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    bill_id   = db.Column(db.Integer, db.ForeignKey('split_bill.id'), nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount    = db.Column(db.Float, nullable=False)
    is_paid   = db.Column(db.Boolean, default=False)
    paid_at   = db.Column(db.DateTime)
    user      = db.relationship('User')


# ============================================================
# HELPERS
# ============================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_translation():
    lang = current_user.language if current_user.is_authenticated else 'id'
    return dict(t=get_translation(lang))


def log_activity(group_id, user_id, action):
    db.session.add(ActivityLog(group_id=group_id, user_id=user_id, action=action))
    db.session.commit()


def get_budget_status(user_id):
    budget = Budget.query.filter_by(user_id=user_id).first()
    if not budget:
        return None

    now = datetime.utcnow()
    if budget.period == 'daily':
        start        = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = 'Hari Ini'
    elif budget.period == 'weekly':
        start        = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = 'Minggu Ini'
    else:
        start        = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_label = 'Bulan Ini'

    transactions  = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.type    == 'expense',
        Transaction.date    >= start
    ).all()

    total_expense = sum(t.amount for t in transactions)
    percentage    = (total_expense / budget.amount * 100) if budget.amount > 0 else 0
    remaining     = budget.amount - total_expense

    if percentage >= 100:
        status  = 'danger'
        message = f'Budget {period_label} sudah habis!'
    elif percentage >= 90:
        status  = 'warning'
        message = f'Hampir habis! Sisa budget {period_label} tinggal Rp {remaining:,.0f}'
    else:
        status  = 'safe'
        message = None

    return {
        'amount'       : budget.amount,
        'period'       : budget.period,
        'period_label' : period_label,
        'total_expense': total_expense,
        'remaining'    : remaining,
        'percentage'   : min(percentage, 100),
        'status'       : status,
        'message'      : message,
    }


# OCR detail produk
def _ocr_receipt(file_stream):
    img   = Image.open(file_stream)
    text  = pytesseract.image_to_string(img, lang='ind+eng')
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    items = []
    total = 0
    for line in lines:
        match = re.findall(r'(.+?)\s+([\d.,]+)', line)
        if match:
            for name, price in match:
                clean = price.replace('.', '').replace(',', '')
                if clean.isdigit():
                    amount = int(clean)
                    items.append({'name': name, 'amount': amount})
        if any(w in line.lower() for w in ['total', 'jumlah', 'bayar']):
            nums = re.findall(r'[\d.,]+', line)
            if nums:
                clean = nums[-1].replace('.', '').replace(',', '')
                if clean.isdigit():
                    total = int(clean)

    return items, total



# ============================================================
# LANDING PAGE
# ============================================================

@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('landing.html')


# ============================================================
# AUTH
# ============================================================

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

        new_user = User(name=name, email=email,
                        password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()

        # Auto login setelah register
        login_user(new_user)
        flash('Akun berhasil dibuat! Selamat datang 🎉', 'success')
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        user     = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash('Email atau password salah!', 'danger')
            return redirect(url_for('login'))

        login_user(user)

        # Catat riwayat login
        db.session.add(LoginHistory(
            user_id    = user.id,
            ip_address = request.remote_addr,
            user_agent = request.headers.get('User-Agent', '')[:200]
        ))
        db.session.commit()

        flash(f'Selamat datang, {user.name}!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Berhasil logout!', 'success')
    return redirect(url_for('login'))


# ============================================================
# MAIN — TRANSAKSI PERSONAL
# ============================================================

@app.route('/index')
@login_required
def index():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
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


@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        date_str = request.form.get('date', '')
        tanggal  = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

        db.session.add(Transaction(
            title    = request.form['title'],
            amount   = float(request.form['amount']),
            category = request.form['category'],
            type     = request.form['type'],
            note     = request.form.get('note', ''),
            date     = tanggal,
            user_id  = current_user.id
        ))
        db.session.commit()
        flash('Transaksi berhasil ditambahkan!', 'success')
        return redirect(url_for('index'))

    today = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('add_transaction.html', today=today)

@app.route('/edit_transaction/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    transaction = Transaction.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        transaction.title    = request.form['title']
        transaction.amount   = float(request.form['amount'])
        transaction.category = request.form['category']
        transaction.type     = request.form['type']
        transaction.note     = request.form.get('note', '')

        date_str = request.form.get('date', '')
        transaction.date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

        db.session.commit()
        flash('Transaksi berhasil diperbarui!', 'success')
        return redirect(url_for('index'))

    return render_template('edit_transaction.html', transaction=transaction)


@app.route('/delete_transaction/<int:id>', methods=['GET'])
@login_required
def delete_transaction(id):
    transaction = Transaction.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaksi berhasil dihapus!', 'success')
    return redirect(url_for('index'))


# ============================================================
# LAPORAN
# ============================================================

@app.route('/report')
@login_required
def report():
    transactions  = Transaction.query.filter_by(user_id=current_user.id).all()
    total_income  = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance       = total_income - total_expense

    # Data untuk grafik kategori
    category_data = {}
    for t in transactions:
        if t.type == 'expense':
            category_data[t.category] = category_data.get(t.category, 0) + t.amount

    # Data bulanan
    monthly_data = {}
    for t in transactions:
        key = t.date.strftime('%b %Y')
        if key not in monthly_data:
            monthly_data[key] = {'income': 0, 'expense': 0}
        monthly_data[key][t.type] += t.amount

    return render_template('report.html',
                           total_income=total_income,
                           total_expense=total_expense,
                           balance=balance,
                           category_data=category_data,
                           monthly_data=monthly_data)


# ============================================================
# SCAN STRUK
# ============================================================

@app.route('/scan', methods=['GET', 'POST'])
@login_required
def scan():
    if request.method == 'POST':
        file = request.files.get('receipt')
        if not file or file.filename == '':
            flash('Pilih file dulu!', 'danger')
            return redirect(url_for('scan'))

        items, total = _ocr_receipt(file.stream)
        result = {
            'items': items,
            'total': total,
            'date': datetime.utcnow().strftime('%Y-%m-%d')
        }
        return render_template('scan.html', result=result)

    return render_template('scan.html', result=None)


# ============================================================
# BUDGET
# ============================================================

@app.route('/budget', methods=['POST'])
@login_required
def budget():
    amount = float(request.form['amount'])
    period = request.form['period']

    budget = Budget.query.filter_by(user_id=current_user.id).first()
    if budget:
        budget.amount = amount
        budget.period = period
    else:
        budget = Budget(user_id=current_user.id, amount=amount, period=period)
        db.session.add(budget)

    db.session.commit()
    flash('Budget berhasil diatur!', 'success')
    return redirect(url_for('index'))


# ============================================================
# GRUP — SHARING MODE
# ============================================================

@app.route('/groups')
@login_required
def groups():
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    return render_template('groups.html', memberships=memberships)


@app.route('/groups/create', methods=['POST'])
@login_required
def create_group():
    name = request.form['name']
    code = secrets.token_hex(3).upper()
    group = Group(name=name, code=code)
    db.session.add(group)
    db.session.commit()

    gm = GroupMember(user_id=current_user.id, group_id=group.id, role='admin')
    db.session.add(gm)
    db.session.commit()

    flash('Grup berhasil dibuat!', 'success')
    return redirect(url_for('groups'))


@app.route('/groups/join', methods=['POST'])
@login_required
def join_group():
    code = request.form['code']
    group = Group.query.filter_by(code=code).first()
    if not group:
        flash('Kode grup tidak ditemukan!', 'danger')
        return redirect(url_for('groups'))

    if GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id).first():
        flash('Kamu sudah tergabung di grup ini!', 'warning')
        return redirect(url_for('groups'))

    gm = GroupMember(user_id=current_user.id, group_id=group.id)
    db.session.add(gm)
    db.session.commit()

    flash('Berhasil bergabung ke grup!', 'success')
    return redirect(url_for('groups'))


@app.route('/group_detail/<int:id>')
@login_required
def group_detail(id):
    group = Group.query.get_or_404(id)
    members = group.members
    transactions = group.transactions
    funds = group.funds

    total_income  = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance       = total_income - total_expense

    return render_template('group_detail.html',
                           group=group,
                           members=members,
                           transactions=transactions,
                           funds=funds,
                           total_income=total_income,
                           total_expense=total_expense,
                           balance=balance)

@app.route('/add_group_transaction/<int:group_id>/add', methods=['POST'])
@login_required
def add_group_transaction(group_id):
    if not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
        flash('Kamu bukan anggota grup ini!', 'danger')
        return redirect(url_for('groups'))

    date_str = request.form.get('date', '')
    title    = request.form['title']
    amount   = float(request.form['amount'])

    db.session.add(GroupTransaction(
        group_id = group_id,
        fund_id  = request.form.get('fund_id') or None,
        user_id  = current_user.id,
        title    = title,
        amount   = amount,
        category = request.form['category'],
        type     = request.form['type'],
        note     = request.form.get('note', ''),
        date     = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()
    ))
    db.session.commit()
    log_activity(group_id, current_user.id, f'menambahkan transaksi "{title}" Rp {amount:,.0f}')
    flash('Transaksi grup berhasil ditambahkan!', 'success')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/delete/<int:trans_id>')
@login_required
def delete_group_transaction(group_id, trans_id):
    t = GroupTransaction.query.filter_by(id=trans_id, group_id=group_id).first_or_404()
    log_activity(group_id, current_user.id, f'menghapus transaksi "{t.title}" Rp {t.amount:,.0f}')
    db.session.delete(t)
    db.session.commit()
    flash('Transaksi berhasil dihapus!', 'danger')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/edit/<int:trans_id>', methods=['GET', 'POST'])
@login_required
def edit_group_transaction(group_id, trans_id):
    group  = Group.query.get_or_404(group_id)
    member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    if not member:
        flash('Kamu bukan anggota grup ini!', 'danger')
        return redirect(url_for('groups'))

    t = GroupTransaction.query.filter_by(id=trans_id, group_id=group_id).first_or_404()

    if request.method == 'POST':
        old_title, old_amount = t.title, t.amount
        t.title    = request.form['title']
        t.amount   = float(request.form['amount'])
        t.category = request.form['category']
        t.type     = request.form['type']
        t.note     = request.form.get('note', '')
        t.fund_id  = request.form.get('fund_id') or None
        date_str   = request.form.get('date', '')
        if date_str:
            t.date = datetime.strptime(date_str, '%Y-%m-%d')
        db.session.commit()
        log_activity(group_id, current_user.id,
                     f'mengedit transaksi "{old_title}" (Rp {old_amount:,.0f} → Rp {t.amount:,.0f})')
        flash('Transaksi berhasil diperbarui!', 'success')
        return redirect(url_for('group_detail', group_id=group_id))

    funds = GroupFund.query.filter_by(group_id=group_id).all()
    return render_template('edit_group_transaction.html', group=group, transaction=t, funds=funds)


# ── Dana / Pos Keuangan ──

@app.route('/groups/<int:group_id>/fund/add', methods=['POST'])
@login_required
def add_fund(group_id):
    name = request.form['fund_name']
    db.session.add(GroupFund(
        group_id    = group_id,
        name        = name,
        target      = float(request.form.get('fund_target', 0)),
        description = request.form.get('fund_desc', '')
    ))
    db.session.commit()
    log_activity(group_id, current_user.id, f'membuat dana "{name}"')
    flash(f'Dana "{name}" berhasil dibuat!', 'success')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/fund/edit/<int:fund_id>', methods=['POST'])
@login_required
def edit_fund(group_id, fund_id):
    fund = GroupFund.query.filter_by(id=fund_id, group_id=group_id).first_or_404()
    if not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
        flash('Kamu bukan anggota grup ini!', 'danger')
        return redirect(url_for('groups'))

    old_name         = fund.name
    fund.name        = request.form['fund_name']
    fund.target      = float(request.form.get('fund_target', 0))
    fund.description = request.form.get('fund_desc', '')
    db.session.commit()
    log_activity(group_id, current_user.id, f'mengedit dana "{old_name}" menjadi "{fund.name}"')
    flash(f'Dana "{fund.name}" berhasil diperbarui!', 'success')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/fund/delete/<int:fund_id>')
@login_required
def delete_fund(group_id, fund_id):
    fund = GroupFund.query.filter_by(id=fund_id, group_id=group_id).first_or_404()
    if not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
        flash('Kamu bukan anggota grup ini!', 'danger')
        return redirect(url_for('groups'))

    log_activity(group_id, current_user.id, f'menghapus dana "{fund.name}"')
    db.session.delete(fund)
    db.session.commit()
    flash(f'Dana "{fund.name}" berhasil dihapus!', 'danger')
    return redirect(url_for('group_detail', group_id=group_id))


# ── Laporan Grup ──

@app.route('/groups/<int:id>/report')
@login_required
def group_report(id):
    group = Group.query.get_or_404(id)
    transactions = group.transactions

    total_income  = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance       = total_income - total_expense

    # Data kategori
    category_data = {}
    for t in transactions:
        if t.type == 'expense':
            category_data[t.category] = category_data.get(t.category, 0) + t.amount

    # Data bulanan
    monthly_data = {}
    for t in transactions:
        key = t.date.strftime('%b %Y')
        if key not in monthly_data:
            monthly_data[key] = {'income': 0, 'expense': 0}
        monthly_data[key][t.type] += t.amount

    # Data per anggota
    member_data = {}
    for t in transactions:
        if t.type == 'expense':
            member_data[t.user.name] = member_data.get(t.user.name, 0) + t.amount

    # Data per dana
    fund_data = {}
    for t in transactions:
        if t.type == 'expense' and t.fund:
            fund_data[t.fund.name] = fund_data.get(t.fund.name, 0) + t.amount

    return render_template('group_report.html',
                           group=group,
                           total_income=total_income,
                           total_expense=total_expense,
                           balance=balance,
                           category_data=category_data,
                           monthly_data=monthly_data,
                           member_data=member_data,
                           fund_data=fund_data)

# ── Split Tagihan ──

@app.route('/groups/<int:id>/split')
@login_required
def split_bill(id):
    group = Group.query.get_or_404(id)
    bills = SplitBill.query.filter_by(group_id=id).all()
    return render_template('split_bill.html', group=group, bills=bills)


@app.route('/groups/<int:id>/split/create', methods=['POST'])
@login_required
def create_split(id):
    group = Group.query.get_or_404(id)
    title = request.form['title']
    total = float(request.form['total_amount'])
    note  = request.form.get('note', '')

    bill = SplitBill(title=title, total_amount=total,
                     note=note, group_id=id,
                     created_by=current_user.id)
    db.session.add(bill)
    db.session.commit()

    # Bagi rata ke anggota yang dicentang
    member_ids = request.form.getlist('member_ids')
    if member_ids:
        each = total / len(member_ids)
        for uid in member_ids:
            sd = SplitDetail(bill_id=bill.id, user_id=int(uid), amount=each)
            db.session.add(sd)
    db.session.commit()

    flash('Split tagihan berhasil dibuat!', 'success')
    return redirect(url_for('split_bill', id=id))


@app.route('/groups/<int:group_id>/split/<int:bill_id>/pay/<int:detail_id>')
@login_required
def mark_paid(group_id, bill_id, detail_id):
    detail         = SplitDetail.query.get_or_404(detail_id)
    detail.is_paid = True
    detail.paid_at = datetime.utcnow()
    db.session.commit()
    log_activity(group_id, current_user.id,
                 f'menandai pembayaran "{detail.bill.title}" Rp {detail.amount:,.0f} sebagai lunas')
    flash('Pembayaran berhasil ditandai lunas!', 'success')
    return redirect(url_for('split_list', group_id=group_id))


@app.route('/groups/<int:group_id>/split/<int:bill_id>/delete')
@login_required
def delete_split(group_id, bill_id):
    bill = SplitBill.query.filter_by(id=bill_id, group_id=group_id).first_or_404()
    if bill.created_by != current_user.id:
        flash('Hanya pembuat tagihan yang bisa menghapus!', 'danger')
        return redirect(url_for('split_list', group_id=group_id))

    log_activity(group_id, current_user.id, f'menghapus split tagihan "{bill.title}"')
    db.session.delete(bill)
    db.session.commit()
    flash('Split tagihan berhasil dihapus!', 'danger')
    return redirect(url_for('split_list', group_id=group_id))


@app.route('/groups/<int:group_id>/split/scan', methods=['GET', 'POST'])
@login_required
def scan_split(group_id):
    group  = Group.query.get_or_404(group_id)
    member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    if not member:
        flash('Kamu bukan anggota grup ini!', 'danger')
        return redirect(url_for('groups'))

    members = GroupMember.query.filter_by(group_id=group_id).all()

    if request.method == 'POST':
        file = request.files.get('receipt')
        if not file or file.filename == '':
            flash('Pilih file dulu!', 'danger')
            return redirect(url_for('scan_split', group_id=group_id))

        title, amount, note = _ocr_receipt(file.stream)
        result = {'title': title, 'amount': amount, 'note': note}
        return render_template('scan_split.html', group=group, members=members, result=result)

    return render_template('scan_split.html', group=group, members=members, result=None)


# ============================================================
# SETTINGS
# ============================================================

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')


@app.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    current_user.name  = request.form['name']
    current_user.email = request.form['email']

    file = request.files.get('photo')
    if file and file.filename != '':
        filename = f"{current_user.id}_{secrets.token_hex(4)}.png"
        path     = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        current_user.photo = filename

    db.session.commit()
    flash('Profil berhasil diperbarui!', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form['current_password']
    new_pw     = request.form['new_password']
    confirm_pw = request.form['confirm_password']

    if not check_password_hash(current_user.password, current_pw):
        flash('Password saat ini salah!', 'danger')
    elif new_pw != confirm_pw:
        flash('Password baru tidak cocok!', 'danger')
    elif len(new_pw) < 6:
        flash('Password minimal 6 karakter!', 'danger')
    else:
        current_user.password = generate_password_hash(new_pw)
        db.session.commit()
        flash('Password berhasil diubah!', 'success')

    return redirect(url_for('settings'))


@app.route('/settings/preferences', methods=['POST'])
@login_required
def update_preferences():
    current_user.language    = request.form['language']
    current_user.theme       = request.form['theme']
    current_user.timezone    = request.form['timezone']
    current_user.notif_popup = 'notif_popup' in request.form

    db.session.commit()
    flash('Preferensi berhasil disimpan!', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/security', methods=['POST'])
@login_required
def update_password():
    current_password = request.form['current_password']
    new_password     = request.form['new_password']
    confirm_password = request.form['confirm_password']

    if not check_password_hash(current_user.password, current_password):
        flash('Password saat ini salah!', 'danger')
        return redirect(url_for('settings'))

    if new_password != confirm_password:
        flash('Password baru tidak cocok!', 'danger')
        return redirect(url_for('settings'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password berhasil diubah!', 'success')
    return redirect(url_for('settings'))

@app.route('/settings/export')
@login_required
def export_data():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    return render_template('export.html', transactions=transactions)


@app.route('/settings/delete-account', methods=['POST'])
@login_required
def delete_account():
    if not check_password_hash(current_user.password, request.form['password']):
        flash('Password salah! Akun tidak dihapus.', 'danger')
        return redirect(url_for('settings'))

    Transaction.query.filter_by(user_id=current_user.id).delete()
    Budget.query.filter_by(user_id=current_user.id).delete()
    LoginHistory.query.filter_by(user_id=current_user.id).delete()
    GroupMember.query.filter_by(user_id=current_user.id).delete()

    user = User.query.get(current_user.id)
    logout_user()
    db.session.delete(user)
    db.session.commit()

    flash('Akun berhasil dihapus.', 'success')
    return redirect(url_for('login'))


# ============================================================
# RUN
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database siap!")
    app.run(debug=True)