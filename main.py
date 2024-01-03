from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import psycopg2
import psycopg2.extras
import re, hashlib
import pytz
import os

app = Flask(__name__)

app.secret_key = os.environ.get('secret_key')

def get_db_connection():
    # DATABASE_URL環境変数から接続情報を取得
    DATABASE_URL = os.environ.get('DATABASE_URL')
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def utc_to_jst(utc_dt):
    jst_tz = pytz.timezone('Asia/Tokyo')
    return utc_dt.astimezone(jst_tz)

@app.route('/attendance/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']

        # パスワードのハッシュ化
        hash = password + app.secret_key
        hash = hashlib.sha1(hash.encode())
        hashed_password = hash.hexdigest()

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # ハッシュ化されたパスワードでデータベースを検索
        cur.execute('SELECT * FROM accounts WHERE username = %s AND password = %s', (username, hashed_password,))
        account = cur.fetchone()
        cur.close()
        conn.close()
        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            return redirect(url_for('home'))
        else:
            msg = 'ユーザー名またはパスワードが間違っています！'
    return render_template('index.html', msg=msg)

@app.route('/attendance/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM accounts WHERE username = %s', (username,))
        account = cur.fetchone()

        if account:
            msg = 'アカウントがすでに存在しています！'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = '無効なメールアドレスです！'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'ユーザー名は文字と数字のみを含む必要があります！'
        elif len(password) < 8:
            msg = 'パスワードは8文字以上必要です！'
        elif not username or not password or not email:
            msg = 'フォームを記入してください！'
        else:
            # パスワードのハッシュ化
            hash = password + app.secret_key
            hash = hashlib.sha1(hash.encode())
            password = hash.hexdigest()

            cur.execute('INSERT INTO accounts (username, password, email) VALUES (%s, %s, %s)', (username, password, email,))
            conn.commit()
            msg = '登録が成功しました！'
        cur.close()
        conn.close()
    return render_template('register.html', msg=msg)

@app.route('/attendance/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/attendance/home')
def home():
    if 'loggedin' in session:
        return render_template('home.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/')
def home_root():
    if 'loggedin' in session:
        return render_template('home.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/record-attendance', methods=['POST'])
def record_attendance():
    if 'loggedin' in session:
        user_id = session['id']
        now_utc = datetime.now(pytz.utc)
        now_jst = utc_to_jst(now_utc)
        
        action = request.form['action']
        formatted_jst_time = now_jst.strftime('%Y-%m-%d %H:%M:%S%z')  # JST時刻を文字列形式に変換

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            if action == '出勤記録':
                cur.execute('INSERT INTO attendance (user_id, check_in_time) VALUES (%s, %s)', (user_id, formatted_jst_time))
            elif action == '退勤記録':
                cur.execute("""
                    UPDATE attendance 
                    SET check_out_time = %s 
                    WHERE id = (
                        SELECT id FROM attendance 
                        WHERE user_id = %s 
                        ORDER BY check_in_time DESC 
                        LIMIT 1
                    )
                """, (formatted_jst_time, user_id))
            conn.commit()
        except Exception as e:
            print(e)
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('home'))
    else:
        return redirect(url_for('login'))

@app.route('/attendance/admin')
def admin():
    if 'loggedin' in session and session['username'] == 'admin':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # attendanceテーブルとaccountsテーブルを結合
        cur.execute("""
            SELECT attendance.user_id, accounts.username, attendance.check_in_time, attendance.check_out_time
            FROM attendance
            JOIN accounts ON attendance.user_id = accounts.id
            ORDER BY attendance.check_in_time DESC
        """)

        attendance_records = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('admin.html', attendance_records=attendance_records)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
