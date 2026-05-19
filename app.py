from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import re
from PIL import Image
import pytesseract

# Arahkan ke lokasi Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'fintrack-secret'

db = SQLAlchemy(app)

# =====================
# MODEL DATABASE
# =====================

class Transaction(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    title    = db.Column(db.String(100), nullable=False)
    amount   = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    type     = db.Column(db.String(10), nullable=False)  # pip'income' atau 'expense'
    date     = db.Column(db.DateTime, default=datetime.utcnow)
    note     = db.Column(db.String(200), nullable=True)

# =====================
# ROUTES
# =====================

@app.route('/')
def index():
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    
    total_income  = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance       = total_income - total_expense

    return render_template('index.html',
                            transactions=transactions,
                            total_income=total_income,
                            total_expense=total_expense,
                            balance=balance)

@app.route('/add', methods=['GET', 'POST'])
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
            date=tanggal
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Transaksi berhasil ditambahkan!', 'success')
        return redirect(url_for('index'))

    today = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('add_transaction.html', today=today)

@app.route('/delete/<int:id>')
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaksi berhasil dihapus!', 'danger')
    return redirect(url_for('index'))

@app.route('/report')
def report():
    transactions = Transaction.query.order_by(Transaction.date.asc()).all()

    # Pengeluaran per kategori
    category_data = {}
    for t in transactions:
        if t.type == 'expense':
            category_data[t.category] = category_data.get(t.category, 0) + t.amount

    # Pemasukan vs pengeluaran per bulan
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

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_transaction(id):
    transaction = Transaction.query.get_or_404(id)

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

@app.route('/scan', methods=['GET', 'POST'])
def scan():
    if request.method == 'POST':
        if 'receipt' not in request.files:
            flash('Tidak ada file yang diupload!', 'danger')
            return redirect(url_for('scan'))

        file = request.files['receipt']
        if file.filename == '':
            flash('Pilih file dulu!', 'danger')
            return redirect(url_for('scan'))

        # Baca gambar dan jalankan OCR
        img = Image.open(file.stream)
        text = pytesseract.image_to_string(img, lang='ind+eng')

        # Coba deteksi total dari teks struk
        amount = 0
        lines  = text.split('\n')

        # Cari baris yang mengandung kata total/grand total
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

        # Coba deteksi nama toko (biasanya di baris pertama)
        title = 'Belanja'
        for line in lines[:5]:
            line = line.strip()
            if len(line) > 3 and not line.isdigit():
                title = line.title()
                break

        # Kumpulkan semua teks sebagai catatan
        note_lines = [l.strip() for l in lines if len(l.strip()) > 3]
        note = ', '.join(note_lines[:5])

        today = datetime.utcnow().strftime('%Y-%m-%d')

        result = {
            'title'   : title,
            'amount'  : amount,
            'category': 'Belanja',
            'date'    : today,
            'note'    : note,
            'raw_text': text  # untuk debugging
        }

        return render_template('scan.html', result=result)

    return render_template('scan.html', result=None)


# =====================
# JALANKAN APP
# =====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database siap!")
    app.run(debug=True)